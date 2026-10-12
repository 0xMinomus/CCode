"""Distribution version (88plug rolling calver).

Matches hub ``sync_marketplace._auto_version``: ``YEAR.MONTH.<commit-count>``.
Resolution order:
  1. Basename of ``CLAUDE_PLUGIN_ROOT`` / ``GROK_PLUGIN_ROOT`` (e.g. ``.../2026.6.18``)
  2. ``git rev-list --count`` + latest commit date in this repo
  3. ``dev``
"""

import os
import re
import subprocess

_CALVER_RE = re.compile(r"^\d{4}\.\d+\.\d+$")
_REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
_FALLBACK = "dev"


def _from_plugin_root() -> str | None:
    root = os.environ.get("CLAUDE_PLUGIN_ROOT") or os.environ.get("GROK_PLUGIN_ROOT")
    if not root:
        return None
    name = os.path.basename(os.path.abspath(root.rstrip(os.sep)))
    return name if _CALVER_RE.fullmatch(name) else None


def _from_git() -> str | None:
    try:
        count = subprocess.check_output(
            ["git", "rev-list", "--count", "HEAD"],
            cwd=_REPO_ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        ).strip()
        iso = subprocess.check_output(
            ["git", "log", "-1", "--format=%cI", "HEAD"],
            cwd=_REPO_ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        ).strip()
        if not count.isdigit() or len(iso) < 7:
            return None
        return f"{iso[:4]}.{int(iso[5:7])}.{count}"
    except Exception:
        return None


def distribution_version() -> str:
    return _from_plugin_root() or _from_git() or _FALLBACK


__version__ = distribution_version()
