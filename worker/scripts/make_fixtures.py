"""מייצר נתוני דמה דטרמיניסטיים ל-data/fixtures. להרצה: python3 worker/scripts/make_fixtures.py

כל הקודים והשמות בדמו בדויים (קופות "דמו"). אין כאן מזהים אישיים אמיתיים.
כשיהיו קודי קופה רשמיים מאומתים, מחליפים את catalog.json ולא את הלוגיקה.
"""
from __future__ import annotations

import hashlib
import json
import random
import uuid
from pathlib import Path

OUT = Path(__file__).resolve().parents[2] / "data" / "fixtures"
NS = uuid.UUID("6f1d2c3a-0000-4000-8000-00000000f1f1")

CATALOG = [
    {"track_key": "9101-01", "cma_fund_code": "9101", "cma_track_code": "01", "fund_name": "פנסיה דמו א'",
     "track_name": "מסלול כללי לבני 50 ומטה", "product_type": "pension", "age_group": "up_to_50",
     "aliases": ["פנסיה דמו א' - כללי 50-"]},
    {"track_key": "9101-02", "cma_fund_code": "9101", "cma_track_code": "02", "fund_name": "פנסיה דמו א'",
     "track_name": "מסלול מניות לבני 50 ומטה", "product_type": "pension", "age_group": "up_to_50", "aliases": []},
    {"track_key": "9102-01", "cma_fund_code": "9102", "cma_track_code": "01", "fund_name": "פנסיה דמו ב'",
     "track_name": "מסלול כללי לבני 50 ומטה", "product_type": "pension", "age_group": "up_to_50", "aliases": []},
    {"track_key": "9201-01", "cma_fund_code": "9201", "cma_track_code": "01", "fund_name": "גמל להשקעה דמו א'",
     "track_name": "מסלול כללי", "product_type": "gemel_invest", "age_group": "unknown", "aliases": []},
    {"track_key": "9201-02", "cma_fund_code": "9201", "cma_track_code": "02", "fund_name": "גמל להשקעה דמו א'",
     "track_name": "מסלול S&P 500", "product_type": "gemel_invest", "age_group": "unknown", "aliases": []},
    {"track_key": "9202-01", "cma_fund_code": "9202", "cma_track_code": "01", "fund_name": "גמל להשקעה דמו ב'",
     "track_name": "מסלול כללי", "product_type": "gemel_invest", "age_group": "unknown", "aliases": []},
]

# mean/sd חודשיים באחוזים, דמי ניהול מצבירה והפקדה, שארפ, הרכב נכסים
PARAMS = {
    "9101-01": dict(mean=0.45, sd=0.9, fee_accum=0.12, fee_dep=0.5, sharpe=0.61, assets=2_500_000,
                    mix=dict(israel_equity_pct=15, foreign_equity_pct=25, bonds_pct=50, fx_pct=5, other_pct=5)),
    "9101-02": dict(mean=0.80, sd=2.4, fee_accum=0.28, fee_dep=0.5, sharpe=0.45, assets=1_100_000,
                    mix=dict(israel_equity_pct=25, foreign_equity_pct=55, bonds_pct=5, fx_pct=10, other_pct=5)),
    "9102-01": dict(mean=0.35, sd=0.8, fee_accum=0.22, fee_dep=0.7, sharpe=0.38, assets=900_000,
                    mix=dict(israel_equity_pct=14, foreign_equity_pct=20, bonds_pct=58, fx_pct=3, other_pct=5)),
    "9201-01": dict(mean=0.50, sd=1.1, fee_accum=0.18, fee_dep=0.0, sharpe=0.55, assets=640_000,
                    mix=dict(israel_equity_pct=18, foreign_equity_pct=24, bonds_pct=50, fx_pct=4, other_pct=4)),
    "9201-02": dict(mean=0.90, sd=3.0, fee_accum=0.35, fee_dep=0.0, sharpe=0.48, assets=410_000,
                    mix=dict(israel_equity_pct=2, foreign_equity_pct=92, bonds_pct=0, fx_pct=6, other_pct=0)),
    "9202-01": dict(mean=0.42, sd=1.0, fee_accum=0.30, fee_dep=0.0, sharpe=0.40, assets=220_000,
                    mix=dict(israel_equity_pct=16, foreign_equity_pct=22, bonds_pct=54, fx_pct=4, other_pct=4)),
}


def periods(start=(2023, 11), end=(2026, 10)) -> list[str]:
    y, m = start
    out = []
    while (y, m) <= end:
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def compound(xs: list[float]) -> float:
    g = 1.0
    for x in xs:
        g *= 1 + x / 100
    return (g - 1) * 100


