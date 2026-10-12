"""Rolling regime: plugin.json must not pin a version (hub auto-calvers)."""

from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def test_plugin_json_is_version_less() -> None:
    manifest = json.loads((REPO / ".claude-plugin" / "plugin.json").read_text())
    assert "version" not in manifest, (
        "plugin.json must stay version-less (rolling regime); "
        "hub sync_marketplace.py auto-stamps YEAR.MONTH.<commit-count>"
    )
