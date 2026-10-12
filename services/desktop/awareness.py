"""awareness.py — window/monitor awareness for mcp-screen (v1.2).

Primary source is the `window-info@local` GNOME Shell extension, which exports a
D-Bus object on the session bus (owned by org.gnome.Shell). We call it through the
shared bus in state.py.

The extension only loads after a Wayland logout/login, so the D-Bus methods may not
respond yet. Every function here is defensive: it NEVER raises and degrades to
None / [] / "unavailable". As a partial fallback (native GTK/AT-SPI apps only) we
enumerate window titles via AT-SPI.
"""

import os
import time
import json

from gi.repository import Gio, GLib

import state

# Negative-verdict cache for summary()'s degraded path. When window-info isn't loaded,
# summary() falls back to atspi_titles(), which SPAWNS A PYTHON SUBPROCESS — measured at
# 263.6ms, on EVERY screenshot, purely to render the line "awareness: unavailable". That was
# ~24% of a 1084ms shot. Whether the extension is loaded only changes on a Wayland re-login
# (which the extension itself requires) or a screen_reload, so re-probing per shot is waste.
# Cached with a TTL rather than forever so AT-SPI coming up later is still picked up.
AWARENESS_TTL_S = float(os.environ.get("MCP_SCREEN_AWARENESS_TTL_S", "30"))
_AWARE_CACHE = {"t": 0.0, "text": None}

# The extension service is owned by the Shell process.
DEST = "org.gnome.Shell"
PATH = "/org/gnome/Shell/Extensions/WindowInfo"
IFACE = "org.gnome.Shell.Extensions.WindowInfo"


def _call(method):
    """Call a no-arg WindowInfo method, return the JSON string, or None on any error."""
    try:
        reply = state.bus.call_sync(
            DEST,
            PATH,
            IFACE,
            method,
            None,  # no args
            GLib.VariantType("(s)"),  # expected reply type
            Gio.DBusCallFlags.NONE,
            2000,  # ms timeout — fail fast if not loaded
            None,
        )
        return reply.unpack()[0]
    except Exception:
        return None


def _call_arg(method, sig, args, reply="(b)"):
    """Call a WindowInfo method WITH arguments (mirrors _call). Returns the unpacked first
    value or None. Never raises — degrades when the extension isn't loaded yet."""
    try:
        r = state.bus.call_sync(
            DEST,
            PATH,
            IFACE,
            method,
            GLib.Variant(sig, args),
            GLib.VariantType(reply),
            Gio.DBusCallFlags.NONE,
            2000,
            None,
        )
        return r.unpack()[0]
    except Exception:
        return None


def activate_window(win_id):
    """Raise + give keyboard focus to a window by id (from list_windows/focused_window) via the
    extension's ActivateWindow. Returns True on success, False if the extension/method is absent
    (caller then falls back to overview activation). Never raises."""
    if win_id is None:
        return False
    try:
        return bool(_call_arg("ActivateWindow", "(t)", (int(win_id),), reply="(b)"))
    except Exception:
        return False


def find_window(app=None, title=None):
    """Best window dict matching app (substring on app/wm_class, case-insensitive) and/or title
    (substring). Exact app match wins, else first substring hit. None if no match / extension
    down. Read-only."""
    al = app.lower() if app else None
    tl = title.lower() if title else None
    best = None
    for w in list_windows():
        wa = (w.get("app") or w.get("wm_class") or "").lower()
        wt = (w.get("title") or "").lower()
        if al and al not in wa:
            continue
        if tl and tl not in wt:
            continue
        if al and wa == al:
            return w
        best = best or w
    return best


def focused_window():
    """Focused window as a dict, or None if unavailable / nothing focused."""
    try:
        raw = _call("GetFocusedWindow")
        if not raw or raw == "null":
            return None
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def list_windows():
    """All windows as a list of dicts, or [] on any error."""
    try:
        raw = _call("ListWindows")
        if not raw:
            return []
        obj = json.loads(raw)
        return obj if isinstance(obj, list) else []
    except Exception:
        return []


def monitors():
    """Monitor geometry as a list of dicts, or [] on any error."""
    try:
        raw = _call("GetMonitors")
        if not raw:
            return []
        obj = json.loads(raw)
        return obj if isinstance(obj, list) else []
    except Exception:
        return []


