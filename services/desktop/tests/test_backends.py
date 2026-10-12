"""X11 capture fallback + AT-SPI accelerator. Runs headless (both modules are gi-light).

Both are FALLBACK/OPTIONAL paths, so the contract under test is mostly about degrading
honestly: never raise, never claim availability that a real grab would not deliver, and
never let an empty AT-SPI tree be mistaken for an empty screen.
"""

import os
from typing import Any, cast

import pytest
from PIL import Image

import atspi_tree
import x11capture


# --- x11capture ------------------------------------------------------------------------


def test_no_display_means_unavailable(monkeypatch):
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.setattr(x11capture, "_PROBE", None)
    assert x11capture.display() is None
    assert x11capture.available() is False
    assert x11capture.geometry() == []
    assert x11capture.grab_root() is None


def test_env_kill_switch_wins(monkeypatch):
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(x11capture, "DISABLED", True)
    monkeypatch.setattr(x11capture, "_PROBE", None)
    assert x11capture.available() is False
    assert x11capture.grab_root() is None


def test_availability_is_a_real_probe_not_a_path_check(monkeypatch):
    """ "A grabber exists on PATH" is not "capture works": under Xwayland the root rejects
    XGetImage and ImageMagick fails too, which made a PATH-only check report available=True
    while every grab returned None."""
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(x11capture, "DISABLED", False)
    monkeypatch.setattr(x11capture, "_which_grabber", lambda: "import")
    monkeypatch.setattr(x11capture, "_pillow_ok", lambda: True)
    monkeypatch.setattr(x11capture, "grab_root", lambda: None)
    monkeypatch.setattr(x11capture, "_PROBE", None)
    assert x11capture.available() is False, "must probe, not trust PATH"


def test_availability_caches_and_rechecks(monkeypatch):
    calls = []

    def fake_grab():
        calls.append(1)
        # NON-black on purpose: availability now validates pixel content, because an
        # all-zero frame is exactly what rootless Xwayland returns without raising.
        return Image.new("RGB", (4, 4), (120, 30, 90))

    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(x11capture, "DISABLED", False)
    monkeypatch.setattr(x11capture, "grab_root", fake_grab)
    monkeypatch.setattr(x11capture, "_PROBE", None)
    assert x11capture.available() is True
    assert x11capture.available() is True
    assert len(calls) == 1, "probe must be cached"
    assert x11capture.available(recheck=True) is True
    assert len(calls) == 2, "recheck must re-probe"


def test_grab_region_clamps_inside_the_root(monkeypatch):
    """An out-of-bounds crop must not raise or return a wrong-sized image — callers pass
    caller-supplied coordinates straight through."""
    monkeypatch.setattr(
        x11capture, "grab_root", lambda: Image.new("RGB", (800, 600), (1, 2, 3))
    )
    im = x11capture.grab_region(700, 500, 999, 999)
    assert im is not None and im.size == (100, 100)
    im2 = x11capture.grab_region(-50, -50, 100, 100)
    assert im2 is not None and im2.size == (100, 100)
    tiny = x11capture.grab_region(0, 0, 0, 0)
    assert tiny is not None and tiny.size == (1, 1)


def test_geometry_parses_xrandr(monkeypatch):
    sample = (
        "Screen 0: minimum 320 x 200, current 3840 x 1080\n"
        "eDP-1 connected primary 1920x1080+0+0 (normal left inverted) 344mm x 194mm\n"
        "HDMI-1 connected 1920x1080+1920+0 (normal) 530mm x 300mm\n"
        "DP-2 disconnected (normal left inverted right x axis y axis)\n"
    )

    class _R:
        stdout = sample

    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(x11capture.shutil, "which", lambda _n: "/usr/bin/xrandr")
    monkeypatch.setattr(x11capture.subprocess, "run", lambda *a, **k: _R())
    geo = x11capture.geometry()
    assert geo == [
        {"x": 0, "y": 0, "w": 1920, "h": 1080},
        {"x": 1920, "y": 0, "w": 1920, "h": 1080},
    ], geo


