"""Tests for tools/style/check.py.

Example phrases are split across string literals so this file does not
itself break the rules it tests.
"""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("style_check", ROOT / "tools" / "style" / "check.py")
style = importlib.util.module_from_spec(spec)
sys.modules["style_check"] = style  # dataclasses look the module up by name
spec.loader.exec_module(style)

RULES = style.load_rules()
HARD = "under the " + "hood"
SOFT = "it " + "bites"
SOFT_WORD = "lever" + "age"


def tiers(name, text):
    return sorted(h.tier for h in style.find_hits(Path(name), text, RULES) if not h.allowed)


def test_markdown_prose_checked_code_exempt():
    assert tiers("a.md", f"Some text {HARD}.\n") == ["hard"]
    assert tiers("a.md", f"Some `{HARD}` text.\n\n```\n{HARD}\n```\n") == []


def test_markdown_vacuous_headings():
    assert tiers("a.md", "## The " + "idea\n") == ["hard"]
    assert tiers("a.md", "## How it " + "stays safe\n") == ["hard"]
    assert tiers("a.md", "**The " + "problem:** text\n") == ["hard"]
    assert tiers("a.md", "## Checks applied to every change\n") == []


def test_markdown_hard_wrap():
    assert tiers("a.md", "First line of a paragraph\ncontinues here.\n") == ["hard"]
    assert tiers("a.md", "- item one\n- item two\n\nA paragraph.\n") == []


def test_python_checks_comments_and_strings_not_code():
    code = f'{SOFT_WORD} = 1  # {HARD}\n\ndef f():\n    """Docstring: {SOFT}."""\n    return {SOFT_WORD}\n'
    assert tiers("a.py", code) == ["hard", "soft"]


def test_python_consecutive_comments_joined():
    code = "# this goes under the\n# " + "hood of things\nx = 1\n"
    assert tiers("a.py", code) == ["hard"]


def test_soft_allow_marker():
    assert tiers("a.md", f"The dog: {SOFT}. <!-- style: allow -->\n") == []
    assert tiers("a.md", f"{HARD} <!-- style: allow -->\n") == ["hard"]


def test_only_new_matches_flagged():
    old = f"Old text {HARD}.\n"
    assert style.new_hits(Path("a.md"), old, old + "\nMore text.\n", RULES) == []
    assert len(style.new_hits(Path("a.md"), old, old + f"\nAgain {HARD}.\n", RULES)) == 1


def test_repository_passes():
    hard, _ = style.check_files(style.git_files(changed=False), RULES)
    assert hard == []
