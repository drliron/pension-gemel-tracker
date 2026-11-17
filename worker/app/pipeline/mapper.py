"""סוכן מיפוי: מקשר שם מסלול כפי שמופיע בדוח לקוד מסלול רשמי (track_key) מתוך הקטלוג."""
from __future__ import annotations

import re


def _norm(s: str) -> str:
    s = s.replace("״", '"').replace("׳", "'").replace("-", " ")
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def match_track(reported: str, catalog: list[dict]) -> dict:
    """מחזיר {"track_key": ..., "method": ..., "candidates": [...]}.

    שיטות: התאמה מדויקת (אחרי נרמול) לשם מסלול או לכינוי; אחרת הצעות לפי חפיפת מילים.
    אין התאמה אוטומטית מעבר לזה, כדי לא לשייך מסלול שגוי בשקט.
    """
    target = _norm(reported)
    if not target:
        return {"track_key": None, "method": "none", "candidates": []}

    exact = []
    for t in catalog:
        names = [t["track_name"], t["fund_name"] + " " + t["track_name"], *t.get("aliases", [])]
        if any(_norm(n) == target for n in names):
            exact.append(t["track_key"])
    if len(exact) == 1:
        return {"track_key": exact[0], "method": "exact", "candidates": []}
    if len(exact) > 1:
        # שם מסלול משותף לכמה קופות: לא משייכים בשקט
        return {"track_key": None, "method": "ambiguous", "candidates": exact[:3]}

    tokens = set(target.split())
    scored = []
    for t in catalog:
        names = " ".join([t["fund_name"], t["track_name"], *t.get("aliases", [])])
        overlap = len(tokens & set(_norm(names).split()))
        if overlap:
            scored.append((overlap / max(len(tokens), 1), t["track_key"]))
    scored.sort(reverse=True)
    candidates = [k for _, k in scored[:3]]
    return {"track_key": None, "method": "needs_review", "candidates": candidates}
