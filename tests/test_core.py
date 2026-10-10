import datetime as dt
import random

from conftest import make_row

from safedata import store
from safedata.changeset import apply, diff
from safedata.merge import merge
from safedata.store import has_conflicts, parse_conflicted, to_text_with_conflicts
from safedata.schema import canon, validate


# ---------------------------------------------------------------- schema

def test_canon_normalizes_values(schema):
    c = schema.column
    assert canon(" 5.0 ", c("id")) == "5"
    assert canon(3.50, c("value")) == "3.5"
    assert canon("2.10", c("value")) == "2.1"
    assert canon(dt.datetime(2020, 3, 4), c("date")) == "2020-03-04"
    assert canon("2020-03-04 00:00:00", c("date")) == "2020-03-04"
    assert canon("YES", c("verified")) == "true"
    assert canon(False, c("verified")) == "false"
    assert canon("north", c("site")) == "North"
    assert canon(None, c("notes")) == ""
    assert canon("03/04/2020", c("date")) == "03/04/2020"  # ambiguous: left for validation


def test_validate_reports_problems(schema):
    rows = [
        make_row(1),
        make_row(1, site="Moon"),                 # duplicate id, bad choice
        make_row(3, date="03/04/2020"),           # bad date
        make_row(4, value="-2"),                  # below minimum
        make_row(5, observer=""),                 # required
        make_row(6, date="1980-01-01"),           # before minimum date
    ]
    errors = validate(schema.names, rows, schema)
    text = "\n".join(errors)
    assert "already used on line 2" in text
    assert "'Moon' is not one of" in text
    assert "not a date" in text
    assert "below the minimum" in text
    assert "observer: is required" in text
    assert "1980-01-01 is below the minimum" in text
    assert validate(schema.names, [make_row(1), make_row(2)], schema) == []


def test_validate_header(schema):
    assert "Missing columns: notes" in validate(schema.names[:-1], [], schema)[0]


# ---------------------------------------------------------------- store

def test_normalization_is_deterministic(schema):
    rows = [make_row(i, value=f"{i}.50") for i in range(1, 30)]
    reference = store.to_text(rows, schema)
    random.seed(0)
    random.shuffle(rows)
    shuffled = store.to_text(rows, schema)
    assert shuffled == reference
    assert store.normalize_text(reference, schema) == reference
    # as saved by Excel: byte-order mark and CRLF line endings
    messy = "﻿" + reference.replace("\n", "\r\n")
    assert store.normalize_text(messy, schema) == reference
    lines = reference.splitlines()
    assert lines[1].startswith("1,") and lines[10].startswith("10,")  # sorted as numbers: 10 after 9


def test_normalize_passes_through_garbage(schema):
    assert store.normalize_text("not,a,records\nfile\n", schema) == "not,a,records\nfile\n"


# ---------------------------------------------------------------- changeset

def test_diff_and_apply_roundtrip(schema):
    base = [make_row(1), make_row(2), make_row(3)]
    new = [make_row(1, value="9"), make_row(3), make_row("", observer="Luca")]
    cs = diff(base, new, schema)
    assert cs.updates == {"1": {"value": ("1.5", "9")}}
    assert list(cs.deletes) == ["2"]
    assert len(cs.adds) == 1
    result = apply(base, cs, schema)
    assert not result.conflicts
    assert [r["id"] for r in result.rows] == ["1", "3", "4"]
    assert result.rows[2]["observer"] == "Luca"


def test_missing_rows_kept_for_edit_sheets(schema):
    cs = diff([make_row(1), make_row(2)], [make_row(1)], schema, missing_means_delete=False)
    assert cs.is_empty()


# ---------------------------------------------------------------- merge

BASE = [make_row(1), make_row(2), make_row(3)]


def test_merge_disjoint_records(schema):
    ours = [make_row(1, value="10"), make_row(2), make_row(3)]
    theirs = [make_row(1), make_row(2), make_row(3, notes="checked")]
    r = merge(BASE, ours, theirs, schema)
    assert not r.conflicts
    assert r.rows[0]["value"] == "10" and r.rows[2]["notes"] == "checked"


