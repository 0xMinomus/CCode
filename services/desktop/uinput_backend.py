"""uinput_backend.py — kernel-level input injection for mcp-screen (v1.2).

WHY THIS EXISTS: the xdg-desktop-portal RemoteDesktop path injects pointer MOTION per
ScreenCast stream, and on a multi-monitor / damage-driven (static) setup that motion is
unreliable — absolute moves to an idle monitor get coalesced/dropped, so the positionless
button/axis that follow land at the wrong place. The fix the leading GNOME-Wayland tools
(agent-sh/computer-use-linux) use: a private uinput device exposing a TRUE absolute pointer
(ABS_X/ABS_Y) whose range equals the full native desktop. The compositor maps that range
across the whole logical layout, so writing ABS(x,y) makes the pointer JUMP to native pixel
(x,y) — exact, acceleration-free, scaling-free, monitor-state-independent. Clicks/scroll then
land where intended with no portal, no cursor-readback dependency.

Requires /dev/uinput writable (group `input`, udev rule) + python-evdev. If either is missing
this module reports unavailable and input.py falls back to the portal path. CPU-only, no GPU.
"""

import os
import time
import threading
from typing import Any, cast

try:
    import evdev
    from evdev import UInput, AbsInfo, ecodes as e
except Exception:  # pragma: no cover - evdev / kernel headers absent
    evdev = None
    UInput = cast(Any, None)
    AbsInfo = cast(Any, None)
    e = cast(Any, None)

_DEV = None
_LOCK = threading.Lock()
_W = _H = 0  # native desktop bounds the ABS range is mapped to

# Pointer button -> evdev code.
_BTN = {"left": 0x110, "right": 0x111, "middle": 0x112}  # BTN_LEFT/RIGHT/MIDDLE


def available():
    """True if we can inject via uinput (evdev importable + /dev/uinput writable)."""
    if evdev is None or os.environ.get("MCP_SCREEN_NO_UINPUT") == "1":
        return False
    return os.access("/dev/uinput", os.W_OK)


def _keycodes_needed():
    """Every KEY_* evdev code we might emit, so the device advertises them at create time
    (a uinput device can only emit keys declared in its capabilities)."""
    return list(range(1, 248))  # KEY_ESC(1)..KEY_MICMUTE(248): covers all standard keys


def ensure_device(w, h):
    """Create (once) ONE unified uinput device: absolute pointer (ABS_X/Y over the full
    desktop) + buttons + keyboard + relative wheel (hi-res + legacy), tagged INPUT_PROP_POINTER.

    Unified ON PURPOSE (was two devices): Chromium/Electron resolve a scroll's target at
    wl_pointer.frame time via the seat's CURRENT pointer-focused surface, set only by a prior
    enter from pointer motion. A separate wheel device whose own pointer never moved has no
    focus, so Chromium drops the axis (GTK is laxer — hence 'terminal scrolls, Slack doesn't').
    With one device, the abs-move that positions the cursor and the wheel that follows share the
    same seat pointer, so the scroll lands on the focused surface. INPUT_PROP_POINTER makes
    libinput classify the ABS+REL mix as a screen-mapped pointer rather than a touchpad."""
    global _DEV, _W, _H
    if not available():
        return None
    with _LOCK:
        if _DEV is not None and (_W, _H) == (w, h):
            return _DEV
        try:
            if _DEV is not None:
                _DEV.close()
        except Exception:
            pass
        _DEV = None
        cap = {
            e.EV_KEY: [_BTN["left"], _BTN["right"], _BTN["middle"]]
            + _keycodes_needed(),
            e.EV_ABS: [
                # resolution=1 unit/px: libinput treats an abs device with no resolution as
                # buggy; 1 unit/px keeps the axis in pixel units mapped 1:1 to the desktop.
                (
                    e.ABS_X,
                    AbsInfo(
                        value=0, min=0, max=max(1, w - 1), fuzz=0, flat=0, resolution=1
                    ),
                ),
                (
                    e.ABS_Y,
                    AbsInfo(
                        value=0, min=0, max=max(1, h - 1), fuzz=0, flat=0, resolution=1
                    ),
                ),
            ],
            e.EV_REL: [
                e.REL_WHEEL,
                e.REL_WHEEL_HI_RES,
                e.REL_HWHEEL,
                e.REL_HWHEEL_HI_RES,
            ],
        }
        try:
            dev = UInput(
                cap,
                name="mcp-screen-pointer",
                version=0x1,
                input_props=[e.INPUT_PROP_POINTER],
            )
        except TypeError:
            # older python-evdev without input_props kwarg — create without the prop bit
            dev = UInput(cap, name="mcp-screen-pointer", version=0x1)
        except Exception:
            return None
        _DEV, _W, _H = dev, w, h
        # NOTE: the ABS range is in NATIVE px. Mutter maps an absolute device across the LOGICAL
        # layout extent — equal to native ONLY when every monitor is scale=1.0 (the case here).
        # Under fractional scaling, native != logical and abs clicks would land off by
        # x*(1-1/scale). This used to only reach an internal log file the caller never read, so
        # click()/move() reported clean "[uinput]" success while known-miscalibrated — see
        # fractional_scale_warning(), which move()/click() in input.py now surface into the
        # tool's own returned text.
        scale_warn = fractional_scale_warning()
        if scale_warn:
            try:
                import state as _st

                _st.log("WARN uinput: " + scale_warn)
            except Exception:
                pass
        time.sleep(0.4)  # let udev/libinput enumerate before the first event
        return _DEV


