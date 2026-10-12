import shutil

import pytest
from conftest import FIXTURES, make_row

from safedata import cli, dataset, store


@pytest.fixture
def ds(tmp_path, monkeypatch):
    """A dataset folder (not a git repository), used as the current folder."""
    (tmp_path / "safedata.toml").write_text('records = "data/records.csv"\nschema = "data/schema.yaml"\n')
    (tmp_path / "data").mkdir()
    shutil.copy(FIXTURES / "schema.yaml", tmp_path / "data" / "schema.yaml")
    monkeypatch.chdir(tmp_path)
    return dataset.load(tmp_path)


def write(path, rows, ds):
    store.write_file(path, rows, ds.load_schema())
    return str(path)


def test_merge_driver_explains_conflicts(ds, tmp_path, capsys):
    base = write(tmp_path / "base.csv", [make_row(1), make_row(2)], ds)
    ours = write(tmp_path / "ours.csv", [make_row(1, value="7"), make_row(2, notes="a")], ds)
    theirs = write(tmp_path / "theirs.csv", [make_row(1, value="8"), make_row(2, observer="Luca")], ds)

    assert cli.main(["merge-driver", base, ours, theirs, "7", "data/records.csv"]) == 1
    err = capsys.readouterr().err
    assert "record 1 in data/records.csv changed differently on both sides" in err
    assert f"in the dataset folder {ds.root}" in err
    assert "git add data/records.csv" in err and "git merge --abort" in err
    # record 2 merged cleanly; record 1 is left as a conflict block
    clean, pairs = store.parse_conflicted(open(ours).read(), ds.load_schema())
    assert clean == [make_row(2, notes="a", observer="Luca")]
    assert pairs == {"1": (make_row(1, value="7"), make_row(1, value="8"))}


def test_validate_refuses_conflicted_file(ds, capsys):
    pairs = {"2": (make_row(2, value="7"), make_row(2, value="8"))}
    ds.records_path.write_text(store.to_text_with_conflicts([make_row(1)], pairs, ds.load_schema()))
    assert cli.main(["validate"]) == 1
    err = capsys.readouterr().err
    assert "still contains merge conflicts (record 2)" in err
    assert "git add data/records.csv" in err


def test_outside_a_dataset(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert cli.main(["validate"]) == 1
    assert "not inside a dataset folder" in capsys.readouterr().err


def test_pre_commit_check_passes_outside_a_dataset(tmp_path, monkeypatch, capsys):
    """A hook left in a repository that is no longer a dataset must not block commits."""
    monkeypatch.chdir(tmp_path)
    assert cli.main(["validate", "--staged"]) == 0
    assert capsys.readouterr().err == ""


def test_powerquery_writes_the_path_into_the_query(ds, capsys):
    assert cli.main(["powerquery"]) == 0
    query = capsys.readouterr().out
    assert query.startswith("let\n")  # only the query: can be redirected to a file and pasted
    assert f'File.Contents("{ds.records_path}")' in query
    assert "Encoding=65001, QuoteStyle=QuoteStyle.Csv" in query
    assert '{"date", type date}' in query and '{"verified", type logical}' in query
    assert "DataPath" not in query


def test_invalid_schema_problems_are_listed(ds, capsys):
    write(ds.records_path, [make_row(1)], ds)
    ds.schema_path.write_text(ds.schema_path.read_text().replace("type: int", "type: string", 1))
    assert cli.main(["validate"]) == 1
    err = capsys.readouterr().err
    assert "is not valid:\n  - the key column 'id' must have type int" in err and "Traceback" not in err


def test_missing_files(ds, capsys):
    assert cli.main(["validate"]) == 1
    assert "the records file" in capsys.readouterr().err

    write(ds.records_path, [make_row(1)], ds)
    ds.schema_path.unlink()
    assert cli.main(["validate"]) == 1
    assert "the schema file" in capsys.readouterr().err


def test_merge_driver_stops_when_the_combined_records_repeat(ds, tmp_path, capsys):
    """Both sides add the same entry under different ids: each side is valid, the merge is not."""
    ds.schema_path.write_text(ds.schema_path.read_text().replace(
        "unique_entries: []", "unique_entries:\n  - [date, site]"))
    base = write(tmp_path / "base.csv", [make_row(1)], ds)
    ours = write(tmp_path / "ours.csv", [make_row(1), make_row(2, date="2021-05-06")], ds)
    theirs = write(tmp_path / "theirs.csv",
                   [make_row(1), make_row(2, date="2022-01-01"), make_row(3, date="2021-05-06", observer="Luca")], ds)

    assert cli.main(["merge-driver", base, ours, theirs, "7", "data/records.csv"]) == 1
    err = capsys.readouterr().err
    assert "were combined, but together they break the schema" in err
    assert "date, site (2021-05-06, North) is the same as on line" in err
    assert "fix the records listed above with `safedata edit`" in err and "git add data/records.csv" in err
    # the combined records are written, without conflict markers, ready to be fixed
    merged = store.read_file(ours, ds.load_schema())
    assert [(r["id"], r["date"]) for r in merged] == [("1", "2020-01-01"), ("2", "2021-05-06"),
                                                      ("3", "2022-01-01"), ("4", "2021-05-06")]


def test_audit_duplicates_reports_and_exits_0(ds, capsys):
    ds.schema_path.write_text(ds.schema_path.read_text().replace(
        "unique_entries: []", "unique_entries:\n  - [date, site, notes]"))
    write(ds.records_path, [make_row(1, notes="flooded road"), make_row(2, notes="Flooded  road"),
                            make_row(3, notes="dry")], ds)
    assert cli.main(["audit-duplicates"]) == 0
    out = capsys.readouterr().out
    assert "1 possible duplicate(s) among 3 records" in out
    assert "records 1 and 2: date, site, notes" in out and "100% similar" in out


def test_audit_duplicates_nothing_to_compare_and_bad_threshold(ds, capsys):
    write(ds.records_path, [make_row(1)], ds)
    assert cli.main(["audit-duplicates"]) == 0  # unique_entries: [] in the fixture
    assert "Nothing to compare" in capsys.readouterr().out
    assert cli.main(["audit-duplicates", "--threshold", "85"]) == 1
    assert "--threshold must be between 0 and 1" in capsys.readouterr().err