def monitor_power():
    """Best-effort per-output power verdict via org.gnome.Mutter.DisplayConfig.

    Returns a list of dicts {x, y, w, h, on} in LOGICAL desktop coords (one per logical
    monitor that is currently assigned/active), or [] on any failure. GNOME-specific; on a
    non-GNOME compositor (or if Mutter changes its API) this degrades cleanly to [].

    GetCurrentState returns (serial, monitors, logical_monitors, properties). A logical
    monitor present in that list is part of the active layout (powered on); an output that
    has been DPMS-blanked / disabled drops out of logical_monitors. We therefore treat every
    logical monitor we can read as on=True and leave callers to mark anything we DON'T see as
    'off' / 'unknown'. Each logical monitor carries (x, y, scale, transform, primary, [conns],
    props); we compute its logical w/h from the assigned mode of its first connector."""
    try:
        reply = state.bus.call_sync(
            "org.gnome.Mutter.DisplayConfig",
            "/org/gnome/Mutter/DisplayConfig",
            "org.gnome.Mutter.DisplayConfig",
            "GetCurrentState",
            None,
            GLib.VariantType(
                "(ua((ssss)a(siiddada{sv})a{sv})a(iiduba(ssss)a{sv})a{sv})"
            ),
            Gio.DBusCallFlags.NONE,
            2000,
            None,
        )
        _serial, monitors_v, logical_v, _props = reply.unpack()
    except Exception:
        return []
    try:
        # monitors: [ ((connector,vendor,product,serial), [modes], props) ]
        # mode tuple: (id, width, height, refresh, preferred_scale, [scales], props)
        # We index current-mode pixel size per connector to size each logical monitor.
        mode_by_conn = {}
        for mon in monitors_v:
            (conn, _v, _p, _s) = mon[0]
            cur = None
            for mode in mon[1]:
                _mid, mw, mh = mode[0], mode[1], mode[2]
                mprops = mode[6] if len(mode) > 6 else {}
                if mprops.get("is-current"):
                    cur = (mw, mh)
                    break
                if cur is None:
                    cur = (mw, mh)  # fallback: first mode
            if cur is not None:
                mode_by_conn[conn] = cur
        out = []
        for lm in logical_v:
            lx, ly, scale = lm[0], lm[1], lm[2]
            conns = [c[0] for c in lm[5]]  # [(connector,vendor,product,serial)]
            px = next((mode_by_conn[c] for c in conns if c in mode_by_conn), None)
            if px is None:
                continue
            sc = scale or 1.0
            # Logical size = native mode size / scale (fractional scaling); round to int px.
            out.append(
                {
                    "x": int(lx),
                    "y": int(ly),
                    "w": int(round(px[0] / sc)),
                    "h": int(round(px[1] / sc)),
                    "on": True,
                }
            )
        return out
    except Exception:
        return []


_ATSPI_SCRIPT = """
import json, gi
gi.require_version("Atspi", "2.0")
from gi.repository import Atspi
titles = []
for i in range(Atspi.get_desktop_count()):
    desktop = Atspi.get_desktop(i)
    for j in range(desktop.get_child_count()):
        try:
            app = desktop.get_child_at_index(j)
            if app is None: continue
            for k in range(app.get_child_count()):
                try:
                    frame = app.get_child_at_index(k)
                    if frame and frame.get_name(): titles.append(frame.get_name())
                except: pass
        except: pass
print(json.dumps(titles))
"""


def atspi_titles():
    """FALLBACK: window titles via AT-SPI. Isolated in a subprocess so AT-SPI's
    g_error() abort (when the bus is absent) cannot kill the server process."""
    import subprocess
    import sys
    import json

    try:
        r = subprocess.run(
            [sys.executable, "-c", _ATSPI_SCRIPT],
            capture_output=True,
            text=True,
            timeout=4.0,
        )
        if r.returncode == 0 and r.stdout.strip():
            return json.loads(r.stdout.strip())
    except Exception:
        pass
    return []


_EXT_UUID = "window-info@local"


def extension_state():
    """Installed vs D-Bus-loaded state for window-info@local. Never raises."""
    import os

    dest = os.path.expanduser(f"~/.local/share/gnome-shell/extensions/{_EXT_UUID}")
    installed = os.path.isfile(os.path.join(dest, "extension.js"))
    loaded = _call("GetMonitors") is not None
    if loaded:
        hint = None
    elif installed:
        hint = "installed; log out/in (Wayland) to activate window-info"
    else:
        hint = "not installed; run gnome-shell-extension/window-info@local/install.sh"
    return {"installed": installed, "loaded": loaded, "hint": hint}


def _ext_install_state():
    """Human hint for summary() when the extension is not loaded."""
    return extension_state()["hint"]


def summary():
    """Short text line for screenshot metadata. Never raises."""
    try:
        fw = focused_window()
        if fw:
            app = fw.get("app") or fw.get("wm_class") or "unknown"
            title = fw.get("title") or ""
            return f"focused: {app} — {title}".rstrip(" —")

        # Degraded path only — see _AWARE_CACHE. atspi_titles() below costs a subprocess
        # spawn; serve a recent verdict instead of paying it on every screenshot.
        now = time.monotonic()
        cached = _AWARE_CACHE["text"]
        if cached is not None and (now - _AWARE_CACHE["t"]) < AWARENESS_TTL_S:
            return cached

        hint = _ext_install_state()
        titles = atspi_titles()
        if titles:
            text = f"awareness: window-info not loaded ({hint}); AT-SPI sees {len(titles)} window(s)"
        else:
            text = f"awareness: unavailable — {hint}"
        _AWARE_CACHE["t"], _AWARE_CACHE["text"] = now, text
        return text
    except Exception:
        return "awareness: unavailable (window-info extension not loaded)"


if __name__ == "__main__":
    print("summary():", summary())
    print("focused_window():", focused_window())
    print("monitors():", monitors())
    print("list_windows():", len(list_windows()), "windows")
    print("atspi_titles():", atspi_titles())
