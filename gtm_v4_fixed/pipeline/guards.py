"""Input and output guardrails (deterministic fast-path + LLM fallback)."""
import re
import json
import ipaddress
from typing import List, Dict, Any, Optional, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from core.config import GUARD_MODEL
from core.llm import parse_llm
from core.prompts import INPUT_GUARD_PROMPT, OUTPUT_GUARD_PROMPT
from utils.verify import is_non_official_domain, domain_from_url, norm_name


REFUSAL_MESSAGE = [
    "I can only help with market and competitive research - for example analyzing "
    "a company's competitors, market size, pricing, positioning, business models, "
    "customer segments, channels, or industry trends. I can't help with that request."
]

_INJECTION_RE = re.compile(
    r"\b(ignore\s+(all\s+|the\s+|your\s+|previous\s+)*(instruction|prompt|rule)s?"
    r"|disregard\s+(the|all|your|previous|prior)"
    r"|system\s+prompt|developer\s+message|you\s+are\s+now|from\s+now\s+on\s+you"
    r"|act\s+as\s+|pretend\s+to\s+be|role\s*[:=]\s*system"
    r"|reveal\s+(your|the)\s+(prompt|instructions|system|rules)"
    r"|print\s+(your|the)\s+(prompt|system|instructions)"
    r"|jailbreak|developer\s+mode|\bDAN\b|do\s+anything\s+now"
    r"|override\s+(your|the)\s+(guard|rule|instruction))",
    re.I,
)

_MALICIOUS_RE = re.compile(
    r"\b(exploit|vulnerabilit|0-?day|cve-\d|sql\s*injection|\bxss\b|\bcsrf\b"
    r"|ddos|botnet|malware|ransomware|trojan|rootkit|keylogger|spyware"
    r"|phish|spear-?phish|credential\s+(stuff|dump|theft|harvest)|password\s+(dump|crack)"
    r"|brute\s*force|port\s*scan|\bnmap\b|metasploit|payload\s+for"
    r"|exfiltrat|backdoor|privilege\s+escalation"
    r"|\bdox|home\s+address\s+of|social\s+security\s+number|\bSSN\b"
    r"|personal\s+(data|info|email)s?\s+of|scrape\s+(emails|users|personal|private)"
    r"|stalk|surveil(l)?(e|ance)\s+(a\s+person|someone|an\s+individual))",
    re.I,
)

_MARKET_RE = re.compile(
    r"\b(market|compet|industr|pricing|\bprice|\bswot\b|persona|segment|landscape"
    r"|vendor|alternativ|\btam\b|\bsam\b|\bsom\b|go.?to.?market|business\s+model"
    r"|revenue\s+model|positioning|trend|forecast|share|customer|buyer|b2b|b2c"
    r"|go-to-market|channel|industry\s+overview|product\s+comparison|review|feedback)",
    re.I,
)


class InputVerdict(BaseModel):
    verdict: Literal["PASS", "BLOCK"]
    category: Literal[
        "ON_TOPIC", "OFF_TOPIC", "PROMPT_INJECTION",
        "MALICIOUS_CYBER", "DISALLOWED", "UNKNOWN",
    ]
    reason: str


class OutputVerdict(BaseModel):
    verdict: Literal["PASS", "BLOCK"]
    reason: str
    issues: List[str] = Field(default_factory=list)


_BLOCKED_HOSTS = {"localhost", "metadata.google.internal", "metadata",
                  "169.254.169.254"}


def validate_url(url: str) -> Dict[str, Any]:
    """Validate the OPTIONAL company/product URL (SSRF-aware). Empty is allowed."""
    raw = (url or "").strip()
    if not raw:
        return {"ok": True, "url": "", "reason": "no URL provided (optional)"}
    u = raw if re.match(r"^https?://", raw, re.I) else "https://" + raw
    try:
        p = urlparse(u)
    except Exception:
        return {"ok": False, "url": "", "reason": "Malformed URL."}
    if p.scheme not in ("http", "https"):
        return {"ok": False, "url": "", "reason": "Only http/https URLs allowed."}
    host = (p.hostname or "").lower()
    if not host or "." not in host:
        return {"ok": False, "url": "", "reason": "URL has no valid host."}
    if host in _BLOCKED_HOSTS:
        return {"ok": False, "url": "", "reason": "Internal/metadata host not allowed."}
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return {"ok": False, "url": "", "reason": "Private/internal IP not allowed."}
    except ValueError:
        pass
    return {"ok": True, "url": u, "reason": "valid"}


