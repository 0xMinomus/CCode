"""Unit tests for reliability.py — focused on the ack-gate (the safety surface that
went from "advertised but dead code" to "wired into server._action" this session) plus
the audit log shape. The pure-frame primitives (frame_hash, mean_abs_diff, region_diff,
wait_for_stable_frame) are tested too — they were the only safe-to-use reliability
helpers before today's wiring and now back-stop the audit-log diff fields."""

import json

import numpy as np
import pytest

import reliability


# ---------------------------------------------------------------------------
# needs_ack — the ack gate that now actually fires from server._action
# ---------------------------------------------------------------------------
@pytest.fixture
def guard_on(monkeypatch):
    monkeypatch.setenv("MCP_SCREEN_GUARD", "1")
    monkeypatch.delenv("MCP_SCREEN_APPS", raising=False)


def test_needs_ack_returns_none_when_guard_disabled(monkeypatch):
    monkeypatch.delenv("MCP_SCREEN_GUARD", raising=False)
    assert reliability.needs_ack("screen_key", {"keys": "Ctrl+W"}, None) is None


def test_needs_ack_flags_window_close_combos(guard_on):
    for combo in ("ctrl+w", "Ctrl+W", "control-w", "Alt+F4", "cmd+q", "command+q"):
        assert (
            reliability.needs_ack("screen_key", {"keys": combo}, None) == "window-close"
        )


def test_needs_ack_ignores_non_close_combos(guard_on):
    for combo in ("ctrl+l", "ctrl+a", "ctrl+t", "Enter", "F5"):
        assert reliability.needs_ack("screen_key", {"keys": combo}, None) is None


def test_needs_ack_keyword_matches_destructive_ocr(guard_on):
    assert (
        reliability.needs_ack(
            "screen_click", {"x": 100, "y": 100}, "Delete account permanently"
        )
        == "keyword:delete"
    )
    assert (
        reliability.needs_ack("screen_click", {"x": 100, "y": 100}, "Pay $99 now")
        == "keyword:pay"
    )


def test_needs_ack_passes_benign_ocr(guard_on):
    assert (
        reliability.needs_ack("screen_click", {"x": 100, "y": 100}, "Open settings")
        is None
    )


def test_needs_ack_allowlist_blocks_out_of_app(monkeypatch):
    monkeypatch.setenv("MCP_SCREEN_GUARD", "1")
    monkeypatch.setenv("MCP_SCREEN_APPS", "firefox,terminal")
    # Allowlist check runs FIRST in needs_ack; non-matching focused app blocks every tool.
    assert (
        reliability.needs_ack(
            "screen_click", {"_focused_app": "chrome", "x": 1, "y": 1}, None
        )
        == "out-of-allowlist"
    )
    assert (
        reliability.needs_ack(
            "screen_click", {"_focused_app": "firefox", "x": 1, "y": 1}, None
        )
        is None
    )


# ---------------------------------------------------------------------------
# log_action — the audit trail that server._action now writes on every call
# ---------------------------------------------------------------------------
def test_log_action_writes_jsonl_record(monkeypatch, tmp_path):
    log_path = tmp_path / "actions.jsonl"
    monkeypatch.setattr(reliability, "LOG_PATH", str(log_path))
    reliability.log_action(
        {
            "tool": "screen_click",
            "args": {"x": 10, "y": 20},
            "resolved_coords": [10, 20],
            "ms": 7,
        }
    )
    lines = log_path.read_text().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["tool"] == "screen_click"
    assert rec["resolved_coords"] == [10, 20]
    assert rec["ms"] == 7
    # ts must be a real timestamp, not None — the prior `setdefault` no-opped because
    # the dict-comp pre-populates "ts" to None, leaving the key present-but-empty.
    assert isinstance(rec["ts"], (int, float)) and rec["ts"] > 0


def test_log_action_two_calls_append(monkeypatch, tmp_path):
    log_path = tmp_path / "actions.jsonl"
    monkeypatch.setattr(reliability, "LOG_PATH", str(log_path))
    reliability.log_action({"tool": "screen_key", "args": {"keys": "Enter"}})
    reliability.log_action({"tool": "screen_click", "args": {"x": 1, "y": 1}})
    assert len(log_path.read_text().splitlines()) == 2


def test_log_action_failure_is_swallowed(monkeypatch):
    """The audit log is a side-channel: any failure (disk full, permission denied) must
    NEVER raise from log_action — the action it's recording has already happened.
    /dev/null is a character device, not a directory, so os.makedirs(dirname=/dev/null)
    raises NotADirectoryError reliably across distros without touching the filesystem."""
    monkeypatch.setattr(reliability, "LOG_PATH", "/dev/null/cannot-write-here.jsonl")
    reliability.log_action({"tool": "x", "args": {}})  # must not raise


# ---------------------------------------------------------------------------
# Pure frame primitives
# ---------------------------------------------------------------------------
def test_frame_hash_is_deterministic_and_drops_alpha():
    rgb = np.zeros((32, 32, 3), dtype=np.uint8)
    rgba = np.zeros((32, 32, 4), dtype=np.uint8)
    rgba[..., 3] = 200
    h1 = reliability.frame_hash(rgb)
    h2 = reliability.frame_hash(rgba)
    assert h1 == h2 and len(h1) == 16  # alpha ignored; 8-byte hex digest


def test_frame_hash_changes_with_content():
    a = np.zeros((32, 32, 3), dtype=np.uint8)
    b = a.copy()
    b[10:20, 10:20] = 255
    assert reliability.frame_hash(a) != reliability.frame_hash(b)


