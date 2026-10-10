"""Three-way merge of two versions of the records, keyed by record, cell by cell."""

from __future__ import annotations

from dataclasses import dataclass

from .changeset import apply, diff
from .schema import Schema
from .store import Pair, Rows, canonical_rows, index


@dataclass
class MergeResult:
    rows: Rows                  # merged records; for conflicting keys, the local version
    conflicts: dict[str, Pair]  # key -> (local record, incoming record); None = deleted
    notes: list[str]


def merge(base: Rows, ours: Rows, theirs: Rows, schema: Schema) -> MergeResult:
    """Combine `theirs` into `ours`, both descending from `base`.

    Changes to different records, or to different fields of one record, are
    combined. Where both sides changed the same field differently, or one side
    edited a record the other deleted, the record is returned as a conflict.
    """
    result = apply(ours, diff(base, theirs, schema), schema)
    merged = index(result.rows, schema)
    theirs_ix = index(canonical_rows(theirs, schema), schema)
    conflicts: dict[str, Pair] = {}
    for c in result.conflicts:
        if c.column == "*":
            conflicts[c.key] = (merged.get(c.key), theirs_ix.get(c.key))
        else:
            local = merged[c.key]
            incoming = dict(conflicts.get(c.key, (local, local))[1])
            incoming[c.column] = c.theirs
            conflicts[c.key] = (local, incoming)
    return MergeResult(result.rows, conflicts, result.notes)
