"""Shared text sanitiser used by the PDF and Word exporters (cp1252-safe)."""
from typing import Any

_CHARMAP = {
    "\u2014": "-", "\u2013": "-", "\u2012": "-", "\u2011": "-", "\u2010": "-",
    "\u2212": "-", "\u2022": "-", "\u00b7": "-", "\u2026": "...",
    "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
    "\u2192": "->", "\u2190": "<-", "\u2713": "", "\u2717": "",
    "\u00a0": " ", "\u202f": " ", "\u200b": "",
    "\u2080": "0", "\u2081": "1", "\u2082": "2", "\u2083": "3", "\u2084": "4",
    "\u2085": "5", "\u2086": "6", "\u2087": "7", "\u2088": "8", "\u2089": "9",
}


def _san(s: Any) -> str:
    s = "" if s is None else str(s)
    for k, v in _CHARMAP.items():
        s = s.replace(k, v)
    return s.encode("cp1252", "ignore").decode("cp1252")


def _esc(s: Any) -> str:
    s = _san(s)
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
