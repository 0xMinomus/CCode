#!/usr/bin/env bash
# install.sh — install the window-info@local GNOME Shell extension.
set -euo pipefail

UUID="window-info@local"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="$HOME/.local/share/gnome-shell/extensions/$UUID"

echo "Installing $UUID ..."
mkdir -p "$DEST"
cp -f "$SRC/metadata.json" "$SRC/extension.js" "$DEST/"
echo "  copied -> $DEST"

# Enabling is harmless even before the Shell knows about the extension; the
# enabled-list is read at next Shell start.
if command -v gnome-extensions >/dev/null 2>&1; then
    gnome-extensions enable "$UUID" || true
    echo "  gnome-extensions enable $UUID (queued)"
else
    echo "  WARNING: gnome-extensions CLI not found; enable manually."
fi

cat <<'NOTE'

================================================================================
  IMPORTANT — Wayland relogin required for FIRST activation
================================================================================
  You are on GNOME Shell on Wayland. A brand-NEW extension cannot be loaded
  into the running Shell: there is no `gnome-shell --replace` / Alt+F2 'r'
  hot-reload on Wayland (confirmed). The Shell only scans for and loads a
  newly-installed extension at startup.

  => Log out and log back in (or reboot) once. After that the D-Bus service
     at /org/gnome/Shell/Extensions/WindowInfo (interface
     org.gnome.Shell.Extensions.WindowInfo, dest org.gnome.Shell) will be live.

  Until you relog, mcp-screen awareness.py degrades gracefully (returns
  None/[]/"unavailable") and uses the AT-SPI fallback where possible.

  Verify after relogin:
    gnome-extensions list --enabled | grep window-info
    gdbus call --session --dest org.gnome.Shell \
      --object-path /org/gnome/Shell/Extensions/WindowInfo \
      --method org.gnome.Shell.Extensions.WindowInfo.GetMonitors
================================================================================
NOTE
