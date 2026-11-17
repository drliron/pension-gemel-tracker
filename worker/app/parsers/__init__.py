"""רישום התבניות. בחירת תבנית לפי ציון ההתאמה הגבוה ביותר (סף מינימלי 0.34)."""
from __future__ import annotations

from . import csv_export, kv_report

REGISTRY = [kv_report, csv_export]
MIN_DETECT = 0.34


def pick_parser(text: str):
    scored = [(m.detect(text), m) for m in REGISTRY]
    score, module = max(scored, key=lambda t: t[0])
    if score < MIN_DETECT:
        return None
    return module
