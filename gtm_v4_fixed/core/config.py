"""Environment, OpenAI client, model choices and runtime knobs.

Secrets are read from the environment or a local .env file (see .env.example).
"""
import os
from typing import Optional

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()  # load variables from a local .env if present

# Optional LangChain tool decorator (graceful no-op fallback if not installed).
try:
    from langchain_core.tools import tool
except Exception:
    def tool(fn):
        return fn

# True ONLY inside an actual Jupyter/Colab kernel - not merely because IPython is
# installed (a plain `python main.py` run must print the report to the terminal).
def _detect_notebook() -> bool:
    try:
        from IPython import get_ipython
        return get_ipython().__class__.__name__ == "ZMQInteractiveShell"
    except Exception:
        return False

IN_NOTEBOOK = _detect_notebook()


def load_secret(name: str) -> Optional[str]:
    return os.environ.get(name)


OPENAI_API_KEY = load_secret("OPENAI_API_KEY")
# Anthropic key (used by the content agent to enhance PPTX decks with Claude).
ANTHROPIC_API_KEY = load_secret("ANTHROPIC_API_KEY")
TAVILY_API_KEY = load_secret("TAVILY_API_KEY")
FIRECRAWL_API_KEY = load_secret("FIRECRAWL_API_KEY")     # search fallback #1
GOOGLE_API_KEY = load_secret("GOOGLE_API_KEY")           # search fallback #2 (Custom Search JSON API)
GOOGLE_CSE_ID = load_secret("GOOGLE_CSE_ID")             # Programmable Search Engine id (cx)
assert OPENAI_API_KEY, "Set OPENAI_API_KEY (in your environment or a .env file)."
if not TAVILY_API_KEY:
    print("   \u26a0 TAVILY_API_KEY not set - search will fall back to Firecrawl / Google / DuckDuckGo.")

client = OpenAI(api_key=OPENAI_API_KEY, timeout=120.0, max_retries=2)

# Optional Anthropic client (graceful no-op if package/key missing). Used only
# by the content agent's PPTX enhancement tool — never required to run the app.
anthropic_client = None
if ANTHROPIC_API_KEY:
    try:
        from anthropic import Anthropic
        anthropic_client = Anthropic(api_key=ANTHROPIC_API_KEY, timeout=120.0, max_retries=2)
    except Exception:
        anthropic_client = None
else:
    print("   \u26a0 ANTHROPIC_API_KEY not set - PPTX content enhancement will be skipped.")

ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")

PLAN_MODEL   = os.getenv("PLAN_MODEL",   "gpt-4.1-mini")
SYNTH_MODEL  = os.getenv("SYNTH_MODEL",  "gpt-5")
SYNTH_EFFORT = os.getenv("SYNTH_EFFORT", "minimal")

# Content agent (spec: primary Claude Sonnet, fallback GPT-5; defaults to GPT-5
# unless CONTENT_MODEL is set so it runs out-of-the-box on an OpenAI-only setup).
CONTENT_MODEL  = os.getenv("CONTENT_MODEL",  SYNTH_MODEL)
CONTENT_EFFORT = os.getenv("CONTENT_EFFORT", "minimal")
# Cross-model fallback (used by llm.parse_llm on persistent failure).
FALLBACK_MODEL = os.getenv("FALLBACK_MODEL", "gpt-4.1-mini")
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "3"))
# SQLite storage / long-term memory.
STORAGE_DB = os.getenv("STORAGE_DB", "./storage/gtm.db")
# Evaluators (LLM-as-judge). OFF by default so they add no cost unless enabled.
ENABLE_EVALUATORS = os.getenv("ENABLE_EVALUATORS", "false").lower() == "true"
EVAL_MODEL = os.getenv("EVAL_MODEL", PLAN_MODEL)
GUARD_MODEL  = os.getenv("GUARD_MODEL",  "gpt-4.1-mini")
ENABLE_INPUT_GUARD  = os.getenv("ENABLE_INPUT_GUARD",  "1") != "0"
ENABLE_OUTPUT_GUARD = os.getenv("ENABLE_OUTPUT_GUARD", "1") != "0"

RESULTS_PER_QUERY   = 3
SEARCH_WORKERS      = 12
TOOL_WORKERS        = 3
SYNTH_WORKERS       = 3
MAX_SOURCES_FOR_LLM = 22
SOURCE_CHARS        = 26000
RAW_CONTENT_CHARS   = 1400
REQ_TIMEOUT         = (4, 12)

print(f"\u2713 agent ready | plan={PLAN_MODEL} synth={SYNTH_MODEL} effort={SYNTH_EFFORT}")


# --- Internal knowledge base (RAG) ---
# Drop the organisation's PDFs into this folder; the RAG tool indexes them lazily.
RAG_DOCS_FOLDER = os.getenv("RAG_DOCS_FOLDER", "./rag_docs")
# Subjects that should trigger the internal RAG tool (matched case-insensitively,
# spaces ignored). Override via env: INTERNAL_ENTITIES="weclouddata,beamdata,acme"
INTERNAL_ENTITIES = {
    e.strip().lower().replace(" ", "")
    for e in os.getenv("INTERNAL_ENTITIES", "weclouddata,beamdata").split(",")
    if e.strip()
}


# --- LangSmith tracing (optional observability) ---
import contextvars
from concurrent.futures import ThreadPoolExecutor

_LS_KEY = os.getenv("LANGSMITH_API_KEY") or os.getenv("LANGCHAIN_API_KEY")
if _LS_KEY:
    # A key is enough to opt in; defaults below are overridable via env.
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    os.environ.setdefault("LANGCHAIN_API_KEY", _LS_KEY)
    os.environ.setdefault(
        "LANGCHAIN_PROJECT",
        os.getenv("LANGSMITH_PROJECT", "market-analyst-agent"))

TRACING_ENABLED = (os.getenv("LANGCHAIN_TRACING_V2", "").lower() == "true"
                   and bool(_LS_KEY))

# Real LangSmith decorator if available, else a no-op (supports @traceable and
# @traceable(...) forms) so the agent runs with or without langsmith installed.
try:
    from langsmith import traceable  # type: ignore
except Exception:
    def traceable(*d_args, **d_kwargs):
        if len(d_args) == 1 and callable(d_args[0]) and not d_kwargs:
            return d_args[0]
        def _wrap(fn):
            return fn
        return _wrap


def map_in_context(fn, items, max_workers):
    """ThreadPoolExecutor.map that runs each task in a COPY of the current context
    (captured in the calling thread). This propagates LangSmith's run tree into
    worker threads so threaded LLM/tool spans nest correctly. Order preserved."""
    items = list(items)
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = [ex.submit(contextvars.copy_context().run, fn, it) for it in items]
        return [f.result() for f in futures]


if TRACING_ENABLED:
    print(f"\u2713 LangSmith tracing ON | project={os.environ.get('LANGCHAIN_PROJECT')}")
