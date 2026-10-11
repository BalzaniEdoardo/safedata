#!/bin/sh
# Installs the safedata command for the current user (macOS and Linux):
# uv first if it is missing, then safedata as a uv tool. No administrator rights needed.
#
#   curl -LsSf https://raw.githubusercontent.com/BalzaniEdoardo/safedata/main/install.sh | sh
#
# Running it again upgrades safedata. Set SAFEDATA_SOURCE to install from
# somewhere else (a local folder, a fork, a tag: git+https://...@v1.0.0).
set -eu

SOURCE="${SAFEDATA_SOURCE:-git+https://github.com/BalzaniEdoardo/safedata}"

fail() {
    echo "error: $*" >&2
    exit 1
}

command -v git >/dev/null 2>&1 || fail "git is not installed. Install it from https://git-scm.com and run this again."

# uv: use the one on PATH, or one installed earlier in its default folder, or install it.
if ! command -v uv >/dev/null 2>&1; then
    if [ -x "$HOME/.local/bin/uv" ]; then
        PATH="$HOME/.local/bin:$PATH"
    else
        echo "Installing uv (https://docs.astral.sh/uv/) ..."
        if command -v curl >/dev/null 2>&1; then
            curl -LsSf https://astral.sh/uv/install.sh | sh
        elif command -v wget >/dev/null 2>&1; then
            wget -qO- https://astral.sh/uv/install.sh | sh
        else
            fail "neither curl nor wget is installed, so uv cannot be downloaded."
        fi
        PATH="$HOME/.local/bin:$PATH"
    fi
fi
command -v uv >/dev/null 2>&1 || fail "uv was installed but cannot be found. Open a new terminal and run this again."

echo "Installing safedata from $SOURCE ..."
uv tool install --force "$SOURCE"

# Make sure the folder with the safedata command is on PATH in new terminals.
uv tool update-shell

BIN="$(uv tool dir --bin)"
"$BIN/safedata" --help >/dev/null || fail "safedata was installed in $BIN but does not run."

echo
echo "safedata is installed in $BIN."
echo "Open a new terminal, then in a clone of your dataset repository run:  safedata install"
