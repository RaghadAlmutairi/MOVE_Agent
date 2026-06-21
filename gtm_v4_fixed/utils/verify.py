# -*- coding: utf-8 -*-
"""Official-source verification + competitor-candidate helpers.

Core principle: a search result is NOT official just because the query said
"official". A URL is treated as official only when its DOMAIN actually matches
the entity (or a verified expected domain) and is not a known third-party site.
"""
import re
from urllib.parse import urlparse
from typing import List, Dict, Any

# Known NON-official domains (listicles, directories, social, news, review sites).
NON_OFFICIAL_DOMAINS = {
    "linkedin.com", "youtube.com", "twitter.com", "x.com", "facebook.com",
    "instagram.com", "tiktok.com", "reddit.com", "medium.com", "substack.com",
    "wikipedia.org", "crunchbase.com", "g2.com", "capterra.com", "trustradius.com",
    "trustpilot.com", "getapp.com", "softwareadvice.com", "producthunt.com",
    "forbes.com", "techcrunch.com", "bloomberg.com", "businessinsider.com",
    "cbinsights.com", "owler.com", "getlatka.com", "explodingtopics.com",
    "semrush.com", "similarweb.com", "glassdoor.com", "indeed.com",
    "news.ycombinator.com", "quora.com", "apps.apple.com", "play.google.com",
    "github.com", "stackoverflow.com",
}


def norm_name(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def domain_from_url(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""


def is_non_official_domain(domain: str) -> bool:
    d = (domain or "").lower().replace("www.", "")
    return any(d == bad or d.endswith("." + bad) for bad in NON_OFFICIAL_DOMAINS)


def soft_entity_domain_match(entity_name: str, domain: str) -> bool:
    entity = norm_name(entity_name)
    stem = re.sub(r"[^a-z0-9]", "", (domain or "").split(".")[0].lower())
    if not entity or not stem or len(stem) < 4:
        return False
    return stem in entity or entity in stem


def is_likely_official_url(url: str, entity_name: str, expected_domain: str = "") -> bool:
    domain = domain_from_url(url)
    if not domain or is_non_official_domain(domain):
        return False
    if expected_domain:
        exp = expected_domain.lower().replace("www.", "")
        if domain == exp or domain.endswith("." + exp) or exp.endswith("." + domain):
            return True
    return soft_entity_domain_match(entity_name, domain)


def retag_official(sources: List[Dict[str, Any]], entity_name: str,
                   expected_domain: str = "", official_role: str = "competitor_official",
                   other_role: str = "competitor_third_party") -> List[Dict[str, Any]]:
    """Re-tag each source's official flag + role by VERIFYING the URL/domain
    against the entity, instead of trusting the search query."""
    for s in sources:
        off = is_likely_official_url(s.get("url", ""), entity_name, expected_domain)
        s["official"] = off
        s["role"] = official_role if off else other_role
        s["candidate_entity"] = entity_name
        if expected_domain:
            s["expected_domain"] = expected_domain
    return sources


def dedupe_candidates(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rank = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}
    seen: Dict[str, Dict[str, Any]] = {}
    for c in candidates:
        name = (c.get("name") or "").strip()
        if not name:
            continue
        key = norm_name(name)
        for suf in ("inc", "ltd", "llc", "corp", "company"):
            key = key.replace(suf, "")
        if (key not in seen
                or rank.get(c.get("confidence", "LOW"), 0)
                > rank.get(seen[key].get("confidence", "LOW"), 0)):
            seen[key] = c
    return list(seen.values())


def build_discovery_queries(subject: str, market: str, industry: str,
                            geography: str, subject_type: str = "") -> List[str]:
    """Subject-type-aware DISCOVERY queries (third-party allowed; NOT official)."""
    base = subject or market
    ind = industry or market
    st = (subject_type or "").upper()
    if not subject:
        return [f"top companies in {market} {geography}",
                f"{market} vendors {geography}",
                f"{market} market map",
                f"{ind} platforms comparison",
                f"leading {ind} companies {geography}"]
    if st in ("PLATFORM_MARKETPLACE", "PLATFORM", "MARKETPLACE"):
        return [f"{base} competitors platforms {ind} {geography}",
                f"{base} alternatives marketplaces {market} {geography}",
                f"top platforms in {ind} {geography}",
                f"{ind} marketplaces comparison",
                f"{base} vs competitors"]
    if st == "PRODUCT":
        return [f"{base} alternatives",
                f"{base} competitors",
                f"best alternatives to {base}",
                f"{market} products comparison {geography}",
                f"{base} vs similar products"]
    return [f"{base} competitors {ind} {geography}",
            f"{base} alternatives {market} {geography}",
            f"top companies in {ind} {geography}",
            f"{ind} vendor landscape {geography}",
            f"{base} vs competitors pricing"]


def choose_official_homepage(entity_name: str, sources: List[Dict[str, Any]]) -> str:
    """Pick the best OFFICIAL homepage for an entity from the verified source pool
    (Python-side, so the LLM never invents official URLs)."""
    cands = []
    for s in sources:
        url = s.get("url", "")
        domain = s.get("domain", "") or domain_from_url(url)
        if not url or not domain or is_non_official_domain(domain):
            continue
        score = 0
        if s.get("official"):
            score += 5
        if s.get("candidate_entity") and norm_name(s["candidate_entity"]) == norm_name(entity_name):
            score += 5
        if soft_entity_domain_match(entity_name, domain):
            score += 3
        parsed = urlparse(url)
        path = parsed.path.strip("/")
        if not path:
            score += 2
        elif len(path.split("/")) <= 2:
            score += 1
        if score > 0:
            cands.append((score, f"{parsed.scheme or 'https'}://{parsed.netloc}"))
    if not cands:
        return ""
    cands.sort(reverse=True)
    return cands[0][1]


def print_source_diagnostics(sources: List[Dict[str, Any]]) -> None:
    by_role: Dict[str, int] = {}
    by_domain: Dict[str, int] = {}
    for s in sources:
        by_role[s.get("role", "unknown")] = by_role.get(s.get("role", "unknown"), 0) + 1
        d = s.get("domain", "unknown")
        by_domain[d] = by_domain.get(d, 0) + 1
    print("\n      source diagnostics:")
    print("        roles: " + ", ".join(f"{k}={v}" for k, v in
                                         sorted(by_role.items(), key=lambda x: -x[1])))
    top = sorted(by_domain.items(), key=lambda x: -x[1])[:6]
    print("        top domains: " + ", ".join(f"{k}({v})" for k, v in top))
    print(f"        verified competitor-official sources: "
          f"{by_role.get('competitor_official', 0)}")
