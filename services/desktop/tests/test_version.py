"""Tests for version.distribution_version() calver resolution."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import version

REPO = Path(__file__).resolve().parent.parent
_CALVER = re.compile(r"^\d{4}\.\d+\.\d+$")


def test_distribution_version_matches_git_formula(monkeypatch):
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    monkeypatch.delenv("GROK_PLUGIN_ROOT", raising=False)
    count = subprocess.check_output(
        ["git", "rev-list", "--count", "HEAD"],
        cwd=REPO,
        text=True,
    ).strip()
    iso = subprocess.check_output(
        ["git", "log", "-1", "--format=%cI", "HEAD"],
        cwd=REPO,
        text=True,
    ).strip()
    expected = f"{iso[:4]}.{int(iso[5:7])}.{count}"
    assert version.distribution_version() == expected


def test_from_plugin_root(monkeypatch):
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", "/cache/88plug/screen-mcp/2026.7.20")
    assert version.distribution_version() == "2026.7.20"


def test_calver_format(monkeypatch):
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    monkeypatch.delenv("GROK_PLUGIN_ROOT", raising=False)
    v = version.distribution_version()
    assert _CALVER.fullmatch(v), f"expected calver, got {v!r}"