def test_mean_abs_diff_extremes():
    a = np.zeros((10, 10, 3), dtype=np.uint8)
    b = np.full((10, 10, 3), 255, dtype=np.uint8)
    assert reliability.mean_abs_diff(a, a) == 0.0
    assert reliability.mean_abs_diff(a, b) == 255.0


def test_mean_abs_diff_handles_size_mismatch():
    a = np.zeros((10, 10, 3), dtype=np.uint8)
    b = np.zeros((20, 20, 3), dtype=np.uint8)
    assert reliability.mean_abs_diff(a, b) == 0.0  # shared prefix, no raise


def test_region_diff_localises_change_inside_bbox():
    a = np.zeros((40, 40, 3), dtype=np.uint8)
    b = a.copy()
    b[10:18, 12:22] = 255  # 8x10 block changed
    changed, bbox = reliability.region_diff(a, b, [5, 5, 30, 30])
    assert changed is True
    assert bbox == [12, 10, 10, 8]  # tight to the changed pixels


def test_region_diff_returns_false_when_no_change():
    a = np.zeros((40, 40, 3), dtype=np.uint8)
    changed, bbox = reliability.region_diff(a, a, [0, 0, 40, 40])
    assert changed is False and bbox is None


def test_region_diff_clamps_bbox_to_frame():
    a = np.zeros((20, 20, 3), dtype=np.uint8)
    # bbox extends way past the frame; function must clip, not raise.
    changed, _ = reliability.region_diff(a, a, [-50, -50, 1000, 1000])
    assert changed is False


def test_wait_for_stable_frame_settles_quickly_on_constant_frames():
    frame = np.zeros((10, 10, 3), dtype=np.uint8)
    stable, last = reliability.wait_for_stable_frame(
        lambda _node: (10, 10, frame), node=0, interval=0, window=2, timeout=1.0
    )
    assert stable is True and last == 0.0


def test_wait_for_stable_frame_times_out_on_animation():
    counter = {"n": 0}

    def grab(_node):
        counter["n"] += 1
        f = np.full((10, 10, 3), (counter["n"] * 30) % 255, dtype=np.uint8)
        return (10, 10, f)

    stable, last = reliability.wait_for_stable_frame(
        grab, node=0, interval=0, window=2, timeout=0.1, thresh=1.0
    )
    assert stable is False  # never settled


def test_wait_for_stable_frame_handles_initial_grab_failure():
    def grab(_node):
        raise RuntimeError("portal down")

    stable, last = reliability.wait_for_stable_frame(
        grab, node=0, interval=0, timeout=0.05
    )
    assert stable is False  # fails open, no raise


# --- probes A/B: event-driven wake for the post-action change-gate ---


def _changing_grab(flip_after):
    """grab_fn that returns a constant frame until `flip_after` calls, then a different one.
    Counts calls so a probe can be scored on grabs-per-wait."""
    n = {"calls": 0}

    def grab(_node):
        n["calls"] += 1
        v = 0 if n["calls"] <= flip_after else 200
        return (10, 10, np.full((10, 10, 3), v, dtype=np.uint8))

    return grab, n


def test_wait_for_changed_frame_poll_mode_detects_change():
    grab, n = _changing_grab(flip_after=2)
    base = reliability.frame_hash(grab(0)[2])
    changed, _ = reliability.wait_for_changed_frame(
        grab, node=0, baseline_hash=base, interval=0, timeout=1.0
    )
    assert changed is True


def test_wait_for_changed_frame_event_mode_grabs_only_on_damage():
    """Probe A: with a waiter that reports damage, the loop must not burn a grab per interval."""
    grab, n = _changing_grab(flip_after=2)
    base = reliability.frame_hash(grab(0)[2])
    n["calls"] = 0
    waits = {"n": 0}

    def wait_fn(_budget):
        waits["n"] += 1
        return True  # damage every time

    changed, _ = reliability.wait_for_changed_frame(
        grab,
        node=0,
        baseline_hash=base,
        interval=0,
        timeout=1.0,
        mode="event",
        wait_fn=wait_fn,
    )
    assert changed is True
    assert (
        n["calls"] == 3
    )  # two unchanged grabs, then the changed one — one per damage event
    assert waits["n"] == 2


def test_wait_for_changed_frame_event_mode_falls_back_to_poll_without_waiter():
    grab, _n = _changing_grab(flip_after=1)
    base = reliability.frame_hash(grab(0)[2])
    changed, _ = reliability.wait_for_changed_frame(
        grab, node=0, baseline_hash=base, interval=0, timeout=1.0, mode="event"
    )
    assert changed is True  # no wait_fn injected => original poll behaviour


def test_wait_for_changed_frame_hybrid_counts_backstop_when_no_damage():
    """Probe B negative signal: no damage event arrives, so the poll floor carries the loop."""
    grab, _n = _changing_grab(flip_after=2)
    base = reliability.frame_hash(grab(0)[2])
    notes = []
    changed, _ = reliability.wait_for_changed_frame(
        grab,
        node=0,
        baseline_hash=base,
        interval=0,
        timeout=1.0,
        mode="hybrid",
        wait_fn=lambda _b: False,  # damage never arrives
        note_fn=notes.append,
    )
    assert changed is True
    assert "backstop_fires" in notes  # degraded to polling rather than stalling


def test_wait_for_changed_frame_times_out_and_notes_it():
    static = np.zeros((10, 10, 3), dtype=np.uint8)
    base = reliability.frame_hash(static)
    notes = []
    changed, _ = reliability.wait_for_changed_frame(
        lambda _n: (10, 10, static),
        node=0,
        baseline_hash=base,
        interval=0,
        timeout=0.05,
        mode="event",
        wait_fn=lambda _b: False,
        note_fn=notes.append,
    )
    assert changed is False
    assert notes == ["timeouts"]
