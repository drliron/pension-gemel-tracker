"""תבנית kv_report_v1: דוח טקסטואלי בפורמט "תווית: ערך", כפי שמופק מ-PDF של דוח מסלקה/בית השקעות.

הערה: זו תבנית גנרית. לכל מוסד שיש לו דוח אמיתי תתווסף תבנית ייעודית, אחרי שיהיה דוגמה אמיתית מאושרת.
"""
from __future__ import annotations

import re

from .base import AMOUNT_RE, PCT_RE, ParseResult, parse_amount, parse_date

NAME = "kv_report"
VERSION = "1"

KEYS = {
    "as_of": r"(?:תאריך\s*(?:ה?דוח|יתרה|לתאריך)|לתאריך)",
    "balance": r"(?:יתרה(?:\s*לתאריך)?|סך\s*צבירה|שווי\s*החשבון)",
    "deposits_ytd": r"(?:הפקדות\s*מתחילת\s*השנה|הפקדות\s*השנה)",
    "monthly_deposit": r"(?:הפקדה\s*חודשית)",
    "fee_deposit": r"(?:דמי\s*ניהול\s*מהפקדות)",
    "fee_accum": r"(?:דמי\s*ניהול\s*מהצבירה|דמי\s*ניהול\s*מצבירה)",
    "track": r"(?:מסלול\s*השקעה|מסלול)",
}


def _find(text: str, key: str, value_re: str) -> str | None:
    m = re.search(rf"^\s*{KEYS[key]}\s*[:\-]\s*{value_re}", text, re.MULTILINE)
    return m.group(1) if m else None


def detect(text: str) -> float:
    hits = sum(1 for k in ("balance", "track", "as_of") if re.search(rf"^\s*{KEYS[k]}\s*[:\-]", text, re.MULTILINE))
    return hits / 3


def parse(text: str) -> ParseResult:
    res = ParseResult(NAME, VERSION)
    f = res.fields

    raw_date = _find(text, "as_of", r"(\d{4}-\d{1,2}-\d{1,2}|\d{1,2}[./]\d{1,2}[./]\d{4})")
    if raw_date and (d := parse_date(raw_date)):
        f["as_of"] = d
        res.found += 1
    else:
        res.warnings.append("לא נמצא תאריך דוח")

    raw_bal = _find(text, "balance", AMOUNT_RE)
    if raw_bal:
        f["balance_ils"] = parse_amount(raw_bal)
        res.found += 1
    else:
        res.warnings.append("לא נמצאה יתרה")

    track = re.search(rf"^\s*{KEYS['track']}\s*[:\-]\s*(.+)$", text, re.MULTILINE)
    if track:
        f["reported_track_name"] = track.group(1).strip()
        res.found += 1
    else:
        res.warnings.append("לא נמצא שם מסלול")

    for key, field_name, value_re in [
        ("deposits_ytd", "deposits_ytd_ils", AMOUNT_RE),
        ("monthly_deposit", "monthly_deposit_ils", AMOUNT_RE),
        ("fee_deposit", "fee_deposit_pct", PCT_RE),
        ("fee_accum", "fee_accum_pct", PCT_RE),
    ]:
        raw = _find(text, key, value_re)
        if raw is not None:
            f[field_name] = parse_amount(raw) if "ils" in field_name else float(raw)

    res.required = 3
    return res
