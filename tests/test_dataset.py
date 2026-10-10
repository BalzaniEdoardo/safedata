import pytest

from safedata import dataset


def make_dataset(folder, text='records = "data/records.csv"\nschema = "data/schema.yaml"\n'):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "safedata.toml").write_text(text)


def test_find_walks_up_to_the_marker(tmp_path):
    make_dataset(tmp_path / "records")
    inner = tmp_path / "records" / "data" / "deeper"
    inner.mkdir(parents=True)
    ds = dataset.find(inner)
    assert ds.root == (tmp_path / "records").resolve()
    assert ds.records_path == ds.root / "data" / "records.csv"
    assert ds.schema_path == ds.root / "data" / "schema.yaml"


def test_find_without_marker(tmp_path):
    with pytest.raises(dataset.DatasetNotFound, match="no safedata.toml"):
        dataset.find(tmp_path)


def test_marker_must_set_both_paths(tmp_path):
    make_dataset(tmp_path, 'records = "data/records.csv"\n')
    with pytest.raises(dataset.DatasetNotFound, match="does not set: schema"):
        dataset.load(tmp_path)


def test_unreadable_marker(tmp_path):
    make_dataset(tmp_path, "records = \n")
    with pytest.raises(dataset.DatasetNotFound, match="cannot be read"):
        dataset.load(tmp_path)
