"""Read-only git queries, plus the config writes done by `safedata install`.

Nothing here pulls, commits, pushes or changes history: that is left to
whichever git tool the user prefers.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


class GitError(RuntimeError):
    pass


def git(*args: str, cwd: str | Path, check: bool = True) -> str:
    proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    if check and proc.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed:\n{proc.stderr.strip() or proc.stdout.strip()}")
    return proc.stdout


def repo_root(start: str | Path = ".") -> Path:
    return Path(git("rev-parse", "--show-toplevel", cwd=start).strip())


def show(root: Path, rev: str, path: str) -> str:
    """File content at `rev` ("HEAD", a hash, or "" for the staged version)."""
    return git("show", f"{rev}:{path}", cwd=root)


def status(root: Path) -> dict:
    """Branch and how far it is from its upstream (as of the last fetch)."""
    info = {"branch": git("rev-parse", "--abbrev-ref", "HEAD", cwd=root, check=False).strip() or None,
            "ahead": None, "behind": None}
    counts = git("rev-list", "--left-right", "--count", "HEAD...@{upstream}", cwd=root, check=False).split()
    if len(counts) == 2:
        info["ahead"], info["behind"] = int(counts[0]), int(counts[1])
    return info


def safedata_config(root: Path) -> dict[str, str]:
    """The safedata entries in this clone's git config, e.g. {"filter.safedata.clean": "..."}."""
    out = git("config", "--get-regexp", r"^(filter|merge|diff)\.safedata\.", cwd=root, check=False)
    return dict(line.split(" ", 1) for line in out.splitlines() if " " in line)


def attributes(root: Path, path: str, names: list[str]) -> dict[str, str]:
    """The git attributes `names` of `path`, as git resolves them from .gitattributes."""
    out = git("check-attr", *names, "--", path, cwd=root)
    # each line: "<path>: <attribute>: <value>"
    return {parts[1]: parts[2] for parts in (line.rsplit(": ", 2) for line in out.splitlines()) if len(parts) == 3}


def hooks_dir(root: Path) -> Path:
    return root / git("rev-parse", "--git-path", "hooks", cwd=root).strip()


def set_config(root: Path, name: str, value: str) -> None:
    git("config", name, value, cwd=root)
