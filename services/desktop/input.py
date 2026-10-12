"""input.py — pointer/keyboard injection for mcp-screen (v1.2).

Drives the xdg-desktop-portal RemoteDesktop session that `state` owns. All public
tool entry points (move/click/scroll/drag/key/type_text) resolve their coordinates to
global NATIVE composite pixels (the same space screenshots live in), map those to the
per-stream LOGICAL coordinate space PipeWire/the portal expect, and emit Notify* calls.

Coordinate mapping (the important part):
  NotifyPointerMotionAbsolute coords are in the *stream's* LOGICAL space, per-stream,
  keyed by node_id. Under fractional scaling the logical size = native size / scale.
  We therefore divide the in-monitor native offset by that monitor's scale and add the
  monitor's logical origin (lpx/lpy). This replaces the old native-px + relative-motion
  remainder hack entirely — no COORD_MODE, no NotifyPointerMotion fixup."""

import os
import time
import shutil
import subprocess
from typing import Any, cast

import state
import awareness
import uinput_backend as ui  # kernel-level absolute-pointer path (preferred when available)


def _use_uinput():
    """Prefer the uinput backend when it's available AND we know the desktop bounds (so the
    ABS range can be mapped 1:1 to native px). The portal path remains the fallback."""
    return (
        ui.available() and bool(state.SESSION.get("W")) and bool(state.SESSION.get("H"))
    )


def _stamp_input():
    """Record that we just injected input, so a screenshot taken right after settles the
    frame first. App-agnostic: any post-action capture (not just verify=true) waits for the
    UI to stop changing instead of grabbing a pre-change / mid-transition frame."""
    state.SESSION["last_input_t"] = time.monotonic()


# gi.repository is imported in a try/except so the pure-math helpers below
# (resolve_xy, global_to_logical, _keysym, _char_keysym) stay importable on a box
# without PyGObject — making them unit-testable. Portal-emitting functions will
# raise AttributeError on `GLib`/`Gio` being None if you actually try to use them
# without gi installed; the math helpers never touch them.
try:
    from gi.repository import GLib, Gio
except Exception:  # pragma: no cover - host-dependent
    GLib = cast(Any, None)
    Gio = cast(Any, None)

# Linux input event button codes.
BTN = {"left": 0x110, "right": 0x111, "middle": 0x112}

# How far (global native px) the live pointer may sit from where WE last commanded it
# before we treat it as the user having taken the mouse. Calibrated against the residual
# between a commanded move and the position the compositor reports back.
GUARD_THRESH = int(os.environ.get("MCP_SCREEN_GUARD_PX", "40"))

# A STATIC monitor's cursor-metadata sample never refreshes (cursor_pos(prefer_node=...)
# returns it "regardless of freshness" by design). Without a staleness cutoff, guard_user
# compares our own varying commanded positions against ONE frozen point forever: it false-
# fires identically on every subsequent action once tripped, AND blocks capture's own
# _nudge_prime (which calls guard_user() before priming a fresh frame) from ever refreshing
# that sample — a self-sustaining false-positive loop. Confirmed live 2026-07-03: repeated
# STOPPED errors reporting the IDENTICAL "live" position across many unrelated clicks.
GUARD_STALE_S = float(os.environ.get("MCP_SCREEN_GUARD_STALE_S", "3.0"))

# How long read_selection waits for the app to put a selection on the clipboard. Polled, not
# slept: a fixed delay overcharges every fast app and false-negatives every slow one.
SELECTION_TIMEOUT_S = float(os.environ.get("MCP_SCREEN_SELECTION_TIMEOUT_S", "1.5"))


class UserControlError(RuntimeError):
    """Raised when the live pointer has drifted off where we last commanded it — the user
    grabbed the mouse, so we stop rather than fight them for the pointer."""


class StaleViewError(RuntimeError):
    """Raised when a view-space click carries a view_id that an intervening screenshot has
    superseded — the coords would map through the wrong transform. Tells the caller to
    re-screenshot rather than click blind."""


class FocusDriftError(StaleViewError):
    """Raised when a focus/window-activation happened after the bound view was captured.
    Root-caused 2026-07-24: raising a window (extension ActivateWindow, or the no-extension
    overview-search fallback) can silently change which window sits at the screenshot's
    coordinates — clicking those coordinates then lands on whatever the focus call raised,
    not the window that was actually screenshotted. A subclass of StaleViewError so every
    existing `except StaleViewError` catch site handles this the same way, with no changes
    needed there."""


