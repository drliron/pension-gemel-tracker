"""שכבת שירות: מחברת את הצנרת למסד הנתונים. כל פונקציה מקבלת conn ומחזירה מילונים הניתנים ל-JSON."""
from __future__ import annotations

import csv
import io
import json
import statistics
import uuid
from datetime import date
from pathlib import Path

from .db import one, rows
from .pipeline import analytics
from .pipeline.estimator import estimate
from .pipeline.extract import IngestError, ingest
from .pipeline.mapper import match_track
from .pipeline.market import freshness, import_manual, sync_official
from .pipeline.timeline import detect_transitions

PRODUCT_TYPES = {"pension", "gemel_invest", "hishtalmut", "insurance_savings"}
NS = uuid.UUID("6f1d2c3a-0000-4000-8000-000000000001")


class ServiceError(ValueError):
    pass


# ---------- קטלוג ומקורות ----------

def catalog(conn) -> list[dict]:
    out = rows(conn, "SELECT * FROM fund_tracks ORDER BY product_type, fund_name, track_name")
    for t in out:
        t["aliases"] = t.pop("aliases", [])
    return out


def catalog_keys(conn) -> set[str]:
    return {r["track_key"] for r in rows(conn, "SELECT track_key FROM fund_tracks")}


def load_sources(conn, config_path: Path) -> list[dict]:
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    for s in cfg:
        conn.execute(
            """INSERT INTO sources (source_id, kind, base_url, automation_allowed, terms_reviewed_on,
                 min_seconds_between_requests, ttl_hours) VALUES (?,?,?,?,?,?,?)
               ON CONFLICT(source_id) DO UPDATE SET kind=excluded.kind, base_url=excluded.base_url,
                 automation_allowed=excluded.automation_allowed, terms_reviewed_on=excluded.terms_reviewed_on,
                 min_seconds_between_requests=excluded.min_seconds_between_requests, ttl_hours=excluded.ttl_hours""",
            (s["source_id"], s["kind"], s.get("base_url", ""), int(s["automation_allowed"]),
             s.get("terms_reviewed_on"), s.get("min_seconds_between_requests", 5), s.get("ttl_hours", 24)),
        )
    conn.commit()
    return cfg


def sync_source(conn, config: list[dict], source_id: str, cache_dir: Path) -> dict:
    cfg = next((s for s in config if s["source_id"] == source_id), None)
    if cfg is None:
        raise ServiceError("מקור לא מוכר")
    if cfg["kind"] != "official_file":
        # מקורות משניים (aggregator) מתווספים כאן בעתיד, אחרי בדיקת תנאי שימוש
        return {"status": "not_implemented", "message": "שליפה אוטומטית ממקור זה עדיין לא נתמכת"}
    row = one(conn, "SELECT * FROM sources WHERE source_id=?", (source_id,))
    merged = {**row, "url": cfg.get("url"), "column_map": cfg.get("column_map")}
    merged["automation_allowed"] = bool(row["automation_allowed"])
    return sync_official(conn, merged, cache_dir, catalog_keys(conn))


def manual_import_csv(conn, text: str) -> dict:
    reader = csv.DictReader(io.StringIO(text.strip()))
    return import_manual(conn, list(reader), catalog_keys(conn))


# ---------- אחזקות ----------

def create_holding(conn, track_key: str, label: str, opened_on: str | None) -> dict:
    if track_key not in catalog_keys(conn):
        raise ServiceError("מסלול לא מוכר בקטלוג")
    hid = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO holdings (holding_id, track_key, status, opened_on, label) VALUES (?,?, 'active', ?, ?)",
        (hid, track_key, opened_on, label),
    )
    conn.commit()
    return {"holding_id": hid}


def _statements(conn, holding_id: str) -> list[dict]:
    return rows(
        conn,
        "SELECT * FROM statements WHERE holding_id=? AND user_confirmed=1 ORDER BY as_of",
        (holding_id,),
    )


