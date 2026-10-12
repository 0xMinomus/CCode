"""atspi_tree.py — optional AT-SPI element source.

OPT-IN, tried first, falls through silently.

CORRECTED CONCLUSION. The first version of this file claimed AT-SPI needs a global gsettings
toggle *and* a restart of every app you want to drive, and therefore could never serve an
already-open desktop. That was wrong, and the reason is worth recording: this development
box disables accessibility outright in the environment —

    /etc/environment                      NO_AT_BRIDGE=1, GTK_A11Y=none
    ~/.config/environment.d/noa11y.conf   NO_AT_BRIDGE=1, GTK_A11Y=none

which every freshly spawned process inherits. The measurement ("0 apps exposed") was real;
the inference drawn from it was not. With those two variables unset, a newly launched app
exposes a full widget tree immediately (verified: 110 actionable elements).

What is actually true: GTK3 and GTK4 register with AT-SPI unconditionally at startup — GTK3
via an unconditional `_gtk_accessibility_init()`, GTK4 whenever the bus address resolves,
and `org.a11y.Bus.GetAddress` is ungated and starts the bus on demand. `NO_AT_BRIDGE=1` is
the only thing that stops GTK3. Qt and Firefox likewise do not need a relaunch. Orca is the
existence proof: it sets `org.a11y.Status IsEnabled=true` and then enumerates the
ALREADY-RUNNING desktop, with no restart step anywhere in its codebase.

The one genuine exception is Chromium/Electron web CONTENT: `IsEnabled` only brings up the
browser chrome. The renderer escalates to full accessibility when a client touches
`GetAttributes` / `GetRelationSet` on a node — or with `--force-renderer-accessibility`. A
client that reads only role/name/children gets an empty web subtree and no error.

Still NOT primary, for a different and narrower reason than first claimed: availability
varies per app and per host config, and an empty tree is indistinguishable from an empty
screen. OCR/OmniParser stays the path that always works; this is the accelerator that makes
the common case cheap.

Do NOT set `ScreenReaderEnabled` — on GNOME, gsd-a11y-settings mirrors it and starts Orca.

Everything degrades to []: no Atspi typelib, no a11y bus, accessibility off, app not
registered. Callers must treat an empty list as "no information", never as "empty screen".
"""

import os
import shutil
import subprocess

ENABLED = os.environ.get("MCP_SCREEN_ATSPI", "1") != "0"
MAX_NODES = int(os.environ.get("MCP_SCREEN_ATSPI_MAX_NODES", "1200"))
MAX_DEPTH = int(os.environ.get("MCP_SCREEN_ATSPI_MAX_DEPTH", "24"))

#: Roles worth returning as click targets. AT-SPI exposes a lot of structural noise
#: (fillers, panels, scroll panes) that is useless to an agent choosing where to click.
_ACTIONABLE = {
    "push button", "toggle button", "radio button", "check box", "menu item",
    "check menu item", "radio menu item", "link", "text", "entry", "password text",
    "combo box", "list item", "tab", "page tab", "slider", "spin button", "menu",
    "tree item", "table cell", "icon", "label", "heading", "button",
}  # fmt: skip

_ATSPI = None
_TRIED = False


def _atspi():
    """Import + init Atspi once. Returns the module or None."""
    global _ATSPI, _TRIED
    if _TRIED:
        return _ATSPI
    _TRIED = True
    if not ENABLED:
        return None
    try:
        import gi

        gi.require_version("Atspi", "2.0")
        from gi.repository import Atspi

        # atspi_init() RETURNS a status (0 ok, 1 already-inited, 2 no bus) and only
        # g_warning()s — it does NOT abort. The abort lives in _atspi_bus(), reached by
        # every SUBSEQUENT call, so the return code is the correct gate. Verified here:
        # `Atspi.init()` with no bus -> 2, exit 0; then `get_desktop(0).get_child_count()`
        # -> "dbind-ERROR: Couldn't connect to accessibility bus" + SIGABRT.
        #
        # This is strictly better than probing org.a11y.Bus over D-Bus: it also catches a
        # bus name that is OWNED but whose socket is unreachable (AT_SPI_BUS_ADDRESS
        # pointing at a dead path), which the name probe reports as healthy.
        if Atspi.init() not in (0, 1):
            return None
        _ATSPI = Atspi
    except Exception:
        _ATSPI = None
    return _ATSPI