def guard_user(force=False):
    """Stop if the user took the mouse. Compares the live pointer (read from the screencast
    cursor metadata) to the last position WE commanded; raises UserControlError if they
    diverge by more than GUARD_THRESH. Fails OPEN (returns quietly) when force is set, when
    we haven't moved yet this session, or when the cursor can't be read."""
    if force:
        return
    cmd = state.SESSION.get("cmd_cursor")
    if cmd is None:
        return
    import capture  # lazy: capture imports state, not input — no cycle

    # Pin the read to the SAME node we last commanded, so we compare like-for-like. Without
    # this, cursor_pos() returns the freshest sample across ALL monitors, which on a static
    # target is a DIFFERENT monitor's position — a cross-monitor compare that trips the 40px
    # threshold spuriously and aborts a correctly-positioned action.
    node = state.SESSION.get("cmd_node")
    # A stale-beyond-trust sample can't tell us the user moved anything — it's frozen from
    # whenever this monitor last painted, not "now." Treat it the same as "can't be read":
    # fail open rather than compare our own commanded moves against a fixed old point.
    age = capture.cursor_sample_age(node)
    if age is not None and age > GUARD_STALE_S:
        return
    live = (
        capture.cursor_pos(prefer_node=node)
        if node is not None
        else capture.cursor_pos()
    )
    if live is None:
        return
    # Fail OPEN on a cross-monitor reading: if the live sample resolved to a different monitor
    # than the one we commanded, we can't compare meaningfully (stale METADATA cursor on a
    # static target) — don't treat that as user takeover.
    if node is not None:
        geo = {m["node"]: m for m in (state.SESSION.get("geo") or [])}
        m = geo.get(node)
        if m and not (
            m["x"] <= live[0] < m["x"] + m["w"] and m["y"] <= live[1] < m["y"] + m["h"]
        ):
            return
    if abs(live[0] - cmd[0]) > GUARD_THRESH or abs(live[1] - cmd[1]) > GUARD_THRESH:
        raise UserControlError(
            f"user moved the mouse to {live}; I last left it at {cmd}. Stopping so I don't "
            f"fight you for the pointer — re-issue with force=true to take control back."
        )


# ---------------------------------------------------------------------------
# Thin Notify* wrappers (state.bus.call_sync against the RemoteDesktop iface)
# ---------------------------------------------------------------------------
def _notify_motion(node, lx, ly):
    state.bus.call_sync(
        state.PORTAL,
        state.OBJ,
        state.RD,
        "NotifyPointerMotionAbsolute",
        GLib.Variant(
            "(oa{sv}udd)",
            (state.SESSION["handle"], {}, int(node), float(lx), float(ly)),
        ),
        None,
        Gio.DBusCallFlags.NONE,
        -1,
        None,
    )


def _notify_button(code, btn_state):
    state.bus.call_sync(
        state.PORTAL,
        state.OBJ,
        state.RD,
        "NotifyPointerButton",
        GLib.Variant(
            "(oa{sv}iu)", (state.SESSION["handle"], {}, int(code), int(btn_state))
        ),
        None,
        Gio.DBusCallFlags.NONE,
        -1,
        None,
    )
    _stamp_input()


def _notify_axis(axis, step):
    state.bus.call_sync(
        state.PORTAL,
        state.OBJ,
        state.RD,
        "NotifyPointerAxisDiscrete",
        GLib.Variant("(oa{sv}ui)", (state.SESSION["handle"], {}, int(axis), int(step))),
        None,
        Gio.DBusCallFlags.NONE,
        -1,
        None,
    )
    _stamp_input()


def _notify_axis_px(dx, dy, finish=False):
    """Smooth-scroll by a PIXEL delta (NotifyPointerAxis). Electron/Chromium apps (Slack, VS
    Code, browsers) honor smooth pixel scroll reliably but often IGNORE single discrete
    notches — that's why the old AxisDiscrete(step=1) path no-op'd in Slack. `finish=True`
    flushes the smooth-scroll sequence so the app applies it (a kinetic-scroll requirement)."""
    opts = {"finish": GLib.Variant("b", True)} if finish else {}
    state.bus.call_sync(
        state.PORTAL,
        state.OBJ,
        state.RD,
        "NotifyPointerAxis",
        GLib.Variant(
            "(oa{sv}dd)", (state.SESSION["handle"], opts, float(dx), float(dy))
        ),
        None,
        Gio.DBusCallFlags.NONE,
        -1,
        None,
    )
    _stamp_input()


def _notify_keysym(ks, key_state):
    state.bus.call_sync(
        state.PORTAL,
        state.OBJ,
        state.RD,
        "NotifyKeyboardKeysym",
        GLib.Variant(
            "(oa{sv}iu)", (state.SESSION["handle"], {}, int(ks), int(key_state))
        ),
        None,
        Gio.DBusCallFlags.NONE,
        -1,
        None,
    )
    _stamp_input()


def _notify_keycode(kc, key_state):
    """Inject a raw evdev KEYCODE (not keysym). Primary keyboard path: Mutter reverse-maps
    keysyms to keycodes against the active layout, which is fragile and silently drops keys in
    some apps (the bug that made typing/Ctrl+K no-op). Keycodes go straight through. Mirrors
    what the leading GNOME-Wayland tools (computer-use-linux) settled on."""
    state.bus.call_sync(
        state.PORTAL,
        state.OBJ,
        state.RD,
        "NotifyKeyboardKeycode",
        GLib.Variant(
            "(oa{sv}iu)", (state.SESSION["handle"], {}, int(kc), int(key_state))
        ),
        None,
        Gio.DBusCallFlags.NONE,
        -1,
        None,
    )
    _stamp_input()


