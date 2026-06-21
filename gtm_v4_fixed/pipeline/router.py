"""Routes a query to a ToolPlan (subject, type, industry, scope, tools)."""
from core.config import PLAN_MODEL
from core.llm import parse_llm
from core.prompts import ROUTER_PROMPT
from core.schemas import ToolPlan


def route(query: str) -> ToolPlan:
    return parse_llm(model=PLAN_MODEL, system=ROUTER_PROMPT,
                     user=f"USER QUERY:\n{query}", schema=ToolPlan,
                     temperature=0, reasoning_effort="minimal", label="route")


# Deterministic minimum tool set so competitor analysis can NEVER be silently
# skipped (general: depends only on subject/type, not on any specific entity).
_COMPETITIVE_TYPES = {"COMPANY", "PRODUCT", "BOTH", "PLATFORM_MARKETPLACE"}


def enforce_tool_floor(plan: ToolPlan) -> ToolPlan:
    req = list(plan.required_tools)

    def ensure(t):
        if t not in req:
            req.append(t)

    if plan.subject_entity:
        ensure("market_analysis_tool")
        ensure("customer_intelligence_tool")
    if (plan.subject_type or "").upper() in _COMPETITIVE_TYPES:
        ensure("competitive_landscape_tool")
    plan.required_tools = req
    return plan
