#!/bin/bash
# Opens the records editor in the browser. Keep this window open while editing.
cd "$(dirname "$0")/.." || exit 1
uv run safedata edit