def fractional_scale_warning():
    """None if every known monitor is scale 1.0; otherwise a short warning string that
    uinput absolute clicks/moves on a fractionally-scaled monitor may land off-target
    (native ABS range vs. the compositor's logical layout). Callers (input.py's move/click)
    append this to their own success text instead of leaving it only in the internal log,
    so an agent relying on a clean 'clicked ... [uinput]' response is actually told when
    that response is known-miscalibrated."""
    try:
        import state as _st

        bad = [
            g
            for g in (_st.SESSION.get("geo") or [])
            if (g.get("sx") or 1.0) != 1.0 or (g.get("sy") or 1.0) != 1.0
        ]
        if bad:
            return (
                f"{len(bad)} monitor(s) have fractional scale; uinput abs-click mapping "
                f"assumes native==logical (scale 1.0) — this click/move may be offset"
            )
    except Exception:
        pass
    return None


def _abs_move(dev, x, y):
    x = max(0, min(int(x), _W - 1))
    y = max(0, min(int(y), _H - 1))
    dev.write(e.EV_ABS, e.ABS_X, x)
    dev.write(e.EV_ABS, e.ABS_Y, y)
    dev.syn()


def move(x, y):
    dev = ensure_device(*_bounds())
    if dev is None:
        return False
    with _LOCK:
        _abs_move(dev, x, y)
    return True


def click(x, y, button="left", double=False, in_place=False):
    dev = ensure_device(*_bounds())
    if dev is None:
        return False
    code = _BTN.get(button, _BTN["left"])
    with _LOCK:
        if not in_place:
            # Focus-wake: land at an OFFSET pixel, then the target — so the compositor sees a
            # real pointer-motion transition (a leave→enter), which Chromium/Electron require to
            # route the click to the surface/row under the cursor. NOTE: two abs-writes to the
            # SAME pixel emit only ONE motion event (the kernel coalesces identical ABS values),
            # so the old "move to (x,y) twice" produced no second motion and didn't re-arm hover.
            # Offsetting by a few px guarantees two distinct motion events.
            ox = x + 6 if x + 6 < _W else x - 6
            oy = y + 6 if y + 6 < _H else y - 6
            _abs_move(dev, ox, oy)
            time.sleep(0.05)
            _abs_move(dev, x, y)
            time.sleep(0.06)
        for _ in range(2 if double else 1):
            dev.write(e.EV_KEY, code, 1)
            dev.syn()
            time.sleep(
                0.035
            )  # hold (matches the proven reference recipe; 20ms can be coalesced)
            dev.write(e.EV_KEY, code, 0)
            dev.syn()
            time.sleep(0.04)
    return True


def scroll(x, y, dy_notches=0, dx_notches=0, at=True):
    """Scroll dy/dx in wheel notches at (x,y). Emits hi-res (120/notch) + legacy wheel so both
    Electron and classic apps respond. Positive dy = down convention is handled by caller sign."""
    dev = ensure_device(*_bounds())
    if dev is None:
        return False
    with _LOCK:
        if at:
            # Position the pointer over the target pane so Chromium gets a wl_pointer.enter and
            # sets focus on that surface — required or it drops the scroll frame. Move twice
            # (a static monitor can need a beat to route the cross-monitor jump).
            _abs_move(dev, x, y)
            time.sleep(0.05)
            _abs_move(dev, x, y)
            time.sleep(0.08)
        steps = max(abs(dy_notches), abs(dx_notches))
        vy = 1 if dy_notches > 0 else -1 if dy_notches < 0 else 0
        vx = 1 if dx_notches > 0 else -1 if dx_notches < 0 else 0
        # Emit on the SAME device as the pointer (so the axis is attributed to the focused
        # surface). Per notch: REL_WHEEL_HI_RES ±120 + legacy REL_WHEEL ±1 in one SYN frame —
        # a real hi-res mouse. Chromium v8+ takes axis_value120; legacy keeps GTK/older happy.
        for _ in range(steps):
            if vy:
                dev.write(e.EV_REL, e.REL_WHEEL_HI_RES, vy * 120)
                dev.write(e.EV_REL, e.REL_WHEEL, vy)
            if vx:
                dev.write(e.EV_REL, e.REL_HWHEEL_HI_RES, vx * 120)
                dev.write(e.EV_REL, e.REL_HWHEEL, vx)
            dev.syn()
            time.sleep(0.02)
    return True


