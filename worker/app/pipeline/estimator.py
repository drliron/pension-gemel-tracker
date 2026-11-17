"""חישוב יתרה משוערכת חיה: return_compounding_v1.

הנוסחה (לכל חודש p שאחרי חודש הדוח, לפי הסדר):
    value = value + deposit_net          # הפקדה נכנסת בתחילת החודש
    value = value * (1 + r_p / 100)      # תשואה חודשית של המסלול
כאשר deposit_net = monthly_deposit * (1 - fee_deposit_pct / 100).

הטווח: low / high מחושבים באותה נוסחה כשכל r_p מוזז ב-∓ סטיית התקן החודשית של המסלול (עד 60 חודשים).
הפונקציה דטרמיניסטית ואינה מבצעת קריאות רשת.
"""
from __future__ import annotations

import math

METHOD = "return_compounding_v1"


def _stdev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return math.sqrt(sum((v - mean) ** 2 for v in values) / (len(values) - 1))


def _project(base: float, returns: list[float], deposit_net: float, shift: float) -> float:
    value = base
    for r in returns:
        value += deposit_net
        value *= 1 + (r + shift) / 100
    return value


def estimate(statement: dict, track_returns: list[tuple[str, float]]) -> dict:
    """statement: {statement_id, as_of, balance_ils, monthly_deposit_ils, fee_deposit_pct}
    track_returns: [(YYYY-MM, monthly_return_pct), ...] בסדר עולה, לכל המסלול.
    """
    base_period = statement["as_of"][:7]
    base = float(statement["balance_ils"])
    deposit = float(statement.get("monthly_deposit_ils") or 0.0)
    fee_dep = float(statement.get("fee_deposit_pct") or 0.0)
    deposit_net = deposit * (1 - fee_dep / 100)

    after = [(p, r) for p, r in track_returns if p > base_period]
    returns = [r for _, r in after]
    history = [r for p, r in track_returns][-60:]
    sigma = _stdev(history)

    if not after:
        return {
            "statement_id": statement["statement_id"],
            "base_balance_ils": round(base, 2),
            "estimated_balance_ils": round(base, 2),
            "low_ils": round(base, 2),
            "high_ils": round(base, 2),
            "data_through": base_period,
            "method": METHOD,
            "assumptions": ["אין נתוני תשואה חודשיים מאז תאריך הדוח, ולכן ההערכה זהה לדוח"],
        }

    mid = _project(base, returns, deposit_net, 0.0)
    low = _project(base, returns, deposit_net, -sigma)
    high = _project(base, returns, deposit_net, sigma)
    data_through = after[-1][0]
    months = len(after)

    assumptions = [
        f"נתוני תשואה עד {data_through} ({months} חודשים מאז תאריך הדוח)",
        "הערכה מתחילת החודש שאחרי תאריך הדוח, ללא חודש חלקי",
        "הפקדה חודשית נכנסת בתחילת כל חודש, בניכוי דמי ניהול מהפקדות",
        f"טווח לפי ±סטיית תקן חודשית של המסלול ({sigma:.2f}%)",
        "ההנחה שתשואות המסלול המתפרסמות נטו מדמי ניהול צבירה: לאימות מול המקור",
    ]
    return {
        "statement_id": statement["statement_id"],
        "base_balance_ils": round(base, 2),
        "estimated_balance_ils": round(mid, 2),
        "low_ils": round(min(low, high), 2),
        "high_ils": round(max(low, high), 2),
        "data_through": data_through,
        "method": METHOD,
        "assumptions": assumptions,
    }
