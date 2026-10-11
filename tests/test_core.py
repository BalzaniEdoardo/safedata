import datetime as dt
import random

import pytest
from conftest import make_row

from safedata import store
from safedata.changeset import apply, diff
from safedata.merge import merge
from safedata.schema import KeyGroup, SchemaError, canon, load_schema, parse_schema, validate
from safedata.store import has_conflicts, parse_conflicted, to_text_with_conflicts


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
    assert "'Moon' is not an allowed value; choose one of: North, South, East, West" in text
    assert "'03/04/2020' is not a date; write dates as YYYY-MM-DD" in text
    assert "value: -2 is smaller than the smallest allowed value, 0" in text
    assert "observer: is empty, but this column is required" in text
    assert "1980-01-01 is earlier than the earliest allowed date, 1990-03-26" in text
    assert validate(schema.names, [make_row(1), make_row(2)], schema) == []


def test_validate_header(schema):
    assert "Missing columns: notes" in validate(schema.names[:-1], [], schema)[0]


def test_sort_key_groups(schema):
    assert schema.sort_key("12") == (KeyGroup.NUMBER, 12)
    assert schema.sort_key("A7") == (KeyGroup.TEXT, "A7")
    assert schema.sort_key("") == (KeyGroup.EMPTY, "")
    keys = ["10", "", "B", "9", "A", "-1", ""]
    assert sorted(keys, key=schema.sort_key) == ["-1", "9", "10", "A", "B", "", ""]


def write_schema(tmp_path, key_spec):
    path = tmp_path / "schema.yaml"
    path.write_text(f"key: id\nunique_entries: []\ncolumns:\n  - name: id\n{key_spec}  - name: note\n    type: string\n")
    return path


def test_key_is_always_required_and_unique(tmp_path):
    schema = load_schema(write_schema(tmp_path, "    type: int\n"))  # no required/unique in the file
    rows = [{"id": "1", "note": "a"}, {"id": "1", "note": "b"}, {"id": "", "note": "c"}]
    text = "\n".join(validate(schema.names, rows, schema))
    assert "id: 1 is already used on line 2" in text
    assert "id: is empty, but this column is required" in text


def test_schema_rules_all_reported_together():
    raw = {
        "key": "id",
        "unique_entries": [],
        "colums": [],  # misspelled top-level setting
        "columns": [
            {"name": "id", "type": "int"},
            {"name": "a"},                                              # no type
            {"name": "b", "type": "text"},                              # unknown type
            {"name": "c", "type": "string", "requird": True},           # misspelled setting
            {"name": "d", "type": "string", "required": "yes"},         # not a boolean
            {"name": "e", "type": "choice"},                            # no choices
            {"name": "f", "type": "choice", "choices": ["x", "x"]},     # repeated choice
            {"name": "g", "type": "int", "choices": ["x"]},             # choices on an int
            {"name": "h", "type": "string", "min": 1},                  # min on a string
            {"name": "i", "type": "int", "min": "abc"},                 # min not a number
            {"name": "j", "type": "float", "min": 5, "max": 1},         # min > max
            {"name": "k", "type": "date", "max": None},                 # empty max
            {"name": "l", "type": "string", "description": 3},          # description not text
            {"name": "id", "type": "int"},                              # name used twice
            {"type": "int"},                                            # no name
        ],
    }
    with pytest.raises(SchemaError) as e:
        parse_schema(raw)
    expected = [
        "unknown top-level setting 'colums'",
        "column 2 (a): `type` is required",
        "column 3 (b): unknown type 'text'",
        "column 4 (c): unknown setting 'requird'",
        "column 5 (d): `required` must be true or false, not 'yes'",
        "column 6 (e): type choice needs `choices`",
        "column 7 (f): `choices` lists x more than once",
        "column 8 (g): `choices` is only allowed for type choice",
        "column 9 (h): `min` is only allowed for types int, float, date",
        "column 10 (i): `min` 'abc' is not a whole number",
        "column 11 (j): `min` (5) is greater than `max` (1)",
        "column 12 (k): `max` is empty",
        "column 13 (l): `description` must be text",
        "column 14 (id): the name is already used by another column",
        "column 15: `name` is required",
    ]
    for text in expected:
        assert any(text in p for p in e.value.problems), text
    assert len(e.value.problems) == len(expected)


def test_schema_needs_key_and_columns():
    with pytest.raises(SchemaError) as e:
        parse_schema({})
    assert [p.split(":")[0] for p in e.value.problems] == ["`key` is required", "`columns` is required"]


PLACES = {
    "key": "id",
    "unique_entries": [["country", "city", "neighborhood"]],
    "columns": [{"name": "id", "type": "int"}, {"name": "country", "type": "string"},
                {"name": "city", "type": "string"}, {"name": "neighborhood", "type": "string"},
                {"name": "year", "type": "int"}],
}


def place(id, country="Italy", city="Rome", neighborhood="Trastevere", year="2024"):
    return {"id": str(id), "country": country, "city": city, "neighborhood": neighborhood, "year": year}


def test_unique_entries_reject_repeated_combinations():
    schema = parse_schema(PLACES)
    rows = [place(1), place(2, neighborhood="Monti"), place(3), place(4, city="Milan")]
    [error] = validate(schema.names, rows, schema)
    assert error == ("Line 4 (record 3): country, city, neighborhood (Italy, Rome, Trastevere) is the same "
                     "as on line 2 (record 1); together, these columns must differ between records")


def test_unique_entries_skip_records_with_an_empty_value():
    schema = parse_schema(PLACES)
    rows = [place(1, neighborhood=""), place(2, neighborhood=""), place(3)]
    assert validate(schema.names, rows, schema) == []


def test_unique_entries_empty_list_allows_duplicates():
    schema = parse_schema({**PLACES, "unique_entries": []})
    assert validate(schema.names, [place(1), place(2)], schema) == []


def test_unique_entries_setting_is_checked():
    with pytest.raises(SchemaError) as e:
        parse_schema({k: v for k, v in PLACES.items() if k != "unique_entries"})
    assert "`unique_entries` is required" in e.value.problems[0]

    with pytest.raises(SchemaError) as e:
        parse_schema({**PLACES, "unique_entries": None})  # `unique_entries:` with nothing after it
    assert "`unique_entries` must be a list" in e.value.problems[0]

    with pytest.raises(SchemaError) as e:
        parse_schema({**PLACES, "unique_entries": [
            "country",                      # not a list
            [],                             # empty group
            ["country", "town"],            # unknown column
            ["city", "city"],               # repeated column
            ["id", "year"],                 # contains the key
            ["city", "country"],            # same columns as ...
            ["country", "city"],            # ... this group
        ]})
    expected = [
        "group 1: must be a list of column names",
        "group 2: must be a list of column names",
        "group 3: town is not a column",
        "group 4: lists city more than once",
        "group 5: includes the key column 'id'",
        "group 7: has the same columns as an earlier group",
    ]
    for text in expected:
        assert any(text in p for p in e.value.problems), text
    assert len(e.value.problems) == len(expected)


def test_key_must_be_an_int_column(tmp_path):
    with pytest.raises(ValueError, match="must have type int, not 'string'"):
        load_schema(write_schema(tmp_path, "    type: string\n"))
    path = tmp_path / "other.yaml"
    path.write_text("key: number\ncolumns:\n  - name: id\n    type: int\n")
    with pytest.raises(ValueError, match="'number' is not one of the columns"):
        load_schema(path)


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
