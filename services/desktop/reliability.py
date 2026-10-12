"""reliability.py — reliability layer for mcp-screen (v1.2).

Kills the two silent failure modes that make desktop automation flaky:
  1. Stale screenshots — acting on a frame that is mid-animation / not yet settled.
  2. Silent misclicks — a click/type that lands on nothing and produces no visible change.

This module provides the primitives, not an integrated pipeline — server.py's `_action`
composes them directly around every tool call: `wait_for_stable_frame` before/after,
`frame_hash`/`region_diff` to detect whether a click/type produced no visible change
(`_verify`, opt-in via `verify=true`), `needs_ack` as an opt-in ack gate before destructive
keystrokes, and `log_action` to append every call to a JSONL audit log. (An earlier
all-in-one `wrap_call` wrapper existed here but was never actually wired into the live
dispatch path — server.py always called handlers directly — so it was dead code; removed
2026-07-24 rather than kept as a second, diverging implementation of the same checks.)

Imports `state` only (state.SESSION{W,H,view}, state.log). The frame grabber is GIVEN to
us at call time as `grab(node) -> (w, h, RGBA ndarray)` — we never import capture, so this
module stays trivially unit-testable on synthetic numpy arrays. All numpy ops are kept
cheap (strided downsample, min-length flatten, single boolean reduction)."""

import os
import re
import json
import time
import hashlib

import numpy as np

import state


# ---------------------------------------------------------------------------
# Tunables (env-overridable starting points, not hard limits)
# ---------------------------------------------------------------------------
LOG_PATH = os.path.expanduser("~/.local/state/mcp-screen/actions.jsonl")

# Keystroke combos that close/kill a window — always worth an ack when the guard is on.
# `cmd+q` is here so the comment at the normalisation site below isn't a lie: aliases
# control+/command+ are mapped to ctrl+/cmd+ FIRST, then matched. (Bug: the prior set
# omitted cmd+q, so command+q slipped through ungated.)
_CLOSE_COMBOS = {"alt+f4", "ctrl+w", "ctrl+q", "cmd+q"}

# Destructive intent words; matched case-insensitively against OCR text near the target.
_DESTRUCTIVE = re.compile(
    r"\b(delete|remove|close|quit|submit|pay|purchase|confirm|send|discard|format)\b",
    re.IGNORECASE,
)

# Tools where a no-visible-change result is expected and must NOT raise a misclick warning.
_NO_NOOP_WARN = {
    "screen_screenshot",
    "screen_list_monitors",
    "screen_move_mouse",
    "screen_reload",
}


