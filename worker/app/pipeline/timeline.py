"""סוכן היסטוריה ומעברי מסלולים: מצליב דוחות מאותה אחזקה ומזהה מעברים.

כלל: רק דוחות שאושרו על ידי המשתמש נכנסים לציר הזמן. מעבר מתועד רק כשיש שני דוחות מאושרים
עם מסלולים רשומים שונים. תאריך המעבר הוא תאריך הדוח הראשון שמראה את המסלול החדש, והוא מסומן
כ"מוערך" בממשק.
"""
from __future__ import annotations


def detect_transitions(holding_id: str, confirmed: list[dict]) -> list[dict]:
    """confirmed: דוחות מאושרים של אחזקה אחת, בכל סדר. מחזיר רשימת מעברים."""
    ordered = sorted(confirmed, key=lambda s: s["as_of"])
    out = []
    for prev, curr in zip(ordered, ordered[1:]):
        a, b = prev.get("matched_track_key"), curr.get("matched_track_key")
        if not a or not b or a == b:
            continue
        out.append(
            {
                "holding_id": holding_id,
                "from_track_key": a,
                "to_track_key": b,
                "effective_on": curr["as_of"],
                "evidence_statement_ids": [prev["statement_id"], curr["statement_id"]],
                "approximate": True,
            }
        )
    return out
