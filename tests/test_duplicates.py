from safedata import duplicates
from safedata.schema import parse_schema

SCHEMA = parse_schema({
    "key": "id",
    "unique_entries": [["country", "city", "neighborhood", "year"]],
    "columns": [{"name": "id", "type": "int"}, {"name": "country", "type": "choice", "choices": ["Italy", "Spain"]},
                {"name": "city", "type": "string"}, {"name": "neighborhood", "type": "string"},
                {"name": "year", "type": "int"}],
})


def place(id, country="Italy", city="Rome", neighborhood="Trastevere", year="2024"):
    return {"id": str(id), "country": country, "city": city, "neighborhood": neighborhood, "year": year}


def keys(found):
    return [(d.first["id"], d.second["id"]) for d in found]


def test_misspelling_is_reported():
    found = duplicates.find([place(1), place(2, neighborhood="Trastevre"), place(3, neighborhood="Monti")], SCHEMA)
    assert keys(found) == [("1", "2")]
    assert found[0].describe(SCHEMA).startswith(
        "records 1 and 2: country, city, neighborhood, year (Italy, Rome, Trastevere, 2024 / Italy, Rome, Trastevre, 2024)")


def test_case_and_spacing_differences_are_100_percent_similar():
    [d] = duplicates.find([place(1), place(2, city="rome", neighborhood=" Trastevere  ")], SCHEMA)
    assert d.similarity == 1.0


def test_non_text_columns_must_match_exactly():
    rows = [place(1), place(2, neighborhood="Trastevre", year="2025"), place(3, neighborhood="Trastevre", country="Spain")]
    assert duplicates.find(rows, SCHEMA) == []


def test_records_with_an_empty_value_are_skipped():
    assert duplicates.find([place(1, neighborhood=""), place(2, neighborhood="")], SCHEMA) == []


def test_only_pairs_involving_given_records():
    rows = [place(1), place(2, neighborhood="Trastevre"), place(3, neighborhood="Trastever")]
    assert set(keys(duplicates.find(rows, SCHEMA))) == {("1", "2"), ("1", "3"), ("2", "3")}
    assert set(keys(duplicates.find(rows, SCHEMA, only={"3"}))) == {("1", "3"), ("2", "3")}


def test_groups_without_text_columns_and_empty_unique_entries_report_nothing():
    no_text = parse_schema({"key": "id", "unique_entries": [["year"]],
                            "columns": [{"name": "id", "type": "int"}, {"name": "year", "type": "int"}]})
    assert duplicates.find([{"id": "1", "year": "2024"}, {"id": "2", "year": "2024"}], no_text) == []
    none = parse_schema({"key": "id", "unique_entries": [], "columns": [{"name": "id", "type": "int"}]})
    assert duplicates.find([{"id": "1"}, {"id": "2"}], none) == []