def test_diag_never_raises(monkeypatch):
    monkeypatch.setattr(x11capture, "_PROBE", None)
    d = x11capture.diag()
    assert set(d) >= {"display", "available", "pillow_xcb", "external_grabber"}


# --- atspi_tree ------------------------------------------------------------------------


def test_disabled_by_env_returns_nothing(monkeypatch):
    monkeypatch.setattr(atspi_tree, "ENABLED", False)
    monkeypatch.setattr(atspi_tree, "_TRIED", False)
    monkeypatch.setattr(atspi_tree, "_ATSPI", None)
    assert atspi_tree.elements() == []


def test_missing_atspi_degrades_to_empty(monkeypatch):
    monkeypatch.setattr(atspi_tree, "_TRIED", True)
    monkeypatch.setattr(atspi_tree, "_ATSPI", None)
    assert atspi_tree.elements() == []
    assert atspi_tree.diag()["atspi_typelib"] is False


def test_diag_explains_why_the_tree_is_empty():
    """0 apps is the NORMAL case and must not read as "empty screen" — the note is the
    whole reason a caller does not misinterpret it."""
    d = atspi_tree.diag()
    assert "restart" in d["note"].lower()
    assert "toolkit_accessibility" in d


def test_zero_and_negative_extents_are_not_click_targets():
    """AT-SPI reports 0x0 or negative bounds for offscreen / unmapped widgets. Emitting
    those as targets would send clicks to (0,0) or off the desktop."""

    class _E:
        def __init__(self, x, y, w, h):
            self.x, self.y, self.width, self.height = x, y, w, h

    class _Node:
        def __init__(self, e):
            self._e = e

        def get_extents(self, _t):
            return self._e

    assert atspi_tree._extents(_Node(_E(0, 0, 0, 0))) is None
    assert atspi_tree._extents(_Node(_E(-5, 10, 20, 20))) is None
    assert atspi_tree._extents(_Node(_E(10, 20, 30, 40))) == (10, 20, 30, 40)


def test_extents_failure_is_swallowed():
    class _Bad:
        def get_extents(self, _t):
            raise RuntimeError("dbus went away")

    assert atspi_tree._extents(_Bad()) is None


@pytest.mark.parametrize("role", ["push button", "menu item", "entry", "link"])
def test_actionable_roles_cover_the_common_widgets(role):
    assert role in atspi_tree._ACTIONABLE


def test_structural_noise_is_not_actionable():
    for role in ("filler", "panel", "scroll pane", "separator"):
        assert role not in atspi_tree._ACTIONABLE


def test_node_and_depth_caps_are_bounded():
    """A browser's a11y bridge can expose an enormous tree, and this runs on the hot path."""
    assert 0 < atspi_tree.MAX_NODES <= 20000
    assert 0 < atspi_tree.MAX_DEPTH <= 100


def test_env_overrides_are_read():
    assert atspi_tree.MAX_NODES == int(
        os.environ.get("MCP_SCREEN_ATSPI_MAX_NODES", "1200")
    )


def test_atspi_bails_on_the_init_return_code(monkeypatch):
    """CORRECTED after measuring: `Atspi.init()` does NOT abort without a bus — it returns
    2 and only g_warning()s (verified: init() -> 2, exit 0). The abort lives in the NEXT
    call, `_atspi_bus()`, reached by every subsequent API.

    So the correct gate is the RETURN CODE, not a D-Bus name probe. It is also strictly
    better: a bus name can be owned while its socket is unreachable
    (AT_SPI_BUS_ADDRESS=unix:path=/nonexistent), which a NameHasOwner probe calls healthy
    and which then aborts."""
    monkeypatch.setattr(atspi_tree, "_TRIED", False)
    monkeypatch.setattr(atspi_tree, "_ATSPI", None)
    monkeypatch.setattr(atspi_tree, "ENABLED", True)

    import sys
    import types

    fake = cast(Any, types.ModuleType("gi.repository"))
    fake.Atspi = types.SimpleNamespace(init=lambda: 2, get_desktop=_must_not_call)
    monkeypatch.setitem(sys.modules, "gi.repository", fake)
    assert atspi_tree._atspi() is None, "a non-0/1 init status must abort the gate"


