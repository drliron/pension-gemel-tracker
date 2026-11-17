"""תבנית csv_export_v1: קובץ CSV עם כותרות בעברית, בשורה אחת של נתון לכל מסלול.

עמודות נדרשות: תאריך, מסלול, יתרה. עמודות אופציונליות: הפקדות_מתחילת_השנה, הפקדה_חודשית,
דמי_ניהול_מהפקדות, דמי_ניהול_מהצבירה. הכותרות מנורמלות (רווחים -> קו תחתון).
"""
from __future__ import annotations

import csv
import io

from .base import ParseResult, parse_amount, parse_date

NAME = "csv_export"
VERSION = "1"

ALIASES = {
    "as_of": ["תאריך", "תאריך_דוח", "as_of"],
    "track": ["מסלול", "מסלול_השקעה", "track"],
    "balance": ["יתרה", "שווי", "balance"],
    "deposits_ytd": ["הפקדות_מתחילת_השנה", "הפקדות_השנה"],
    "monthly_deposit": ["הפקדה_חודשית"],
    "fee_deposit": ["דמי_ניהול_מהפקדות"],
    "fee_accum": ["דמי_ניהול_מהצבירה", "דמי_ניהול_מצבירה"],
}


def _norm(h: str) -> str:
    return h.strip().replace(" ", "_")


def _col(headers: list[str], key: str) -> str | None:
    for alias in ALIASES[key]:
        for h in headers:
            if _norm(h) == alias:
                return h
    return None


def detect(text: str) -> float:
    first = text.strip().splitlines()[0] if text.strip() else ""
    if "," not in first:
        return 0.0
    headers = [_norm(h) for h in first.split(",")]
    hits = sum(1 for k in ("as_of", "track", "balance") if any(a in headers for a in ALIASES[k]))
    return hits / 3


def parse(text: str) -> ParseResult:
    res = ParseResult(NAME, VERSION)
    reader = csv.DictReader(io.StringIO(text.strip()))
    headers = reader.fieldnames or []
    rows = list(reader)
    if not rows:
        res.warnings.append("הקובץ ריק")
        return res

    # דוח CSV מייצג סטטוס אחד לכל הקובץ: לוקחים את השורה האחרונה לפי תאריך
    row = max(rows, key=lambda r: r.get(_col(headers, "as_of") or "", ""))
    f = res.fields

    if (c := _col(headers, "as_of")) and (d := parse_date(row[c] or "")):
        f["as_of"] = d
        res.found += 1
    else:
        res.warnings.append("לא נמצא תאריך תקין")
    if (c := _col(headers, "balance")) and row[c]:
        f["balance_ils"] = parse_amount(row[c].replace("₪", "").strip())
        res.found += 1
    else:
        res.warnings.append("לא נמצאה יתרה")
    if (c := _col(headers, "track")) and row[c]:
        f["reported_track_name"] = row[c].strip()
        res.found += 1
    else:
        res.warnings.append("לא נמצא שם מסלול")

    for key, field_name in [
        ("deposits_ytd", "deposits_ytd_ils"),
        ("monthly_deposit", "monthly_deposit_ils"),
        ("fee_deposit", "fee_deposit_pct"),
        ("fee_accum", "fee_accum_pct"),
    ]:
        c = _col(headers, key)
        if c and row[c].strip():
            value = row[c].replace("%", "").replace(",", "").strip()
            f[field_name] = float(value)
    return res
