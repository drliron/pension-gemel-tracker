"""סוכני ניתוח חשיפות והשוואה: פונקציות טהורות על נתונים שכבר נטענו מהמסד.

כל הפונקציות כאן דטרמיניסטיות ואינן מבצעות קריאות רשת. הציון "בריאות התיק" הוא היוריסטיקה
שקופה ולא המלצה להשקעה.
"""
from __future__ import annotations

import statistics

ASSET_KEYS = ["israel_equity_pct", "foreign_equity_pct", "bonds_pct", "fx_pct", "other_pct"]
ASSET_LABELS = {
    "israel_equity_pct": "מניות ישראל",
    "foreign_equity_pct": "מניות חו\"ל",
    "bonds_pct": "אג\"ח",
    "fx_pct": "מט\"ח",
    "other_pct": "אחר",
}


def compound(returns_pct: list[float]) -> float | None:
    """תשואה מצטברת באחוזים מתוך תשואות חודשיות (לפי סדר)."""
    if not returns_pct:
        return None
    g = 1.0
    for r in returns_pct:
        g *= 1 + r / 100
    return round((g - 1) * 100, 2)


def annualize(total_pct: float | None, months: int) -> float | None:
    if total_pct is None or months <= 0:
        return None
    return round(((1 + total_pct / 100) ** (12 / months) - 1) * 100, 2)


def benchmark(own_key: str, peers: list[dict]) -> dict:
    """peers: [{track_key, label, returns (רשימה, מהישן לחדש), fee_accum_pct, fee_deposit_pct, sharpe_5y}]"""
    rows = []
    for p in peers:
        rets = p["returns"]
        r12 = compound(rets[-12:]) if len(rets) >= 12 else None
        r36 = annualize(compound(rets[-36:]), 36) if len(rets) >= 36 else None
        rows.append(
            {
                "track_key": p["track_key"],
                "label": p["label"],
                "return_12m_pct": r12,
                "return_3y_annual_pct": r36,
                "fee_accum_pct": p.get("fee_accum_pct"),
                "fee_deposit_pct": p.get("fee_deposit_pct"),
                "sharpe_5y": p.get("sharpe_5y"),
                "is_own": p["track_key"] == own_key,
            }
        )
    rows.sort(key=lambda r: (r["return_12m_pct"] is None, -(r["return_12m_pct"] or 0)))
    r12_values = [r["return_12m_pct"] for r in rows if r["return_12m_pct"] is not None]
    fees = [r["fee_accum_pct"] for r in rows if r["fee_accum_pct"] is not None]
    own = next((r for r in rows if r["is_own"]), None)
    summary = {
        "median_return_12m_pct": round(statistics.median(r12_values), 2) if r12_values else None,
        "median_fee_accum_pct": round(statistics.median(fees), 3) if fees else None,
        "own_rank": (rows.index(own) + 1) if own else None,
        "peer_count": len(rows),
    }
    return {"rows": rows, "summary": summary}


def allocation(holdings: list[dict]) -> dict:
    """holdings: [{label, weight_ils, asset_mix: {israel_equity_pct,...}}]. מחזיר חשיפה משוקללת לתיק."""
    total = sum(h["weight_ils"] for h in holdings if h["weight_ils"] > 0)
    totals = {k: 0.0 for k in ASSET_KEYS}
    if total <= 0:
        return {"total_ils": 0, "categories": [], "by_holding": []}
    by_holding = []
    for h in holdings:
        w = h["weight_ils"] / total
        mix = h.get("asset_mix") or {}
        for k in ASSET_KEYS:
            totals[k] += w * float(mix.get(k, 0.0))
        by_holding.append({"label": h["label"], "weight_pct": round(w * 100, 2), "asset_mix": mix})
    categories = [
        {"key": k, "label": ASSET_LABELS[k], "pct": round(totals[k], 2)} for k in ASSET_KEYS
    ]
    return {"total_ils": round(total, 2), "categories": categories, "by_holding": by_holding}


def health_score(*, weighted_fee_accum: float | None, peer_median_fee: float | None,
                 sharpe: float | None, top_weight_pct: float, unknown_tracks: int) -> dict:
    """ציון 0-100 לפי כללים שקופים. כל הפחתה מוסברת בשדה reasons."""
    score = 100.0
    reasons = []
    if weighted_fee_accum is not None and peer_median_fee is not None:
        gap = weighted_fee_accum - peer_median_fee
        if gap > 0.1:
            pen = min(30.0, round(gap * 40, 1))
            score -= pen
            reasons.append(f"דמי ניהול מצבירה גבוהים מחציון הקבוצה ב-{gap:.2f}% (-{pen})")
    if sharpe is not None and sharpe < 0.5:
        score -= 15
        reasons.append(f"מדד שארפ 5 שנים נמוך ({sharpe:.2f}) (-15)")
    if top_weight_pct > 60:
        score -= 10
        reasons.append(f"ריכוז: אחזקה אחת מהווה {top_weight_pct:.0f}% מהתיק (-10)")
    if unknown_tracks:
        score -= 5 * min(unknown_tracks, 3)
        reasons.append(f"{unknown_tracks} אחזקות ללא מיפוי מסלול (-{5 * min(unknown_tracks, 3)})")
    return {"score": max(0, round(score)), "reasons": reasons or ["לא זוהו בעיות לפי הכללים"]}


def whatif(*, balance: float, monthly_deposit: float, current: dict, alternative: dict,
           window_months: int, horizon_years: int, fee_delta_pct: float) -> dict:
    """סימולציה חודשית. current / alternative: {returns (מהישן לחדש), fee_deposit_pct, fee_accum_pct}.

    fee_delta_pct: שינוי שנתי בדמי הניהול מצבירה של החלופה (למשל +0.2 = יקר יותר ב-0.2% בשנה).
    התשואה החודשית ההיסטורית מחושבת כממוצע גיאומטרי על החלון, ומופחתת לחודש את דמי הניהול המוספים.
    """
    def monthly_geo(returns: list[float]) -> float:
        window = returns[-window_months:] if len(returns) >= window_months else returns
        if not window:
            return 0.0
        total = compound(window) / 100
        return (1 + total) ** (1 / len(window)) - 1

    def run(cfg: dict, extra_fee_pct: float) -> list[dict]:
        g = monthly_geo(cfg["returns"]) - extra_fee_pct / 100 / 12
        dep_net = monthly_deposit * (1 - (cfg.get("fee_deposit_pct") or 0) / 100)
        v = balance
        series = [{"year": 0, "value": round(v, 0)}]
        for m in range(1, horizon_years * 12 + 1):
            v = v * (1 + g) + dep_net
            if m % 12 == 0:
                series.append({"year": m // 12, "value": round(v, 0)})
        return series

    cur = run(current, 0.0)
    alt = run(alternative, fee_delta_pct)
    diff = alt[-1]["value"] - cur[-1]["value"]
    return {
        "horizon_years": horizon_years,
        "window_months": window_months,
        "current": cur,
        "alternative": alt,
        "difference_at_horizon_ils": round(diff, 0),
        "note": "סימולציה על בסיס תשואות היסטוריות. תשואות עבר אינן מבטיחות תשואות עתידיות.",
    }