# ---------------------------------------------------------------------------
# Coordinate mapping
# ---------------------------------------------------------------------------
def global_to_logical(Gx, Gy):
    """Map global NATIVE composite px (Gx,Gy) — the space screenshots use — to the
    (node, logical_x, logical_y) the portal's NotifyPointerMotionAbsolute expects.

    Picks the monitor whose native rect contains the point (fallback: first monitor),
    then divides the in-monitor native offset by that monitor's scale and adds the
    monitor's logical origin. If geo has no lpx/lpy, the logical origin defaults to the
    native origin divided by scale."""
    geo = state.SESSION["geo"]
    m = None
    if not geo:
        raise RuntimeError(
            "no monitor geometry yet — nothing has probed the desktop in this session. "
            "Take a screenshot (or call screen_list_monitors) first; batch tools must "
            "prime geo before injecting input."
        )
    for cand in geo:
        if (
            cand["x"] <= Gx < cand["x"] + cand["w"]
            and cand["y"] <= Gy < cand["y"] + cand["h"]
        ):
            m = cand
            break
    if m is None:
        m = geo[0]
    sx = m.get("sx", 1.0) or 1.0
    sy = m.get("sy", 1.0) or 1.0
    # NotifyPointerMotionAbsolute coords are LOCAL to the stream (0..monitor_logical_size);
    # the node id selects the monitor. Do NOT add the global logical origin (lpx/lpy) — that
    # overflows the stream's logical width and the portal clamps it ("Invalid position").
    logical_x = (Gx - m["x"]) / sx
    logical_y = (Gy - m["y"]) / sy
    return (m["node"], logical_x, logical_y)


def resolve_xy(args):
    """Resolve a tool's (x,y) to global NATIVE desktop px.

    space='view' (default): x,y are pixels in the last screenshot; map through
        state.SESSION['view'] {ox,oy,scale}: desktop = (ox + x/scale, oy + y/scale).
    space='desktop': x,y are raw global native px.
    space='norm': x,y in [0,1000] of the last view's rendered size; normalize to view px
        first (using the view's rendered dimensions dw*scale x dh*scale), then to desktop."""
    space = args.get("space", "view")
    x, y = float(args["x"]), float(args["y"])
    v = state.SESSION.get("view")

    # Stale-view guard: if the caller bound these coords to a specific screenshot (view_id) and a
    # LATER screenshot has since rebound the view transform, refuse rather than silently mapping
    # through the wrong origin/scale (which lands on the wrong spot — wrong monitor, even). Only
    # enforced for view/norm space (desktop coords are absolute, transform-independent).
    if space in ("view", "norm"):
        want = args.get("view_id")
        if (
            want is not None
            and v
            and v.get("id") is not None
            and int(want) != int(v["id"])
        ):
            raise StaleViewError(
                f"coords reference screenshot view#{want} but the current view is "
                f"view#{v['id']} (a later screenshot rebound the transform). Re-screenshot "
                f"and click with the fresh view's coords + view_id."
            )
        # Window-stacking-drift guard: a focus/activate-window call (screen_focus, or a
        # focus= kwarg on this same action) can raise a DIFFERENT window over the same
        # screen region without changing the view's scale/origin at all — the check above
        # only catches a REBOUND transform, not a reshuffled window stack under an
        # unchanged one. _do_focus flips this flag on every raise attempt; only a fresh
        # screenshot (which re-establishes ground truth for whatever is now on top) clears
        # it. Root-caused 2026-07-24: this is exactly why clicks landed on the wrong
        # browser window/tab during live use.
        if v and state.SESSION.get("focus_changed_since_view"):
            raise FocusDriftError(
                "a window focus/activation happened after this screenshot was taken — "
                "the window under these coordinates may no longer be the one you saw. "
                "Re-screenshot after focusing, then click the fresh coordinates."
            )

    if space == "desktop":
        return int(round(x)), int(round(y))

    if space == "norm":
        if not v:
            return int(round(x)), int(round(y))
        # rendered view size = desktop size * downscale factor
        rw = v["dw"] * v["scale"]
        rh = v["dh"] * v["scale"]
        vx = (x / 1000.0) * rw
        vy = (y / 1000.0) * rh
        return int(round(v["ox"] + vx / v["scale"])), int(
            round(v["oy"] + vy / v["scale"])
        )

    # space == 'view'
    if v:
        return int(round(v["ox"] + x / v["scale"])), int(
            round(v["oy"] + y / v["scale"])
        )
    return int(round(x)), int(round(y))


def _goto(Gx, Gy):
    node, lx, ly = global_to_logical(Gx, Gy)
    # Send the absolute move TWICE with a short settle. A single NotifyPointerMotionAbsolute to
    # a never-damaged (static) monitor can be coalesced/dropped; the second carries even if the
    # first was swallowed, so the positionless button/axis that follows lands at the target.
    _notify_motion(node, lx, ly)
    if GLib is not None:
        GLib.usleep(8000)
    _notify_motion(node, lx, ly)
    # Guard baseline = the COMMANDED coords, full stop. We do NOT read the cursor back: with
    # cursor_mode=METADATA the position only updates on a fresh screencast frame, so on a static
    # monitor the readback is stale (often resolving to the WRONG monitor's last sample). Using
    # that stale value as the baseline made guard_user() false-fire and silently abort the next
    # click/scroll — the core bug behind "clicks/scroll do nothing." Commanded coords are exact
    # for our own moves; real user takeover is still caught by guard_user's own (node-pinned) read.
    state.SESSION["cmd_cursor"] = (int(Gx), int(Gy))
    state.SESSION["cmd_node"] = node


