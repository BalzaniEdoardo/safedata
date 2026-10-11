"""Table schema: column definitions, value normalization, and validation.

All values are handled as canonical strings, so the same data always produces
the same CSV text regardless of where it came from (CSV, Excel, a web form).
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path

import yaml

TYPES = ("int", "float", "date", "bool", "choice", "string")
_TRUE = {"true", "yes", "y", "1"}
_FALSE = {"false", "no", "n", "0"}


@dataclass
class Column:
    name: str
    type: str
    required: bool = False
    unique: bool = False
    choices: list[str] = field(default_factory=list)
    min: str | None = None
    max: str | None = None
    description: str = ""


class KeyGroup(IntEnum):
    """Groups that records are sorted in, by the kind of key they have."""
    NUMBER = 0  # a whole number: every key in a valid file
    TEXT = 1    # anything else; only in a file that fails validation
    EMPTY = 2   # no key yet: a new record before it is numbered


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

    def sort_key(self, value: str) -> tuple[KeyGroup, int | str]:
        """Order records by key: numbers first and numerically, then other text, then empty keys.

        Values are compared only within a group, where they have the same type, so
        sorting works (and validation can report the problem) even in an invalid file.
        """
        if value == "":
            return (KeyGroup.EMPTY, "")
        try:
            return (KeyGroup.NUMBER, int(value))
        except ValueError:
            return (KeyGroup.TEXT, value)


class SchemaError(ValueError):
    """The schema file breaks one or more rules; `problems` lists them all."""

    def __init__(self, problems: list[str]):
        super().__init__("\n".join(problems))
        self.problems = problems


SETTINGS = ("name", "type", "required", "unique", "choices", "min", "max", "description")
_LIMITED_TYPES = ("int", "float", "date")  # the types that can have min and max


def load_schema(path: str | Path) -> Schema:
    """Read a schema file, checking every rule. Raises SchemaError listing all problems."""
    try:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise SchemaError([f"the file is not valid YAML: {e}"]) from None
    return parse_schema(raw)


def parse_schema(raw) -> Schema:
    problems: list[str] = []
    if not isinstance(raw, dict):
        raise SchemaError(["the file must contain the settings `key` and `columns`"])
    for setting in raw.keys() - {"key", "columns"}:
        problems.append(f"unknown top-level setting {setting!r}; allowed: key, columns")
    key_name = raw.get("key")
    if not isinstance(key_name, str) or not key_name:
        problems.append("`key` is required: the name of the column that identifies each record")
    specs = raw.get("columns")
    if not isinstance(specs, list) or not specs:
        problems.append("`columns` is required: a list with one entry per column")
        raise SchemaError(problems)

    columns: list[Column] = []
    for i, spec in enumerate(specs, start=1):
        col = _parse_column(i, spec, problems)
        if col is not None:
            if col.name in [c.name for c in columns]:
                problems.append(f"column {i} ({col.name}): the name is already used by another column")
            columns.append(col)

    # Records are identified by their key everywhere (saving, merging, conflicts), so
    # it must be a whole number, present and unique in every record, whatever the
    # schema file says. Int keys also let new records be numbered automatically.
    key = next((c for c in columns if c.name == key_name), None)
    if isinstance(key_name, str) and key_name and key is None:
        problems.append(f"the key column {key_name!r} is not one of the columns")
    elif key is not None:
        if key.type != "int":
            problems.append(f"the key column {key.name!r} must have type int, not {key.type!r}")
        key.required = key.unique = True

    if problems:
        raise SchemaError(problems)
    return Schema(key=key_name, columns=columns)


def _parse_column(i: int, spec, problems: list[str]) -> Column | None:
    """Build one column, adding any problem to `problems`. Returns None if it has no usable name."""
    if not isinstance(spec, dict):
        problems.append(f"column {i}: must be a list of settings (name, type, ...)")
        return None
    name = spec.get("name")
    if not isinstance(name, str) or not name.strip():
        problems.append(f"column {i}: `name` is required")
        return None
    where = f"column {i} ({name})"

    for setting in spec.keys() - set(SETTINGS):
        problems.append(f"{where}: unknown setting {setting!r}; allowed: {', '.join(SETTINGS)}")

    t = spec.get("type")
    if t is None:
        problems.append(f"{where}: `type` is required; one of: {', '.join(TYPES)}")
        return None
    if t not in TYPES:
        problems.append(f"{where}: unknown type {t!r}; one of: {', '.join(TYPES)}")
        return None
    col = Column(name=name, type=t)

    for flag in ("required", "unique"):
        if flag in spec:
            if isinstance(spec[flag], bool):
                setattr(col, flag, spec[flag])
            else:
                problems.append(f"{where}: `{flag}` must be true or false, not {spec[flag]!r}")

    if "description" in spec:
        if isinstance(spec["description"], str):
            col.description = spec["description"]
        else:
            problems.append(f"{where}: `description` must be text")

    choices = spec.get("choices")
    if t == "choice":
        if not isinstance(choices, list) or not choices:
            problems.append(f"{where}: type choice needs `choices`, a non-empty list of the allowed values")
        else:
            col.choices = [str(c).strip() for c in choices]
            if any(c == "" for c in col.choices):
                problems.append(f"{where}: `choices` contains an empty value")
            repeated = sorted({c for c in col.choices if col.choices.count(c) > 1})
            if repeated:
                problems.append(f"{where}: `choices` lists {', '.join(repeated)} more than once")
    elif choices is not None:
        problems.append(f"{where}: `choices` is only allowed for type choice")

    for limit in ("min", "max"):
        if limit not in spec:
            continue
        if t not in _LIMITED_TYPES:
            problems.append(f"{where}: `{limit}` is only allowed for types {', '.join(_LIMITED_TYPES)}")
            continue
        value = canon(spec[limit], col)
        if value == "":
            problems.append(f"{where}: `{limit}` is empty; give a value or remove the setting")
            continue
        problem = is_valid_value(value, Column(name=name, type=t))
        if problem:
            problems.append(f"{where}: `{limit}` {problem}")
        else:
            setattr(col, limit, value)
    if col.min is not None and col.max is not None and _typed(col.min, t) > _typed(col.max, t):
        problems.append(f"{where}: `min` ({col.min}) is greater than `max` ({col.max})")
    return col


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
