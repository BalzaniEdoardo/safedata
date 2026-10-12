"""Finding records that are probably the same entry, written slightly differently.

The schema's `unique_entries` groups say which columns identify an entry.
Validation refuses records whose values in a group are identical; this module
looks for records whose values are only *similar*, such as "Trastevere" and
"Trastevre", or "Rome" and "rome". It only reports: similarity is a guess, so
nothing here refuses or blocks a change.

For each group, only text (`string`) columns are compared by similarity. The
other columns of the group (dates, numbers, yes/no, choices) must be equal, so
that, for example, the same place in two different years is not reported.
Records are first grouped by those equal values, and similarity is computed
only within each group, which keeps the search fast on large tables.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from itertools import combinations

from .schema import Schema

SIMILAR_TYPES = ("string",)
DEFAULT_THRESHOLD = 0.85


@dataclass
class PossibleDuplicate:
    group: list[str]
    first: dict[str, str]
    second: dict[str, str]
    similarity: float  # 0 to 1, over the text columns of the group, ignoring case and spacing

    def describe(self, schema: Schema) -> str:
        values = lambda row: ", ".join(row[c] for c in self.group)
        return (f"records {self.first[schema.key]} and {self.second[schema.key]}: "
                f"{', '.join(self.group)} ({values(self.first)} / {values(self.second)}), "
                f"{self.similarity:.0%} similar")


def _normalized(value: str) -> str:
    return " ".join(value.casefold().split())


def _pairs(bucket: list[dict[str, str]], key: str, only: set[str] | None):
    """Every pair of records in the bucket, or, with `only`, the pairs involving those records.

    With `only`, start from those records instead of filtering all pairs: a few
    records against a large bucket, not every pair of it.
    """
    if only is None:
        yield from combinations(bucket, 2)
        return
    for i, a in enumerate(bucket):
        if a[key] not in only:
            continue
        for j, b in enumerate(bucket):
            # a pair of two `only` records is produced once, from the first of the two
            if j != i and (b[key] not in only or j > i):
                yield (a, b) if i < j else (b, a)  # in file order, as without `only`


def find(rows: list[dict[str, str]], schema: Schema, threshold: float = DEFAULT_THRESHOLD,
         only: set[str] | None = None) -> list[PossibleDuplicate]:
    """Pairs of records that look like the same entry, most similar first.

    `only`: if given, report only pairs that involve at least one of these keys
    (for example, the records being edited).
    """
    found: list[PossibleDuplicate] = []
    for group in schema.unique_entries:
        text_cols = [c for c in group if schema.column(c).type in SIMILAR_TYPES]
        exact_cols = [c for c in group if c not in text_cols]
        if not text_cols:  # identical values are already refused by validation
            continue
        buckets: dict[tuple[str, ...], list[dict[str, str]]] = {}
        for row in rows:
            if any(row.get(c, "") == "" for c in group):  # as in validation, empty values are not checked
                continue
            buckets.setdefault(tuple(row[c] for c in exact_cols), []).append(row)

        matcher = SequenceMatcher(autojunk=False)
        for bucket in buckets.values():
            for a, b in _pairs(bucket, schema.key, only):
                text_a = " | ".join(_normalized(a[c]) for c in text_cols)
                text_b = " | ".join(_normalized(b[c]) for c in text_cols)
                matcher.set_seqs(text_a, text_b)
                # quick upper bounds first: most pairs are far apart and are skipped cheaply
                if (matcher.real_quick_ratio() >= threshold and matcher.quick_ratio() >= threshold
                        and (ratio := matcher.ratio()) >= threshold):
                    found.append(PossibleDuplicate(group, a, b, ratio))
    found.sort(key=lambda d: -d.similarity)
    return found
