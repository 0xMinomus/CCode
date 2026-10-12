#!/usr/bin/env bash
# Verify screen-mcp's capture backends against a REAL desktop session in a VM.
#
# This exists because "it works" was asserted for the X11 backend for a long time on the
# strength of unit tests and component probes on a borrowed host, and the assembled path had
# never actually run. Everything below runs inside the guest, against a live GNOME session,
# and prints numbers rather than a verdict.
#
# Usage:  ./verify.sh x11 | wayland | both
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
KEY="${SMCP_VM_KEY:-$HOME/.ssh/vmbed_ed25519}"
USER_NAME="${SMCP_VM_USER:-tester}"

_port() { case "$1" in wayland) echo 22210 ;; x11) echo 22211 ;; *) return 1 ;; esac; }

_sh() {
  local bed="$1"; shift
  ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o BatchMode=yes \
    -o ConnectTimeout=15 -i "$KEY" -p "$(_port "$bed")" "${USER_NAME}@127.0.0.1" "$@" \
    2>&1 | grep -viE '^warning|post-quantum|store now|openssh\.com/pq|^\*\*' || true
}

_verify() {
  local bed="$1"
  echo "=============== $bed bed ==============="
  scp -q -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o BatchMode=yes \
    -i "$KEY" -P "$(_port "$bed")" \
    "$REPO/x11capture.py" "$REPO/budget.py" "$REPO/atspi_tree.py" \
    "${USER_NAME}@127.0.0.1:/tmp/" 2>/dev/null || {
      echo "  UNREACHABLE — is the bed running? (./launch.sh $bed)"; return 1; }

  _sh "$bed" 'bash -s' <<'GUEST'
set -u
export DISPLAY="${DISPLAY:-:0}"
sid=$(loginctl list-sessions --no-legend | awk '/seat0/{print $1}' | head -1)
echo "  session      : $(loginctl show-session "$sid" -p Type --value) / active=$(loginctl show-session "$sid" -p Active --value)"
echo "  gnome-shell  : $(gnome-shell --version 2>/dev/null | head -1)"
echo "  gstreamer    : $(python3 -c 'import gi;gi.require_version("Gst","1.0");from gi.repository import Gst;Gst.init([]);print(Gst.version_string())' 2>/dev/null)"

# The appsink freshest-frame property. Hard-coding leaky-type made GStreamer >= 1.28 a
# silent requirement and excluded Ubuntu 24.04 (1.24 has only `drop`).
python3 - <<'PY'
import gi
gi.require_version("Gst", "1.0")
from gi.repository import Gst
Gst.init([])
f = Gst.ElementFactory.find("appsink")
names = {p.name for p in f.create(None).list_properties()}
prop = "leaky-type=downstream" if "leaky-type" in names else "drop=true"
print(f"  appsink prop : {prop}")
Gst.parse_launch(
    "videotestsrc num-buffers=1 ! videoconvert ! video/x-raw,format=RGB "
    f"! appsink name=s max-buffers=1 {prop}"
)
print("  pipeline     : parses OK")
PY

# The runtime capability probe that should gate capture — NOT XDG_SESSION_TYPE.
for iface in ScreenCast RemoteDesktop; do
  ok=$(busctl --user introspect org.freedesktop.portal.Desktop /org/freedesktop/portal/desktop 2>/dev/null \
       | grep -c "org.freedesktop.portal.$iface" || true)
  echo "  portal $iface: $( [ "${ok:-0}" -gt 0 ] && echo present || echo ABSENT )"
done
echo "  srcTypes     : $(busctl --user get-property org.freedesktop.portal.Desktop /org/freedesktop/portal/desktop org.freedesktop.portal.ScreenCast AvailableSourceTypes 2>/dev/null)"
echo "  uinput       : $(test -w /dev/uinput && echo writable || echo 'not writable')"

# The X11 capture backend, end to end, asserting PIXEL CONTENT — a black frame is the
# failure mode that an exception-only check silently passes.
cd /tmp && python3 - <<'PY'
import json
import x11capture as x
print("  x11 display  :", x.display())
print("  x11 geometry :", json.dumps(x.geometry()))
print("  x11 available:", x.available())
im = x.grab_root()
if im is None:
    print("  x11 grab     : None (expected on Wayland/Xwayland — rootless has no root storage)")
else:
    from PIL import ImageStat
    s = ImageStat.Stat(im.convert("L"))
    print(f"  x11 grab     : {im.size} mean={s.mean[0]:.1f} sd={s.stddev[0]:.1f} "
          f"NON_BLANK={s.stddev[0] > 1.0}")
    r = x.grab_region(0, 0, 400, 200)
    print("  x11 region   :", r.size if r else None)
PY

# AT-SPI: 0 apps is normal and must not be read as an empty screen.
cd /tmp && python3 -c "
import atspi_tree as a, json
d = a.diag()
print('  atspi        :', json.dumps({k: d[k] for k in ('atspi_typelib','toolkit_accessibility','apps_exposed')}))
print('  atspi elems  :', len(a.elements()))" 2>/dev/null || echo "  atspi        : probe failed"
GUEST
}

case "${1:-both}" in
  x11|wayland) _verify "$1" ;;
  both) _verify wayland; echo; _verify x11 ;;
  *) echo "usage: $0 {x11|wayland|both}" >&2; exit 2 ;;
esac
