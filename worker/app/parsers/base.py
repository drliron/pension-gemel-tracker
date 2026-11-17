"""ממשק משותף לתבניות חילוץ. כל תבנית מזהה את הפורמט שלה ומחזירה שדות עם רמת ביטחון."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

AMOUNT_RE = r"(-?\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?|-?\d+(?:\.\d{1,2})?)"
PCT_RE = r"(-?\d+(?:\.\d{1,4})?)\s*%?"


@dataclass
class ParseResult:
    parser_name: str
    parser_version: str
    fields: dict = field(default_factory=dict)
    found: int = 0           # כמה שדות חובה נמצאו
    required: int = 3        # תאריך, יתרה, מסלול
    warnings: list[str] = field(default_factory=list)

    @property
    def confidence(self) -> float:
        return round(self.found / self.required, 2) if self.required else 0.0


def parse_amount(s: str) -> float:
    return float(s.replace(",", ""))


def parse_date(s: str) -> str | None:
    """מחזיר YYYY-MM-DD. תומך ב-2026-06-30 וב-30/06/2026."""
    s = s.strip()
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        y, mo, d = map(int, m.groups())
    else:
        m = re.fullmatch(r"(\d{1,2})[./](\d{1,2})[./](\d{4})", s)
        if not m:
            return None
        d, mo, y = map(int, m.groups())
    try:
        return date(y, mo, d).isoformat()
    except ValueError:
        return None
