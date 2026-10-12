"""x11capture.py — X11 screen capture without the portal or PipeWire.

Why this exists: the portal ScreenCast path is not always available. Measured on a real
GNOME/**X11** box (Zorin OS 15.3): `xdg-desktop-portal` absent, 0 ScreenCast/RemoteDesktop
interfaces on the session bus, GStreamer 1.14 with no appsink `leaky-type`. None of that is
"X11" per se — but on such a host our normal pipeline cannot run at all, while plain X11
capture works fine. `/dev/uinput` was writable there too, so INPUT already works unchanged;
only capture needed a second path.

gi-free by design (same rule as budget.py / reliability.py) so CI can execute it: it imports
only stdlib + Pillow. No new dependencies — every grabber here is either Pillow, which is
already a hard dep, or a binary that was already present on the target host.

This is a FALLBACK, not a replacement. It has no damage-driven streaming, no cursor
metadata, and no per-monitor PipeWire nodes; it grabs whole-root pixels on demand.
"""

import os
import re
import shutil
import subprocess
import tempfile

from PIL import Image

#: Opt out entirely (e.g. to force the portal path for debugging).
DISABLED = os.environ.get("MCP_SCREEN_NO_X11", "") == "1"

_GRAB_TIMEOUT_S = float(os.environ.get("MCP_SCREEN_X11_TIMEOUT", "10"))


def display():
    """The X display to target, or None when there is no X11 at all."""
    return os.environ.get("DISPLAY") or None


_PROBE = None


def available(recheck=False):
    """True only when a grab ACTUALLY succeeds — cached after the first probe.

    "A grabber is on PATH" is not the same as "capture works". Under Xwayland the root
    window rejects XGetImage (BadMatch) and ImageMagick fails too, so a PATH-only check
    reported available=True while every grab returned None. Probe once, for real.
    """
    global _PROBE
    if DISABLED or not display():
        return False
    if recheck:
        _PROBE = None
    if _PROBE is None:
        _PROBE = _probe_pixels()
    return _PROBE


def _probe_pixels():
    """A capture is only "available" if it returns NON-BLANK pixels.

    Checking `is not None` is not enough: on rootless Xwayland an XShm grab can return an
    all-zero image and NOT raise, so an exception-only probe reports available=True and
    every later frame is silently black — strictly worse than the loud BadMatch, because
    nothing surfaces the failure."""
    try:
        img = grab_root()
        if img is None:
            return False
        small = img.resize((min(64, img.width), min(64, img.height)))
        return any(px != (0, 0, 0) for px in small.convert("RGB").getdata())
    except Exception:
        return False


_SCT = {}


def _mss(cursor=False):
    """Cached MSS handle. Reconnecting per frame costs an X handshake plus a shared-memory
    attach. Keyed by `cursor` because with_cursor is fixed at construction, so one shared
    handle would silently ignore a later cursor=True."""
    if cursor not in _SCT:
        import mss  # imported lazily: it is an optional accelerator, not a hard dep

        try:
            _SCT[cursor] = mss.mss(display=display(), with_cursor=cursor)
        except TypeError:  # mss < 10.2 has no with_cursor
            _SCT[cursor] = mss.mss(display=display())
    return _SCT[cursor]


def _mss_grab(x, y, w, h, cursor=False):
    """Server-side region grab -> RGB PIL image, or None.

    SERVER-SIDE is the point: the previous implementation captured the whole root and
    cropped, which is both wasteful and, on a 4K root, ~15x more expensive than asking X for
    just the region."""
    from PIL import Image as _Image

    s = _mss(cursor).grab(
        {"left": int(x), "top": int(y), "width": int(w), "height": int(h)}
    )
    return _Image.frombytes("RGB", s.size, s.rgb)


def _pillow_ok():
    """Pillow's ImageGrab needs XCB compiled in. Present on modern Pillow, absent on the
    ancient builds that ship with old LTS distros — which is exactly where we land."""
    try:
        from PIL import features

        return bool(features.check("xcb"))
    except Exception:
        return False


def _which_grabber():
    """First external grabber on PATH. Order is by cost: `import` writes one PNG, ffmpeg
    spins up a whole x11grab pipeline."""
    for exe in ("import", "maim", "scrot", "ffmpeg"):
        if shutil.which(exe):
            return exe
    return None


