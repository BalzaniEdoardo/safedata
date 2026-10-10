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