def _track_names(conn) -> dict[str, str]:
    return {r["track_key"]: f'{r["fund_name"]} · {r["track_name"]}' for r in rows(conn, "SELECT * FROM fund_tracks")}


def _persist_transitions(conn, holding_id: str) -> None:
    conn.execute("DELETE FROM transitions WHERE holding_id=?", (holding_id,))
    for t in detect_transitions(holding_id, _statements(conn, holding_id)):
        conn.execute(
            """INSERT INTO transitions (holding_id, from_track_key, to_track_key, effective_on, evidence_json)
               VALUES (?,?,?,?,?)""",
            (t["holding_id"], t["from_track_key"], t["to_track_key"], t["effective_on"],
             json.dumps(t["evidence_statement_ids"])),
        )
    conn.commit()


# ---------- קליטה ואישור דוח ----------

def draft_statement(conn, filename: str, raw: bytes) -> dict:
    """שלב הטיוטה: חילוץ, מחיקת מזהים, מיפוי מסלול. שום דבר לא נשמר למסד."""
    try:
        result = ingest(raw, filename)
    except IngestError as exc:
        raise ServiceError(str(exc)) from exc
    fields = result["fields"]
    mapping = match_track(fields.get("reported_track_name", ""), catalog(conn))
    return {
        "source_sha256": result["source_sha256"],
        "parser": result["parser"],
        "confidence": result["confidence"],
        "warnings": result["warnings"],
        "redactions": result["redactions"],
        "clean_text": result["clean_text"],   # לתצוגת אימות בלבד, לא נשמר
        "fields": fields,
        "mapping": mapping,
    }


def confirm_statement(conn, holding_id: str, draft: dict, edits: dict) -> dict:
    """נשמר רק אחרי אישור המשתמש. edits מחליף שדות מהטיוטה."""
    hold = one(conn, "SELECT * FROM holdings WHERE holding_id=?", (holding_id,))
    if not hold:
        raise ServiceError("אחזקה לא נמצאה")
    f = {**draft.get("fields", {}), **edits}
    as_of = f.get("as_of")
    try:
        date.fromisoformat(str(as_of))
    except ValueError as exc:
        raise ServiceError("תאריך דוח לא תקין") from exc
    if f.get("balance_ils") is None:
        raise ServiceError("חסרה יתרה")
    track_key = edits.get("matched_track_key") or draft.get("mapping", {}).get("track_key")
    if track_key not in catalog_keys(conn):
        raise ServiceError("יש לשייך את הדוח למסלול מהקטלוג")

    sid = str(uuid.uuid5(NS, f'{holding_id}|{as_of}|{draft.get("source_sha256", "")}'))
    conn.execute(
        """INSERT OR REPLACE INTO statements (statement_id, holding_id, as_of, balance_ils, deposits_ytd_ils,
             monthly_deposit_ils, fee_deposit_pct, fee_accum_pct, reported_track_name, matched_track_key,
             source_sha256, parser_name, parser_version, parser_confidence, redactions_json, user_confirmed)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)""",
        (
            sid, holding_id, as_of, float(f["balance_ils"]), f.get("deposits_ytd_ils"),
            f.get("monthly_deposit_ils"), f.get("fee_deposit_pct"), f.get("fee_accum_pct"),
            f.get("reported_track_name", ""), track_key, draft.get("source_sha256", "manual"),
            (draft.get("parser") or {}).get("name", "manual"),
            (draft.get("parser") or {}).get("version", "0"),
            float(draft.get("confidence", 1.0)),
            json.dumps(draft.get("redactions", {})),
        ),
    )
    conn.commit()
    _persist_transitions(conn, holding_id)
    return {"statement_id": sid}


def add_manual_statement(conn, holding_id: str, as_of: str, balance_ils: float, track_key: str,
                         monthly_deposit_ils: float | None, fee_deposit_pct: float | None,
                         fee_accum_pct: float | None) -> dict:
    draft = {"source_sha256": "manual", "parser": None, "confidence": 1.0, "redactions": {},
             "fields": {"reported_track_name": "", "as_of": as_of, "balance_ils": balance_ils,
                        "monthly_deposit_ils": monthly_deposit_ils, "fee_deposit_pct": fee_deposit_pct,
                        "fee_accum_pct": fee_accum_pct},
             "mapping": {"track_key": track_key}}
    return confirm_statement(conn, holding_id, draft, {})