def build_market() -> list[dict]:
    pers = periods()
    points = []
    for track, p in PARAMS.items():
        rng = random.Random(track)
        rets = [round(rng.gauss(p["mean"], p["sd"]), 2) for _ in pers]
        for i, per in enumerate(pers):
            same_year = [r for r, q in zip(rets[: i + 1], pers[: i + 1]) if q[:4] == per[:4]]
            row = {
                "track_key": track,
                "period": per,
                "monthly_return_pct": rets[i],
                "ytd_return_pct": round(compound(same_year), 2),
                "return_12m_pct": round(compound(rets[max(0, i - 11): i + 1]), 2) if i >= 11 else None,
                "return_3y_pct": None,
                "return_5y_pct": None,
                "sharpe_5y": p["sharpe"],
                "fee_deposit_pct": p["fee_dep"],
                "fee_accum_pct": p["fee_accum"],
                "assets_ils_k": p["assets"],
                "asset_mix": p["mix"],
            }
            if i == len(pers) - 1:
                row["return_3y_pct"] = round(((1 + compound(rets[-36:]) / 100) ** (12 / 36) - 1) * 100, 2)
            points.append(row)
    return points


def sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def build_holdings() -> dict:
    h1 = str(uuid.UUID("11111111-1111-4111-8111-000000000001"))
    h2 = str(uuid.UUID("11111111-1111-4111-8111-000000000002"))
    h3 = str(uuid.UUID("11111111-1111-4111-8111-000000000003"))

    def st(holding, as_of, balance, track, reported, dep_m, fee_dep, fee_acc, dep_ytd, tag):
        return {
            "statement_id": str(uuid.uuid5(NS, f"{holding}|{as_of}")),
            "holding_id": holding, "as_of": as_of, "balance_ils": balance,
            "deposits_ytd_ils": dep_ytd, "monthly_deposit_ils": dep_m, "fee_deposit_pct": fee_dep,
            "fee_accum_pct": fee_acc, "reported_track_name": reported, "matched_track_key": track,
            "source_sha256": sha(f"demo-{tag}-{as_of}"),
        }

    return {
        "_about": "נתוני דמה. קופות בדויות. אין כאן מזהים אישיים.",
        "holdings": [
            {"holding_id": h1, "track_key": "9101-02", "status": "active", "opened_on": "2019-03-01",
             "closed_on": None, "label": "פנסיה מהעבודה הנוכחית"},
            {"holding_id": h2, "track_key": "9201-02", "status": "active", "opened_on": "2021-01-15",
             "closed_on": None, "label": "גמל להשקעה"},
            {"holding_id": h3, "track_key": "9102-01", "status": "closed", "opened_on": "2012-05-01",
             "closed_on": "2024-03-31", "label": "פנסיה ישנה (נסגרה)"},
        ],
        "statements": [
            st(h1, "2024-12-31", 210000, "9101-01", "פנסיה דמו א' מסלול כללי לבני 50 ומטה", 2100, 0.5, 0.12, 25200, "h1"),
            st(h1, "2025-06-30", 232000, "9101-01", "פנסיה דמו א' מסלול כללי לבני 50 ומטה", 2100, 0.5, 0.12, 12600, "h1"),
            st(h1, "2025-12-31", 255000, "9101-02", "פנסיה דמו א' מסלול מניות לבני 50 ומטה", 2100, 0.5, 0.28, 25200, "h1"),
            st(h1, "2026-06-30", 281000, "9101-02", "פנסיה דמו א' מסלול מניות לבני 50 ומטה", 2100, 0.5, 0.28, 12600, "h1"),
            st(h2, "2025-06-30", 118000, "9201-01", "גמל להשקעה דמו א' מסלול כללי", 800, 0.0, 0.18, 4800, "h2"),
            st(h2, "2025-12-31", 124000, "9201-01", "גמל להשקעה דמו א' מסלול כללי", 800, 0.0, 0.18, 9600, "h2"),
            st(h2, "2026-06-30", 131500, "9201-02", "גמל להשקעה דמו א' מסלול S&P 500", 800, 0.0, 0.35, 4800, "h2"),
            st(h3, "2023-12-31", 60000, "9102-01", "פנסיה דמו ב' מסלול כללי לבני 50 ומטה", 0, 0.7, 0.22, 0, "h3"),
        ],
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "catalog.json").write_text(json.dumps(CATALOG, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "market_monthly.json").write_text(
        json.dumps(build_market(), ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / "holdings_demo.json").write_text(
        json.dumps(build_holdings(), ensure_ascii=False, indent=2), encoding="utf-8")
    print("fixtures written to", OUT)


if __name__ == "__main__":
    main()
