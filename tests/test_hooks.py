import shutil
import subprocess

import pytest

from safedata.hooks import BEGIN, END, ForeignHook, block, update_pre_commit

PY = "/tools/safedata/bin/python"


def test_new_hook():
    assert update_pre_commit(None, PY) == "#!/bin/sh\n" + block(PY)


def test_hook_from_earlier_versions_is_replaced():
    old = f'#!/bin/sh\nexec "{PY}" -m safedata validate --staged\n'
    assert update_pre_commit(old, PY) == "#!/bin/sh\n" + block(PY)


def test_running_twice_changes_nothing():
    once = update_pre_commit(None, PY)
    assert update_pre_commit(once, PY) == once


def test_only_the_block_is_replaced():
    existing = f"#!/bin/bash\necho before\n{block('/old/python')}echo after\nexec other-tool\n"
    updated = update_pre_commit(existing, PY)
    assert updated == f"#!/bin/bash\necho before\n{block(PY)}echo after\nexec other-tool\n"


def test_block_goes_first_in_someone_elses_shell_hook():
    existing = "#!/usr/bin/env bash\nset -e\nexec lint-staged\n"
    updated = update_pre_commit(existing, PY)
    assert updated == f"#!/usr/bin/env bash\n{block(PY)}set -e\nexec lint-staged\n"
    assert updated.index(BEGIN) < updated.index("exec lint-staged")
    assert update_pre_commit(updated, PY) == updated  # and a second install keeps it single


def test_non_shell_hook_is_left_alone():
    with pytest.raises(ForeignHook, match="validate --staged"):
        update_pre_commit("#!/usr/bin/env python3\nprint('hi')\n", PY)


def test_block_content():
    lines = block(PY).splitlines()
    assert lines[0] == BEGIN and lines[-1] == END
    assert f'if [ -x "{PY}" ]; then' in lines
    assert f'  "{PY}" -m safedata validate --staged || exit 1' in lines
    assert any("is not installed anymore" in line for line in lines)


@pytest.mark.skipif(shutil.which("sh") is None, reason="needs a POSIX shell")
def test_block_runs_and_explains_a_missing_tool(tmp_path):
    hook = tmp_path / "pre-commit"
    hook.write_text(update_pre_commit(None, str(tmp_path / "gone" / "python")))
    proc = subprocess.run(["sh", str(hook)], capture_output=True, text=True)
    assert proc.returncode == 1
    assert "is not installed anymore" in proc.stderr and "safedata install" in proc.stderr
