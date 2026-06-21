"""CLI entry point for the GTM multi-agent system.

Execution flow
--------------
1. Collect user query + optional URL.
2. Run the research agent (standalone).
3. Hand the result to the orchestrator, which manages:
     - Human approval of research
     - Parallel: strategy agent + content agent Phase A
     - Human approval of strategy and Phase A content
     - Content agent Phase B (full suite, requires approved strategy)
     - Human approval of Phase B content
     - Reporting / export
"""
import json

from pipeline.research_graph import run_research
from agents.orchestrator import run_pipeline, _has_llm_output


def main() -> None:
    q   = input("Market research query: ").strip()
    url = input("Company / product URL (optional, press Enter to skip): ").strip()

    # ---- Run research agent (always runs first, standalone) ----
    result = run_research(q, url=url)

    if not _has_llm_output(result):
        stage = result.get("stage", "output")
        print(f"\n\n================ NO REPORT ({stage}) ================\n")
        for m in result.get("message", []):
            print(m)
        for it in result.get("output_guard", {}).get("issues", []):
            print(f"  • {it}")
        with open("market_research_result.json", "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print("\nSaved: market_research_result.json")
        return

    # ---- Hand off to the orchestrator ----
    def _regenerate():
        return run_research(q, url=url)

    run_pipeline(result, regenerate_research=_regenerate)


if __name__ == "__main__":
    main()
