from safedata.clonecheck import clone_problems
from safedata.hooks import update_pre_commit

PY = "/tools/safedata/bin/python"
CONFIG = {
    "filter.safedata.clean": f'"{PY}" -m safedata normalize',
    "merge.safedata.name": "safedata record-level merge",
    "merge.safedata.driver": f'"{PY}" -m safedata merge-driver %O %A %B %L %P',
    "diff.safedata.wordRegex": "[^,]+",
}
ATTRS = {"filter": "safedata", "merge": "safedata", "diff": "safedata"}
HOOK = update_pre_commit(None, PY)


def problems(config=CONFIG, hook=HOOK, attrs=ATTRS, exists=lambda p: True):
    return clone_problems("data/records.csv", config, hook, attrs, exists=exists)


def test_set_up_clone():
    assert problems() == []


def test_setting_names_are_case_insensitive():
    """`git config --get-regexp` prints names in lowercase."""
    assert problems(config={name.lower(): value for name, value in CONFIG.items()}) == []


def test_install_never_run():
    found = problems(config={}, hook=None)
    assert len(found) == 4 and all(p.fixed_by_install for p in found)
    assert "filter.safedata.clean is not set" in found[0].message
    assert "no pre-commit hook" in found[-1].message


def test_tool_removed_after_install():
    [p] = problems(exists=lambda path: path != PY)
    assert f"run {PY}, which does not exist anymore" in p.message and p.fixed_by_install


def test_someone_elses_hook_without_the_check():
    [p] = problems(hook="#!/bin/sh\nexec lint-staged\n")
    assert "does not run the safedata check" in p.message


def test_gitattributes_missing():
    found = problems(attrs={"filter": "unspecified", "merge": "unspecified", "diff": "unspecified"})
    assert [p.fixed_by_install for p in found] == [False, False, False]
    assert ".gitattributes does not set filter=safedata for data/records.csv" in found[0].message
