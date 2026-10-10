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


def set_config(root: Path, name: str, value: str) -> None:
    git("config", name, value, cwd=root)
