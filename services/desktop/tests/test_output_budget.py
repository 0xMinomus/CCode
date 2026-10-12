"""Client tool-output budget fitting.

Grok Build truncates an MCP tool result at 20KB. A base64 image cut mid-string fails its
integrity check and the whole image is dropped, so the model sees NOTHING — strictly worse
than a low-fidelity image. These tests pin the fitting behaviour and, critically, that the
default (Claude, uncapped) path stays a byte-for-byte no-op.
"""

import pytest


# conftest now imports the REAL capture against a stubbed gi, so these run everywhere.
# They exercise pure logic only (client-cap detection, the region/monitor translation) —
# anything that needs a live pipeline stays in test_capture_real.py behind REAL_STACK.

import budget  # noqa: E402
import server  # noqa: E402


@pytest.fixture
def restore_cap():
    prev = budget.MAX_OUT_KB
    yield
    budget.MAX_OUT_KB = prev


@pytest.mark.parametrize(
    "client,expected",
    [
        ("grok", 20),
        ("Grok Build", 20),
        ("claude-code", 0),
        ("Claude Code", 0),
        ("cursor", 0),
        ("", 0),
    ],
)
def test_client_cap_detection(client, expected, restore_cap, monkeypatch):
    monkeypatch.delenv("MCP_SCREEN_MAX_OUTPUT_KB", raising=False)
    budget.MAX_OUT_KB = 0
    server._apply_client_limits({"clientInfo": {"name": client}})
    assert budget.MAX_OUT_KB == expected


@pytest.mark.parametrize(
    "params",
    [{}, {"clientInfo": None}, {"clientInfo": {}}, {"clientInfo": {"name": None}}],
)
def test_malformed_handshake_does_not_raise(params, restore_cap, monkeypatch):
    monkeypatch.delenv("MCP_SCREEN_MAX_OUTPUT_KB", raising=False)
    budget.MAX_OUT_KB = 0
    server._apply_client_limits(params)
    assert budget.MAX_OUT_KB == 0


def test_explicit_env_override_beats_client_detection(restore_cap, monkeypatch):
    monkeypatch.setenv("MCP_SCREEN_MAX_OUTPUT_KB", "99")
    budget.MAX_OUT_KB = 99
    server._apply_client_limits({"clientInfo": {"name": "grok"}})
    assert budget.MAX_OUT_KB == 99


# --- region + monitor precedence -------------------------------------------------------


def test_region_with_monitor_is_translated_not_dropped(monkeypatch):
    """region+monitor used to silently return the WHOLE monitor. Both together must mean
    'this box, relative to that monitor's origin'."""
    import capture as cap

    geo = [
        {"node": 1, "x": 0, "y": 0, "w": 3840, "h": 2160, "live": True},
        {"node": 2, "x": 3840, "y": 0, "w": 3840, "h": 2160, "live": True},
    ]
    seen = {}

    monkeypatch.setattr(cap, "ensure_geo", lambda force=False: geo)
    monkeypatch.setattr(cap, "validate_scope", lambda *a, **k: None)
    monkeypatch.setattr(
        cap, "monitors_for", lambda r: (seen.update(region=r), [geo[0]])[1]
    )
    monkeypatch.setattr(cap.state, "SESSION", {"W": 7680, "H": 2160})

    class _Img:
        def crop(self, box):
            seen["crop"] = box
            return self

    monkeypatch.setattr(cap, "_full_canvas", lambda m: _Img())
    monkeypatch.setattr(
        cap, "grab", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("cold"))
    )

    cap.capture_desktop(region=[0, 0, 600, 300], monitor=1)
    assert seen["region"] == [3840, 0, 600, 300], (
        "region must be offset by monitor origin"
    )
    assert seen["crop"] == (3840, 0, 4440, 300)


def test_region_alone_is_desktop_absolute(monkeypatch):
    """The pre-existing contract: region with no monitor stays desktop-absolute."""
    import capture as cap

    geo = [{"node": 1, "x": 0, "y": 0, "w": 3840, "h": 2160, "live": True}]
    seen = {}
    monkeypatch.setattr(cap, "ensure_geo", lambda force=False: geo)
    monkeypatch.setattr(cap, "validate_scope", lambda *a, **k: None)
    monkeypatch.setattr(cap, "monitors_for", lambda r: (seen.update(region=r), [])[1])
    monkeypatch.setattr(cap.state, "SESSION", {"W": 3840, "H": 2160})
    with pytest.raises(RuntimeError):
        cap.capture_desktop(region=[10, 20, 600, 300])
    assert seen["region"] == [10, 20, 600, 300]
