#!/usr/bin/env bash
# setup.sh — one-shot install: Python venv, pip deps, window-info extension.
# System packages (GStreamer, PipeWire, portal, PyGObject) still come from the OS — see README.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

echo "== screen-mcp setup =="

if ! command -v python3 >/dev/null 2>&1; then
  echo "error: python3 not found" >&2
  exit 1
fi

if [ ! -d .venv ]; then
  echo "Creating .venv ..."
  python3 -m venv .venv
fi

echo "Installing Python dependencies ..."
.venv/bin/pip install -q -U pip
.venv/bin/pip install -q -r requirements.txt

echo "Installing window-info@local GNOME Shell extension ..."
bash gnome-shell-extension/window-info@local/install.sh

echo ""
echo "Prerequisite check:"
.venv/bin/python3 prereqs.py

cat <<'NOTE'

Next steps:
  1. Install OS packages from README if any prereq shows status "fail".
  2. Log out and log back in once if window_info is "installed but not loaded".
  3. First screenshot will ask for monitor screen-share consent (portal_token).
  4. Launch MCP via bin/screen-mcp or your client's plugin manifest.

NOTE