"""pytest scaffolding for mcp-screen.

REAL-FIRST. The runtime modules (state.py, capture.py, input.py) import gi.repository at
module top and state.py opens a D-Bus session bus at import. Stubs let the pure-math tests
run headless — but a stub that ALWAYS wins means the shipped code is never executed by the
suite. Every capture bug this session (a read-only ndarray aliasing an unmapped GstBuffer, a
missed rename, a handler returning a bare str where the dispatcher indexes ["content"]) was
caught by driving the real desktop, because the tests could not reach that code at all.

So: try the real modules first, and install a stub ONLY for what genuinely will not import
here. `REAL_STACK` records the outcome so tests can gate on it — real coverage where a
desktop stack exists, clean skips in CI where it does not.
"""

import sys
import types
from typing import Any, cast

#: True when the real gi/GStreamer stack imported — set by _install_gi_stub().
REAL_STACK = False


def _real_gi_available():
    """Can we import the genuine gi + Gst + a live session bus? Only then is it safe to let
    tests touch capture/state for real."""
    try:
        import gi  # noqa: F401

        gi.require_version("Gst", "1.0")
        gi.require_version("Gio", "2.0")
        from gi.repository import Gio, Gst  # noqa: F401

        Gst.init(None if Gst.is_initialized() else [])
        Gio.bus_get_sync(Gio.BusType.SESSION, None)  # state.py does this at import
        return True
    except Exception:
        return False


def _install_gi_stub():
    global REAL_STACK
    if _real_gi_available():
        REAL_STACK = True
        return  # real gi/Gst/D-Bus present — do not shadow the shipped code
    if "gi" in sys.modules and "gi.repository" in sys.modules:
        return
    gi = cast(Any, types.ModuleType("gi"))
    gi.require_version = lambda *_a, **_kw: None
    repo = cast(Any, types.ModuleType("gi.repository"))

    class _GLib:
        @staticmethod
        def quark_from_string(_s):  # capture.py builds _CURSOR_QUARK at import
            return 1

        @staticmethod
        def usleep(_):
            return None

        @staticmethod
        def Variant(*_a, **_kw):
            return None

    class _Gio:
        class DBusCallFlags:
            NONE = 0

        class BusType:
            SESSION = 0

        @staticmethod
        def bus_get_sync(*_a, **_kw):
            return types.SimpleNamespace(
                get_unique_name=lambda: ":1.0",
                call_sync=lambda *_a, **_kw: None,
            )

    class _Gst:
        """Enough Gst for capture.py to IMPORT. Not enough to capture anything — the tests
        that reach a pipeline are still REAL_STACK-gated. The point is that capture's pure
        logic (validate_scope, the region/monitor translation, encode_store wiring) becomes
        reachable in CI instead of hiding behind a wholesale `capture` stub."""

        SECOND = 1_000_000_000

        class State:
            NULL = 0
            PLAYING = 4

        class PadProbeType:
            BUFFER = 1

        @staticmethod
        def init(_argv=None):
            return None

        @staticmethod
        def is_initialized():
            return True

        @staticmethod
        def parse_launch(*_a, **_kw):
            raise RuntimeError("stubbed Gst: no pipelines headless")

        class ElementFactory:
            @staticmethod
            def find(_name):
                return None

    repo.GLib = _GLib
    repo.Gio = _Gio
    repo.Gst = _Gst
    repo.GstApp = types.ModuleType("GstApp")
    sys.modules["gi"] = gi
    sys.modules["gi.repository"] = repo


def _install_state_stub():
    if REAL_STACK or "state" in sys.modules:
        return
    state = cast(Any, types.ModuleType("state"))
    state.SESSION = {}
    state.PORTAL = state.OBJ = state.RD = state.SC = ""
    state.bus = types.SimpleNamespace(call_sync=lambda *_a, **_kw: None)
    state.log = lambda *_a, **_kw: None
    sys.modules["state"] = state


def _install_capture_stub():
    """input.guard_user does a lazy `import capture`; stub it so importing input is enough.

    REAL-FIRST here too: try the genuine capture module against the gi stub above. It
    imports fine (its module-level work is just Gst.init + a quark), which puts its pure
    logic under test in CI. Only fall back to the 2-function stub if that fails."""
    if REAL_STACK or "capture" in sys.modules:
        return
    try:
        import capture  # noqa: F401

        return
    except Exception:
        pass
    cap = cast(Any, types.ModuleType("capture"))
    cap.cursor_pos = lambda *_a, **_kw: None
    cap.cursor_sample_age = lambda *_a, **_kw: None
    sys.modules["capture"] = cap


_install_gi_stub()
_install_state_stub()
_install_capture_stub()