def geometry():
    """Return [{x, y, w, h}] per connected output, or a single root-sized entry.

    mss FIRST, because the shell-out path below is not merely slower — it is wrong on a
    normal machine. It parses `xrandr`, falling back to `xdpyinfo`; NEITHER binary exists on
    this development host, so the shipped version returned [] — zero monitors on a
    two-monitor box, i.e. the X11 fallback could never have worked here at all.

    mss reads XRandR through XCB in-process (no binaries) and returns per-output geometry
    plus names. Verified on this host: DP-1 (3840,0,3840,2160) and DP-2 (0,0,3840,2160),
    matching the portal's own geometry exactly.
    """
    d = display()
    if not d:
        return []
    try:
        mons = _mss().monitors
        out = [
            {
                "x": m["left"],
                "y": m["top"],
                "w": m["width"],
                "h": m["height"],
                "name": m.get("output"),
            }  # fmt: skip
            for m in mons[1:]
        ]
        if out:
            return out
        if mons:
            m = mons[0]
            return [{"x": m["left"], "y": m["top"], "w": m["width"], "h": m["height"],
                     "name": None}]  # fmt: skip
    except Exception:
        pass
    if shutil.which("xrandr"):
        try:
            out = subprocess.run(
                ["xrandr", "--query"],
                capture_output=True,
                text=True,
                timeout=_GRAB_TIMEOUT_S,
                env={**os.environ, "DISPLAY": d},
            ).stdout
            mons = []
            for m in re.finditer(
                r"^(\S+) connected(?: primary)?\s+(\d+)x(\d+)\+(\d+)\+(\d+)",
                out,
                re.M,
            ):
                _, w, h, x, y = m.groups()
                mons.append({"x": int(x), "y": int(y), "w": int(w), "h": int(h)})
            if mons:
                return mons
        except Exception:
            pass
    size = root_size()
    return [{"x": 0, "y": 0, "w": size[0], "h": size[1]}] if size else []


def root_size():
    """(w, h) of the whole X root, or None."""
    d = display()
    if not d:
        return None
    if shutil.which("xdpyinfo"):
        try:
            out = subprocess.run(
                ["xdpyinfo"],
                capture_output=True,
                text=True,
                timeout=_GRAB_TIMEOUT_S,
                env={**os.environ, "DISPLAY": d},
            ).stdout
            m = re.search(r"dimensions:\s+(\d+)x(\d+)", out)
            if m:
                return int(m.group(1)), int(m.group(2))
        except Exception:
            pass
    img = grab_root()
    return img.size if img is not None else None


def grab_root():
    """Capture the whole X root as an RGB PIL image, or None.

    Tries Pillow's XCB grab first (in-process, no temp file), then an external grabber.
    Returns None rather than raising so callers can fall through to the portal path.
    """
    d = display()
    if DISABLED or not d:
        return None

    try:
        m = _mss().monitors[0]
        img = _mss_grab(m["left"], m["top"], m["width"], m["height"])
        if img is not None:
            return img
    except Exception:
        pass  # mss absent, or Xwayland's rootless root rejects GetImage.

    if _pillow_ok():
        try:
            from PIL import ImageGrab

            return ImageGrab.grab(xdisplay=d).convert("RGB")
        except Exception:
            pass  # Xwayland roots reject XGetImage with BadMatch; fall through.

    exe = _which_grabber()
    if not exe:
        return None
    env = {**os.environ, "DISPLAY": d}
    # NamedTemporaryFile(delete=False) + explicit unlink: the grabber writes the file, so it
    # must not be open on our side while that happens.
    fd, path = tempfile.mkstemp(prefix="screen-x11-", suffix=".png")
    os.close(fd)
    try:
        if exe == "import":
            cmd = ["import", "-window", "root", path]
        elif exe == "maim":
            cmd = ["maim", path]
        elif exe == "scrot":
            cmd = ["scrot", "-o", path]
        else:
            size = "%dx%d" % (root_size() or (1920, 1080))
            cmd = [
                "ffmpeg", "-loglevel", "quiet", "-f", "x11grab",
                "-video_size", size, "-i", d, "-frames:v", "1", "-y", path,
            ]  # fmt: skip
        r = subprocess.run(cmd, capture_output=True, timeout=_GRAB_TIMEOUT_S, env=env)
        if r.returncode != 0 or not os.path.getsize(path):
            return None
        with Image.open(path) as im:
            return im.convert("RGB")  # load before the file is unlinked
    except Exception:
        return None
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def grab_region(x, y, w, h):
    """Capture just this rectangle. Asks X for the region directly when mss is available —
    the old root-grab-then-crop was ~15x more expensive on a 4K root."""
    try:
        img = _mss_grab(x, y, w, h)
        if img is not None:
            return img
    except Exception:
        pass
    img = grab_root()
    if img is None:
        return None
    W, H = img.size
    x, y = max(0, min(int(x), W - 1)), max(0, min(int(y), H - 1))
    w, h = max(1, min(int(w), W - x)), max(1, min(int(h), H - y))
    return img.crop((x, y, x + w, y + h))


def diag():
    """Backend health for screen_diag."""
    return {
        "display": display(),
        "disabled": DISABLED,
        "pillow_xcb": _pillow_ok(),
        "external_grabber": _which_grabber(),
        "available": available(),
        "monitors": len(geometry()),
    }
