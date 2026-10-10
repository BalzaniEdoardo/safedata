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
    """Return canonical CSV text, or the input unchanged if it can't be read.

    Used as a git clean filter, so it must never fail: problems (wrong columns,
    unresolved merge conflicts) are left for validation to report.
    """
    if has_conflicts(text):
        return text
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


# ---------------------------------------------------------------- merge conflicts
#
# A conflicted file uses git's standard markers, so any git tool can show and
# resolve it. Each conflict block holds whole records (one line each):
#
#   <<<<<<< local
#   12,2020-01-01,North,...,7,...
#   =======
#   12,2020-01-01,North,...,8,...
#   >>>>>>> incoming
#
# A side with no line means the record was deleted on that side.

MARK_OURS, MARK_BASE, MARK_SEP, MARK_THEIRS = "<<<<<<<", "|||||||", "=======", ">>>>>>>"
Pair = tuple["dict[str, str] | None", "dict[str, str] | None"]


def has_conflicts(text: str) -> bool:
    return any(line.startswith(MARK_OURS) for line in text.splitlines())


def to_text_with_conflicts(rows: Rows, pairs: dict[str, Pair], schema: Schema,
                           labels: tuple[str, str] = ("local", "incoming"), size: int = 7) -> str:
    """Canonical CSV text with a conflict block for each key in `pairs`."""
    def line(row):
        buf = io.StringIO(newline="")
        csv.writer(buf, lineterminator="\n").writerow([row[n] for n in schema.names])
        return buf.getvalue()

    by_key = {r[schema.key]: r for r in canonical_rows(rows, schema)}
    pairs = {k: tuple(None if r is None else canonical_rows([r], schema)[0] for r in p)
             for k, p in pairs.items()}
    out = [line({n: n for n in schema.names})]
    for key in sorted(set(by_key) | set(pairs), key=schema.sort_key):
        if key in pairs:
            ours, theirs = pairs[key]
            out.append(f"{'<' * size} {labels[0]}\n")
            out.append(line(ours) if ours else "")
            out.append(f"{'=' * size}\n")
            out.append(line(theirs) if theirs else "")
            out.append(f"{'>' * size} {labels[1]}\n")
        else:
            out.append(line(by_key[key]))
    return "".join(out)


def parse_conflicted(text: str, schema: Schema) -> tuple[Rows, dict[str, Pair]]:
    """Split a conflicted file into the rows outside conflicts and a (local, incoming)
    pair per conflicting key. Also reads files merged line by line by plain git."""
    clean: list[str] = []
    blocks: list[tuple[list[str], list[str]]] = []
    state, ours, theirs = None, [], []
    for raw in text.lstrip("\ufeff").split("\n"):
        line = raw.rstrip("\r")
        if line.startswith(MARK_OURS) and state is None:
            state, ours, theirs = "ours", [], []
        elif line.startswith(MARK_BASE) and state == "ours":
            state = "base"
        elif line.startswith(MARK_SEP) and state in ("ours", "base"):
            state = "theirs"
        elif line.startswith(MARK_THEIRS) and state == "theirs":
            blocks.append((ours, theirs))
            state = None
        elif state == "ours":
            ours.append(line)
        elif state == "theirs":
            theirs.append(line)
        elif state is None:
            clean.append(line)
    if state is not None:
        raise ValueError("a conflict block is not closed")
    if not clean or sorted(h.strip() for h in clean[0].split(",")) != sorted(schema.names):
        raise ValueError("the conflict involves the column headers; resolve it in a text editor")

    header = clean[0]
    rows = read_text("\n".join(clean), schema)
    pairs: dict[str, Pair] = {}
    for ours_lines, theirs_lines in blocks:
        o = index(read_text("\n".join([header] + ours_lines), schema), schema)
        t = index(read_text("\n".join([header] + theirs_lines), schema), schema)
        for key in set(o) | set(t):
            pairs[key] = (o.get(key), t.get(key))
    rows = [r for r in rows if r[schema.key] not in pairs]
    return rows, pairs
