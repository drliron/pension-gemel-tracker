"""חוזה הנתונים: השורות שבמסד (אחרי seed) חייבות לעמוד ב-schema/pension_portfolio.schema.json."""
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from app import service
from app.db import connect, rows

WORKER = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((WORKER / "schema" / "pension_portfolio.schema.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def seeded(tmp_path_factory):
    c = connect(tmp_path_factory.mktemp("db") / "t.sqlite")
    service.load_sources(c, WORKER / "config" / "sources.json")
    service.seed_demo(c, WORKER.parent / "data" / "fixtures")
    yield c
    c.close()


def _validate(instances, def_name):
    v = Draft202012Validator({"$defs": SCHEMA["$defs"], **SCHEMA["$defs"][def_name]},
                             format_checker=Draft202012Validator.FORMAT_CHECKER)
    errors = []
    for inst in instances:
        errors += [f"{def_name}: {e.message}" for e in v.iter_errors(inst)]
    return errors


def test_fund_tracks_match_schema(seeded):
    data = rows(seeded, "SELECT * FROM fund_tracks")
    for d in data:
        d["aliases"] = d.pop("aliases", [])
        d["is_fixture"] = bool(d["is_fixture"])
    assert _validate(data, "FundTrack") == []


def test_holdings_match_schema(seeded):
    data = rows(seeded, "SELECT * FROM holdings")
    assert _validate(data, "Holding") == []


def test_statements_match_schema(seeded):
    data = rows(seeded, "SELECT * FROM statements")
    for d in data:
        d["user_confirmed"] = bool(d["user_confirmed"])
        d.pop("created_at", None)
    errors = _validate(data, "Statement")
    assert errors == [], errors[:5]


def test_market_points_match_schema(seeded):
    data = rows(seeded, "SELECT * FROM market_points LIMIT 500")
    assert _validate(data, "MarketPoint") == []


def test_transitions_match_schema(seeded):
    data = rows(seeded, "SELECT * FROM transitions")
    assert data, "הדמו אמור לכלול מעברי מסלול"
    for d in data:
        d["approximate"] = True
        d["evidence_statement_ids"] = d.pop("evidence")
    assert _validate(data, "Transition") == []
