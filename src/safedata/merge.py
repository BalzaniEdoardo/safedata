"""Three-way merge of two versions of the records, keyed by record, cell by cell."""

from __future__ import annotations

from .changeset import ApplyResult, apply, diff
from .schema import Schema
from .store import Rows


def merge(base: Rows, ours: Rows, theirs: Rows, schema: Schema) -> ApplyResult:
    """Combine `theirs` into `ours`, both descending from `base`.

    Changes to different records, or to different fields of one record, combine
    automatically. When both sides changed the same field differently, `ours`
    is kept and a conflict is reported.
    """
    return apply(ours, diff(base, theirs, schema), schema)


def conflict_report(result: ApplyResult, path: str = "") -> str:
    lines = [
        f"Conflicting changes in {path or 'the records'}.",
        "Both sides changed the same thing. The local value was kept for each item below;",
        "decide which value is right, fix the file, then finish the merge.",
        "",
    ]
    lines += [f"  - {c.describe()}" for c in result.conflicts]
    if result.notes:
        lines += ["", "Also:"] + [f"  - {n}" for n in result.notes]
    return "\n".join(lines) + "\n"
