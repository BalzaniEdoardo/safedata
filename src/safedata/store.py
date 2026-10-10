"""Reading and writing the canonical records CSV.

The canonical form is: schema column order, rows sorted by key, every value in
canonical form, UTF-8 without BOM, LF line endings, minimal quoting. Writing
the same data always yields the same bytes, so git diffs show only real changes.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

from .schema import Schema, canon

Rows = list[dict[str, str]]


def parse(text: str) -> tuple[list[str], Rows]:
    """Parse CSV text into (header, rows) without interpreting any value."""
    text = text.lstrip("﻿")
    reader = csv.reader(io.StringIO(text, newline=""))
    lines = [line for line in reader if any(cell.strip() for cell in line)]
    if not lines:
        return [], []
    header = [h.strip() for h in lines[0]]
    rows = []
    for line in lines[1:]:
        if len(line) > len(header):
            raise ValueError(f"a row has more cells than there are columns: {line}")
        line = line + [""] * (len(header) - len(line))
        rows.append(dict(zip(header, line)))
    return header, rows


def canonical_rows(rows: Rows, schema: Schema) -> Rows:
    out = [{c.name: canon(row.get(c.name, ""), c) for c in schema.columns} for row in rows]
    out.sort(key=lambda r: schema.sort_key(r[schema.key]))
    return out


def to_text(rows: Rows, schema: Schema) -> str:
    buf = io.StringIO(newline="")
    writer = csv.writer(buf, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(schema.names)
    for row in canonical_rows(rows, schema):
        writer.writerow([row[n] for n in schema.names])
    return buf.getvalue()


def normalize_text(text: str, schema: Schema) -> str:
    """Return canonical CSV text, or the input unchanged if its columns don't match.

    Used as a git clean filter, so it must never fail: problems are left for
    validation to report.
    """
    try:
        header, rows = parse(text)
    except (ValueError, csv.Error):
        return text
    if sorted(header) != sorted(schema.names):
        return text
    return to_text(rows, schema)


def read_text(text: str, schema: Schema) -> Rows:
    header, rows = parse(text)
    if sorted(header) != sorted(schema.names):
        raise ValueError(
            f"columns {header} do not match the schema columns {schema.names}"
        )
    return canonical_rows(rows, schema)


def read_file(path: str | Path, schema: Schema) -> Rows:
    return read_text(Path(path).read_text(encoding="utf-8"), schema)


def write_file(path: str | Path, rows: Rows, schema: Schema) -> None:
    Path(path).write_text(to_text(rows, schema), encoding="utf-8", newline="")


def index(rows: Rows, schema: Schema) -> dict[str, dict[str, str]]:
    return {row[schema.key]: row for row in rows}