def _set_cmd(Gx, Gy):
    """Record the COMMANDED pointer position AND its monitor node, for the takeover guard. The
    node matters: guard_user pins its (stale-prone) cursor readback to cmd_node and FAILS OPEN on
    a cross-monitor reading. The uinput input paths used to set only cmd_cursor — so on a static
    monitor (where the readback resolves to a DIFFERENT, live monitor) the guard's cross-monitor
    fail-open was skipped and it FALSE-FIRED, which also aborted capture's _nudge_prime (it calls
    guard_user) → stale frames. Always set both."""
    try:
        node, _lx, _ly = global_to_logical(int(Gx), int(Gy))
    except Exception:
        node = state.SESSION.get("cmd_node")
    state.SESSION["cmd_cursor"] = (int(Gx), int(Gy))
    state.SESSION["cmd_node"] = node


def _ok(text):
    return {"content": [{"type": "text", "text": text}]}


def _ok_uinput(text):
    """Like _ok, but appends uinput's fractional-scale miscalibration warning (if any) into
    the visible response instead of leaving it only in the internal log — a caller trusting
    a clean '[uinput]' success string used to have no way to know the click/move might be
    off-target on a fractionally-scaled monitor."""
    warn = ui.fractional_scale_warning()
    if warn:
        text = f"{text} — WARN: {warn}"
    return _ok(text)


# ---------------------------------------------------------------------------
# Public tool entry points
# ---------------------------------------------------------------------------
def move(args):
    Gx, Gy = resolve_xy(args)
    if _use_uinput() and ui.move(Gx, Gy):
        _set_cmd(Gx, Gy)
        _stamp_input()
        return _ok_uinput(f"moved to desktop ({Gx},{Gy}) [uinput]")
    _goto(Gx, Gy)
    return _ok(f"moved to desktop ({Gx},{Gy})")


def click(args):
    button = args.get("button", "left")
    have_xy = "x" in args or "y" in args
    Gx = Gy = None
    if have_xy:
        Gx, Gy = resolve_xy(args)
    # Preferred: kernel-level absolute click — the pointer JUMPS to the native pixel and the
    # button presses there, so it lands exactly regardless of monitor/scaling/static state.
    if _use_uinput():
        gx, gy = (Gx, Gy) if have_xy else (state.SESSION.get("cmd_cursor") or (0, 0))
        if ui.click(
            gx, gy, button=button, double=bool(args.get("double")), in_place=not have_xy
        ):
            if have_xy:
                _set_cmd(Gx, Gy)
            _stamp_input()
            return _ok_uinput(
                f"clicked {button} {('(' + str(Gx) + ',' + str(Gy) + ')') if have_xy else '(in place)'} [uinput]"
            )
    # Fallback: portal path.
    btn = BTN.get(button, 0x110)
    if have_xy:
        _goto(Gx, Gy)
        GLib.usleep(30000)
        where = f"({Gx},{Gy})"
    else:
        where = "(in place)"
    for _ in range(2 if args.get("double") else 1):
        _notify_button(btn, 1)
        GLib.usleep(20000)
        _notify_button(btn, 0)
        GLib.usleep(20000)
    return _ok(f"clicked {button} {where}")


SCROLL_PX = int(
    os.environ.get("MCP_SCREEN_SCROLL_PX", "120")
)  # px per notch (one wheel step)


def scroll(args):
    # Scroll is POSITIONLESS — it acts wherever the pointer is. Position over the target first:
    # explicit x,y, else the center of the last view (the area the agent is looking at).
    if "x" in args and "y" in args:
        Gx, Gy = resolve_xy(args)
    elif state.SESSION.get("view"):
        v = state.SESSION["view"]
        Gx, Gy = int(v["ox"] + v["dw"] / 2), int(v["oy"] + v["dh"] / 2)
    else:
        Gx, Gy = state.SESSION.get("cmd_cursor") or (0, 0)
    direction = args.get("direction", "down")
    amount = int(args.get("amount", 3))
    horizontal = direction in ("left", "right")
    sign = 1 if direction in ("down", "right") else -1
    # Preferred: kernel-level hi-res wheel at (Gx,Gy). The uinput abs-pointer positions exactly
    # and the wheel events (120/notch hi-res + legacy) are what Electron/Chromium actually honor.
    if _use_uinput():
        dy = sign * amount if not horizontal else 0
        dx = sign * amount if horizontal else 0
        if ui.scroll(Gx, Gy, dy_notches=dy, dx_notches=dx, at=True):
            _set_cmd(Gx, Gy)
            _stamp_input()  # ui.scroll repositions the pointer to (Gx,Gy)
            return _ok_uinput(f"scrolled {direction} x{amount} [uinput hi-res]")
    # Fallback: portal smooth pixel axis.
    _goto(Gx, Gy)
    GLib.usleep(20000)
    try:
        for i in range(amount):
            ddx, ddy = (sign * SCROLL_PX, 0) if horizontal else (0, sign * SCROLL_PX)
            _notify_axis_px(ddx, ddy, finish=(i == amount - 1))
            GLib.usleep(15000)
        return _ok(f"scrolled {direction} x{amount} ({amount * SCROLL_PX}px smooth)")
    except Exception:
        axis = 1 if horizontal else 0
        for _ in range(amount):
            _notify_axis(axis, sign)
            GLib.usleep(15000)
        return _ok(f"scrolled {direction} x{amount} (discrete)")