def toolkit_accessibility_enabled():
    """Read the GNOME toggle that gates whether apps register with AT-SPI at all.

    Shelled out on purpose, but NOT for the reason first recorded here. The original note
    blamed a missing dconf backend; that is measurably false — `GSETTINGS_BACKEND=nosuch`
    falls back silently and `GSETTINGS_BACKEND=memory` does not help. What actually aborts
    is a MISSING SCHEMA or a missing key: `Gio.Settings.new("org.example.not.installed")`
    dies with `GLib-GIO-ERROR ** Settings schema ... is not installed` + SIGABRT, which no
    try/except can catch, taking the MCP server down on a screen_diag from any host without
    GNOME's schemas installed.

    A subprocess can only fail, so the cost of being wrong is a None instead of a core dump.
    (The in-process alternative is a SettingsSchemaSource lookup guard — see
    prereqs.check_gsettings_key — which we use where a schema is expected to exist.)

    Returns True/False, or None when it cannot be determined."""
    exe = shutil.which("gsettings")
    if not exe:
        return None
    try:
        r = subprocess.run(
            [exe, "get", "org.gnome.desktop.interface", "toolkit-accessibility"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return None
    val = (r.stdout or "").strip().lower()
    if r.returncode != 0 or val not in ("true", "false"):
        return None
    return val == "true"


def _extents(node):
    """Screen-coordinate bounds, or None. AT-SPI can report 0x0 or negative for offscreen
    and not-yet-mapped widgets — those are not click targets, so drop them."""
    try:
        e = node.get_extents(1)  # 1 = ATSPI_COORD_TYPE_SCREEN
    except Exception:
        return None
    if e is None or e.width <= 0 or e.height <= 0 or e.x < 0 or e.y < 0:
        return None
    return int(e.x), int(e.y), int(e.width), int(e.height)


def elements(app_name=None):
    """Return [{role, text, x, y, bbox, source}] for on-screen accessible widgets.

    `x, y` is the CENTRE of the widget in desktop pixels — directly clickable, no OCR and no
    coordinate guessing. Empty list means "AT-SPI told us nothing", which is the common case
    (see the module docstring); it never means the screen is blank.
    """
    A = _atspi()
    if A is None:
        return []
    out = []
    try:
        desktop = A.get_desktop(0)
        napps = desktop.get_child_count()
    except Exception:
        return []

    for i in range(napps):
        if len(out) >= MAX_NODES:
            break
        try:
            app = desktop.get_child_at_index(i)
            if app is None:
                continue
            name = app.get_name() or ""
            if app_name and app_name.lower() not in name.lower():
                continue
        except Exception:
            continue
        _walk(app, out, 0, name)
    return out[:MAX_NODES]


def _walk(node, out, depth, app):
    """Iterative-ish DFS with hard depth and node caps. A pathological tree (a big web page
    under a browser's a11y bridge) can be enormous, and this runs on the tool's hot path."""
    if depth > MAX_DEPTH or len(out) >= MAX_NODES:
        return
    try:
        n = node.get_child_count()
    except Exception:
        return
    for i in range(n):
        if len(out) >= MAX_NODES:
            return
        try:
            child = node.get_child_at_index(i)
            if child is None:
                continue
            role = (child.get_role_name() or "").lower()
            label = (child.get_name() or "").strip()
        except Exception:
            continue
        if role in _ACTIONABLE and label:
            box = _extents(child)
            if box:
                x, y, w, h = box
                out.append(
                    {
                        "role": role,
                        "text": label,
                        "x": x + w // 2,
                        "y": y + h // 2,
                        "bbox": [x, y, x + w, y + h],
                        "app": app,
                        "source": "atspi",
                    }
                )
        _walk(child, out, depth + 1, app)


def diag():
    """Health for screen_diag — including WHY the tree is empty, which is the useful part."""
    A = _atspi()
    apps = 0
    if A is not None:
        try:
            apps = A.get_desktop(0).get_child_count()
        except Exception:
            apps = -1
    return {
        "enabled": ENABLED,
        "atspi_typelib": A is not None,
        "toolkit_accessibility": toolkit_accessibility_enabled(),
        "apps_exposed": apps,
        "note": (
            "0 apps usually means accessibility is disabled for the SESSION, not that the "
            "screen is empty. Check NO_AT_BRIDGE / GTK_A11Y in /etc/environment and "
            "~/.config/environment.d/ — those block GTK from registering at all — then "
            "org.a11y.Status IsEnabled. GTK/Qt/Firefox do NOT need an app restart; only "
            "Chromium/Electron web content needs --force-renderer-accessibility. "
            "OCR/OmniParser remains the path that always works."
        ),
    }
