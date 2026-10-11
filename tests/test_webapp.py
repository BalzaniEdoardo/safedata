import json
import shutil
import threading
import urllib.error
import urllib.request

import pytest
from conftest import FIXTURES, make_row

from safedata import dataset, store, webapp


@pytest.fixture
def folder(tmp_path):
    """A dataset outside git with three records."""
    (tmp_path / "safedata.toml").write_text('records = "data/records.csv"\nschema = "data/schema.yaml"\n')
    (tmp_path / "data").mkdir()
    shutil.copy(FIXTURES / "schema.yaml", tmp_path / "data" / "schema.yaml")
    ds = dataset.load(tmp_path)
    store.write_file(ds.records_path, [make_row(1), make_row(2), make_row(3)], ds.load_schema())
    return ds


def records(ds):
    return store.read_file(ds.records_path, ds.load_schema())


def test_state(folder):
    state = webapp.get_state(folder)
    assert [r["id"] for r in state["rows"]] == ["1", "2", "3"]
    assert state["conflicts"] is None
    assert state["uncommitted"] is None  # not a git repository


def test_save_writes_only_the_csv(folder):
    before = set(folder.root.rglob("*"))
    state = webapp.get_state(folder)
    res = webapp.save(folder, {
        "version": state["version"],
        "adds": [make_row("", observer="Luca", site="south")],
        "updates": {"1": {"value": ["1.5", "42"]}},
        "deletes": {"2": make_row(2)},
    })
    assert set(folder.root.rglob("*")) == before
    assert [(r["id"], r["value"], r["observer"], r["site"]) for r in records(folder)] == [
        ("1", "42", "Maria", "North"), ("3", "1.5", "Maria", "North"), ("4", "1.5", "Luca", "South")]
    assert "+ record 4: " in res["saved"][0]


def test_save_refuses_invalid_and_conflicting_edits(folder):
    state = webapp.get_state(folder)
    with pytest.raises(webapp.Refused) as e:
        webapp.save(folder, {"version": state["version"], "updates": {"1": {"site": ["North", "Moon"]}}})
    assert "'Moon' is not an allowed value" in e.value.problems[0]

    # the file changes on disk (e.g. after git pull) while the page still shows the old values
    rows = records(folder)
    rows[0]["value"] = "99"
    store.write_file(folder.records_path, rows, folder.load_schema())
    with pytest.raises(webapp.Refused) as e:
        webapp.save(folder, {"version": state["version"], "updates": {"1": {"value": ["1.5", "42"]}}})
    assert "record 1, value" in e.value.problems[0]
    # an edit to another record still applies on top of the new file
    webapp.save(folder, {"version": state["version"], "updates": {"3": {"notes": ["", "ok"]}}})
    assert [r["value"] for r in records(folder)] == ["99", "1.5", "1.5"]
    assert records(folder)[2]["notes"] == "ok"


def test_resolve_conflicts(folder):
    pairs = {"2": (make_row(2, value="7"), make_row(2, value="8")), "3": (make_row(3), None)}
    text = store.to_text_with_conflicts([make_row(1)], pairs, folder.load_schema())
    folder.records_path.write_text(text, encoding="utf-8")

    state = webapp.get_state(folder)
    assert [c["key"] for c in state["conflicts"]] == ["2", "3"]
    with pytest.raises(webapp.Refused):
        webapp.save(folder, {"version": state["version"], "updates": {"1": {"notes": ["", "x"]}}})
    with pytest.raises(webapp.Refused):
        webapp.resolve(folder, {"version": state["version"], "choices": {"2": "local"}})
    webapp.resolve(folder, {"version": state["version"], "choices": {"2": "incoming", "3": "incoming"}})
    assert [(r["id"], r["value"]) for r in records(folder)] == [("1", "1.5"), ("2", "8")]


def test_http_requires_token(folder):
    server, url = webapp.serve(folder)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base, token = url.split("/#")
    try:
        with urllib.request.urlopen(base + "/") as r:
            assert b"Records editor" in r.read()
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(base + "/api/state")
        assert e.value.code == 403
        req = urllib.request.Request(base + "/api/state", headers={"X-Token": token})
        with urllib.request.urlopen(req) as r:
            assert len(json.load(r)["rows"]) == 3
    finally:
        server.shutdown()
        server.server_close()


def test_check_uses_schema_rules(folder):
    res = webapp.check(folder, {"rows": {"7": make_row("", site="Moon", value="-1", date="2020-02-30")}})
    assert set(res["problems"]["7"]) == {"site", "value", "date"}
    assert webapp.check(folder, {"rows": {"7": make_row("")}})["problems"]["7"] == {}


def test_new_column_needs_only_a_schema_change(folder):
    """A column added to schema.yaml (and the CSV) is served and checked without code changes."""
    folder.schema_path.write_text(folder.schema_path.read_text() + (
        "\n  - name: depth\n    type: int\n    min: 0\n    max: 50\n"
        "\n  - name: weather\n    type: choice\n    choices: [dry, wet]\n"), encoding="utf-8")
    store.write_file(folder.records_path, [{**make_row(1), "depth": "3", "weather": "dry"}], folder.load_schema())

    cols = {c["name"]: c["input"] for c in webapp.get_state(folder)["schema"]["columns"]}
    assert cols["depth"] == {"kind": "text", "inputmode": "numeric", "sort": "number"}
    assert cols["weather"] == {"kind": "select", "options": ["dry", "wet"], "sort": "text"}
    problems = webapp.check(folder, {"rows": {"1": {**make_row(1), "depth": "99", "weather": "snow"}}})
    assert set(problems["problems"]["1"]) == {"depth", "weather"}


def test_save_refuses_a_duplicate_entry(folder):
    folder.schema_path.write_text(folder.schema_path.read_text().replace(
        "unique_entries: []", "unique_entries:\n  - [date, site, notes]"))
    state = webapp.get_state(folder)
    with pytest.raises(webapp.Refused) as e:
        webapp.save(folder, {"version": state["version"], "updates": {"1": {"notes": ["", "rain"]}},
                             "adds": [make_row("", notes="rain")]})
    assert "date, site, notes (2020-01-01, North, rain) is the same as on line" in e.value.problems[0]
    assert [r["notes"] for r in records(folder)] == ["", "", ""]  # nothing was saved