def deterministic_input_guard(query: str) -> Optional[Dict[str, Any]]:
    q = (query or "").strip()
    if len(q) < 3:
        return {"verdict": "BLOCK", "category": "OFF_TOPIC",
                "reason": "Empty or too-short query.", "by": "deterministic"}
    if _INJECTION_RE.search(q):
        return {"verdict": "BLOCK", "category": "PROMPT_INJECTION",
                "reason": "Instruction-override / prompt-exfiltration pattern.",
                "by": "deterministic"}
    if _MALICIOUS_RE.search(q):
        return {"verdict": "BLOCK", "category": "MALICIOUS_CYBER",
                "reason": "Offensive-security or personal-data request.",
                "by": "deterministic"}
    if _MARKET_RE.search(q):
        return {"verdict": "PASS", "category": "ON_TOPIC",
                "reason": "Matches market-research scope.", "by": "deterministic"}
    return None


def input_guard(query: str) -> Dict[str, Any]:
    det = deterministic_input_guard(query)
    if det is not None:
        return det
    v = parse_llm(model=GUARD_MODEL, system=INPUT_GUARD_PROMPT,
                  user=f"USER QUERY:\n{query}", schema=InputVerdict,
                  temperature=0, label="input-guard")
    d = v.model_dump()
    d["by"] = "llm"
    return d


def _collect_cited(obj) -> set:
    """Collect every cited source NUMBER from the report: the plain numbers in
    any source_ids list, plus inline bracketed citations like [3] or [3][7].
    Bare numbers (e.g. a $20 price) are ignored - only bracketed/explicit
    source references count - so prices never look like phantom citations."""
    nums: set = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "source_ids" and isinstance(v, list):
                for x in v:
                    if str(x).strip().isdigit():
                        nums.add(int(x))
            else:
                nums |= _collect_cited(v)
    elif isinstance(obj, list):
        for x in obj:
            nums |= _collect_cited(x)
    elif isinstance(obj, str):
        for m in re.findall(r"\[(\d+)\]", obj):
            nums.add(int(m))
    return nums


def deterministic_output_guard(report: Dict[str, Any], sources, plan=None) -> List[str]:
    """Deterministic, revision-fixable checks: bad citations, non-official
    official_website, and the subject listed as its own competitor."""
    n_sources = sources if isinstance(sources, int) else len(sources)
    issues: List[str] = []

    bad = sorted(i for i in _collect_cited(report) if i < 1 or i > n_sources)
    if bad:
        issues.append("Citations reference non-existent sources: "
                      + ", ".join(f"[{i}]" for i in bad))

    for key in ("company_competitors", "product_competitors", "alternative_solutions"):
        for e in report.get(key, []):
            site = (e.get("official_website") or "").strip()
            if site:
                d = domain_from_url(site)
                if d and is_non_official_domain(d):
                    issues.append(f"{e.get('name', '?')} official_website points to a "
                                  f"non-official domain ({d}); use the real homepage or blank.")

    if plan:
        subj = norm_name(plan.get("subject_entity", ""))
        if subj:
            for key in ("company_competitors", "product_competitors"):
                for e in report.get(key, []):
                    if norm_name(e.get("name", "")) == subj:
                        issues.append(f"Subject '{plan.get('subject_entity')}' is listed as "
                                      "its own competitor; remove it.")
    return issues


def _sources_index(sources: List[Dict[str, Any]]) -> str:
    return "\n".join(f"[{s['id']}] {s.get('domain','')} - {s['url']}" for s in sources)


def output_guard(query: str, report: Dict[str, Any],
                 sources: List[Dict[str, Any]], plan=None) -> Dict[str, Any]:
    det_issues = deterministic_output_guard(report, sources, plan)
    if det_issues:
        return {"verdict": "BLOCK", "by": "deterministic",
                "reason": "Deterministic QA failed (citations / official websites / "
                          "subject-as-competitor).",
                "issues": det_issues}

    payload = f"""
USER QUERY: {query}

VALID SOURCE LIST (only these source numbers exist):
{_sources_index(sources)}

GENERATED REPORT (JSON):
{json.dumps(report, ensure_ascii=False)[:14000]}

Review against the criteria and return the schema.
"""
    v = parse_llm(model=GUARD_MODEL, system=OUTPUT_GUARD_PROMPT, user=payload,
                  schema=OutputVerdict, temperature=0, label="output-guard")
    d = v.model_dump()
    d["by"] = "llm"
    d.setdefault("issues", [])
    return d