# ---------------------------------------------------------------------------
# Frame primitives (pure numpy — cheap, synthetic-array friendly)
# ---------------------------------------------------------------------------
def frame_hash(arr, ds=16):
    """Perceptual-ish fingerprint of a frame: downsample RGB to ~ds×ds, blake2b hex.

    Strided slicing (not interpolation) keeps this O(ds^2) regardless of frame size.
    Alpha is dropped so an opaque-vs-transparent flag never perturbs the hash. Returns an
    8-byte (16 hex char) digest — collision-cheap but tiny for the audit log."""
    a = np.asarray(arr)
    if a.ndim == 3 and a.shape[2] >= 3:
        a = a[..., :3]
    h = a.shape[0] if a.ndim >= 1 else 0
    w = a.shape[1] if a.ndim >= 2 else 0
    if h and w:
        step_y = max(1, h // ds)
        step_x = max(1, w // ds)
        small = a[::step_y, ::step_x]
    else:
        small = a
    small = np.ascontiguousarray(small, dtype=np.uint8)
    return hashlib.blake2b(small.tobytes(), digest_size=8).hexdigest()


def mean_abs_diff(a, b):
    """Mean absolute per-channel difference over RGB, 0..255.

    Flattens both frames' RGB to 1-D and compares over the shared min length, so frames
    of slightly different size (a resize mid-transition) still yield a sane scalar instead
    of throwing. Returns 0.0 when there is nothing to compare."""
    a = np.asarray(a)
    b = np.asarray(b)
    if a.ndim == 3 and a.shape[2] >= 3:
        a = a[..., :3]
    if b.ndim == 3 and b.shape[2] >= 3:
        b = b[..., :3]
    fa = a.reshape(-1)
    fb = b.reshape(-1)
    n = min(fa.shape[0], fb.shape[0])
    if n == 0:
        return 0.0
    # int16 subtraction avoids uint8 wraparound; mean over the shared prefix.
    diff = np.abs(fa[:n].astype(np.int16) - fb[:n].astype(np.int16))
    return float(diff.mean())


def wait_for_changed_frame(
    grab_fn,
    node,
    baseline_hash,
    interval=0.06,
    timeout=2.5,
    mode="poll",
    wait_fn=None,
    note_fn=None,
):
    """Poll grab_fn(node)[2] until its frame_hash DIFFERS from baseline_hash, or timeout.

    This is the anti-stale primitive for a damage-driven (static) monitor: after an action,
    `wait_for_stable_frame` is satisfied instantly by a REPEATED stale frame ("stable" != "new"),
    and a keepalive resend carries old pixels with a fresh timestamp — so neither stability nor
    PTS proves the capture reflects the action. A changed pixel-hash does. Returns
    (changed: bool, last_hash). On timeout returns (False, last_hash) so the caller still
    proceeds with whatever frame it has.

    `mode` selects the wake source (probes A/B). 'poll' is the default and is byte-identical
    to the original loop. 'event'/'hybrid' block on `wait_fn(remaining)` — an injected damage
    waiter — so no frame is grabbed or converted until damage actually lands; 'hybrid' still
    honours `interval` as a backstop so an absent event degrades to polling, never to a stall.
    `wait_fn`/`note_fn` are INJECTED (this module must not import capture — the grabber and now
    the waiter both come from the caller). Falls back to polling if no waiter is supplied."""
    deadline = time.monotonic() + timeout
    last = baseline_hash
    # Narrow to the callable itself, not a bool — a separate `evented` flag reads as
    # Optional at the call site below and is a real None-call risk, not just a type nit.
    waiter = wait_fn if mode in ("event", "hybrid") else None
    while True:
        try:
            last = frame_hash(grab_fn(node)[2])
        except Exception as ex:  # noqa: BLE001 — never crash the capture path
            state.log("wait_for_changed_frame: grab failed:", ex)
            return False, last
        if last != baseline_hash:
            return True, last
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            if note_fn:
                note_fn("timeouts")
            return False, last
        if waiter is None:
            time.sleep(min(interval, remaining))
            continue
        # Block for damage instead of burning a grab+convert+hash per interval. In hybrid the
        # wait is capped at `interval` so the loop still re-checks on its own if no event comes.
        budget = min(remaining, interval) if mode == "hybrid" else remaining
        if waiter(budget):
            if note_fn:
                note_fn("event_wakes")
        elif mode == "hybrid":
            if note_fn:
                note_fn("backstop_fires")


def wait_for_stable_frame(
    grab_fn, node, interval=0.10, window=2, timeout=2.5, thresh=0.5
):
    """Poll grab_fn(node)[2] until the frame stops changing, capping animation via timeout.

    "Stable" = `window` consecutive frame-to-frame mean_abs_diff values all below `thresh`.
    Returns (stable: bool, last_diff: float). On a frame that never settles (e.g. a spinner)
    we bail at `timeout` with stable=False and the most recent diff, so the caller still
    proceeds rather than hanging forever."""
    deadline = time.monotonic() + timeout
    try:
        prev = grab_fn(node)[2]
    except Exception as e:  # noqa: BLE001 — a grab failure shouldn't crash the action path
        state.log("wait_for_stable_frame: initial grab failed:", e)
        return False, float("inf")

    stable_run = 0
    last_diff = float("inf")
    while True:
        if interval > 0:
            time.sleep(interval)
        try:
            cur = grab_fn(node)[2]
        except Exception as e:  # noqa: BLE001
            state.log("wait_for_stable_frame: grab failed:", e)
            return False, last_diff
        last_diff = mean_abs_diff(prev, cur)
        prev = cur
        if last_diff < thresh:
            stable_run += 1
            if stable_run >= window:
                return True, last_diff
        else:
            stable_run = 0
        if time.monotonic() >= deadline:
            return False, last_diff


def region_diff(before, after, bbox, thresh=2.0):
    """Detect + localise change inside `bbox` between two frames.

    bbox = [x, y, w, h] in frame pixels (clipped to the frame). A pixel "changed" if its
    max per-channel abs diff exceeds `thresh`. Returns (changed: bool, changed_bbox | None)
    where changed_bbox is the TIGHT [x, y, w, h] (frame coords) enclosing changed pixels."""
    before = np.asarray(before)
    after = np.asarray(after)
    if before.ndim != 3 or after.ndim != 3:
        return False, None

    fh = min(before.shape[0], after.shape[0])
    fw = min(before.shape[1], after.shape[1])
    if fh == 0 or fw == 0:
        return False, None

    x, y, w, h = (int(round(v)) for v in bbox)
    x0 = max(0, min(x, fw))
    y0 = max(0, min(y, fh))
    x1 = max(x0, min(x + w, fw))
    y1 = max(y0, min(y + h, fh))
    if x1 <= x0 or y1 <= y0:
        return False, None

    b = before[y0:y1, x0:x1, :3].astype(np.int16)
    a = after[y0:y1, x0:x1, :3].astype(np.int16)
    # Max-channel abs diff per pixel, then threshold -> boolean change mask.
    mask = np.abs(a - b).max(axis=2) > thresh
    if not mask.any():
        return False, None

    rows = np.any(mask, axis=1)
    cols = np.any(mask, axis=0)
    ry0, ry1 = np.where(rows)[0][[0, -1]]
    cx0, cx1 = np.where(cols)[0][[0, -1]]
    changed_bbox = [
        int(x0 + cx0),
        int(y0 + ry0),
        int(cx1 - cx0 + 1),
        int(ry1 - ry0 + 1),
    ]
    return True, changed_bbox


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------
def log_action(rec):
    """Append one action record as a JSON line to ~/.local/state/mcp-screen/actions.jsonl.

    Schema keys: ts, tool, args, resolved_coords, pre_hash, post_hash, changed,
    changed_bbox, ms, warn. Best-effort: a logging failure must never break the action."""
    schema = (
        "ts",
        "tool",
        "args",
        "resolved_coords",
        "pre_hash",
        "post_hash",
        "changed",
        "changed_bbox",
        "ms",
        "warn",
    )
    out = {k: rec.get(k) for k in schema}
    # `setdefault` would no-op here because the dict-comp above pre-populates "ts"
    # to None when the caller didn't pass one — so the key exists but is empty.
    # Replace any None/missing ts with now() so every audit line is timestamped.
    if not out.get("ts"):
        out["ts"] = time.time()
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        with open(LOG_PATH, "a") as f:
            f.write(json.dumps(out, default=str) + "\n")
    except Exception as e:  # noqa: BLE001
        state.log("log_action: write failed:", e)


# ---------------------------------------------------------------------------
# Opt-in destructive-action guard
# ---------------------------------------------------------------------------
def needs_ack(tool, args, ocr_near_target):
    """Return a guard reason token if this action should require an explicit `ack`, else None.

    Off by default — only active when env MCP_SCREEN_GUARD=1. Reasons (first match wins):
      'window-close'   — screen_key combo in {alt+f4, ctrl+w, ctrl+q}
      'keyword:<word>' — a destructive verb appears in OCR text near the target
      'out-of-allowlist' — MCP_SCREEN_APPS is set and the focused app isn't in it
    The caller compares the returned token against args['ack'] to decide whether to block."""
    if os.environ.get("MCP_SCREEN_GUARD") != "1":
        return None

    # Allowlist gate: if configured, the focused app must be on it.
    allow = os.environ.get("MCP_SCREEN_APPS")
    if allow:
        apps = {a.strip() for a in allow.split(",") if a.strip()}
        if (args.get("_focused_app") or None) not in apps:
            return "out-of-allowlist"

    if tool == "screen_key":
        combo = str(args.get("keys", "")).lower().replace("-", "+").replace(" ", "")
        # Normalise modifier aliases so 'control+w' / 'cmd+q' map onto the close set.
        combo = combo.replace("control+", "ctrl+").replace("command+", "cmd+")
        if combo in _CLOSE_COMBOS:
            return "window-close"

    if ocr_near_target:
        m = _DESTRUCTIVE.search(ocr_near_target)
        if m:
            return f"keyword:{m.group(1).lower()}"

    return None