def _mod_codes(args):
    """Map a `modifiers` arg (["shift"], or "shift+ctrl") to evdev keycodes, dropping any
    token we can't map. Returns (codes, label) — label echoes what actually got held so a
    silently-dropped modifier can't look like it was applied."""
    raw = args.get("modifiers") or ()
    if isinstance(raw, str):
        raw = [p for p in raw.replace("-", "+").split("+") if p.strip()]
    codes, names = [], []
    for tok in raw:
        kc = _KC_MODS.get(str(tok).strip().lower())
        if kc is not None:
            codes.append(kc)
            names.append(str(tok).strip().lower())
    return codes, "+".join(names)


def drag(args):
    sp = args.get("space", "view")
    vid = args.get("view_id")
    x1, y1 = resolve_xy({"x": args["x1"], "y": args["y1"], "space": sp, "view_id": vid})
    x2, y2 = resolve_xy({"x": args["x2"], "y": args["y2"], "space": sp, "view_id": vid})
    mods, mod_label = _mod_codes(args)
    held = f" holding {mod_label}" if mod_label else ""
    if _use_uinput() and ui.drag(
        x1, y1, x2, y2, button=args.get("button", "left"), mods=mods
    ):
        _set_cmd(x2, y2)
        _stamp_input()
        return _ok_uinput(f"dragged ({x1},{y1})->({x2},{y2}){held} [uinput]")
    btn = BTN.get(args.get("button", "left"), 0x110)
    try:
        for kc in mods:
            _notify_keycode(kc, 1)
        if mods:
            GLib.usleep(12000)  # let the modifier latch before the press
        _goto(x1, y1)
        GLib.usleep(20000)
        _notify_button(btn, 1)
        GLib.usleep(40000)
        steps = 10
        for i in range(1, steps + 1):
            _goto(
                int(round(x1 + (x2 - x1) * i / steps)),
                int(round(y1 + (y2 - y1) * i / steps)),
            )
            GLib.usleep(15000)
        GLib.usleep(40000)
        _notify_button(btn, 0)
    finally:
        for kc in reversed(
            mods
        ):  # ALWAYS release — a stuck modifier poisons later keys
            try:
                _notify_keycode(kc, 0)
            except Exception:
                pass
    return _ok(f"dragged ({x1},{y1})->({x2},{y2}){held}")


# ---------------------------------------------------------------------------
# Keyboard
# ---------------------------------------------------------------------------
SPECIAL = {
    "enter": 0xFF0D,
    "return": 0xFF0D,
    "tab": 0xFF09,
    "backspace": 0xFF08,
    "esc": 0xFF1B,
    "escape": 0xFF1B,
    "space": 0x20,
    "delete": 0xFFFF,
    "up": 0xFF52,
    "down": 0xFF54,
    "left": 0xFF51,
    "right": 0xFF53,
    "home": 0xFF50,
    "end": 0xFF57,
    "pageup": 0xFF55,
    "pagedown": 0xFF56,
}
MODS = {
    "ctrl": 0xFFE3,
    "control": 0xFFE3,
    "alt": 0xFFE9,
    "shift": 0xFFE1,
    "super": 0xFFEB,
    "meta": 0xFFE7,
    "cmd": 0xFFEB,
}

