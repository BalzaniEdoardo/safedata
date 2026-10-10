"""safedata: records in a git repository, with a validating editor and git add-ons."""

from __future__ import annotations

from pathlib import Path


def load(path: str | Path = "."):
    """Load the records of the dataset containing `path` as a typed pandas DataFrame."""
    import pandas as pd

    from . import dataset

    ds = dataset.find(path)
    schema = ds.load_schema()
    df = pd.read_csv(ds.records_path, dtype=str, keep_default_na=False)
    for col in schema.columns:
        s = df[col.name].replace("", None)
        if col.type == "int":
            df[col.name] = pd.to_numeric(s).astype("Int64")
        elif col.type == "float":
            df[col.name] = pd.to_numeric(s).astype("Float64")
        elif col.type == "date":
            df[col.name] = pd.to_datetime(s, format="%Y-%m-%d")
        elif col.type == "bool":
            df[col.name] = s.map({"true": True, "false": False}).astype("boolean")
        elif col.type == "choice":
            df[col.name] = pd.Categorical(s, categories=col.choices)
        else:
            df[col.name] = s.astype("string")
    return df
