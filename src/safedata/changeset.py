"""Changesets: the format that every editing tool produces.

A changeset lists the changes one person made relative to the version they
started from. Applying it compares each change with the current records: if
someone else changed the same value in the meantime, the change is reported as
a conflict and the current value is kept.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

from .schema import Schema
from .store import Rows, canonical_rows, index


@dataclass
class Changeset:
    adds: Rows = field(default_factory=list)
    # key -> column -> (old value, new value)
    updates: dict[str, dict[str, tuple[str, str]]] = field(default_factory=dict)
    # key -> the record as it was when the editor started
    deletes: dict[str, dict[str, str]] = field(default_factory=dict)

    def is_empty(self) -> bool:
        return not (self.adds or self.updates or self.deletes)

    def counts(self) -> str:
        return (
            f"{len(self.adds)} added, {len(self.updates)} changed, "
            f"{len(self.deletes)} deleted"
        )

    def describe(self, schema: Schema) -> list[str]:
        lines = []
        for row in self.adds:
            key = row[schema.key] or "(new)"
            fields = ", ".join(f"{k}={v}" for k, v in row.items() if v and k != schema.key)
            lines.append(f"+ record {key}: {fields}")
        for key, cols in self.updates.items():
            for col, (old, new) in cols.items():
                lines.append(f"~ record {key}, {col}: {old or '(empty)'} -> {new or '(empty)'}")
        for key in self.deletes:
            lines.append(f"- record {key} deleted")
        return lines


@dataclass
class Conflict:
    key: str
    column: str  # "*" when the whole record is involved
    base: str
    ours: str
    theirs: str
    reason: str = ""

    def describe(self) -> str:
        if self.column == "*":
            return f"record {self.key}: {self.reason}"
        return (
            f"record {self.key}, {self.column}: was {self.base or '(empty)'}, "
            f"now {self.ours or '(empty)'} here but {self.theirs or '(empty)'} in the incoming change"
        )


@dataclass
class ApplyResult:
    rows: Rows
    conflicts: list[Conflict]
    notes: list[str]
    assigned: dict[int, str]  # position in changeset.adds -> key it received


def diff(base: Rows, new: Rows, schema: Schema, missing_means_delete: bool = True) -> Changeset:
    """Compute the changes that turn `base` into `new`.

    Rows in `new` with a blank key, or a key not in `base`, are additions.
    Rows of `base` absent from `new` are deletions only if `missing_means_delete`
    (true for whole files; false for edit sheets, where rows may just be filtered out).
    """
    key = schema.key
    base_ix = index(canonical_rows(base, schema), schema)
    cs = Changeset()
    seen = set()
    for row in canonical_rows(new, schema):
        k = row[key]
        if k == "" or k not in base_ix:
            cs.adds.append(row)
            continue
        seen.add(k)
        old = base_ix[k]
        changed = {n: (old[n], row[n]) for n in schema.names if old[n] != row[n]}
        if changed:
            cs.updates[k] = changed
    if missing_means_delete:
        for k, old in base_ix.items():
            if k not in seen:
                cs.deletes[k] = old
    return cs


def apply(current: Rows, cs: Changeset, schema: Schema) -> ApplyResult:
    """Apply a changeset on top of the current records.

    A change applies if the current value still equals the value the editor
    started from (or already equals the new value). Otherwise the current
    value is kept and a Conflict is reported.
    """
    key = schema.key
    rows = index(copy.deepcopy(canonical_rows(current, schema)), schema)
    conflicts: list[Conflict] = []
    notes: list[str] = []
    assigned: dict[int, str] = {}

    for k, cols in cs.updates.items():
        if k not in rows:
            conflicts.append(Conflict(k, "*", "", "", "", "it was edited, but someone else deleted it"))
            continue
        for col, (old, new) in cols.items():
            cur = rows[k][col]
            if cur == old or cur == new:
                rows[k][col] = new
            else:
                conflicts.append(Conflict(k, col, old, cur, new))

    for k, old in cs.deletes.items():
        if k not in rows:
            continue
        if rows[k] == old:
            del rows[k]
        else:
            conflicts.append(
                Conflict(k, "*", "", "", "", "it was deleted, but someone else edited it; it was kept")
            )

    for i, row in enumerate(cs.adds):
        row = dict(row)
        k = row[key]
        if k in rows:
            if rows[k] == row:
                assigned[i] = k
                continue
            if schema.key_column.type != "int":
                conflicts.append(Conflict(k, "*", "", "", "", "two different records were added with this key"))
                continue
            notes.append(f"new record {k} was renumbered because that number was already taken")
            k = ""
        if k == "":
            if schema.key_column.type != "int":
                conflicts.append(Conflict("(new)", "*", "", "", "", f"a new record has no {key}"))
                continue
            k = str(_next_int_key(rows))
            row[key] = k
        rows[k] = row
        assigned[i] = k

    return ApplyResult(canonical_rows(list(rows.values()), schema), conflicts, notes, assigned)


def _next_int_key(rows: dict[str, dict]) -> int:
    nums = [int(k) for k in rows if k.lstrip("-").isdigit()]
    return max(nums, default=0) + 1