def test_merge_same_record_different_fields(schema):
    ours = [make_row(1, value="10"), make_row(2), make_row(3)]
    theirs = [make_row(1, notes="checked"), make_row(2), make_row(3)]
    r = merge(BASE, ours, theirs, schema)
    assert not r.conflicts
    assert r.rows[0]["value"] == "10" and r.rows[0]["notes"] == "checked"


def test_merge_same_field_conflicts(schema):
    ours = [make_row(1, value="10", notes="a"), make_row(2), make_row(3)]
    theirs = [make_row(1, value="20", observer="Luca"), make_row(2), make_row(3)]
    r = merge(BASE, ours, theirs, schema)
    assert list(r.conflicts) == ["1"]
    local, incoming = r.conflicts["1"]
    # both versions carry the fields that merged cleanly; they differ only in `value`
    assert local == make_row(1, value="10", notes="a", observer="Luca")
    assert incoming == make_row(1, value="20", notes="a", observer="Luca")


def test_merge_same_change_on_both_sides(schema):
    ours = [make_row(1, value="10"), make_row(2), make_row(3)]
    r = merge(BASE, ours, ours, schema)
    assert not r.conflicts and r.rows == store.canonical_rows(ours, schema)


def test_merge_both_add_same_new_id_renumbers(schema):
    ours = BASE + [make_row(4, observer="Ana")]
    theirs = BASE + [make_row(4, observer="Tom")]
    r = merge(BASE, ours, theirs, schema)
    assert not r.conflicts
    assert [(x["id"], x["observer"]) for x in r.rows[3:]] == [("4", "Ana"), ("5", "Tom")]
    assert "renumbered" in r.notes[0]


def test_merge_delete_vs_edit_conflicts(schema):
    ours = [make_row(1), make_row(3)]                       # deleted 2
    theirs = [make_row(1), make_row(2, value="7"), make_row(3)]  # edited 2
    r = merge(BASE, ours, theirs, schema)
    assert r.conflicts == {"2": (None, make_row(2, value="7"))}

    r = merge(BASE, theirs, ours, schema)  # the other way round
    assert r.conflicts == {"2": (make_row(2, value="7"), None)}


def test_merge_delete_on_both_sides(schema):
    ours = [make_row(1), make_row(3)]
    r = merge(BASE, ours, ours, schema)
    assert not r.conflicts and [x["id"] for x in r.rows] == ["1", "3"]


# ---------------------------------------------------------------- conflict markers

def test_conflict_markers_roundtrip(schema):
    rows = [make_row(1), make_row(3)]
    pairs = {"2": (make_row(2, value="7"), make_row(2, value="8")), "4": (None, make_row(4))}
    text = to_text_with_conflicts(rows, pairs, schema)
    lines = text.splitlines()
    assert lines[2:7] == ["<<<<<<< local", store.to_text([make_row(2, value="7")], schema).splitlines()[1],
                          "=======", store.to_text([make_row(2, value="8")], schema).splitlines()[1],
                          ">>>>>>> incoming"]
    assert has_conflicts(text)
    assert store.normalize_text(text, schema) == text  # the clean filter leaves conflicts alone
    clean, parsed = parse_conflicted(text, schema)
    assert [r["id"] for r in clean] == ["1", "3"]
    assert parsed == pairs


def test_parse_line_based_git_conflict(schema):
    """Conflicts written by plain git (no merge driver) can span several records."""
    header = store.to_text([], schema)
    line = lambda **kw: store.to_text([make_row(**kw)], schema).splitlines()[1]
    text = (header + line(id=1) + "\n<<<<<<< HEAD\n" + line(id=2, value="7") + "\n" + line(id=3) + "\n"
            "||||||| base\n" + line(id=2) + "\n=======\n" + line(id=2, value="8") + "\n>>>>>>> other\n")
    clean, pairs = parse_conflicted(text, schema)
    assert [r["id"] for r in clean] == ["1"]
    assert pairs == {"2": (make_row(2, value="7"), make_row(2, value="8")), "3": (make_row(3), None)}