# ---------- סדרות תשואה ----------

SOURCE_PRIORITY = "CASE WHEN source_id='manual_import' THEN 1 ELSE 0 END, fetched_at DESC"


def track_series(conn, track_key: str) -> list[dict]:
    raw = rows(
        conn,
        f"SELECT * FROM market_points WHERE track_key=? ORDER BY period, {SOURCE_PRIORITY}",
        (track_key,),
    )
    seen, out = set(), []
    for r in raw:
        if r["period"] in seen:
            continue
        seen.add(r["period"])
        out.append(r)
    return out


def _returns(series: list[dict]) -> list[tuple[str, float]]:
    return [(p["period"], p["monthly_return_pct"]) for p in series]


# ---------- תצוגות ----------

def _holding_view(conn, h: dict, names: dict[str, str]) -> dict:
    stmts = _statements(conn, h["holding_id"])
    latest = stmts[-1] if stmts else None
    trans = rows(conn, "SELECT * FROM transitions WHERE holding_id=? ORDER BY effective_on", (h["holding_id"],))
    est = None
    if latest and h["status"] == "active":
        series = track_series(conn, h["track_key"])
        est = estimate(
            {"statement_id": latest["statement_id"], "as_of": latest["as_of"],
             "balance_ils": latest["balance_ils"], "monthly_deposit_ils": latest["monthly_deposit_ils"],
             "fee_deposit_pct": latest["fee_deposit_pct"]},
            _returns(series),
        )
    return {
        "holding_id": h["holding_id"],
        "label": h["label"],
        "status": h["status"],
        "track_key": h["track_key"],
        "track_name": names.get(h["track_key"], h["track_key"]),
        "product_type": h["product_type"],
        "age_group": h["age_group"],
        "opened_on": h["opened_on"],
        "closed_on": h["closed_on"],
        "latest": latest,
        "estimate": est,
        "timeline": [
            {"as_of": s["as_of"], "balance_ils": s["balance_ils"], "track_key": s["matched_track_key"],
             "track_name": names.get(s["matched_track_key"], ""), "fee_accum_pct": s["fee_accum_pct"]}
            for s in stmts
        ],
        "transitions": [
            {"effective_on": t["effective_on"], "from_track": names.get(t["from_track_key"], t["from_track_key"]),
             "to_track": names.get(t["to_track_key"], t["to_track_key"]), "evidence": t["evidence"],
             "approximate": True}
            for t in trans
        ],
    }


def list_holdings(conn, product_type: str = "all") -> list[dict]:
    names = _track_names(conn)
    sql = """SELECT h.*, t.product_type, t.age_group FROM holdings h
             JOIN fund_tracks t ON t.track_key = h.track_key ORDER BY h.opened_on"""
    out = [_holding_view(conn, h, names) for h in rows(conn, sql)]
    if product_type != "all":
        out = [h for h in out if h["product_type"] == product_type]
    return out


def _ytd_return(series: list[dict]) -> float | None:
    if not series:
        return None
    year = series[-1]["period"][:4]
    return analytics.compound([p["monthly_return_pct"] for p in series if p["period"].startswith(year)])


