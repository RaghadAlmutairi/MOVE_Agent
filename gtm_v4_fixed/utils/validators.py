"""Advisory granularity validator (non-blocking)."""
from typing import List, Dict, Any

import re

# Subject types whose fair peers are OTHER platforms, not single narrow offerings.
_PLATFORM_TYPES = {"PLATFORM_MARKETPLACE"}

# Narrow SINGLE-UNIT terms ONLY. Deliberately EXCLUDES legitimate platform
# offering categories ("certificate", "program", "degree", "subscription",
# "membership", "plan", "course" on its own) so the check does NOT fire on
# correct platform-level output (e.g. "Professional Certificates").
_NARROW_UNIT = re.compile(
    r"\b(bootcamp|nanodegree|single course|one course|individual course|"
    r"a course on|track on|single listing|one listing|single seller|one seller|"
    r"single sku|individual sku|single app|one template)\b",
    re.I,
)


def validate_granularity(report: Dict[str, Any], plan: Dict[str, Any]) -> List[str]:
    """ADVISORY ONLY - never blocks. Flags likely platform-vs-narrow-offering
    mismatches for a PLATFORM_MARKETPLACE subject when the user did NOT restrict
    scope. node_generate attaches any notes to report['_granularity_issues'] so they
    surface in the run log / output guard without failing the report."""
    issues: List[str] = []
    if plan.get("subject_type", "") not in _PLATFORM_TYPES:
        return issues
    if bool(plan.get("scope_is_user_restricted", False)):
        return issues
    for key in ("product_competitors", "alternative_solutions"):
        for e in report.get(key, []):
            blob = (f"{e.get('name','')} {e.get('positioning','')} "
                    f"{e.get('value_proposition','')}")
            if _NARROW_UNIT.search(blob):
                issues.append(
                    f"[{key}] '{e.get('name','?')}' reads as a single narrow "
                    "offering compared against a PLATFORM_MARKETPLACE subject "
                    "(scope not user-restricted) - verify it is a platform-level "
                    "peer, or move it to alternative_solutions."
                )
    return issues
