#!/usr/bin/env python3
"""vmctl — drive the QEMU test-bed VMs over QMP with nothing but the stdlib.

Deliberately dependency-free. The obvious route was a VNC client (vncdotool is on this box)
but it needs `service_identity`, and PEP 668 blocks pip from installing into the system
Python here — so a "just pip install it" harness would not run on the machine it is meant to
test. QEMU already exposes everything needed on its QMP socket:

  screendump        -> a PPM/PNG of the guest framebuffer, no guest cooperation required
  input-send-event  -> absolute pointer + key events, straight into the guest's input stack

That also means the harness can observe a guest that has no working screen-mcp yet, which is
the whole point: it is how we verify the X11 backend on a real X11 session.

Usage:
  ./vmctl.py list
  ./vmctl.py shot wayland out.ppm
  ./vmctl.py click x11 640 400
  ./vmctl.py key wayland ret
  ./vmctl.py type x11 "hello"
  ./vmctl.py info wayland
"""

import json
import os
import socket
import sys
import time

STATE = os.environ.get("SMCP_VM_STATE", "/var/tmp/vmbed")
VMS = {"wayland": "gnomevm", "x11": "x11vm"}


class Qmp:
    """Minimal QMP client. QMP is line-delimited JSON over a unix socket: read the greeting,
    send `qmp_capabilities`, then one JSON object per command."""

    def __init__(self, path, timeout=20.0):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(timeout)
        self.sock.connect(path)
        self.buf = b""
        self._read()  # greeting
        self.cmd("qmp_capabilities")

    def _read(self):
        """Return the next JSON object, skipping asynchronous events.

        QEMU interleaves `event` objects with command replies, so a naive read-one-line can
        hand back an event and desynchronise every later command.
        """
        while True:
            while b"\n" in self.buf:
                line, self.buf = self.buf.split(b"\n", 1)
                line = line.strip()
                if not line:
                    continue
                msg = json.loads(line)
                if "event" in msg:
                    continue
                return msg
            chunk = self.sock.recv(65536)
            if not chunk:
                raise RuntimeError("QMP socket closed")
            self.buf += chunk

    def cmd(self, execute, **args):
        payload = {"execute": execute}
        if args:
            payload["arguments"] = args
        self.sock.sendall(json.dumps(payload).encode() + b"\n")
        reply = self._read()
        if "error" in reply:
            raise RuntimeError(f"{execute}: {reply['error'].get('desc')}")
        return reply.get("return")

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


def _sock(name):
    p = os.path.join(STATE, f"{VMS.get(name, name)}.qmp")
    if not os.path.exists(p):
        raise SystemExit(f"no QMP socket for {name!r} at {p} — is the VM running?")
    return p


def _connect(name):
    return Qmp(_sock(name))


def _abs_events(x, y, w, h):
    """QMP abs coordinates are 0..32767 of the display, not pixels."""
    return [
        {"type": "abs", "data": {"axis": "x", "value": int(x * 32767 / max(1, w))}},
        {"type": "abs", "data": {"axis": "y", "value": int(y * 32767 / max(1, h))}},
    ]


def click(name, x, y, w=None, h=None, button="left"):
    """Move then click at guest pixel (x, y). Needs the display size to scale into QMP's
    fixed 0..32767 axis space; pass it or let us read it from the VM."""
    q = _connect(name)
    try:
        if w is None or h is None:
            w, h = display_size_via(q)
        q.cmd("input-send-event", events=_abs_events(x, y, w, h))
        q.cmd(
            "input-send-event",
            events=[{"type": "btn", "data": {"down": True, "button": button}}],
        )
        q.cmd(
            "input-send-event",
            events=[{"type": "btn", "data": {"down": False, "button": button}}],
        )
        return {"x": x, "y": y, "w": w, "h": h}
    finally:
        q.close()


def key(name, *keys):
    """send-key takes qcode names: ret, tab, esc, ctrl, a … (see QEMU QKeyCode)."""
    q = _connect(name)
    try:
        q.cmd("send-key", keys=[{"type": "qcode", "data": k} for k in keys])
    finally:
        q.close()


_SHIFTED = {
    "!": "1", "@": "2", "#": "3", "$": "4", "%": "5", "^": "6", "&": "7",
    "*": "8", "(": "9", ")": "0", "_": "minus", "+": "equal", ":": "semicolon",
    '"': "apostrophe", "<": "comma", ">": "dot", "?": "slash", "|": "backslash",
    "~": "grave_accent", "{": "bracket_left", "}": "bracket_right",
}  # fmt: skip
_PLAIN = {
    " ": "spc", "-": "minus", "=": "equal", ";": "semicolon", "'": "apostrophe",
    ",": "comma", ".": "dot", "/": "slash", "\\": "backslash", "`": "grave_accent",
    "[": "bracket_left", "]": "bracket_right", "\n": "ret", "\t": "tab",
}  # fmt: skip


