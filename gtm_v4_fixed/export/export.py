"""Fourth tool (post-approval): export the approved report to PDF or Word."""
from typing import Dict, Any, Literal

from core.config import tool
from export.export_pdf import Market_report_analysis
from export.export_docx import export_docx
from export.export_pptx import export_pptx


@tool
def market_report_analysis_tool(result: Dict[str, Any],
                                fmt: Literal["pdf", "word", "pptx"] = "pdf",
                                path: str = "") -> Dict[str, Any]:
    """Pure-Python export of the APPROVED report to the chosen document format.
    No LLM. Returns the written file path."""
    print(f"\n      [tool] market_report_analysis_tool (fmt={fmt})")
    if fmt == "word":
        p = export_docx(result, path or None)
    elif fmt == "pptx":
        p = export_pptx(result, path or None)
    else:
        p = Market_report_analysis(result, path or None)
    return {"tool": "market_report_analysis_tool", "format": fmt, "path": p}
