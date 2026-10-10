"""safedata: records in a git repository, with a validating editor and git add-ons."""

from __future__ import annotations

from pathlib import Path


def load(repo: str | Path = "."):
    """Load the records as a typed pandas DataFrame (for Python-based analysis)."""
    import pandas as pd

    from . import gitops
    from .webapp import DATA_FILE, SCHEMA_FILE
    from .schema import load_schema

    root = gitops.repo_root(repo)
    schema = load_schema(root / SCHEMA_FILE)
    df = pd.read_csv(root / DATA_FILE, dtype=str, keep_default_na=False)
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