def type_text(name, text):
    """One send-key per character. Slow but dependency-free and layout-independent enough
    for a test harness (we only ever type ASCII commands into a terminal)."""
    q = _connect(name)
    try:
        for ch in text:
            if ch.isalnum():
                q.cmd("send-key", keys=[{"type": "qcode", "data": ch.lower()}])
                continue
            if ch in _SHIFTED:
                q.cmd(
                    "send-key",
                    keys=[
                        {"type": "qcode", "data": "shift"},
                        {"type": "qcode", "data": _SHIFTED[ch]},
                    ],
                )
                continue
            qc = _PLAIN.get(ch)
            if qc:
                q.cmd("send-key", keys=[{"type": "qcode", "data": qc}])
    finally:
        q.close()


def keepalive(name):
    """Send a harmless key so GNOME does not idle-blank.

    Measured: GNOME deactivates the CRTC after ~5 min without input, and capture then
    returns either a placeholder ("Display output is not active") or a pure black frame
    depending on the display device. POINTER MOTION DOES NOT WAKE IT — not even a
    multi-step jiggle. A key event does. `shift` is chosen because it mutates nothing.
    """
    key(name, "shift")


def shot(name, out, device=None, head=None):
    """screendump targeting a specific display device.

    `head` is only valid together with `device`, and passing a head beyond the device's
    console count ABORTS THE WHOLE VM on QEMU 11.0.2 (object_property_find_err on
    qemu-fixed-text-console). Confirm heads via /backend/console[N] in the QOM tree before
    ever passing one.
    """
    out = os.path.abspath(out)
    q = _connect(name)
    try:
        args = {"filename": out}
        if device:
            args["device"] = device
            if head is not None:
                args["head"] = int(head)
        try:
            q.cmd("screendump", format="png", **args)
        except RuntimeError:
            q.cmd("screendump", **args)
        last, stable = -1, 0
        for _ in range(60):
            time.sleep(0.1)
            if not os.path.exists(out):
                continue
            sz = os.path.getsize(out)
            if sz and sz == last:
                stable += 1
                if stable >= 2:
                    break
            else:
                stable = 0
            last = sz
        return os.path.getsize(out) if os.path.exists(out) else 0
    finally:
        q.close()


def consoles(name):
    """Enumerate /backend/console[N] — the QOM replacement for the `query-consoles` QMP
    command, which does not exist in QEMU 11.0.2 (verified against query-commands)."""
    q = _connect(name)
    out = []
    try:
        for entry in q.cmd("qom-list", path="/backend") or []:
            n = entry.get("name", "")
            if not n.startswith("console["):
                continue
            row: dict[str, object] = {"path": f"/backend/{n}"}
            for prop in ("device", "head"):
                try:
                    row[prop] = q.cmd("qom-get", path=row["path"], property=prop)
                except Exception:
                    row[prop] = None
            out.append(row)
    finally:
        q.close()
    return out


def display_size_via(q):
    """Guest display size in pixels, from the first active console."""
    for dev in q.cmd("query-display-options") or []:
        pass  # not all QEMU builds report size here; fall through to the console query.
    for c in q.cmd("query-consoles") if _has(q, "query-consoles") else []:
        if c.get("width"):
            return int(c["width"]), int(c["height"])
    return 1280, 800


def _has(q, cmd):
    try:
        names = {c["name"] for c in q.cmd("query-commands")}
        return cmd in names
    except Exception:
        return False


def info(name):
    q = _connect(name)
    try:
        st = q.cmd("query-status") or {}
        vnc = q.cmd("query-vnc") if _has(q, "query-vnc") else {}
        return {
            "status": st.get("status"),
            "running": st.get("running"),
            "vnc": {k: vnc.get(k) for k in ("enabled", "host", "service")}
            if vnc
            else {},
        }
    finally:
        q.close()


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    op = argv[1]
    if op == "list":
        for k, v in VMS.items():
            p = os.path.join(STATE, f"{v}.qmp")
            print(f"  {k:8} {v:14} {'up' if os.path.exists(p) else 'down'}")
        return 0
    if op == "shot":
        n = shot(argv[2], argv[3])
        print(f"  {argv[3]}: {n} bytes")
        return 0 if n else 1
    if op == "click":
        print("  ", click(argv[2], int(argv[3]), int(argv[4])))
        return 0
    if op == "key":
        key(argv[2], *argv[3:])
        return 0
    if op == "type":
        type_text(argv[2], argv[3])
        return 0
    if op == "keepalive":
        keepalive(argv[2])
        return 0
    if op == "consoles":
        print(" ", json.dumps(consoles(argv[2])))
        return 0
    if op == "info":
        print("  ", json.dumps(info(argv[2])))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