def dashboard(conn, product_type: str = "all") -> dict:
    if product_type != "all" and product_type not in PRODUCT_TYPES:
        raise ServiceError("סוג מוצר לא מוכר")
    holdings = [h for h in list_holdings(conn, product_type) if h["status"] == "active" and h["latest"]]
    per, weights, fees, sharpes, ytd_w = [], [], [], [], []
    reported_total = estimated_total = low_total = high_total = 0.0
    unknown = 0
    for h in holdings:
        series = track_series(conn, h["track_key"])
        est = h["estimate"]
        reported = h["latest"]["balance_ils"]
        mid = est["estimated_balance_ils"] if est else reported
        reported_total += reported
        estimated_total += mid
        low_total += est["low_ils"] if est else reported
        high_total += est["high_ils"] if est else reported
        latest_fee = h["latest"]["fee_accum_pct"]
        if latest_fee is None and series:
            latest_fee = series[-1].get("fee_accum_pct")
        if latest_fee is not None:
            fees.append((mid, latest_fee))
        if series and series[-1].get("sharpe_5y") is not None:
            sharpes.append((mid, series[-1]["sharpe_5y"]))
        ytd = _ytd_return(series)
        if ytd is not None:
            ytd_w.append((mid, ytd))
        weights.append({"label": h["track_name"], "weight_ils": mid,
                        "asset_mix": series[-1]["asset_mix"] if series else {}})
        if not series:
            unknown += 1
        per.append({k: h[k] for k in ("holding_id", "label", "track_name", "product_type", "latest", "estimate")})

    def wavg(pairs):
        tot = sum(w for w, _ in pairs)
        return round(sum(w * v for w, v in pairs) / tot, 3) if tot else None

    peer_fees = [
        r["latest_fee"] for r in _peer_latest(conn, product_type)
        if r["latest_fee"] is not None
    ]
    top_weight = (max(w["weight_ils"] for w in weights) / estimated_total * 100) if estimated_total else 0.0
    health = analytics.health_score(
        weighted_fee_accum=wavg(fees),
        peer_median_fee=round(statistics.median(peer_fees), 3) if peer_fees else None,
        sharpe=wavg(sharpes),
        top_weight_pct=top_weight,
        unknown_tracks=unknown,
    )
    return {
        "product_type": product_type,
        "totals": {
            "reported_ils": round(reported_total, 0),
            "estimated_ils": round(estimated_total, 0),
            "estimated_low_ils": round(low_total, 0),
            "estimated_high_ils": round(high_total, 0),
            "data_through": max((h["estimate"]["data_through"] for h in holdings if h["estimate"]), default=None),
        },
        "weighted_return_ytd_pct": wavg(ytd_w),
        "weighted_fee_accum_pct": wavg(fees),
        "health": health,
        "allocation": analytics.allocation(weights),
        "holdings": per,
        "data_status": freshness(conn),
    }


def _peer_latest(conn, product_type: str) -> list[dict]:
    out = []
    for t in rows(conn, "SELECT * FROM fund_tracks WHERE product_type=?", (product_type,)):
        series = track_series(conn, t["track_key"])
        if series:
            out.append({"track_key": t["track_key"], "latest_fee": series[-1].get("fee_accum_pct")})
    return out


def benchmark(conn, holding_id: str) -> dict:
    h = next((x for x in list_holdings(conn) if x["holding_id"] == holding_id), None)
    if not h:
        raise ServiceError("אחזקה לא נמצאה")
    peers = []
    for t in catalog(conn):
        if t["product_type"] != h["product_type"]:
            continue
        if h["age_group"] != "unknown" and t["age_group"] not in (h["age_group"], "unknown"):
            continue
        series = track_series(conn, t["track_key"])
        if not series:
            continue
        last = series[-1]
        peers.append({
            "track_key": t["track_key"],
            "label": f'{t["fund_name"]} · {t["track_name"]}',
            "returns": [p["monthly_return_pct"] for p in series],
            "fee_accum_pct": last.get("fee_accum_pct"),
            "fee_deposit_pct": last.get("fee_deposit_pct"),
            "sharpe_5y": last.get("sharpe_5y"),
        })
    result = analytics.benchmark(h["track_key"], peers)
    return {"holding_id": holding_id, "label": h["label"], **result}


