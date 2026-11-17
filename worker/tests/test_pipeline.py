from __future__ import annotations

import base64
import io
import json
import urllib.error
from pathlib import Path

import pytest

from app import service
from app.db import connect
from app.pipeline import analytics
from app.pipeline.estimator import estimate
from app.pipeline.extract import ingest
from app.pipeline.mapper import match_track
from app.pipeline.market import sync_official
from app.redact import redact_text
from app.parsers import csv_export, kv_report, pick_parser
from app.service import ServiceError

WORKER = Path(__file__).resolve().parents[1]
FIX = WORKER.parent / "data" / "fixtures"
SAMPLES = FIX / "samples"


@pytest.fixture()
def conn(tmp_path):
    c = connect(tmp_path / "t.sqlite")
    service.load_sources(c, WORKER / "config" / "sources.json")
    service.seed_demo(c, FIX)
    yield c
    c.close()


def holding_id(conn, label):
    return next(h["holding_id"] for h in service.list_holdings(conn) if h["label"] == label)


# ---------- מחיקת מזהים ----------

def test_redaction_removes_id_account_and_name():
    text = "שם: נועה דמו\nמספר זהות: 012345678\nמספר חשבון: 987-654321\nיתרה: 1,000.00"
    clean, rep = redact_text(text)
    assert "012345678" not in clean
    assert "987-654321" not in clean
    assert "נועה" not in clean
    assert "1,000.00" in clean          # סכומים לא נמחקים
    assert rep.counts["id"] == 1 and rep.counts["account"] == 1 and rep.counts["name"] == 1


def test_redaction_catches_bare_nine_digits_and_separated_ids():
    clean, rep = redact_text("חלק א 123456789 וחלק ב 01.23.45.678")
    assert "123456789" not in clean and "01.23.45.678" not in clean
    assert rep.counts["id"] == 2


def test_redaction_keeps_normal_amounts():
    clean, rep = redact_text("הפקדה 2,100.50 ודמי ניהול 0.5%")
    assert clean == "הפקדה 2,100.50 ודמי ניהול 0.5%"
    assert rep.total == 0


# ---------- חילוץ ותבניות ----------

def test_kv_report_sample_parses_all_required_fields():
    text = (SAMPLES / "kv_report_sample.txt").read_text(encoding="utf-8")
    clean, _ = redact_text(text)
    res = kv_report.parse(clean)
    assert res.fields["as_of"] == "2026-06-30"
    assert res.fields["balance_ils"] == 281004.37
    assert res.fields["reported_track_name"].startswith("פנסיה דמו א'")
    assert res.fields["fee_accum_pct"] == 0.28
    assert res.confidence == 1.0


def test_csv_export_sample_parses():
    text = (SAMPLES / "csv_export_sample.csv").read_text(encoding="utf-8")
    res = csv_export.parse(text)
    assert res.fields["balance_ils"] == 131500.0
    assert res.fields["as_of"] == "2026-06-30"
    assert res.confidence == 1.0


def test_pick_parser_chooses_by_format():
    assert pick_parser((SAMPLES / "csv_export_sample.csv").read_text(encoding="utf-8")) is csv_export
    assert pick_parser((SAMPLES / "kv_report_sample.txt").read_text(encoding="utf-8")) is kv_report
    assert pick_parser("סתם טקסט בלי שום שדה") is None


def test_ingest_never_returns_identifiers():
    raw = (SAMPLES / "kv_report_sample.txt").read_bytes()
    result = ingest(raw, "report.txt")
    assert "012345678" not in result["clean_text"]
    assert "987-654321" not in result["clean_text"]
    assert result["redactions"]["id"] == 1
    assert len(result["source_sha256"]) == 64


def test_ingest_unknown_format_returns_warning_not_crash():
    result = ingest("מסמך אחר לגמרי".encode("utf-8"), "x.txt")
    assert result["parser"] is None
    assert result["warnings"]


# ---------- מיפוי מסלולים ----------

def test_mapper_exact_match_by_fund_and_track(conn):
    cat = service.catalog(conn)
    m = match_track("פנסיה דמו א' מסלול מניות לבני 50 ומטה", cat)
    assert m["track_key"] == "9101-02" and m["method"] == "exact"