def drag(x1, y1, x2, y2, button="left", steps=20, mods=()):
    """Press-drag, optionally holding `mods` (evdev keycodes) for the WHOLE gesture.

    Shift+drag is the reason this exists: a TUI that enables mouse tracking (Claude Code,
    vim, htop) consumes the drag itself, so no terminal-level selection is ever made and a
    copy afterwards returns nothing. Holding Shift makes the terminal emulator bypass the
    app's mouse grab and do its own selection instead. Modifiers press inside the same
    _LOCK as the drag so nothing interleaves, and release in a `finally` — a stuck Shift
    would corrupt every keystroke that follows."""
    dev = ensure_device(*_bounds())
    if dev is None:
        return False
    code = _BTN.get(button, _BTN["left"])
    with _LOCK:
        try:
            for m in mods:
                dev.write(e.EV_KEY, int(m), 1)
                dev.syn()
            if mods:
                time.sleep(0.012)  # let the modifier latch propagate before the press
            _abs_move(dev, x1, y1)
            time.sleep(0.03)
            dev.write(e.EV_KEY, code, 1)
            dev.syn()
            time.sleep(0.04)
            for i in range(1, steps + 1):
                _abs_move(dev, x1 + (x2 - x1) * i / steps, y1 + (y2 - y1) * i / steps)
                time.sleep(0.012)
            time.sleep(0.04)
            dev.write(e.EV_KEY, code, 0)
            dev.syn()
        finally:
            for m in reversed(list(mods)):  # ALWAYS release — a stuck modifier is worse
                try:
                    dev.write(e.EV_KEY, int(m), 0)
                    dev.syn()
                except Exception:
                    pass
    return True


def key_codes(codes):
    """Press a chord of evdev keycodes, release in reverse. Treats the LAST code as the key and
    the rest as modifiers, with a STAGGER: a real keyboard has ms between pressing Ctrl and the
    key, but writing Ctrl-down and K-down back-to-back lands them in one dispatch batch — Mutter
    can deliver the keydown to the app BEFORE the modifier latch propagates, so the app sees a
    plain 'K' (ctrlKey=false) and the shortcut (e.g. Ctrl+K quick switcher) never fires. Single
    keys work because there's no modifier to latch first. The ~12ms stagger fixes it."""
    dev = ensure_device(*_bounds())
    if dev is None:
        return False
    mods, key = (codes[:-1], codes[-1:]) if len(codes) > 1 else ([], codes)
    with _LOCK:
        for c in mods:  # press modifiers first
            dev.write(e.EV_KEY, int(c), 1)
            dev.syn()
        if mods:
            time.sleep(0.012)  # let the modifier latch propagate before the key
        for c in key:
            dev.write(e.EV_KEY, int(c), 1)
            dev.syn()
        time.sleep(0.03)  # hold
        for c in reversed(key):
            dev.write(e.EV_KEY, int(c), 0)
            dev.syn()
        if mods:
            time.sleep(0.008)
        for c in reversed(mods):  # release modifiers last
            dev.write(e.EV_KEY, int(c), 0)
            dev.syn()
        time.sleep(0.01)
    return True


def type_codes(seq):
    """Type a sequence of (keycode, needs_shift) tuples. Shift is held around shifted chars.

    This is the DEFAULT typing path (faithful on every surface; never touches the clipboard).
    Inter-key gaps are ~12ms: at 6ms, adjacent keycodes could land in one Mutter dispatch
    batch and be delivered out of order (observed character reordering on longer strings), the
    same latch-race key_codes() guards against. Callers wanting atomic entry into a known
    plain text field can opt into clipboard paste via type_text(paste=True)."""
    dev = ensure_device(*_bounds())
    if dev is None:
        return False
    SHIFT = 42  # KEY_LEFTSHIFT
    with _LOCK:
        for kc, shift in seq:
            if shift:
                dev.write(e.EV_KEY, SHIFT, 1)
                dev.syn()
                time.sleep(0.006)
            dev.write(e.EV_KEY, int(kc), 1)
            dev.syn()
            time.sleep(0.012)
            dev.write(e.EV_KEY, int(kc), 0)
            dev.syn()
            if shift:
                time.sleep(0.006)
                dev.write(e.EV_KEY, SHIFT, 0)
                dev.syn()
            time.sleep(0.012)
    return True


def _bounds():
    """Native desktop bounds (W,H) from the session geometry; (0,0) if unknown."""
    import state

    return int(state.SESSION.get("W") or 0), int(state.SESSION.get("H") or 0)


def diag():
    return {
        "available": available(),
        "evdev": evdev is not None,
        "uinput_writable": os.access("/dev/uinput", os.W_OK) if evdev else False,
        "device": bool(_DEV),
        "bounds": [_W, _H],
    }


def shutdown():
    global _DEV
    with _LOCK:
        try:
            if _DEV is not None:
                _DEV.close()
        except Exception:
            pass
        _DEV = None
