# -*- coding: utf-8 -*-
"""Evaluation service (LLM-as-judge). Scores Research / Strategy / Content against
spec criteria + pass thresholds. Advisory: attaches scores; does not hard-gate."""
import json
from typing import Any, Dict, List

from pydantic import BaseModel, Field

from core.config import EVAL_MODEL, traceable
from core.llm import parse_llm

RESEARCH_CRITERIA = ["Coverage", "Accuracy", "Market Analysis Quality",
                     "Competitor Analysis Quality", "Insight Quality"]
STRATEGY_CRITERIA = ["Strategic Clarity", "Market Fit", "Differentiation",
                     "Feasibility", "Revenue Potential"]
CONTENT_CRITERIA = ["Brand Consistency", "Messaging Consistency", "Readability",
                    "Persuasiveness", "Executive Quality"]
THRESHOLDS = {"research": 85, "strategy": 70, "content": 70}


class CriterionScore(BaseModel):
    criterion: str
    score: int = Field(ge=0, le=100)
    note: str = ""


class Evaluation(BaseModel):
    criteria: List[CriterionScore] = Field(default_factory=list)
    overall: int = Field(default=0, ge=0, le=100)
    passed: bool = False
    summary: str = ""


def _evaluate(kind: str, criteria: List[str], payload: str) -> Dict[str, Any]:
    threshold = THRESHOLDS[kind]
    system = (f"You are a strict {kind} evaluator. Score EACH criterion 0-100 on "
              f"evidence and quality, compute an overall 0-100, and set passed=true "
              f"only if overall >= {threshold}. Be critical; do not inflate.")
    user = (f"CRITERIA: {', '.join(criteria)}\nPASS THRESHOLD: {threshold}\n\n"
            f"ARTIFACT:\n{payload[:9000]}\n\nReturn only the schema.")
    try:
        ev = parse_llm(model=EVAL_MODEL, system=system, user=user,
                       schema=Evaluation, temperature=0, label=f"eval-{kind}")
        d = ev.model_dump()
        d["threshold"] = threshold
        d["passed"] = d.get("overall", 0) >= threshold
        return d
    except Exception as e:
        return {"criteria": [], "overall": 0, "passed": False,
                "summary": f"evaluation failed: {str(e)[:80]}", "threshold": threshold}


@traceable(name="evaluate_research")
def evaluate_research(report: Dict[str, Any]) -> Dict[str, Any]:
    return _evaluate("research", RESEARCH_CRITERIA, json.dumps(report)[:9000])


@traceable(name="evaluate_strategy")
def evaluate_strategy(gtm: Dict[str, Any]) -> Dict[str, Any]:
    return _evaluate("strategy", STRATEGY_CRITERIA, json.dumps(gtm)[:9000])


@traceable(name="evaluate_content")
def evaluate_content(content: Dict[str, Any]) -> Dict[str, Any]:
    return _evaluate("content", CONTENT_CRITERIA, json.dumps(content)[:9000])
