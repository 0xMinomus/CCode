#!/usr/bin/env bash
# Lightweight wiring check for CI — no live D-Bus / portal / GPU required.
# Compiles every Python module (syntax only, no heavy imports), bash-checks the
# shell scripts, and validates the JSON manifests.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
PY="${PYTHON:-python3}"

echo "=== smoke: python syntax (py_compile, no imports) ==="
"$PY" -m compileall -q ./*.py
echo "  ok: all .py compile"

echo "=== smoke: shell script syntax (bash -n) ==="
for f in bin/screen-mcp $(find . -name '*.sh' -not -path './.git/*'); do
    bash -n "$f" && echo "  ok: $f"
done

echo "=== smoke: JSON manifests valid ==="
for j in .claude-plugin/plugin.json .claude-plugin/marketplace.json marketplace-entry.json; do
    "$PY" -c "import json,sys; json.load(open('$j'))" && echo "  ok: $j"
done

echo "=== smoke: all good ==="

echo "== run-python launcher =="
test -f scripts/run-python.sh
bash -n scripts/run-python.sh
bash -n bin/screen-mcp
grep -q 'run-python.sh' bin/screen-mcp
bash scripts/run-python.sh -c 'import sys; assert sys.version_info >= (3, 10)'
echo "  ok: run-python"