def test_mapper_refuses_ambiguous_shared_track_name(conn):
    cat = service.catalog(conn)
    m = match_track("מסלול כללי לבני 50 ומטה", cat)
    assert m["track_key"] is None and m["method"] == "ambiguous"
    assert set(m["candidates"]) == {"9101-01", "9102-01"}


def test_mapper_unknown_name_needs_review(conn):
    m = match_track("משהו שלא קיים", service.catalog(conn))
    assert m["track_key"] is None and m["method"] in ("needs_review", "none")


# ---------- הצטרפות ואישור ----------

def test_draft_does_not_persist(conn):
    before = conn.execute("SELECT COUNT(*) FROM statements").fetchone()[0]
    hid = holding_id(conn, "פנסיה מהעבודה הנוכחית")
    service.draft_statement(conn, "r.txt", (SAMPLES / "kv_report_sample.txt").read_bytes())
    after = conn.execute("SELECT COUNT(*) FROM statements").fetchone()[0]
    assert before == after and hid


def test_confirm_requires_catalog_track_and_balance(conn):
    hid = holding_id(conn, "פנסיה מהעבודה הנוכחית")
    draft = service.draft_statement(conn, "r.csv", (SAMPLES / "csv_export_sample.csv").read_bytes())
    with pytest.raises(ServiceError):
        service.confirm_statement(conn, hid, {**draft, "mapping": {"track_key": None}}, {})
    with pytest.raises(ServiceError):
        service.confirm_statement(conn, hid, draft, {"balance_ils": None})


def test_confirm_then_transitions_are_recomputed(conn):
    hid = holding_id(conn, "גמל להשקעה")
    before = service.list_holdings(conn)
    before = next(h for h in before if h["holding_id"] == hid)
    assert [t["effective_on"] for t in before["transitions"]] == ["2026-06-30"]
    # דוח חדש שמראה מסלול אחר באותו תאריך מוחק ויוצר מחדש את המעברים
    draft = service.draft_statement(conn, "r.csv", (SAMPLES / "csv_export_sample.csv").read_bytes())
    service.confirm_statement(conn, hid, draft, {"as_of": "2026-09-30", "matched_track_key": "9201-02"})
    after = next(h for h in service.list_holdings(conn) if h["holding_id"] == hid)
    assert [t["effective_on"] for t in after["transitions"]] == ["2026-06-30"]


# ---------- ציר זמן ומעברים ----------

def test_transition_detected_with_evidence(conn):
    h = next(x for x in service.list_holdings(conn) if x["label"] == "פנסיה מהעבודה הנוכחית")
    assert len(h["transitions"]) == 1
    t = h["transitions"][0]
    assert t["effective_on"] == "2025-12-31"
    assert t["from_track"].endswith("מסלול כללי לבני 50 ומטה")
    assert t["to_track"].endswith("מסלול מניות לבני 50 ומטה")
    assert len(t["evidence"]) == 2


def test_unconfirmed_statement_never_enters_timeline(conn):
    # דוח שרק נותח (טיוטה) לא נכנס לציר הזמן ולא מופיע בו
    before = next(x for x in service.list_holdings(conn) if x["label"] == "פנסיה מהעבודה הנוכחית")["timeline"]
    service.draft_statement(conn, "r.txt", (SAMPLES / "kv_report_sample.txt").read_bytes())
    after = next(x for x in service.list_holdings(conn) if x["label"] == "פנסיה מהעבודה הנוכחית")["timeline"]
    assert before == after


# ---------- יתרה משוערכת ----------

def _stmt(as_of="2026-06-30", balance=100000.0, dep=0.0, fee_dep=0.0):
    return {"statement_id": "s", "as_of": as_of, "balance_ils": balance,
            "monthly_deposit_ils": dep, "fee_deposit_pct": fee_dep}


def test_estimate_compounding_matches_hand_calculation():
    # ללא הפקדות, שתי תשואות 10% ו--10%: 100,000 -> 110,000 -> 99,000
    series = [("2026-06", 0.0), ("2026-07", 10.0), ("2026-08", -10.0)]
    est = estimate(_stmt(), series)
    assert est["estimated_balance_ils"] == pytest.approx(99000.0, abs=0.01)
    assert est["data_through"] == "2026-08"


def test_estimate_deposits_are_net_of_fee():
    series = [("2026-06", 0.0), ("2026-07", 0.0)]
    est = estimate(_stmt(dep=1000.0, fee_dep=10.0), series)
    assert est["estimated_balance_ils"] == pytest.approx(100900.0, abs=0.01)


