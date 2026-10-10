"""Locating a dataset: the folder that holds the records, the schema and a safedata.toml.

safedata.toml marks the dataset root and says where the two files are, relative
to it:

    records = "data/records.csv"
    schema = "data/schema.yaml"

Commands find the dataset by walking up from the current folder until they
meet a safedata.toml, the way git finds .git.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from .schema import Schema, load_schema

MARKER = "safedata.toml"


class DatasetError(Exception):
    """A dataset folder was found, but it is incomplete or cannot be read."""


class DatasetNotFound(DatasetError):
    """No safedata.toml in the folder or any folder above it."""


@dataclass(frozen=True)
class Dataset:
    root: Path
    records: str  # path of the records file, relative to root, with forward slashes
    schema: str   # path of the schema file, relative to root

    @property
    def records_path(self) -> Path:
        return self.root / self.records

    @property
    def schema_path(self) -> Path:
        return self.root / self.schema

    def load_schema(self) -> Schema:
        if not self.schema_path.is_file():
            raise DatasetError(f"the schema file {self.schema_path} (set in {MARKER}) does not exist")
        return load_schema(self.schema_path)


def load(root: str | Path) -> Dataset:
    """Read the safedata.toml in `root`."""
    root = Path(root).resolve()
    try:
        with open(root / MARKER, "rb") as f:
            config = tomllib.load(f)
    except FileNotFoundError:
        raise DatasetNotFound(f"{root} has no {MARKER}") from None
    except tomllib.TOMLDecodeError as e:
        raise DatasetNotFound(f"{root / MARKER} cannot be read: {e}") from None
    missing = [k for k in ("records", "schema") if not isinstance(config.get(k), str)]
    if missing:
        raise DatasetNotFound(f"{root / MARKER} does not set: {', '.join(missing)}")
    return Dataset(root, config["records"], config["schema"])


def find(start: str | Path = ".") -> Dataset:
    """The dataset containing `start`: the nearest folder upwards with a safedata.toml."""
    start = Path(start).resolve()
    for folder in (start, *start.parents):
        if (folder / MARKER).is_file():
            return load(folder)
    raise DatasetNotFound(f"no {MARKER} found in {start} or any folder above it")