def _must_not_call(*_a, **_kw):
    raise AssertionError("must not touch the bus after a failed init()")


def test_toolkit_toggle_is_read_out_of_process(monkeypatch):
    """Gio.Settings.new() aborts when dconf is unavailable, so this must shell out and must
    tolerate the command being absent or failing."""
    monkeypatch.setattr(atspi_tree.shutil, "which", lambda _n: None)
    assert atspi_tree.toolkit_accessibility_enabled() is None

    class _R:
        returncode = 0
        stdout = "true\n"

    monkeypatch.setattr(atspi_tree.shutil, "which", lambda _n: "/usr/bin/gsettings")
    monkeypatch.setattr(atspi_tree.subprocess, "run", lambda *a, **k: _R())
    assert atspi_tree.toolkit_accessibility_enabled() is True

    class _Bad:
        returncode = 1
        stdout = "no schema"

    monkeypatch.setattr(atspi_tree.subprocess, "run", lambda *a, **k: _Bad())
    assert atspi_tree.toolkit_accessibility_enabled() is None


def test_geometry_does_not_depend_on_external_binaries(monkeypatch):
    """THE ZERO-MONITOR BUG. geometry() parsed `xrandr`, falling back to `xdpyinfo`.
    NEITHER binary exists on a normal GNOME desktop — measured on this host — so it
    returned [] on a two-monitor box and the X11 fallback could never have worked.
    mss reads XRandR in-process, so with no binaries at all we must still enumerate."""
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(x11capture.shutil, "which", lambda _n: None)  # no binaries
    monkeypatch.setattr(x11capture, "_MONS", None, raising=False)

    class _S:
        monitors = [
            {"left": 0, "top": 0, "width": 7680, "height": 2160},
            {"left": 3840, "top": 0, "width": 3840, "height": 2160, "output": "DP-1"},
            {"left": 0, "top": 0, "width": 3840, "height": 2160, "output": "DP-2"},
        ]

    monkeypatch.setattr(x11capture, "_mss", lambda cursor=False: _S())
    geo = x11capture.geometry()
    assert len(geo) == 2, f"must enumerate per-output with no binaries, got {geo}"
    assert {g["name"] for g in geo} == {"DP-1", "DP-2"}
    assert geo[0]["w"] == 3840


def test_availability_rejects_an_all_black_frame(monkeypatch):
    """On rootless Xwayland an XShm grab can return an ALL-ZERO image without raising, so
    an exception-only probe reports available=True and every frame is silently black."""
    black = Image.new("RGB", (256, 256), (0, 0, 0))
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(x11capture, "DISABLED", False)
    monkeypatch.setattr(x11capture, "grab_root", lambda: black)
    monkeypatch.setattr(x11capture, "_PROBE", None)
    assert x11capture.available() is False, (
        "an all-black frame is not a working capture"
    )

    real = Image.new("RGB", (256, 256), (0, 0, 0))
    real.putpixel((5, 5), (200, 10, 10))
    monkeypatch.setattr(x11capture, "grab_root", lambda: real)
    monkeypatch.setattr(x11capture, "_PROBE", None)
    assert x11capture.available() is True


def test_region_grab_is_server_side_when_mss_is_present(monkeypatch):
    """Root-grab-then-crop was ~15x more expensive on a 4K root. The region must be asked
    of X directly, so grab_root must NOT be consulted."""
    seen = {}

    def fake(x, y, w, h, cursor=False):
        seen["rect"] = (x, y, w, h)
        return Image.new("RGB", (w, h))

    def _boom():
        raise AssertionError("grab_root must not be used when a region grab works")

    monkeypatch.setattr(x11capture, "_mss_grab", fake)
    monkeypatch.setattr(x11capture, "grab_root", _boom)
    im = x11capture.grab_region(100, 50, 400, 300)
    assert im is not None and im.size == (400, 300)
    assert seen["rect"] == (100, 50, 400, 300)