# --- Linux evdev keycodes (from <linux/input-event-codes.h>) ----------------
# The portal's NotifyKeyboardKeycode wants raw evdev codes. This is the reliable path on
# Mutter (the keysym path is layout-reverse-mapped and drops keys). KEY_LEFTSHIFT etc.
KC_LEFTSHIFT = 42
_KC_MODS = {
    "ctrl": 29,
    "control": 29,
    "alt": 56,
    "shift": 42,
    "super": 125,
    "meta": 125,
    "cmd": 125,
    "rightctrl": 97,
    "rightalt": 100,
}
_KC_SPECIAL = {
    "enter": 28,
    "return": 28,
    "tab": 15,
    "backspace": 14,
    "esc": 1,
    "escape": 1,
    "space": 57,
    "delete": 111,
    "up": 103,
    "down": 108,
    "left": 105,
    "right": 106,
    "home": 102,
    "end": 107,
    "pageup": 104,
    "pagedown": 109,
    "insert": 110,
}
# Unshifted character -> evdev keycode (US QWERTY). Shifted variants resolve via _SHIFTED_TO_BASE.
_KC_CHAR = {
    "a": 30,
    "b": 48,
    "c": 46,
    "d": 32,
    "e": 18,
    "f": 33,
    "g": 34,
    "h": 35,
    "i": 23,
    "j": 36,
    "k": 37,
    "l": 38,
    "m": 50,
    "n": 49,
    "o": 24,
    "p": 25,
    "q": 16,
    "r": 19,
    "s": 31,
    "t": 20,
    "u": 22,
    "v": 47,
    "w": 17,
    "x": 45,
    "y": 21,
    "z": 44,
    "1": 2,
    "2": 3,
    "3": 4,
    "4": 5,
    "5": 6,
    "6": 7,
    "7": 8,
    "8": 9,
    "9": 10,
    "0": 11,
    "-": 12,
    "=": 13,
    "[": 26,
    "]": 27,
    "\\": 43,
    ";": 39,
    "'": 40,
    "`": 41,
    ",": 51,
    ".": 52,
    "/": 53,
    " ": 57,
    "\t": 15,
    "\n": 28,
}
# Shifted ASCII char -> (base unshifted char) on US QWERTY.
_SHIFTED = {
    "A": "a",
    "B": "b",
    "C": "c",
    "D": "d",
    "E": "e",
    "F": "f",
    "G": "g",
    "H": "h",
    "I": "i",
    "J": "j",
    "K": "k",
    "L": "l",
    "M": "m",
    "N": "n",
    "O": "o",
    "P": "p",
    "Q": "q",
    "R": "r",
    "S": "s",
    "T": "t",
    "U": "u",
    "V": "v",
    "W": "w",
    "X": "x",
    "Y": "y",
    "Z": "z",
    "!": "1",
    "@": "2",
    "#": "3",
    "$": "4",
    "%": "5",
    "^": "6",
    "&": "7",
    "*": "8",
    "(": "9",
    ")": "0",
    "_": "-",
    "+": "=",
    "{": "[",
    "}": "]",
    "|": "\\",
    ":": ";",
    '"': "'",
    "~": "`",
    "<": ",",
    ">": ".",
    "?": "/",
}


def _char_to_keycode(ch):
    """ASCII char -> (keycode, needs_shift) on US QWERTY, or (None, False) if unmappable."""
    if ch in _KC_CHAR:
        return _KC_CHAR[ch], False
    if ch in _SHIFTED:
        return _KC_CHAR[_SHIFTED[ch]], True
    return None, False


def _key_to_keycode(name):
    """A key token (combo part) -> evdev keycode, or None if we can't map it (caller falls
    back to the keysym path). Handles modifiers, named specials, single chars, and F-keys."""
    n = name.lower()
    if n in _KC_MODS:
        return _KC_MODS[n]
    if n in _KC_SPECIAL:
        return _KC_SPECIAL[n]
    if len(name) == 1:
        kc, _shift = _char_to_keycode(name.lower())
        return kc
    if n.startswith("f") and n[1:].isdigit():
        fn = int(n[1:])
        if 1 <= fn <= 10:  # F1..F10 = 59..68
            return 58 + fn
        if 11 <= fn <= 12:  # F11=87, F12=88
            return 76 + fn
    return None


def _keysym(name):
    n = name.lower()
    if n in SPECIAL:
        return SPECIAL[n]
    if n in MODS:
        return MODS[n]
    if len(name) == 1:
        return ord(name)
    if n.startswith("f") and n[1:].isdigit():  # F1..  -> 0xFFBE + n-1
        return 0xFFBE + int(n[1:]) - 1
    raise ValueError(f"unknown key: {name}")


def _char_keysym(ch):
    if ch == "\n":
        return 0xFF0D
    if ch == "\t":
        return 0xFF09
    o = ord(ch)
    if o > 0x7F:  # X11 unicode keysym convention
        return 0x01000000 + o
    return o


def key(args):
    combo = args["keys"]
    parts = [p.strip() for p in combo.replace("-", "+").split("+")]
    # When modifiers are present, lowercase single-letter trailing keys before mapping
    # to a keysym. ord("A") = 0x41 is the X11 keysym for CAPITAL A, which the portal
    # presses with an implicit Shift — so "Ctrl+A" would arrive as Ctrl+Shift+a (e.g.
    # Firefox opens the Add-ons Manager instead of selecting all). Standalone single
    # letters (no modifier) keep their case so `key("A")` still types 'A' via implicit
    # Shift — that's the legacy behavior we want to preserve. Callers who want a capital
    # in a combo write "shift+a" explicitly.
    # Primary path: raw evdev keycodes (reliable on Mutter). With a keycode we don't need the
    # case-lowering hack — Shift is an explicit keycode, not implied by an uppercase keysym.
    codes = [_key_to_keycode(p) for p in parts]
    if all(c is not None for c in codes):
        if _use_uinput() and ui.key_codes(
            codes
        ):  # kernel-level — bypasses focus quirks
            _stamp_input()
            return _ok(f"pressed {combo} [uinput]")
        for c in codes:  # press in order
            _notify_keycode(c, 1)
        GLib.usleep(20000)
        for c in reversed(codes):  # release in reverse
            _notify_keycode(c, 0)
        return _ok(f"pressed {combo}")
    # Fallback: keysym path (legacy) for any token we couldn't map to a keycode.
    has_mod = any(p.lower() in MODS for p in parts)
    if has_mod:
        parts = [p.lower() if len(p) == 1 else p for p in parts]
    syms = [_keysym(p) for p in parts]
    for s in syms:
        _notify_keysym(s, 1)
    GLib.usleep(20000)
    for s in reversed(syms):
        _notify_keysym(s, 0)
    return _ok(f"pressed {combo}")