def test_estimate_range_contains_midpoint_and_states_assumptions():
    series = [("2026-06", 0.0)] + [(f"2026-{m:02d}", r) for m, r in zip(range(7, 11), [1.0, -2.0, 3.0, 0.5])]
    est = estimate(_stmt(dep=500), series)
    assert est["low_ils"] <= est["estimated_balance_ils"] <= est["high_ils"]
    assert est["method"] == "return_compounding_v1"
    assert any("ללא חודש חלקי" in a for a in est["assumptions"])


def test_estimate_without_newer_data_returns_base():
    est = estimate(_stmt(), [("2026-05", 1.0), ("2026-06", 2.0)])
    assert est["estimated_balance_ils"] == est["base_balance_ils"] == 100000.0
    assert est["low_ils"] == est["high_ils"]


# ---------- שוק: שליפה, מטמון וגבולות ----------

def test_official_sync_blocked_until_terms_reviewed(conn):
    cfg = {"source_id": "gemelnet_official", "automation_allowed": True, "terms_reviewed_on": None,
           "min_seconds_between_requests": 1, "url": "https://example.invalid/x.csv",
           "column_map": {"cma_fund_code": "a", "cma_track_code": "b", "period": "c", "monthly_return_pct": "d"}}
    out = sync_official(conn, cfg, Path("/tmp/none"), set(), opener=lambda *a, **k: pytest.fail("לא אמורה להיות בקשה"))
    assert out["status"] == "blocked"


def test_official_sync_not_configured_makes_no_request(conn):
    cfg = {"source_id": "gemelnet_official", "automation_allowed": True, "terms_reviewed_on": "2026-11-01",
           "min_seconds_between_requests": 1, "url": None, "column_map": None}
    out = sync_official(conn, cfg, Path("/tmp/none"), set(), opener=lambda *a, **k: pytest.fail("אין בקשה"))
    assert out["status"] == "not_configured"


def test_official_sync_request_contains_no_personal_data(conn, tmp_path):
    seen = {}

    class FakeResp(io.BytesIO):
        headers: dict = {}

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def opener(req, timeout=None):
        seen["url"] = req.full_url
        seen["headers"] = dict(req.header_items())
        body = "cma_fund_code,cma_track_code,period,monthly_return_pct\n9201,02,2026-10,1.1\n".encode()
        resp = FakeResp(body)
        resp.headers = {"ETag": '"v1"', "Last-Modified": "x"}
        return resp

    cfg = {"source_id": "gemelnet_official", "automation_allowed": True, "terms_reviewed_on": "2026-11-01",
           "min_seconds_between_requests": 1, "url": "https://example.invalid/returns.csv",
           "column_map": {"cma_fund_code": "cma_fund_code", "cma_track_code": "cma_track_code",
                          "period": "period", "monthly_return_pct": "monthly_return_pct"}}
    out = sync_official(conn, cfg, tmp_path / "raw", service.catalog_keys(conn), opener=opener)
    assert out["status"] == "ok" and out["written"] == 1
    blob = json.dumps(seen)
    for secret in ("012345678", "987-654321", "נועה", "281004"):
        assert secret not in blob


def test_official_sync_falls_back_to_stale_cache(conn, tmp_path):
    cfg = {"source_id": "gemelnet_official", "automation_allowed": True, "terms_reviewed_on": "2026-11-01",
           "min_seconds_between_requests": 0, "url": "https://example.invalid/x.csv",
           "column_map": {"cma_fund_code": "a", "cma_track_code": "b", "period": "c", "monthly_return_pct": "d"}}
    conn.execute(
        "INSERT INTO cache_entries (cache_key, source_id, url, fetched_at, sha256, body_path, status) "
        "VALUES ('gemelnet_official','gemelnet_official','u','2026-10-01T00:00:00+00:00','h','p','fresh')"
    )
    conn.commit()

    def failing(req, timeout=None):
        raise urllib.error.URLError("network down")

    out = sync_official(conn, cfg, tmp_path, set(), opener=failing)
    assert out["status"] == "stale"
    row = conn.execute("SELECT status FROM cache_entries WHERE cache_key='gemelnet_official'").fetchone()
    assert row["status"] == "stale"


