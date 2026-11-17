"""סוכן מיפוי וסנכרון נתוני שוק.

שני ערוצים:
1. official_file: קובץ רשמי (גמל-נט / פנסיה-נט מ-data.gov.il). נשלף עם בקשה מותנית (ETag / Last-Modified),
   נשמר ב-Cache מקומי, ומתפרש לפי column_map שמוגדר ב-config/sources.json.
2. manual_import: CSV/JSON שהמשתמש מדביק או מעלה. תמיד זמין, והוא הגיבוי כשהערוץ הרשמי לא זמין.

כללים:
- שליפה אוטומטית מותרת רק אם automation_allowed=true *וגם* terms_reviewed_on מוגדר (תאריך בדיקת התנאים).
- אין שליפה לפני שנקבע URL מפורש ב-config. שום URL לא נבנה מנתוני משתמש.
- כשהשליפה נכשלת, נשמר המטמון הקודם עם סטטוס stale, ולא מחושבת הערכה בלי data_through.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..db import one, rows

NUMERIC_FIELDS = [
    "monthly_return_pct", "ytd_return_pct", "return_12m_pct", "return_3y_pct",
    "return_5y_pct", "sharpe_5y", "fee_deposit_pct", "fee_accum_pct", "assets_ils_k",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _num(v) -> float | None:
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    return float(str(v).replace(",", "").replace("%", "").strip())


def upsert_points(conn, points: list[dict], source_id: str) -> int:
    """points: מילונים עם track_key ו-period ושדות המספריים. מחזיר כמה נכתבו."""
    n = 0
    for p in points:
        conn.execute(
            """INSERT INTO market_points (track_key, period, source_id, monthly_return_pct,
                 ytd_return_pct, return_12m_pct, return_3y_pct, return_5y_pct, sharpe_5y,
                 fee_deposit_pct, fee_accum_pct, assets_ils_k, asset_mix_json, fetched_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(track_key, period, source_id) DO UPDATE SET
                 monthly_return_pct=excluded.monthly_return_pct, ytd_return_pct=excluded.ytd_return_pct,
                 return_12m_pct=excluded.return_12m_pct, return_3y_pct=excluded.return_3y_pct,
                 return_5y_pct=excluded.return_5y_pct, sharpe_5y=excluded.sharpe_5y,
                 fee_deposit_pct=excluded.fee_deposit_pct, fee_accum_pct=excluded.fee_accum_pct,
                 assets_ils_k=excluded.assets_ils_k, asset_mix_json=excluded.asset_mix_json,
                 fetched_at=excluded.fetched_at""",
            (
                p["track_key"], p["period"], source_id, p["monthly_return_pct"],
                p.get("ytd_return_pct"), p.get("return_12m_pct"), p.get("return_3y_pct"),
                p.get("return_5y_pct"), p.get("sharpe_5y"), p.get("fee_deposit_pct"),
                p.get("fee_accum_pct"), p.get("assets_ils_k"),
                json.dumps(p.get("asset_mix", {}), ensure_ascii=False), _now(),
            ),
        )
        n += 1
    conn.commit()
    return n


def import_manual(conn, rows_in: list[dict], catalog_keys: set[str]) -> dict:
    """ייבוא ידני: שורות (dict) עם track_key, period ושדות אופציונליים. לא מקבל מזהים אישיים."""
    points, skipped = [], []
    for i, r in enumerate(rows_in):
        tk = (r.get("track_key") or "").strip()
        period = (r.get("period") or "").strip()
        if tk not in catalog_keys:
            skipped.append({"row": i, "reason": "track_key לא מוכר בקטלוג"})
            continue
        if len(period) != 7 or period[4] != "-":
            skipped.append({"row": i, "reason": "period חייב להיות YYYY-MM"})
            continue
        ret = _num(r.get("monthly_return_pct"))
        if ret is None:
            skipped.append({"row": i, "reason": "חסרה תשואה חודשית"})
            continue
        point = {"track_key": tk, "period": period, "monthly_return_pct": ret}
        for f in NUMERIC_FIELDS[1:]:
            point[f] = _num(r.get(f))
        point["asset_mix"] = r.get("asset_mix") if isinstance(r.get("asset_mix"), dict) else {}
        points.append(point)
    written = upsert_points(conn, points, "manual_import")
    return {"written": written, "skipped": skipped}


def parse_official_csv(text: str, column_map: dict, catalog_keys: set[str]) -> tuple[list[dict], int]:
    """column_map: {"cma_fund_code": "שם עמודה", "cma_track_code": ..., "period": ..., "monthly_return_pct": ..., ...}"""
    reader = csv.DictReader(io.StringIO(text))
    points, unknown = [], 0
    for r in reader:
        key = f"{r.get(column_map['cma_fund_code'], '').strip()}-{r.get(column_map['cma_track_code'], '').strip()}"
        if key not in catalog_keys:
            unknown += 1
            continue
        ret = _num(r.get(column_map["monthly_return_pct"]))
        if ret is None:
            continue
        point = {"track_key": key, "period": r[column_map["period"]].strip(), "monthly_return_pct": ret}
        for f in NUMERIC_FIELDS[1:]:
            if f in column_map:
                point[f] = _num(r.get(column_map[f]))
        points.append(point)
    return points, unknown


def sync_official(conn, source: dict, cache_dir: Path, catalog_keys: set[str], opener=urllib.request.urlopen) -> dict:
    """שליפה מותנית מהמקור הרשמי. לא זורקת חריגה למשתמש: מחזירה סטטוס."""
    if not source["automation_allowed"]:
        return {"status": "disabled", "message": "שליפה אוטומטית כבויה עבור מקור זה"}
    if not source.get("terms_reviewed_on"):
        return {"status": "blocked", "message": "נדרש לאשר את תנאי השימוש של המקור לפני שליפה אוטומטית"}
    url = source.get("url")
    column_map = source.get("column_map")
    if not url or not column_map:
        return {"status": "not_configured", "message": "לא הוגדר URL או מיפוי עמודות במקור"}

    prev = one(conn, "SELECT * FROM cache_entries WHERE cache_key=?", (source["source_id"],))
    if prev and datetime.fromisoformat(prev["fetched_at"]) > datetime.now(timezone.utc) - timedelta(
        seconds=source["min_seconds_between_requests"]
    ):
        return {"status": "rate_limited", "message": "הבקשה האחרונה הייתה לפני זמן קצר"}

    headers = {"User-Agent": "pension-portfolio-local/1.0"}
    if prev and prev.get("etag"):
        headers["If-None-Match"] = prev["etag"]
    if prev and prev.get("last_modified"):
        headers["If-Modified-Since"] = prev["last_modified"]

    try:
        with opener(urllib.request.Request(url, headers=headers), timeout=30) as resp:
            body = resp.read()
            etag, lm = resp.headers.get("ETag"), resp.headers.get("Last-Modified")
    except urllib.error.HTTPError as exc:
        if exc.code == 304 and prev:
            _touch(conn, source["source_id"], "fresh")
            return {"status": "not_modified", "message": "אין שינוי במקור"}
        return _fallback(conn, source, prev, f"שגיאת HTTP {exc.code}")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return _fallback(conn, source, prev, f"שגיאת רשת: {exc.__class__.__name__}")

    sha = hashlib.sha256(body).hexdigest()
    cache_dir.mkdir(parents=True, exist_ok=True)
    body_path = cache_dir / f"{sha}.csv"
    body_path.write_bytes(body)
    conn.execute(
        """INSERT INTO cache_entries (cache_key, source_id, url, etag, last_modified, fetched_at, sha256, body_path, status)
           VALUES (?,?,?,?,?,?,?,?,'fresh')
           ON CONFLICT(cache_key) DO UPDATE SET url=excluded.url, etag=excluded.etag,
             last_modified=excluded.last_modified, fetched_at=excluded.fetched_at,
             sha256=excluded.sha256, body_path=excluded.body_path, status='fresh'""",
        (source["source_id"], source["source_id"], url, etag, lm, _now(), sha, str(body_path)),
    )
    conn.commit()

    points, unknown = parse_official_csv(body.decode("utf-8-sig", errors="replace"), column_map, catalog_keys)
    written = upsert_points(conn, points, source["source_id"])
    return {"status": "ok", "written": written, "unknown_tracks": unknown}


def _touch(conn, cache_key: str, status: str) -> None:
    conn.execute("UPDATE cache_entries SET fetched_at=?, status=? WHERE cache_key=?", (_now(), status, cache_key))
    conn.commit()


def _fallback(conn, source: dict, prev: dict | None, reason: str) -> dict:
    if prev:
        conn.execute("UPDATE cache_entries SET status='stale' WHERE cache_key=?", (source["source_id"],))
        conn.commit()
        return {"status": "stale", "message": f"{reason}. מוצגים נתונים מהמטמון מ-{prev['fetched_at'][:10]}"}
    return {"status": "error", "message": f"{reason}. אין מטמון. אפשר לייבא ידנית"}


def freshness(conn) -> list[dict]:
    """סטטוס לכל מקור: תקופה אחרונה, סטטוס מטמון, מתי נשלף."""
    out = []
    for s in rows(conn, "SELECT * FROM sources"):
        last = one(
            conn,
            "SELECT MAX(period) AS p FROM market_points WHERE source_id=?",
            (s["source_id"],),
        )
        cache = one(conn, "SELECT status, fetched_at FROM cache_entries WHERE cache_key=?", (s["source_id"],))
        out.append(
            {
                "source_id": s["source_id"],
                "kind": s["kind"],
                "latest_period": last["p"] if last else None,
                "cache_status": cache["status"] if cache else None,
                "fetched_at": cache["fetched_at"] if cache else None,
                "automation_allowed": bool(s["automation_allowed"]),
                "terms_reviewed_on": s["terms_reviewed_on"],
            }
        )
    return out
