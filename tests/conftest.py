from pathlib import Path

import pytest

from safedata.schema import load_schema

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def schema():
    return load_schema(FIXTURES / "schema.yaml")


def make_row(id, **kw):
    row = {"id": str(id), "date": "2020-01-01", "site": "North", "category": "survey",
           "observer": "Maria", "value": "1.5", "verified": "true", "notes": ""}
    row.update(kw)
    return row
