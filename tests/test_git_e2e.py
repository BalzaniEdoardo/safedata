"""End-to-end checks of the editor and the git add-ons with real git.

Each test builds a bare repository (standing in for the shared server) and two
clones, alice and bob, each with `safedata install` run in it. The editor's
save and resolve are called directly (the same functions the page uses); every
other step is a plain git command.

The tests run git with an empty home folder and no global or system config, so
personal git settings do not affect them. Marked `git`: deselect with
`pytest -m "not git"`.
"""

import shutil
import subprocess
from types import SimpleNamespace

import pytest
from conftest import FIXTURES, make_row

from safedata import cli, dataset, store, webapp

pytestmark = [
    pytest.mark.git,
    pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed"),
]

RECORDS = "data/records.csv"


def git(cwd, *args, check=True):
    proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed ({proc.returncode}):\n{proc.stdout}{proc.stderr}")
    return proc


def output(proc):
    return proc.stdout + proc.stderr


def records(repo):
    ds = dataset.load(repo)
    return {r["id"]: r for r in store.read_file(ds.records_path, ds.load_schema())}


def save(repo, **edits):
    """What the editor's Save button does."""
    ds = dataset.load(repo)
    return webapp.save(ds, {"version": webapp.get_state(ds)["version"], **edits})


def commit(repo, message):
    git(repo, "commit", "-q", "-am", message)


@pytest.fixture
def team(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".gitconfig").write_text("")  # an empty file, not os.devnull, which is "nul" on Windows
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))  # the home folder on Windows
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(home / ".gitconfig"))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")  # also skips Git for Windows' system core.autocrlf

    server = tmp_path / "server.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(server))

    alice = tmp_path / "alice"
    git(tmp_path, "init", "-q", "-b", "main", str(alice))
    (alice / "safedata.toml").write_text(f'records = "{RECORDS}"\nschema = "data/schema.yaml"\n')
    (alice / "data").mkdir()
    shutil.copy(FIXTURES / "schema.yaml", alice / "data" / "schema.yaml")
    ds = dataset.load(alice)
    store.write_file(ds.records_path, [make_row(1), make_row(2), make_row(3)], ds.load_schema())
    (alice / ".gitattributes").write_text(f"{RECORDS}  filter=safedata merge=safedata diff=safedata text eol=lf\n")
    git(alice, "config", "user.name", "Alice")
    git(alice, "config", "user.email", "alice@example.org")
    cli.install(alice)
    git(alice, "add", "-A")
    commit(alice, "initial records")
    git(alice, "remote", "add", "origin", str(server))
    git(alice, "push", "-q", "-u", "origin", "main")

    bob = tmp_path / "bob"
    git(tmp_path, "clone", "-q", str(server), str(bob))
    git(bob, "config", "user.name", "Bob")
    git(bob, "config", "user.email", "bob@example.org")
    cli.install(bob)
    return SimpleNamespace(alice=alice, bob=bob)


def test_saving_only_changes_the_records_file(team):
    save(team.alice, updates={"1": {"value": ["1.5", "42"]}})
    assert git(team.alice, "status", "--porcelain").stdout.splitlines() == [f" M {RECORDS}"]
    diff = git(team.alice, "diff", "--word-diff", RECORDS).stdout
    assert "[-1.5-]{+42+}" in diff  # the word diff marks the changed cell


def test_edits_to_different_columns_and_new_records_are_combined(team):
    a, b = team.alice, team.bob
    save(a, updates={"1": {"value": ["1.5", "7"]}}, adds=[make_row("", observer="Ana")])
    commit(a, "Alice: value of 1, new record")
    git(a, "push", "-q")

    save(b, updates={"1": {"notes": ["", "checked"]}}, adds=[make_row("", observer="Bob")])
    commit(b, "Bob: note on 1, new record")
    git(b, "pull", "-q", "--no-rebase", "--no-edit")

    rows = records(b)
    assert (rows["1"]["value"], rows["1"]["notes"]) == ("7", "checked")
    # both added record 4; the incoming one (Alice's) was renumbered
    assert (rows["4"]["observer"], rows["5"]["observer"]) == ("Bob", "Ana")
    assert git(b, "status", "--porcelain").stdout == ""


def test_same_cell_conflict_is_reported_blocked_and_resolved(team):
    a, b = team.alice, team.bob
    save(a, updates={"2": {"value": ["1.5", "10"]}})
    commit(a, "2 -> 10")
    git(a, "push", "-q")
    save(b, updates={"2": {"value": ["1.5", "20"]}})
    commit(b, "2 -> 20")

    pull = git(b, "pull", "--no-rebase", "--no-edit", check=False)
    assert pull.returncode != 0
    assert f"record 2 in {RECORDS} changed differently on both sides" in output(pull)
    text = (b / RECORDS).read_text()
    assert text.count("<<<<<<<") == 1 and "<<<<<<< local" in text

    # staging alone would mark the conflict resolved; the pre-commit check refuses the markers
    git(b, "add", RECORDS)
    refused = git(b, "commit", "--no-edit", check=False)
    assert refused.returncode != 0
    assert "still contains merge conflicts (record 2)" in output(refused)

    # resolve in the editor (keep Alice's value), then finish the merge with git
    ds = dataset.load(b)
    webapp.resolve(ds, {"version": webapp.get_state(ds)["version"], "choices": {"2": "incoming"}})
    git(b, "add", RECORDS)
    git(b, "commit", "-q", "--no-edit")
    assert records(b)["2"]["value"] == "10"
    git(b, "push", "-q")
    git(a, "pull", "-q", "--no-rebase", "--no-edit")
    assert records(a)["2"]["value"] == "10"


def test_hand_edit_is_normalized_when_staged(team):
    path = team.alice / RECORDS
    header, *body = path.read_text().splitlines()
    body = [line.replace(",North,", ",West,") if line.startswith("2,") else line for line in body]
    path.write_bytes(("\r\n".join([header, *reversed(body)]) + "\r\n").encode())  # unsorted, CRLF

    git(team.alice, "add", RECORDS)
    added, removed, _ = git(team.alice, "diff", "--cached", "--numstat").stdout.split()
    assert (added, removed) == ("1", "1")  # only the edited record changed


def test_pre_commit_check_rejects_invalid_records(team):
    path = team.alice / RECORDS
    path.write_text(path.read_text().replace("3,2020-01-01,North,", "3,2020-01-01,Moon,"))
    refused = git(team.alice, "commit", "-am", "bad site", check=False)
    assert refused.returncode != 0
    assert "'Moon' is not an allowed value" in output(refused)


def test_history_of_one_record(team):
    save(team.alice, updates={"1": {"value": ["1.5", "2"]}})
    commit(team.alice, "first change to 1")
    save(team.alice, updates={"3": {"notes": ["", "unrelated"]}})
    commit(team.alice, "change to 3")
    save(team.alice, updates={"1": {"value": ["2", "3"]}})
    commit(team.alice, "second change to 1")

    log = git(team.alice, "log", "-L", f"/^1,/,+1:{RECORDS}", "--format=%s").stdout
    assert "second change to 1" in log and "first change to 1" in log
    assert "change to 3" not in log  # the commit that touched only record 3 is not listed