def test_manual_import_rejects_unknown_track_and_bad_period(conn):
    csv_text = (FIX / "samples" / "market_import_sample.csv").read_text(encoding="utf-8")
    out = service.manual_import_csv(conn, csv_text)
    assert out["written"] == 1
    reasons = " ".join(s["reason"] for s in out["skipped"])
    assert "track_key" in reasons


# ---------- ניתוח ----------

def test_compound_and_annualize():
    assert analytics.compound([10.0, -10.0]) == -1.0
    assert analytics.annualize(None, 12) is None


def test_allocation_weights_sum_to_full_mix():
    mix = {"israel_equity_pct": 50, "foreign_equity_pct": 50, "bonds_pct": 0, "fx_pct": 0, "other_pct": 0}
    alloc = analytics.allocation([
        {"label": "a", "weight_ils": 300, "asset_mix": mix},
        {"label": "b", "weight_ils": 100, "asset_mix": {"bonds_pct": 100}},
    ])
    total = sum(c["pct"] for c in alloc["categories"])
    assert total == pytest.approx(100.0, abs=0.05)
    bonds = next(c for c in alloc["categories"] if c["key"] == "bonds_pct")["pct"]
    assert bonds == pytest.approx(25.0)


def test_benchmark_ranks_own_track(conn):
    hid = holding_id(conn, "פנסיה מהעבודה הנוכחית")
    b = service.benchmark(conn, hid)
    assert b["summary"]["peer_count"] >= 2
    own = next(r for r in b["rows"] if r["is_own"])
    assert own["track_key"] == "9101-02"
    vals = [r["return_12m_pct"] for r in b["rows"] if r["return_12m_pct"] is not None]
    assert vals == sorted(vals, reverse=True)


def test_whatif_higher_fee_lowers_alternative(conn):
    hid = holding_id(conn, "גמל להשקעה")
    base = service.whatif(conn, hid, "9202-01", 36, 10, 0.0, 800)
    costly = service.whatif(conn, hid, "9202-01", 36, 10, 1.0, 800)
    assert costly["difference_at_horizon_ils"] < base["difference_at_horizon_ils"]
    assert len(base["current"]) == 11


def test_whatif_rejects_out_of_range(conn):
    hid = holding_id(conn, "גמל להשקעה")
    with pytest.raises(ServiceError):
        service.whatif(conn, hid, "9202-01", 0, 10, 0.0, None)


def test_health_score_explains_penalties():
    out = analytics.health_score(weighted_fee_accum=0.6, peer_median_fee=0.2, sharpe=0.3,
                                 top_weight_pct=70, unknown_tracks=0)
    assert out["score"] < 100
    assert any("דמי ניהול" in r for r in out["reasons"])


def test_dashboard_shape_and_privacy(conn):
    d = service.dashboard(conn)
    assert d["totals"]["estimated_low_ils"] <= d["totals"]["estimated_ils"] <= d["totals"]["estimated_high_ils"]
    assert d["allocation"]["categories"]
    blob = json.dumps(d, ensure_ascii=False)
    assert "ת.ז" not in blob and "מספר חשבון" not in blob


def test_dashboard_rejects_unknown_product_type(conn):
    with pytest.raises(ServiceError):
        service.dashboard(conn, "crypto")


# ---------- שכבת HTTP ----------

def test_routes_return_json_and_404(conn, monkeypatch):
    from app import server

    monkeypatch.setattr(server.Ctx, "conn", conn)
    monkeypatch.setattr(server.Ctx, "sources", service.load_sources(conn, WORKER / "config" / "sources.json"))
    status, body = server.route("GET", "/api/dashboard", {"product_type": ["pension"]}, lambda: {})
    assert status == 200 and body["product_type"] == "pension"
    status, _ = server.route("GET", "/api/nope", {}, lambda: {})
    assert status == 404


def test_draft_endpoint_accepts_base64_and_returns_clean_text(conn, monkeypatch):
    from app import server

    monkeypatch.setattr(server.Ctx, "conn", conn)
    raw = (SAMPLES / "kv_report_sample.txt").read_bytes()
    hid = holding_id(conn, "פנסיה מהעבודה הנוכחית")
    status, body = server.route(
        "POST", f"/api/holdings/{hid}/draft", {},
        lambda: {"filename": "r.txt", "content_base64": base64.b64encode(raw).decode()},
    )
    assert status == 200
    assert "012345678" not in body["clean_text"]