def whatif(conn, holding_id: str, alt_track_key: str, window_months: int, horizon_years: int,
           fee_delta_pct: float, monthly_deposit_ils: float | None) -> dict:
    h = next((x for x in list_holdings(conn) if x["holding_id"] == holding_id), None)
    if not h or not h["latest"]:
        raise ServiceError("אחזקה לא נמצאה או ללא דוח מאושר")
    if alt_track_key not in catalog_keys(conn):
        raise ServiceError("מסלול חלופי לא מוכר")
    if not (1 <= window_months <= 60 and 1 <= horizon_years <= 40):
        raise ServiceError("טווח לא חוקי")
    cur_s = track_series(conn, h["track_key"])
    alt_s = track_series(conn, alt_track_key)
    if not cur_s or not alt_s:
        raise ServiceError("אין נתוני תשואה לאחד המסלולים")
    dep = monthly_deposit_ils if monthly_deposit_ils is not None else (h["latest"]["monthly_deposit_ils"] or 0.0)
    cfg = lambda s: {"returns": [p["monthly_return_pct"] for p in s],
                     "fee_deposit_pct": s[-1].get("fee_deposit_pct")}
    result = analytics.whatif(
        balance=h["latest"]["balance_ils"], monthly_deposit=dep,
        current=cfg(cur_s), alternative=cfg(alt_s),
        window_months=window_months, horizon_years=horizon_years, fee_delta_pct=fee_delta_pct,
    )
    result["current_label"] = h["track_name"]
    result["alternative_label"] = next(
        (t["fund_name"] + " · " + t["track_name"] for t in catalog(conn) if t["track_key"] == alt_track_key), alt_track_key
    )
    return result


def seed_demo(conn, fixtures: Path) -> dict:
    """טוען נתוני דמה. לא כולל מזהים אישיים. מסמן את הקטלוג כ-is_fixture."""
    cat = json.loads((fixtures / "catalog.json").read_text(encoding="utf-8"))
    for t in cat:
        conn.execute(
            """INSERT INTO fund_tracks (track_key, cma_fund_code, cma_track_code, fund_name, track_name,
                 product_type, age_group, aliases_json, is_fixture)
               VALUES (?,?,?,?,?,?,?,?,1) ON CONFLICT(track_key) DO UPDATE SET
                 fund_name=excluded.fund_name, track_name=excluded.track_name, aliases_json=excluded.aliases_json""",
            (t["track_key"], t["cma_fund_code"], t["cma_track_code"], t["fund_name"], t["track_name"],
             t["product_type"], t["age_group"], json.dumps(t.get("aliases", []), ensure_ascii=False)),
        )
    conn.commit()

    market = json.loads((fixtures / "market_monthly.json").read_text(encoding="utf-8"))
    from .pipeline.market import upsert_points
    upsert_points(conn, market, "manual_import")

    hold = json.loads((fixtures / "holdings_demo.json").read_text(encoding="utf-8"))
    for h in hold["holdings"]:
        conn.execute(
            """INSERT INTO holdings (holding_id, track_key, status, opened_on, closed_on, label)
               VALUES (?,?,?,?,?,?) ON CONFLICT(holding_id) DO UPDATE SET track_key=excluded.track_key,
                 status=excluded.status, closed_on=excluded.closed_on, label=excluded.label""",
            (h["holding_id"], h["track_key"], h["status"], h["opened_on"], h.get("closed_on"), h["label"]),
        )
    for s in hold["statements"]:
        conn.execute(
            """INSERT OR REPLACE INTO statements (statement_id, holding_id, as_of, balance_ils, deposits_ytd_ils,
                 monthly_deposit_ils, fee_deposit_pct, fee_accum_pct, reported_track_name, matched_track_key,
                 source_sha256, parser_name, parser_version, parser_confidence, redactions_json, user_confirmed)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)""",
            (s["statement_id"], s["holding_id"], s["as_of"], s["balance_ils"], s.get("deposits_ytd_ils"),
             s.get("monthly_deposit_ils"), s.get("fee_deposit_pct"), s.get("fee_accum_pct"),
             s["reported_track_name"], s["matched_track_key"], s["source_sha256"], "demo_fixture", "1",
             1.0, "{}"),
        )
    conn.commit()
    for h in hold["holdings"]:
        _persist_transitions(conn, h["holding_id"])
    return {"tracks": len(cat), "points": len(market), "holdings": len(hold["holdings"])}
