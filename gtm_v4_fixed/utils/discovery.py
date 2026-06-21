# -*- coding: utf-8 -*-
"""Competitor candidate discovery (cheap model extracts candidates from
third-party discovery sources, before any official verification)."""
from typing import List, Dict, Any

from core.config import PLAN_MODEL
from core.llm import parse_llm
from core.prompts import CANDIDATE_EXTRACT_PROMPT
from core.schemas import CompetitorCandidateBlock
from utils.sources import compact_sources


def extract_competitor_candidates(subject_entity: str, subject_type: str,
                                  industry: str, market: str, geography: str,
                                  discovery_sources: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    user = f"""SUBJECT: {subject_entity or '(whole market)'}
SUBJECT_TYPE: {subject_type}
INDUSTRY: {industry}
MARKET: {market}
GEOGRAPHY: {geography}

DISCOVERY SOURCES:
{compact_sources(discovery_sources, prefer_role='competitor_discovery')}

Extract same-granularity competitor candidates."""
    try:
        parsed = parse_llm(model=PLAN_MODEL, system=CANDIDATE_EXTRACT_PROMPT,
                           user=user, schema=CompetitorCandidateBlock,
                           temperature=0, reasoning_effort="minimal",
                           label="extract-candidates")
        return [c.model_dump() for c in parsed.candidates]
    except Exception as e:
        print(f"        candidate extraction failed: {str(e)[:80]}")
        return []