def read_selection(a):
    """Copy the focused window's current selection and return it VERBATIM.

    The lossless read path. OCR sees a 4K frame downscaled to 2576px, which measurably drops
    ~8% of characters on sub-12px code (and costs seconds of grounding); a copy is exact and
    costs milliseconds. Select in the app first (click, drag, or select_all=True), then call
    this instead of screenshotting text you need character-accurate.

    `combo` defaults to ctrl+c — TERMINALS need ctrl+shift+c, where a bare ctrl+c sends SIGINT
    to the foreground process instead of copying. Pass it explicitly for terminal windows.

    THE CLIPBOARD IS CLEARED BEFORE THE COMBO IS SENT, and that is load-bearing, not tidiness.
    Reading it without clearing cannot distinguish "the app copied a selection" from "the app
    ignored the combo and the clipboard still holds what it held before" — the first live test
    of this tool hit exactly that: a TUI swallowed the drag so no selection existed, the copy
    was a no-op, and the caller got the user's PRIOR clipboard contents returned as though they
    had been read off the screen. Clearing first makes an empty read unambiguous proof that
    nothing was copied. The user's clipboard is saved and restored in a `finally` regardless."""
    if not shutil.which("wl-paste") or not shutil.which("wl-copy"):
        return _ok("clipboard read unavailable: wl-clipboard not installed")
    combo = str(a.get("combo") or "ctrl+c")
    prev = None
    try:
        r = subprocess.run(["wl-paste", "--no-newline"], capture_output=True, timeout=2)
        if r.returncode == 0:
            prev = r.stdout
    except Exception:
        prev = None
    try:
        # Clear FIRST so a stale clipboard can never masquerade as a fresh copy.
        subprocess.run(["wl-copy", "--clear"], timeout=2)
        GLib.usleep(40000)
        if a.get("select_all"):
            key({"keys": "ctrl+a"})
            GLib.usleep(60000)
        key({"keys": combo})
        # WAIT for the clipboard to actually fill, don't guess how long the app needs.
        # A fixed sleep here was wrong in both directions: it charged every fast app the
        # full delay, and any app slower than it read back EMPTY — which, now that we clear
        # first, is indistinguishable from "nothing was copied" and gets reported as a
        # false negative. Clearing first is what makes polling sound: non-empty can only
        # mean this copy landed.
        got = ""
        deadline = time.monotonic() + SELECTION_TIMEOUT_S
        while True:
            r = subprocess.run(
                ["wl-paste", "--no-newline"], capture_output=True, timeout=2
            )
            got = r.stdout.decode("utf-8", "replace") if r.returncode == 0 else ""
            if got.strip() or time.monotonic() >= deadline:
                break
            GLib.usleep(15000)
    except Exception as ex:  # noqa: BLE001 — fail-open like the rest of the input path
        return _ok(f"clipboard read failed: {ex}")
    finally:
        try:  # ALWAYS restore — the app's text must not outlive this call
            if prev is not None:
                subprocess.run(["wl-copy"], input=prev, timeout=2)
            else:
                subprocess.run(["wl-copy", "--clear"], timeout=2)
        except Exception:
            pass
    if not got.strip():
        return _ok(
            f"NOTHING COPIED via {combo} — the clipboard was empty after the combo, so no "
            f"selection was taken (nothing selected, or the app ignores that combo). "
            f"Terminals need combo='ctrl+shift+c'; a TUI that grabs the mouse (Claude Code, "
            f"vim, htop) swallows drag-select, so hold Shift while dragging to force a real "
            f"terminal selection. Read the screen instead if that fails."
        )
    return _ok(f"selection ({len(got)} chars, exact — no OCR):\n{got}")


def _clip_paste(text):
    """Set the Wayland clipboard to `text`, paste it with Ctrl+V, then restore the prior
    clipboard. This is how we type UNICODE: the per-char keysym path can't emit non-ASCII
    through the RemoteDesktop portal, but a paste carries any text faithfully. Returns True
    on success, False if wl-copy is missing or the copy fails (caller falls back to keysyms).

    The restore runs in a `finally` so a portal-side paste failure can never leave `text`
    (often a password / token) sitting in the user's clipboard. If we couldn't read the
    prior clipboard, we actively `--clear` rather than leaving our text behind."""
    if not shutil.which("wl-copy"):
        return False
    prev = None  # best-effort save of the user's clipboard
    try:
        r = subprocess.run(["wl-paste", "--no-newline"], capture_output=True, timeout=2)
        if r.returncode == 0:
            prev = r.stdout
    except Exception:
        prev = None
    try:
        subprocess.run(["wl-copy"], input=text.encode("utf-8"), timeout=2, check=True)
    except Exception:
        return False  # we never wrote the clipboard -> nothing to undo
    try:
        GLib.usleep(40000)
        key({"keys": "ctrl+v"})  # paste through the portal
        GLib.usleep(140000)  # let the app consume it before we restore
        return True
    except Exception:
        return False
    finally:
        # ALWAYS run — success or failure — so the sensitive text never outlives this call.
        try:
            if prev is not None:
                subprocess.run(["wl-copy"], input=prev, timeout=2)
            else:
                subprocess.run(["wl-copy", "--clear"], timeout=2)
        except Exception:
            pass


