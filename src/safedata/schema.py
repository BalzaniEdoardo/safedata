"""Table schema: column definitions, value normalization, and validation.

All values are handled as canonical strings, so the same data always produces
the same CSV text regardless of where it came from (CSV, Excel, a web form).
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field
from pathlib import Path

import yaml

TYPES = ("int", "float", "date", "bool", "choice", "string")
_TRUE = {"true", "yes", "y", "1"}
_FALSE = {"false", "no", "n", "0"}


@dataclass
class Column:
    name: str
    type: str = "string"
    required: bool = False
    unique: bool = False
    choices: list[str] = field(default_factory=list)
    min: str | None = None
    max: str | None = None
    description: str = ""


@dataclass
class Schema:
    key: str
    columns: list[Column]

    @property
    def names(self) -> list[str]:
        return [c.name for c in self.columns]

    def column(self, name: str) -> Column:
        for c in self.columns:
            if c.name == name:
                return c
        raise KeyError(name)

    @property
    def key_column(self) -> Column:
        return self.column(self.key)

    def sort_key(self, value: str):
        """Order records by key: numerically for int keys, blanks last."""
        if value == "":
            return (1, 0, "")
        if self.key_column.type == "int":
            try:
                return (0, int(value), "")
            except ValueError:
                pass
        return (0, math.inf, value)


def load_schema(path: str | Path) -> Schema:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    columns = []
    for spec in raw["columns"]:
        col = Column(
            name=str(spec["name"]),
            type=spec.get("type", "string"),
            required=bool(spec.get("required", False)),
            unique=bool(spec.get("unique", False)),
            choices=[str(c) for c in spec.get("choices", [])],
            description=spec.get("description", ""),
        )
        if col.type not in TYPES:
            raise ValueError(f"column {col.name!r}: unknown type {col.type!r}")
        col.min = canon(spec["min"], col) if "min" in spec else None
        col.max = canon(spec["max"], col) if "max" in spec else None
        columns.append(col)
    schema = Schema(key=raw["key"], columns=columns)
    schema.column(schema.key)  # the key must be one of the columns
    return schema


def canon(value, col: Column) -> str:
    """Convert a value (from CSV text, Excel, YAML...) to its canonical string.

    Values that can't be interpreted are returned as stripped text, so that
    validation can report them instead of losing them.
    """
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    if isinstance(value, str):
        value = value.strip()
        if value == "":
            return ""

    t = col.type
    try:
        if t == "int":
            if isinstance(value, bool):
                raise ValueError
            f = float(value)
            if f.is_integer():
                return str(int(f))
        elif t == "float":
            if isinstance(value, bool):
                raise ValueError
            f = float(value)
            if math.isfinite(f):
                return format(f, ".15g")
        elif t == "date":
            return _canon_date(value)
        elif t == "bool":
            if isinstance(value, bool):
                return "true" if value else "false"
            s = str(value).strip().lower()
            if s in _TRUE:
                return "true"
            if s in _FALSE:
                return "false"
        elif t == "choice":
            # Accept a choice typed in the wrong case, but store the official spelling.
            s = str(value).strip()
            for choice in col.choices:
                if s.lower() == choice.lower():
                    return choice
            return s
    except (ValueError, TypeError, OverflowError):
        pass
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat()
    return str(value).strip()


def _canon_date(value) -> str:
    if isinstance(value, dt.datetime):
        if value.time() != dt.time(0):
            raise ValueError
        return value.date().isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    s = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y/%m/%d"):
        try:
            parsed = dt.datetime.strptime(s, fmt)
        except ValueError:
            continue
        if parsed.time() == dt.time(0):
            return parsed.date().isoformat()
    raise ValueError


def is_valid_value(value: str, col: Column) -> str | None:
    """Return None if a canonical value is acceptable, else a sentence saying which rule
    it breaks, written for the person who typed the value."""
    if value == "":
        return "is empty, but this column is required" if col.required else None
    if "\n" in value or "\r" in value:
        return "contains a line break; values must fit on one line"
    t = col.type
    if t == "int":
        try:
            num = int(value)
        except ValueError:
            return f"{value!r} is not a whole number"
    elif t == "float":
        try:
            num = float(value)
        except ValueError:
            return f"{value!r} is not a number"
    elif t == "date":
        try:
            dt.date.fromisoformat(value)
        except ValueError:
            return f"{value!r} is not a date; write dates as YYYY-MM-DD, for example 2024-03-15"
        num = value
    elif t == "bool":
        if value not in ("true", "false"):
            return f"{value!r} is not true or false"
        return None
    elif t == "choice":
        if value not in col.choices:
            return f"{value!r} is not an allowed value; choose one of: {', '.join(col.choices)}"
        return None
    else:
        return None

    if col.min is not None and num < _typed(col.min, t):
        if t == "date":
            return f"{value} is earlier than the earliest allowed date, {col.min}"
        return f"{value} is smaller than the smallest allowed value, {col.min}"
    if col.max is not None and num > _typed(col.max, t):
        if t == "date":
            return f"{value} is later than the latest allowed date, {col.max}"
        return f"{value} is larger than the largest allowed value, {col.max}"
    return None


def input_spec(col: Column) -> dict:
    """How an editor should present and sort a column. Editors build their inputs
    from this, so a new column or type needs no change in the editor code."""
    sort = "number" if col.type in ("int", "float") else "text"  # ISO dates sort as text
    if col.type == "choice":
        return {"kind": "select", "options": col.choices, "sort": sort}
    if col.type == "bool":
        return {"kind": "select", "options": ["true", "false"], "sort": sort}
    if col.type == "date":
        return {"kind": "date", "min": col.min, "max": col.max, "sort": sort}
    if col.type in ("int", "float"):
        return {"kind": "text", "inputmode": "numeric" if col.type == "int" else "decimal", "sort": sort}
    return {"kind": "text", "sort": sort}


def check_value(value, col: Column) -> str | None:
    """Validate one raw value as an editor would submit it."""
    return is_valid_value(canon(value, col), col)


def _typed(value: str, t: str):
    return {"int": int, "float": float}.get(t, str)(value)


def validate(header: list[str], rows: list[dict[str, str]], schema: Schema) -> list[str]:
    """Check a table against the schema. Returns plain-language error messages."""
    errors = []
    if header != schema.names:
        missing = [n for n in schema.names if n not in header]
        extra = [n for n in header if n not in schema.names]
        if missing:
            errors.append(f"Missing columns: {', '.join(missing)}")
        if extra:
            errors.append(f"Unexpected columns: {', '.join(extra)}")
        if not missing and not extra:
            errors.append(f"Columns are out of order; expected: {', '.join(schema.names)}")
        return errors

    seen: dict[str, dict[str, int]] = {c.name: {} for c in schema.columns if c.unique}
    for line, row in enumerate(rows, start=2):
        where = f"Line {line} (record {row.get(schema.key) or '?'})"
        for col in schema.columns:
            value = row.get(col.name, "")
            if value != canon(value, col):
                errors.append(f"{where}, {col.name}: {value!r} is not in standard form")
                continue
            problem = is_valid_value(value, col)
            if problem:
                errors.append(f"{where}, {col.name}: {problem}")
            if col.unique and value:
                if value in seen[col.name]:
                    errors.append(
                        f"{where}, {col.name}: {value} is already used on line {seen[col.name][value]}"
                    )
                else:
                    seen[col.name][value] = line
    return errors
