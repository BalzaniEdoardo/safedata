#!/bin/bash
# Get the latest records. Double-click to run.
cd "$(dirname "$0")/.." || exit 1
uv run safedata update
echo
read -n 1 -s -r -p "Press any key to close this window..."
