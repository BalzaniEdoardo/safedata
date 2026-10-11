"""Checking that a clone of a dataset repository is set up for safedata.

`safedata install` writes the add-on settings into the clone's .git folder,
which git does not copy between clones; .gitattributes, which assigns the
add-ons to the records file, is part of the repository. This module lists what
is missing so that `safedata check` can report it. It changes nothing.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Callable

from .hooks import BEGIN, END

REQUIRED_CONFIG = ("filter.safedata.clean", "merge.safedata.driver", "diff.safedata.wordRegex")
ATTRIBUTES = ("filter", "merge", "diff")


@dataclass
class Problem:
    message: str
    fixed_by_install: bool  # True: `safedata install` fixes it; False: the repository must be changed


def clone_problems(records: str, config: dict[str, str], hook_text: str | None,
                   attrs: dict[str, str], exists: Callable[[str], bool] = os.path.exists) -> list[Problem]:
    """Everything that keeps the safedata add-ons from working in a clone.

    `config` is the clone's safedata git config, `hook_text` its pre-commit hook
    (None if absent), `attrs` the filter/merge/diff attributes of the records file.
    """
    problems: list[Problem] = []
    # Git setting names are case-insensitive, and `git config --get-regexp` prints them
    # in lowercase (diff.safedata.wordregex), so compare in lowercase.
    config = {name.lower(): value for name, value in config.items()}

    for name in REQUIRED_CONFIG:
        if name.lower() not in config:
            problems.append(Problem(f"the git setting {name} is not set in this clone", True))

    tools = {m.group(1) for name in ("filter.safedata.clean", "merge.safedata.driver")
             if (m := re.match(r'\s*"([^"]+)"', config.get(name, "")))}
    for tool in sorted(tools):
        if not exists(tool):
            problems.append(Problem(f"the git settings run {tool}, which does not exist anymore "
                                    "(reinstall safedata first)", True))

    if hook_text is None:
        problems.append(Problem("there is no pre-commit hook, so commits are not checked", True))
    elif BEGIN not in hook_text or END not in hook_text:
        problems.append(Problem("the pre-commit hook does not run the safedata check", True))

    for attr in ATTRIBUTES:
        if attrs.get(attr) != "safedata":
            problems.append(Problem(f".gitattributes does not set {attr}=safedata for {records}", False))
    return problems