def type_text(args):
    text = args["text"]
    # DEFAULT: real per-char keystrokes — the only faithful path for EVERY focused
    # surface (terminals/readline where Ctrl+V is quoted-insert, vim insert mode,
    # password fields), and it never touches the user's clipboard. Non-ASCII must go
    # via paste because keycodes/keysyms are ASCII-only. Paste is otherwise OPT-IN
    # (`paste=True`) — use it only when the target is known to be a plain text field
    # (browser input, address bar) where the atomic paste avoids the per-char
    # keycode reorder seen on fast typing into reactive fields; it is NOT safe as a
    # blanket default (breaks terminals, can't confirm the app consumed the paste,
    # and exposes secrets to clipboard managers).
    needs_paste = any(ord(ch) > 0x7F for ch in text)  # unicode: keycodes can't emit it
    if (needs_paste or args.get("paste")) and _clip_paste(text):
        if args.get("enter"):
            _notify_keycode(28, 1)
            GLib.usleep(8000)
            _notify_keycode(28, 0)
        return _ok(f"typed {len(text)} chars (clipboard)")
    # Per-char path (default). Kernel-level uinput keycodes first (most reliable;
    # bypasses focus quirks), else the portal keysym path below.
    if _use_uinput():
        seq = [_char_to_keycode(ch) for ch in text]
        if all(kc is not None for kc, _s in seq):
            if ui.type_codes(seq):
                if args.get("enter"):
                    ui.key_codes([28])
                _stamp_input()
                return _ok(f"typed {len(text)} chars [uinput]")
    # Portal path: per-char evdev keycodes (+ Shift held for shifted chars). Any char we can't
    # map to a keycode falls back to the keysym emitter for that char.
    for ch in text:
        kc, shift = _char_to_keycode(ch)
        if kc is None:
            _notify_keysym(_char_keysym(ch), 1)
            GLib.usleep(8000)
            _notify_keysym(_char_keysym(ch), 0)
            GLib.usleep(8000)
            continue
        if shift:
            _notify_keycode(KC_LEFTSHIFT, 1)
            GLib.usleep(4000)
        _notify_keycode(kc, 1)
        GLib.usleep(8000)
        _notify_keycode(kc, 0)
        if shift:
            GLib.usleep(4000)
            _notify_keycode(KC_LEFTSHIFT, 0)
        GLib.usleep(8000)
    if args.get("enter"):
        _notify_keycode(28, 1)
        GLib.usleep(8000)
        _notify_keycode(28, 0)
    return _ok(f"typed {len(text)} chars")


def activate_via_overview(name, settle_ms=700):
    """Fallback window activation with NO gnome-shell extension: open the GNOME overview (Super),
    type the app/window name into its search, Enter to focus/launch the match. Uses the same
    compositor-level keycode path as our keyboard tools — which lands reliably even on a static
    monitor (compositor shortcuts aren't routed to an app surface). This is the only focus lever
    before the extension is installed + the user has logged out/in once.

    Returns (issued, verified):
      issued   True once the Super+type+Enter sequence was actually sent (False only on a
               local exception, e.g. no `name`).
      verified True only if awareness.focused_window() came back AND its app/wm_class/title
               matches `name` — i.e. we have positive confirmation the RIGHT window was
               raised. False means either the extension is unavailable (can't check at all,
               the common case tonight) OR it IS available and reports a DIFFERENT window is
               focused (overview search picked the wrong match among several same-named
               windows) — either way, the caller must not treat this as a confirmed focus.

    Root-caused 2026-07-24: this used to unconditionally `return True` as soon as the
    keystrokes were sent, with zero check that the correct window (vs. another window of the
    same app — e.g. multiple Firefox windows) actually ended up focused. That produced
    real, repeated wrong-window clicks during live use."""
    if not name:
        return False, False
    try:
        key({"keys": "super"})
        GLib.usleep(settle_ms * 1000)
        # Per-char keystrokes (the default) — the overview search is a compositor
        # surface; the focus-recovery path must not depend on clipboard/Ctrl+V.
        type_text({"text": name})
        GLib.usleep(250000)
        key({"keys": "enter"})
        GLib.usleep(200000)
    except Exception:
        return False, False
    verified = False
    try:
        fw = awareness.focused_window()
        if fw:
            nl = name.lower()
            hay = f"{fw.get('app') or ''} {fw.get('wm_class') or ''} {fw.get('title') or ''}".lower()
            verified = nl in hay
    except Exception:
        verified = False
    return True, verified
