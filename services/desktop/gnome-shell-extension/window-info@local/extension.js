/* extension.js — Window Info D-Bus (GNOME 45+ ESM)
 *
 * Exports a D-Bus object on the session bus exposing focused-window,
 * window-list and monitor geometry as JSON strings. The service name is
 * owned by org.gnome.Shell (extensions run inside the Shell process), so
 * D-Bus clients call dest 'org.gnome.Shell' at path
 *   /org/gnome/Shell/Extensions/WindowInfo
 * interface
 *   org.gnome.Shell.Extensions.WindowInfo
 */

import Gio from 'gi://Gio';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

const IFACE = `
<node>
  <interface name="org.gnome.Shell.Extensions.WindowInfo">
    <method name="GetFocusedWindow">
      <arg type="s" direction="out"/>
    </method>
    <method name="ListWindows">
      <arg type="s" direction="out"/>
    </method>
    <method name="GetMonitors">
      <arg type="s" direction="out"/>
    </method>
    <method name="ActivateWindow">
      <arg type="t" direction="in" name="id"/>
      <arg type="b" direction="out" name="ok"/>
    </method>
  </interface>
</node>`;

const DBUS_PATH = '/org/gnome/Shell/Extensions/WindowInfo';

function windowToObject(win) {
    const r = win.get_frame_rect();
    return {
        id: win.get_id(),               // stable per-session window id; round-trip to ActivateWindow
        title: win.get_title(),
        wm_class: win.get_wm_class(),
        app: win.get_wm_class_instance(),
        x: r.x,
        y: r.y,
        width: r.width,
        height: r.height,
        monitor: win.get_monitor(),
        focus: win.has_focus(),
        workspace: win.get_workspace() ? win.get_workspace().index() : -1,
    };
}

export default class WindowInfoExtension {
    enable() {
        this._dbus = Gio.DBusExportedObject.wrapJSObject(IFACE, this);
        this._dbus.export(Gio.DBus.session, DBUS_PATH);
    }

    disable() {
        if (this._dbus) {
            this._dbus.unexport();
            this._dbus = null;
        }
    }

    GetFocusedWindow() {
        const win = global.display.focus_window;
        if (!win)
            return 'null';
        return JSON.stringify(windowToObject(win));
    }

    ListWindows() {
        const actors = global.get_window_actors();
        const out = [];
        for (const actor of actors) {
            const win = actor.get_meta_window();
            if (!win)
                continue;
            out.push(windowToObject(win));
        }
        return JSON.stringify(out);
    }

    GetMonitors() {
        const monitors = Main.layoutManager.monitors;
        const out = [];
        for (const m of monitors) {
            out.push({
                index: m.index,
                x: m.x,
                y: m.y,
                width: m.width,
                height: m.height,
                geometry_scale: m.geometry_scale,
            });
        }
        return JSON.stringify(out);
    }

    // Raise + give KEYBOARD focus to a window by its id (from ListWindows/GetFocusedWindow).
    // This is the reliable compositor lever for "make injected keys land in this app" — keyboard
    // events go to the focused surface, which a background/static-monitor window doesn't have.
    // The timestamp MUST be a fresh compositor time (get_current_time_roundtrip); a stale/zero ts
    // makes focus-stealing prevention RAISE the window but DENY keyboard focus. activate() also
    // unminimizes; activate_with_focus switches workspace atomically (no focus flicker).
    ActivateWindow(id) {
        const actors = global.get_window_actors();
        for (const actor of actors) {
            const win = actor.get_meta_window();
            if (!win || win.get_id() !== id)
                continue;
            const ts = global.display.get_current_time_roundtrip();
            if (win.minimized)
                win.unminimize();
            const ws = win.get_workspace();
            if (ws)
                ws.activate_with_focus(win, ts);
            else
                win.activate(ts);
            return true;
        }
        return false;
    }
}
