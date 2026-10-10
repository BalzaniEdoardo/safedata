"""Adding the safedata check to a clone's pre-commit hook without disturbing the rest of it.

The check lives in a marked block that install owns:

    # >>> safedata >>>
    "<python>" -m safedata validate --staged || exit 1
    # <<< safedata <<<

Anything outside the markers belongs to someone else and is kept as it is.
"""

from __future__ import annotations

import re

BEGIN = "# >>> safedata >>>"
END = "# <<< safedata <<<"
# the whole-file hook written by earlier versions: a shebang and one exec line
_OLD_HOOK = re.compile(r'\A#!/bin/sh\nexec "[^"\n]+" -m safedata validate --staged\n?\Z')


class ForeignHook(Exception):
    """The hook is not a shell script, so the block cannot be added automatically."""


def check_line(python: str) -> str:
    return f'"{python}" -m safedata validate --staged || exit 1'


def block(python: str) -> str:
    return f"{BEGIN}\n{check_line(python)}\n{END}\n"


def update_pre_commit(existing: str | None, python: str) -> str:
    """The new content of the pre-commit hook, given its current content (None if absent)."""
    if existing is None or existing.strip() == "" or _OLD_HOOK.match(existing):
        return "#!/bin/sh\n" + block(python)

    if BEGIN in existing and END in existing:
        before, rest = existing.split(BEGIN, 1)
        _, after = rest.split(END, 1)
        return before + block(python) + after.lstrip("\n")

    first, _, rest = existing.partition("\n")
    if not (first.startswith("#!") and re.search(r"\b(sh|bash|zsh|dash)\b", first)):
        raise ForeignHook(
            "the pre-commit hook is not a shell script, so the safedata check was not added. "
            f"Add this command to it so it runs before each commit:\n    {check_line(python)}")
    # Right after the shebang, so the check runs even if the hook ends with `exec`.
    return f"{first}\n{block(python)}{rest}"
