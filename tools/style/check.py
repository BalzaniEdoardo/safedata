#!/usr/bin/env python3
"""Check prose against the writing rules in rules.txt.

Prose means: markdown text outside code, and in Python files the comments,
docstrings and other string literals (so identifiers never match). Other text
files (YAML, TOML, launchers, git config files) are checked whole.

Rules come in two tiers:
  hard  never allowed; the check fails.
  soft  allowed only in a literal sense. From the command line they are
        printed as warnings (failures with --strict). A line containing
        `style: allow` accepts its soft matches.
Markdown has one built-in hard rule: no hard-wrapped paragraphs or list items.

Usage:
  check.py [PATH ...]   check files (default: every tracked or untracked,
                        non-ignored file in the repository)
  check.py --changed    only files with uncommitted changes
  check.py --strict     soft matches fail too
  check.py --hook       Claude Code PreToolUse hook for Write/Edit/MultiEdit
  check.py --stop-hook  Claude Code Stop hook: refuses to end the turn while
                        changed files break a hard rule

Standard library only, so it runs with any Python 3.9+.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import subprocess
import sys
import tempfile
import tokenize
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RULES = HERE / "rules.txt"
ALLOW_MARKER = "style: allow"
REVIEWED = Path(tempfile.gettempdir()) / "safedata-style-reviewed"

MARKDOWN = {".md", ".markdown", ".mdx"}
PYTHON = {".py"}
WHOLE_TEXT = {".yaml", ".yml", ".toml", ".txt", ".cmd", ".bat", ".command", ".sh", ".cfg", ".ini"}
WHOLE_TEXT_NAMES = {".gitattributes", ".gitignore"}
SKIP = {RULES}


@dataclass(frozen=True)
class Rule:
    tier: str  # "hard" or "soft"
    pattern: re.Pattern


@dataclass(frozen=True)
class Hit:
    tier: str
    rule: str
    match: str
    line: int
    context: str
    allowed: bool  # soft match on a line marked `style: allow`

    def key(self):
        return (self.tier, self.rule, self.match.lower())

    def describe(self, path: str) -> str:
        return f'{path}:{self.line}: [{self.tier}] "{self.match}" (rule: {self.rule})\n    {self.context[:160]}'


def load_rules(path: Path = RULES) -> list[Rule]:
    rules, tier = [], "hard"
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line in ("[hard]", "[soft]"):
            tier = line[1:-1]
            continue
        rules.append(Rule(tier, re.compile(line, re.IGNORECASE | re.MULTILINE)))
    return rules


# ---------------------------------------------------------------- prose extraction

def checked(path: Path) -> bool:
    if path.resolve() in SKIP:
        return False
    return path.suffix.lower() in MARKDOWN | PYTHON | WHOLE_TEXT or path.name in WHOLE_TEXT_NAMES


def segments(path: Path, text: str) -> list[tuple[int, str]]:
    """Pieces of prose as (first line number, text)."""
    suffix = path.suffix.lower()
    if suffix in MARKDOWN:
        return list(enumerate(_markdown_without_code(text).split("\n"), start=1))
    if suffix in PYTHON:
        return _python_prose(text)
    return list(enumerate(text.split("\n"), start=1))


def _markdown_without_code(text: str) -> str:
    out, fence = [], False
    for line in text.split("\n"):
        if line.strip().startswith("```"):
            fence = not fence
            out.append("")
        elif fence:
            out.append("")
        else:
            out.append(re.sub(r"`[^`\n]*`", " ", line))
    return "\n".join(out)


def _python_prose(text: str) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    string_parts = {tokenize.STRING} | {getattr(tokenize, n) for n in ("FSTRING_MIDDLE",) if hasattr(tokenize, n)}
    comment_start, comment_lines, last_comment_row = 0, [], -1
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type == tokenize.COMMENT:
                body = tok.string.lstrip("#").strip()
                if tok.start[0] == last_comment_row + 1 and comment_lines:
                    comment_lines.append(body)  # consecutive comment lines form one segment
                else:
                    if comment_lines:
                        found.append((comment_start, " ".join(comment_lines)))
                    comment_start, comment_lines = tok.start[0], [body]
                last_comment_row = tok.start[0]
            elif tok.type in string_parts:
                found.append((tok.start[0], " ".join(tok.string.split())))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        # Unparseable source: fall back to every line that has a comment or a quote.
        return [(i, ln) for i, ln in enumerate(text.split("\n"), start=1) if "#" in ln or '"' in ln or "'" in ln]
    if comment_lines:
        found.append((comment_start, " ".join(comment_lines)))
    return found


# ---------------------------------------------------------------- checks

def find_hits(path: Path, text: str, rules: list[Rule]) -> list[Hit]:
    hits = []
    for line, segment in segments(path, text):
        allowed = ALLOW_MARKER in segment
        for rule in rules:
            for m in rule.pattern.finditer(segment):
                hits.append(Hit(rule.tier, rule.pattern.pattern, m.group(0), line, segment.strip(),
                                allowed and rule.tier == "soft"))
    if path.suffix.lower() in MARKDOWN:
        for line, s in hard_wrapped_lines(text):
            hits.append(Hit("hard", "markdown: one line per paragraph or list item", s[:60], line, s, False))
    return hits


_BLOCK_START = re.compile(r"^\s*(#|\||>|<|```|---\s*$|([-*+]|\d+[.)])\s)")


def hard_wrapped_lines(text: str) -> list[tuple[int, str]]:
    """Markdown lines that continue the previous line instead of starting a new block."""
    found, fence, prev = [], False, ""
    lines = text.split("\n")
    front = bool(lines) and lines[0].strip() == "---"
    for i, line in enumerate(lines, start=1):
        s = line.strip()
        if front:
            front = not (i > 1 and s == "---")
            prev = ""
            continue
        if s.startswith("```"):
            fence, prev = not fence, ""
            continue
        if fence or not s:
            prev = ""
            continue
        p = prev.strip()
        if p and not p.startswith(("#", "|", "<", "```")) and not _BLOCK_START.match(line):
            found.append((i, s))
        prev = line
    return found


def new_hits(path: Path, old: str, new: str, rules: list[Rule]) -> list[Hit]:
    """Hits in `new` that `old` did not already have (counted per rule and matched text)."""
    before = Counter(h.key() for h in find_hits(path, old, rules)) if old else Counter()
    out = []
    for h in find_hits(path, new, rules):
        if before[h.key()]:
            before[h.key()] -= 1
        else:
            out.append(h)
    return out


# ---------------------------------------------------------------- command line

def git_files(changed: bool) -> list[Path]:
    if changed:
        out = subprocess.run(["git", "status", "--porcelain", "-z", "--untracked-files=all"],
                             cwd=ROOT, capture_output=True, text=True).stdout
        names = [e[3:] for e in out.split("\0") if len(e) > 3 and e[0] != "D" and e[1] != "D"]
    else:
        out = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                             cwd=ROOT, capture_output=True, text=True).stdout
        names = [n for n in out.split("\0") if n]
    return [ROOT / n for n in names if (ROOT / n).is_file()]


def check_files(paths: list[Path], rules: list[Rule]) -> tuple[list[str], list[str]]:
    hard, soft = [], []
    for path in paths:
        if not checked(path):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        rel = str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)
        for h in find_hits(path, text, rules):
            if h.tier == "hard":
                hard.append(h.describe(rel))
            elif not h.allowed:
                soft.append(h.describe(rel))
    return hard, soft


def run_cli(args) -> int:
    rules = load_rules()
    paths = [Path(p).resolve() for p in args.paths] or git_files(args.changed)
    hard, soft = check_files(paths, rules)
    for line in hard:
        print(line)
    for line in soft:
        print(line)
    failed = bool(hard) or (args.strict and bool(soft))
    print(f"\n{len(hard)} hard, {len(soft)} soft match(es)." if hard or soft else "Style check passed.")
    if soft and not args.strict:
        print("Soft matches are allowed only in a literal sense; add `style: allow` to accept one.")
    return 1 if failed else 0


# ---------------------------------------------------------------- Claude Code hooks

def _apply_edit(path: Path, tool: str, tool_input: dict) -> tuple[str, str]:
    """(old file text, new file text) for a Write/Edit/MultiEdit call."""
    old = path.read_text(encoding="utf-8") if path.is_file() else ""
    if tool == "Write":
        return old, tool_input.get("content", "")
    edits = [tool_input] if tool == "Edit" else tool_input.get("edits", [])
    new = old
    for e in edits:
        o, n = e.get("old_string", ""), e.get("new_string", "")
        if o and o in new:
            new = new.replace(o, n) if e.get("replace_all") else new.replace(o, n, 1)
        else:  # cannot place the edit: compare the fragments themselves
            return o, n
    return old, new


def run_hook() -> int:
    payload = json.load(sys.stdin)
    tool = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {})
    path = Path(tool_input.get("file_path", "")).expanduser().resolve()
    if tool not in ("Write", "Edit", "MultiEdit") or not path.is_relative_to(ROOT) or not checked(path):
        return 0
    old, new = _apply_edit(path, tool, tool_input)
    hits = new_hits(path, old, new, load_rules())
    rel = str(path.relative_to(ROOT))

    hard = [h for h in hits if h.tier == "hard"]
    if hard:
        sys.stderr.write(
            f"Writing rules (tools/style/rules.txt) broken in {rel}. Rewrite in plain, literal "
            "language that says what happens and why; also rewrite nearby prose in the same style:\n"
            + "\n".join(h.describe(rel) for h in hard) + "\n")
        return 2

    soft = [h for h in hits if h.tier == "soft" and not h.allowed]
    if not soft:
        return 0
    key = hashlib.sha256(json.dumps([str(path), new]).encode()).hexdigest()
    marker = REVIEWED / key
    if marker.exists():  # identical retry: the literal use was confirmed
        marker.unlink()
        return 0
    REVIEWED.mkdir(parents=True, exist_ok=True)
    marker.touch()
    sys.stderr.write(
        f"Review required in {rel}: these phrases are allowed only when meant literally.\n"
        + "\n".join(h.describe(rel) for h in soft)
        + "\nIf every use is literal, resubmit the identical call. Otherwise rewrite it.\n")
    return 2


def run_stop_hook() -> int:
    payload = json.load(sys.stdin)
    if payload.get("stop_hook_active"):
        return 0  # already asked once this turn; do not loop
    hard, _ = check_files(git_files(changed=True), load_rules())
    if not hard:
        return 0
    sys.stderr.write(
        "Changed files break the hard writing rules (tools/style/rules.txt). "
        "Fix them before finishing:\n" + "\n".join(hard[:40]) + "\n")
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check prose against tools/style/rules.txt.")
    parser.add_argument("paths", nargs="*")
    parser.add_argument("--changed", action="store_true", help="only files with uncommitted changes")
    parser.add_argument("--strict", action="store_true", help="soft matches fail too")
    parser.add_argument("--hook", action="store_true", help="run as a Claude Code PreToolUse hook")
    parser.add_argument("--stop-hook", action="store_true", help="run as a Claude Code Stop hook")
    args = parser.parse_args(argv)
    if args.hook:
        return run_hook()
    if args.stop_hook:
        return run_stop_hook()
    return run_cli(args)


if __name__ == "__main__":
    sys.exit(main())
