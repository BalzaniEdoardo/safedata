"""Thin wrappers around the git commands the tools need."""

from __future__ import annotations

import subprocess
from pathlib import Path


class GitError(RuntimeError):
    pass


def git(*args: str, cwd: str | Path, check: bool = True, input: str | None = None) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=cwd,
        input=input,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if check and proc.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed:\n{proc.stderr.strip() or proc.stdout.strip()}")
    return proc.stdout


def repo_root(start: str | Path = ".") -> Path:
    return Path(git("rev-parse", "--show-toplevel", cwd=start).strip())


def head(root: Path) -> str:
    return git("rev-parse", "HEAD", cwd=root).strip()


def show(root: Path, rev: str, path: str) -> str:
    return git("show", f"{rev}:{path}", cwd=root)


def has_upstream(root: Path) -> bool:
    return bool(git("rev-parse", "--abbrev-ref", "@{upstream}", cwd=root, check=False).strip())


def is_modified(root: Path, path: str) -> bool:
    return bool(git("status", "--porcelain", "--", path, cwd=root).strip())


def user_name(root: Path) -> str:
    return git("config", "--get", "user.name", cwd=root, check=False).strip() or "unknown"


def pull(root: Path) -> tuple[bool, str]:
    """Pull and merge the shared history. Returns (ok, message).

    On a merge conflict the merge is aborted so the working copy stays usable,
    and the conflict report is returned in the message.
    """
    if not has_upstream(root):
        return True, "no shared repository configured; working locally"
    report = root / "MERGE_CONFLICTS.txt"
    report.unlink(missing_ok=True)
    proc = subprocess.run(
        ["git", "pull", "--no-rebase", "--no-edit"],
        cwd=root, capture_output=True, text=True, encoding="utf-8",
    )
    if proc.returncode == 0:
        return True, proc.stdout.strip()
    details = report.read_text(encoding="utf-8") if report.exists() else proc.stderr.strip()
    git("merge", "--abort", cwd=root, check=False)
    return False, details


def commit(root: Path, paths: list[str], message: str) -> None:
    git("add", "--", *paths, cwd=root)
    git("commit", "-m", message, "--", *paths, cwd=root)


def push(root: Path) -> tuple[bool, str]:
    if not has_upstream(root):
        return True, "no shared repository configured; change saved locally"
    proc = subprocess.run(["git", "push"], cwd=root, capture_output=True, text=True, encoding="utf-8")
    return proc.returncode == 0, (proc.stderr or proc.stdout).strip()


def log_revisions(root: Path, path: str) -> list[tuple[str, str, str, str]]:
    """(hash, author, date, subject) for commits touching `path`, oldest first."""
    out = git(
        "log", "--first-parent", "--reverse", "--format=%H%x09%an%x09%ad%x09%s",
        "--date=short", "--", path, cwd=root,
    )
    return [tuple(line.split("\t", 3)) for line in out.splitlines() if line]


def set_config(root: Path, name: str, value: str) -> None:
    git("config", name, value, cwd=root)
