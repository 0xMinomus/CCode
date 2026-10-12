"""Pure unit tests for architecture-aware cursor-meta offset selection.

Does not import capture.py (that pulls GStreamer via gi at module load). Loads the
CURSOR_META_OFFSETS table + get_cursor_meta_offsets() by exec'ing that pure region
from source so pytest stays free of portal/display/GStreamer deps.
"""

from __future__ import annotations

import platform
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "capture.py"
_text = _SRC.read_text(encoding="utf-8")
_start = _text.index("CURSOR_META_OFFSETS = {")
_end = _text.index("\nclass _PyWrap")
_ns: dict = {"platform": platform, "sys": sys}
exec(compile(_text[_start:_end], str(_SRC), "exec"), _ns)  # noqa: S102 — load pure API under test
get_cursor_meta_offsets = _ns["get_cursor_meta_offsets"]
CURSOR_META_OFFSETS = _ns["CURSOR_META_OFFSETS"]


def test_x86_64_offsets_match_verified_abi():
    """Regression: do not break the x86-64 path (roi_type@16, x@28, y@32)."""
    assert get_cursor_meta_offsets("x86_64") == {"roi_type": 16, "x": 28, "y": 32}


def test_amd64_alias_same_as_x86_64():
    assert get_cursor_meta_offsets("amd64") == {"roi_type": 16, "x": 28, "y": 32}


def test_aarch64_and_arm64_lp64_match_x86_64():
    expected = {"roi_type": 16, "x": 28, "y": 32}
    assert get_cursor_meta_offsets("aarch64") == expected
    assert get_cursor_meta_offsets("arm64") == expected


def test_case_normalized():
    assert get_cursor_meta_offsets("X86_64") == get_cursor_meta_offsets("x86_64")


def test_unknown_arch_fails_open_and_logs_once(capsys):
    _ns["_CURSOR_META_OFFSETS_WARNED"] = False
    assert get_cursor_meta_offsets("riscv64") is None
    err = capsys.readouterr().err
    assert "riscv64" in err
    assert "disabled" in err
    # one-shot: second call is silent
    assert get_cursor_meta_offsets("riscv64") is None
    assert capsys.readouterr().err == ""


def test_host_arch_resolves_or_none():
    host = platform.machine().lower()
    off = get_cursor_meta_offsets()
    if host in CURSOR_META_OFFSETS:
        assert off == CURSOR_META_OFFSETS[host]
    else:
        assert off is None


def test_table_covers_common_arches():
    for k in ("x86_64", "amd64", "aarch64", "arm64"):
        assert k in CURSOR_META_OFFSETS
        assert set(CURSOR_META_OFFSETS[k]) == {"roi_type", "x", "y"}


def test_returned_dict_is_a_copy():
    a = get_cursor_meta_offsets("x86_64")
    a["x"] = 999
    assert get_cursor_meta_offsets("x86_64")["x"] == 28
