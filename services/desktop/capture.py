"""capture.py — PipeWire frame capture + desktop compositing for mcp-screen (v1.2).

Owns one PERSISTENT pipewiresrc->appsink pipeline per monitor node, kept in PLAYING
so each grab just pulls the latest negotiated frame (no per-call pipeline rebuild).
The single OpenPipeWireRemote fd from state.SESSION backs every pipewiresrc; each
pipewiresrc dup()s the fd internally so sharing is safe. RGB (24-bit, no alpha) is negotiated
on the wire: videoconvert does the channel order in C, and dropping the alpha plane makes every
downstream stage cheaper. The old BGRx-then-swap-in-numpy path cost a 33MB fancy-index
allocation (36.7ms) per grab; carrying a constant-255 alpha then cost another 1.58x on the
LANCZOS resize (471ms -> 298ms) for a channel nothing reads.
appsink's freshest-frame property is chosen at RUNTIME (see _appsink_drop_prop):
`leaky-type=downstream` where present, else `drop=true`. An earlier note here said `drop=`
was gone in 1.28 — it is not: 1.28 exposes BOTH, while GStreamer 1.24 (current Ubuntu LTS)
has only `drop`. Hard-coding leaky-type silently excluded that LTS — the pipeline
failed to parse outright. Measured on a real GNOME/X11 VM.
DAMAGE-DRIVEN STREAMING: GNOME/Mutter negotiates framerate 0/1 (send-on-damage), so a
monitor that is powered ON but STATIC (no cursor, no animation) produces NO buffer until
something on it changes. pipewiresrc's keepalive-time only re-sends an ALREADY-EXISTING
last buffer, and resend-last only fires on EOS — neither can bootstrap the FIRST frame of a
never-damaged source. There is no portal API to force a frame, so the only lever is to
generate a damage event; ensure_geo() nudges the pointer onto a static-but-ON monitor to
prime it (see _nudge_prime).

Imports state (session/portal plumbing). Does NOT open a portal session itself beyond
calling state.ensure_session() at runtime via ensure_geo()."""

import io
import os
import sys
import json
import time
import base64
import ctypes
import platform
import threading
import collections
import statistics

import gi

gi.require_version("Gst", "1.0")
gi.require_version("GstApp", "1.0")
from gi.repository import Gst, GstApp, GLib  # noqa: E402, F401  (GstApp registers appsink type)
import numpy as np  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

import budget  # noqa: E402
import x11capture  # noqa: E402
import state  # noqa: E402

LANCZOS = Image.Resampling.LANCZOS

# WebP lossless encode effort. libwebp's `method` (0-6) and `quality` (compression EFFORT in
# lossless mode, not fidelity) only trade CPU for bytes — the pixels are identical at every
# setting. Measured on a real 2576x1449 desktop frame: method=4 (Pillow's default, what we
# shipped) 3755ms/429KB vs method=0 quality=20 195ms/569KB — 19x faster for 140KB more.
# The extra bytes are free: an image costs ceil(w/28)*ceil(h/28) visual tokens (4784 here)
# regardless of encoded size, and 759KB of base64 is nowhere near the API's 10MB per-image
# cap. Encode was 85% of a plain screenshot's wall time, so this is the whole latency win.
#
# DO NOT RE-TUNE without new evidence — the sweep was redone on the current RGB/INTER_AREA
# output (9 reps, medians) and q=20 is already the floor:
#   lossless m0 q20  202ms 659KB  <- shipped      lossless m1 q0+  344-613ms
#   lossless m0 q30-50  237-251ms 603KB           PNG any level    343-768ms
#   LOSSY q80/90/95     228-307ms                 <- SLOWER than lossless
# Lossy is slower because it runs rate-distortion analysis; lossless m0 is fast entropy
# coding. So the lossless guarantee costs nothing here — it is not a speed/quality tradeoff.
# A 3-rep bench made q=40 look 8% faster; at 9 reps it is 24% SLOWER. Use medians.
WEBP_METHOD = int(os.environ.get("MCP_SCREEN_WEBP_METHOD", "0"))
WEBP_EFFORT = int(os.environ.get("MCP_SCREEN_WEBP_EFFORT", "20"))

# The client tool-output cap and the fitting logic live in budget.py — a gi-free module, so
# CI can actually execute them (capture.py needs a real gi/GStreamer/D-Bus session and is
# stubbed out headless). budget.MAX_OUT_KB is the ONE source of truth; do not shadow it with
# a local copy here.

# Gst.init is binding-version-fragile: older PyGObject accepts None; GStreamer/
# gobject-introspection >= 1.28 rejects it ("Argument 1 does not allow None as a
# value") and requires a list; other builds raise different errors. Try both and
# fall through so the server starts on EVERY version — a genuine GStreamer
# failure then surfaces at pipeline creation with an actionable error, instead of
# crashing import on a binding quirk.
for _gst_argv in (None, []):
    try:
        Gst.init(_gst_argv)
        break
    except Exception:
        continue

# node_id -> {"pipe": Gst.Pipeline, "sink": appsink}. Guarded by _LOCK.
_PIPES = {}
_LOCK = threading.Lock()
# node_id -> human-readable reason for the last _nudge_prime outcome. Debug-only surfacing
# (asleep_hint()/diag() read this) so a no-frame monitor's actual cause — guard blocked it,
# the sample timed out, an exception — is visible instead of the generic "ON but STATIC" hint.
_NUDGE_DEBUG = {}
# node_id -> Lock: serializes concurrent BUILDS of the same node without holding _LOCK during
# the slow build, so different nodes build in parallel. Guarded by _LOCK on first insert.
_BUILDING = {}


_DROP_PROP = None


def _appsink_drop_prop():
    """The appsink "keep only the freshest buffer" property, chosen at RUNTIME.

    This was hard-coded to `leaky-type=downstream`, which made GStreamer >= 1.28 a hard
    requirement and silently excluded the CURRENT Ubuntu LTS. Measured on a real GNOME/X11
    VM (Ubuntu 24.04, GStreamer 1.24.2): `appsink` has `drop` but NOT `leaky-type`, and our
    exact pipeline string fails to parse —

        WARNING: erroneous pipeline: no property "leaky-type" in element "appsink"

    while the `drop=true` form parses cleanly. On this host (1.28) appsink exposes BOTH, so
    `drop` is not gone as an earlier note in CLAUDE.md claimed — it is still there and still
    works. Prefer `leaky-type` where present (it is the modern spelling) and fall back to
    `drop`, which takes the supported floor from 1.28 down to 1.14-era.
    """
    global _DROP_PROP
    if _DROP_PROP is None:
        try:
            factory = Gst.ElementFactory.find("appsink")
            el = factory.create(None) if factory else None
            names = {p.name for p in el.list_properties()} if el else set()
            _DROP_PROP = (
                "leaky-type=downstream" if "leaky-type" in names else "drop=true"
            )
        except Exception:
            _DROP_PROP = "drop=true"  # the widely-supported spelling
    return _DROP_PROP


def _build_pipe(node_id):
    """Create + start a persistent pipewiresrc->appsink pipeline for one node.

    Blocks until caps are negotiated (PLAYING reached, ~5s negotiate) and warms it with a
    pull (~3s) so last_sample is primed. Returns (pipe, sink, fd)."""
    fd = (
        state.open_pw_fd()
    )  # OWN fd per pipeline; sharing one starves concurrent streams
    # keepalive-time only re-sends an EXISTING last buffer and resend-last only fires on EOS,
    # so neither primes the FIRST frame of a never-damaged static source — that needs a damage
    # event (ensure_geo's _nudge_prime). They still help once a buffer has flowed.
    pipe = Gst.parse_launch(
        f"pipewiresrc name=pwsrc fd={fd} path={node_id} keepalive-time=1000 resend-last=true "
        f"! videoconvert ! video/x-raw,format=RGB "
        f"! appsink name=s sync=false max-buffers=1 {_appsink_drop_prop()} "
        f"emit-signals=false enable-last-sample=true"
    )
    sink = pipe.get_by_name("s")
    src = pipe.get_by_name(
        "pwsrc"
    )  # read the cursor meta HERE; videoconvert strips it downstream
    if src is not None:
        pad = src.get_static_pad("src")
        if pad is not None:
            pad.add_probe(Gst.PadProbeType.BUFFER, _cursor_probe, node_id)
    pipe.set_state(Gst.State.PLAYING)
    # Block until the pipeline finishes negotiating (or 5s elapse).
    pipe.get_state(5 * Gst.SECOND)
    # Warm: prime last_sample. An IDLE/static monitor can be slow to emit its first
    # frame, so block up to ~3s (3 x 1s), breaking as soon as a sample lands.
    for _ in range(
        3
    ):  # active monitors deliver in <200ms; idle/DPMS ones never do — fail fast
        if sink.emit("try-pull-sample", 1 * Gst.SECOND) is not None:
            break
    return pipe, sink, fd


def _get_sink(node_id):
    """Return the live appsink for node_id, building/caching the pipeline if needed.

    The ~8s _build_pipe runs OUTSIDE _LOCK so concurrent grabs of DIFFERENT nodes build in
    parallel (was: the lock serialized every cold build, so N monitors cost N*8s). A per-node
    build lock prevents two threads building the SAME node; if we lose that race the loser
    tears down its now-redundant pipeline (each carries its own fd — must not leak)."""
    with _LOCK:
        ent = _PIPES.get(node_id)
        if ent is not None:
            return ent["sink"]
        blk = _BUILDING.setdefault(node_id, threading.Lock())
    with blk:  # serialize builds of THIS node only
        with _LOCK:
            ent = _PIPES.get(node_id)
            if ent is not None:
                return ent["sink"]
        pipe, sink, fd = _build_pipe(node_id)  # slow, lock-free
        with _LOCK:
            ent = _PIPES.get(node_id)
            if ent is not None:  # someone built it while we were building
                redundant = (pipe, fd)
                winning = ent["sink"]
            else:
                _PIPES[node_id] = {"pipe": pipe, "sink": sink, "fd": fd}
                redundant = None
                winning = sink
    if redundant:  # captured under _LOCK above; a concurrent
        try:  # shutdown() can't KeyError us here
            redundant[0].set_state(Gst.State.NULL)
            os.close(redundant[1])
        except Exception:
            pass
    return winning


def _sample_to_rgb(sample):
    """Decode a GstSample (RGB) -> (w, h, ndarray HxWx3 uint8 RGB).

    Two copies used to sit on this path and ran on EVERY grab, including each poll of the
    settle/change-gate loops. At 3840x2160x4 (33MB) they measured 9.7ms and 36.7ms:

      bytes(mi.data)        -> memcpy'd the whole mapped frame. mi.data is already a buffer;
                               np.frombuffer wraps it as a VIEW for free. The view is only
                               valid until unmap, so every read below happens inside the try.
      arr[..., [2,1,0,3]]   -> a 33MB fancy-index allocation to swap BGRx->RGBA. The pipeline
                               now negotiates RGB directly (videoconvert does it in C), so
                               there is nothing left to swap and no alpha plane to carry. The old comment claimed BGRx was
                               "on the wire for speed" — measurably backwards once the cost
                               landed in numpy instead of in GStreamer.

    Still outstanding (measured, not yet wired): a region shot converts the whole frame and
    then discards ~95% of it, which is why a 1500x130 region can cost MORE than a full-monitor
    grab — 87.9ms vs 3.9ms if the crop is applied before the copy. Cropping here would make
    `_note_frame`'s per-monitor freshness signature region-scoped, so it needs its own path
    rather than a flag on this one."""
    st = sample.get_caps().get_structure(0)
    w, h = st.get_value("width"), st.get_value("height")
    buf = sample.get_buffer()
    ok, mi = buf.map(Gst.MapFlags.READ)
    try:
        raw = np.frombuffer(mi.data, dtype=np.uint8)  # view into the mapping, no copy
        # Account for row padding via stride, then trim to exactly w*4 bytes/row.
        stride = len(raw) // h
        view = raw[: stride * h].reshape((h, stride))[:, : w * 3].reshape((h, w, 3))
        # The ONE copy — .copy(), NOT ascontiguousarray: the trimmed view is already
        # contiguous, so ascontiguousarray returns it unchanged. That left `arr` aliasing the
        # mapping (use-after-free once unmap runs below) and read-only, because frombuffer on
        # the mapping yields a read-only array — the alpha write then died with
        # "assignment destination is read-only". Caught on the first live grab.
        arr = view.copy()
    finally:
        buf.unmap(mi)
    return w, h, arr


def _drop(node_id):
    """Tear down + uncache a node's pipeline (so the next grab rebuilds it)."""
    with _LOCK:
        ent = _PIPES.pop(node_id, None)
    if ent:
        try:
            ent["pipe"].set_state(Gst.State.NULL)
        except Exception:
            pass
        try:
            os.close(ent["fd"])
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Cursor position (SPA_META_Cursor, via cursor_mode=METADATA)
#
# pipewiresrc attaches the cursor position to each buffer as a
# GstVideoRegionOfInterestMeta labelled "cursor" (roi_type == quark("cursor")).
# PyGObject can't downcast that meta to read its x/y, and the by-id accessor is a
# broken binding, so we reach the fields with ctypes: pull the GstBuffer* out of the
# PyGObject wrapper, iterate its metas, and read the x/y guints at their struct offsets.
#
# Offsets derived from GStreamer headers (gst/gstmeta.h + gst/video/gstvideometa.h):
#
#   struct GstMeta {
#     GstMetaFlags       flags;   /* guint — 4 bytes */
#     const GstMetaInfo *info;    /* pointer */
#   };
#   struct GstVideoRegionOfInterestMeta {
#     GstMeta meta;
#     GQuark  roi_type;           /* guint32 */
#     gint    id;
#     gint    parent_id;
#     guint   x, y, w, h;
#     GList  *params;
#   };
#
# LP64 (x86_64 / aarch64): pointer=8 → flags@0 + 4-byte pad + info@8 → GstMeta=16;
#   roi_type@16, id@20, parent_id@24, x@28, y@32.
# Both arches share this layout; the table keys both so platform.machine() hits.
# Verified on x86-64 Linux against live pipewiresrc cursor meta (ctypes.Structure
# sizeof/offsetof of the same field list matches). Unknown arch → None (fail open)
# with a one-shot stderr log. Best-effort: any read failure also returns None.
# ---------------------------------------------------------------------------
_GST = ctypes.CDLL("libgstreamer-1.0.so.0")
_GST.gst_buffer_iterate_meta.restype = ctypes.c_void_p
_GST.gst_buffer_iterate_meta.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
_CURSOR_QUARK = GLib.quark_from_string("cursor")

# machine (platform.machine().lower()) -> field byte offsets into the ROI meta.
CURSOR_META_OFFSETS = {
    "x86_64": {"roi_type": 16, "x": 28, "y": 32},
    "amd64": {"roi_type": 16, "x": 28, "y": 32},  # Debian/kernel alias
    "aarch64": {"roi_type": 16, "x": 28, "y": 32},  # same LP64 layout
    "arm64": {"roi_type": 16, "x": 28, "y": 32},  # macOS / some distros
}

_CURSOR_META_OFFSETS_WARNED = False


def get_cursor_meta_offsets(machine=None):
    """Return {roi_type, x, y} byte offsets for GstVideoRegionOfInterestMeta, or None.

    Pure helper (platform.machine only) so unit tests need no GStreamer. Pass
    `machine` to pin an arch; default is the host. Unknown arch → None + one log.
    """
    global _CURSOR_META_OFFSETS_WARNED
    arch = (machine if machine is not None else platform.machine()) or ""
    arch = arch.lower()
    off = CURSOR_META_OFFSETS.get(arch)
    if off is not None:
        return dict(off)
    if not _CURSOR_META_OFFSETS_WARNED:
        print(
            f"mcp-screen: unknown arch {arch!r} for GstVideoRegionOfInterestMeta "
            f"offsets; cursor meta readback disabled (fail open)",
            file=sys.stderr,
        )
        _CURSOR_META_OFFSETS_WARNED = True
    return None


class _PyWrap(
    ctypes.Structure
):  # PyGObject MiniObject wrapper head: refcnt, type, C ptr
    _fields_ = [
        ("rc", ctypes.c_ssize_t),
        ("ty", ctypes.c_void_p),
        ("obj", ctypes.c_void_p),
    ]


# node_id -> (frame_x, frame_y, monotonic_t), fed by the src-pad probe below. The cursor
# ROI meta lives on the pipewiresrc src buffer but videoconvert drops it, so we read it at
# the source rather than off the appsink sample.
_CURSOR = {}

# --- Probe C: INSTRUMENT ONLY, no behavior change -----------------------------------------
# Question: does PipeWire damage arrive densely enough to WAKE on (block on a buffer), or is
# the 1fps poll in screen_wait/screen_watch load-bearing? Recorded at the SOURCE pad, so the
# arrival time is independent of when we happen to pull. The probe returns OK untouched and
# only appends to bounded deques; the JSONL sink is opt-in.
#
# keepalive-time=1000 re-sends the LAST buffer, which also fires this probe — so raw arrivals
# would falsely read as "events flow" on a static monitor. A resend pushes the SAME GstBuffer,
# so an unchanged underlying pointer marks a resend and only pointer CHANGES count as damage.
# That separation is the whole point of the probe; do not collapse it back to raw arrivals.
#
# Probes A/B ride the same pad probe. MCP_SCREEN_WAIT_MODE selects how the post-action
# change-gate waits:
#   poll   (default, unchanged) — grab+convert+hash every `interval`
#   event  (Probe A) — block on real damage only; no grab until damage lands
#   hybrid (Probe B) — block on damage, but a poll floor still fires as a backstop, so a
#                      missed/absent damage event degrades to today's behavior instead of
#                      a stall. backstop_fires > 0 is the signal that events alone are NOT
#                      a sufficient wake source.
WAIT_MODE = os.environ.get("MCP_SCREEN_WAIT_MODE", "poll").strip().lower()
if WAIT_MODE not in ("poll", "event", "hybrid"):
    WAIT_MODE = "poll"
EVENT_LOG_N = int(os.environ.get("MCP_SCREEN_EVENT_LOG_N", "512"))
EVENT_LOG_OFF = os.environ.get("MCP_SCREEN_NO_EVENT_LOG") == "1"
EVENT_LOG_PATH = os.environ.get("MCP_SCREEN_EVENT_LOG") or None
_ARRIVALS = {}  # node -> deque[(t_mono, pts_ns, buf_ptr)]
_PULLS = {}  # node -> deque[(t_mono, got_sample, content_changed)]
# Resend detection and the damage Event are kept OUT of the log deques: probes A/B must keep
# working with the Probe C log disabled.
_LAST_PTR = {}  # node -> last GstBuffer address seen at the source pad
_DAMAGE_EV = {}  # node -> threading.Event, set on a NON-resend buffer
# Probe A/B counters: event_wakes = woken by real damage; backstop_fires = the hybrid poll
# floor fired because no damage event arrived (a NEGATIVE signal for event-only waiting).
_WAIT_STATS = {"event_wakes": 0, "backstop_fires": 0, "timeouts": 0}


def _jsonl(rec):
    """Append one record to the opt-in Probe C log. Never raises; a broken log must not
    break capture."""
    if not EVENT_LOG_PATH:
        return
    try:
        with open(EVENT_LOG_PATH, "a") as fh:
            fh.write(json.dumps(rec) + "\n")
    except Exception:
        pass


def _note_arrival(node_id, buf):
    """Record a buffer arriving at the source pad, tagging keepalive resends, and wake any
    waiter armed on this node when the buffer is real damage."""
    try:
        ptr = _PyWrap.from_address(id(buf)).obj
        resend = _LAST_PTR.get(node_id) == ptr
        _LAST_PTR[node_id] = ptr
        t = time.monotonic()
        if not resend:
            ev = _DAMAGE_EV.get(node_id)
            if ev is not None:
                ev.set()
        if EVENT_LOG_OFF:
            return
        _ARRIVALS.setdefault(node_id, collections.deque(maxlen=EVENT_LOG_N)).append(
            (t, buf.pts, ptr)
        )
        _jsonl({"ev": "arrive", "node": node_id, "t": t, "resend": resend})
    except Exception:
        pass


def arm_damage(node_id):
    """Arm a damage waiter for this node and return it. Must be called BEFORE the caller
    takes its baseline frame, else damage landing in between is lost."""
    ev = _DAMAGE_EV.setdefault(node_id, threading.Event())
    ev.clear()
    return ev


def wait_damage(ev, timeout):
    """Block up to `timeout` seconds for real damage on an armed node. True = damage arrived.

    Probe A/B primitive: waiting here costs nothing, whereas each poll iteration pays a full
    grab + 4K RGB convert + hash. Never raises."""
    try:
        return bool(ev.wait(timeout))
    except Exception:
        return False


def note_wake(kind):
    """Count a Probe A/B wake outcome: event_wakes | backstop_fires | timeouts."""
    if kind in _WAIT_STATS:
        _WAIT_STATS[kind] += 1


def _note_pull(node_id, got, changed):
    """Record a grab() pulling from the appsink — the poll side of the comparison."""
    if EVENT_LOG_OFF:
        return
    try:
        t = time.monotonic()
        _PULLS.setdefault(node_id, collections.deque(maxlen=EVENT_LOG_N)).append(
            (t, bool(got), bool(changed))
        )
        _jsonl(
            {
                "ev": "pull",
                "node": node_id,
                "t": t,
                "got": bool(got),
                "changed": bool(changed),
            }
        )
    except Exception:
        pass


def _pct(vals, p):
    if not vals:
        return None
    s = sorted(vals)
    return round(s[min(len(s) - 1, int(p * len(s)))], 1)


def event_stats():
    """Probe C readout, per node. `damage_*` EXCLUDES keepalive resends, so the gaps describe
    real screen change. `wake_headroom_ms` is the lag from a damage arrival to the next pull
    that actually saw new content — the latency an event-driven wait could remove."""
    out = {"wait_mode": WAIT_MODE, "waits": dict(_WAIT_STATS), "nodes": {}}
    nodes = out["nodes"]
    for nid, arr in _ARRIVALS.items():
        ev = list(arr)
        dmg = [ev[i][0] for i in range(len(ev)) if i == 0 or ev[i][2] != ev[i - 1][2]]
        # Cross-check on the resend discriminator: if the GstBuffer pointer always differs but
        # the PTS repeats, pipewiresrc is re-pushing the same frame under a fresh buffer and the
        # pointer test is blind to it. Both counters near zero while gaps stay capped at the
        # keepalive period means the discriminator is wrong, not that the screen is busy.
        pts_repeats = sum(1 for a, b in zip(ev, ev[1:]) if a[1] == b[1])
        gaps = [(b - a) * 1000.0 for a, b in zip(dmg, dmg[1:])]
        pulls = list(_PULLS.get(nid, ()))
        head = []
        for t, got, changed in pulls:
            if not (got and changed):
                continue
            prior = [d for d in dmg if d <= t]
            if prior:
                head.append((t - prior[-1]) * 1000.0)
        nodes[nid] = {
            "arrivals": len(ev),
            "damage": len(dmg),
            "resends": len(ev) - len(dmg),
            "pts_repeats": pts_repeats,
            "damage_gap_ms": {
                "median": round(statistics.median(gaps), 1) if gaps else None,
                "p95": _pct(gaps, 0.95),
                "max": round(max(gaps), 1) if gaps else None,
            },
            "last_damage_age_s": round(time.monotonic() - dmg[-1], 2) if dmg else None,
            "pulls": len(pulls),
            "pulls_changed": sum(1 for _, g, c in pulls if g and c),
            "wake_headroom_ms": {
                "median": round(statistics.median(head), 1) if head else None,
                "p95": _pct(head, 0.95),
            },
        }
    return out


def _cursor_xy_from_buf(buf):
    """Read the 'cursor' ROI meta (x,y in stream frame px) off a GstBuffer, or None."""
    offs = get_cursor_meta_offsets()
    if offs is None:
        return None
    try:
        bp = _PyWrap.from_address(id(buf)).obj
        st = ctypes.c_void_p(0)
        while True:
            mp = _GST.gst_buffer_iterate_meta(bp, ctypes.byref(st))
            if not mp:
                return None
            if (
                ctypes.c_uint32.from_address(mp + offs["roi_type"]).value
                == _CURSOR_QUARK
            ):
                return (
                    ctypes.c_uint32.from_address(mp + offs["x"]).value,
                    ctypes.c_uint32.from_address(mp + offs["y"]).value,
                )
    except Exception:
        return None


def _cursor_probe(pad, info, node_id):
    """pipewiresrc src-pad buffer probe: stash the latest cursor position for this node."""
    try:
        buf = info.get_buffer()
        _note_arrival(node_id, buf)
        xy = _cursor_xy_from_buf(buf)
        if xy is not None:
            # Reject out-of-frame cursor metas: a stale/garbage ROI value (e.g. x beyond the
            # stream width, seen when a monitor goes static) must not poison the cache and
            # resolve to a bogus global position later. Caps live on the pad, not the buffer.
            fw = fh = None
            cap = pad.get_current_caps()
            if cap is not None:
                st = cap.get_structure(0)
                fw, fh = st.get_value("width"), st.get_value("height")
            if (not fw or 0 <= xy[0] < fw) and (not fh or 0 <= xy[1] < fh):
                with _LOCK:
                    _CURSOR[node_id] = (xy[0], xy[1], time.monotonic())
    except Exception:
        pass
    return Gst.PadProbeReturn.OK


def cursor_pos(refresh=True, prefer_node=None):
    """Best-effort real pointer position in GLOBAL native px (gx, gy), or None.

    Reads the per-node cache the src-pad probes keep current. Normally the cursor meta rides
    only on the stream the pointer is over, so the node with the freshest sample wins. But a
    STATIC monitor never refreshes its sample, so "freshest across all monitors" would resolve
    to whatever LIVE monitor last produced a frame — the wrong monitor. When the caller just
    moved the pointer to a known node, pass prefer_node=<node> to pin the readback to THAT
    monitor's sample (regardless of freshness), falling back to freshest only if it has none.
    Updates the state.SESSION['cursor'] cache."""
    geo = {m["node"]: m for m in (state.SESSION.get("geo") or [])}
    with _LOCK:
        items = dict(_CURSOR)
    if prefer_node is not None and prefer_node in items and prefer_node in geo:
        x, y, t = items[prefer_node]
        m = geo[prefer_node]
        best, bt = (m["x"] + x, m["y"] + y), t
    else:
        best, bt = None, -1.0
        for nid, (x, y, t) in items.items():
            m = geo.get(nid)
            if m and t > bt:
                bt, best = t, (m["x"] + x, m["y"] + y)
    if best is not None:
        state.SESSION["cursor"] = {"gx": best[0], "gy": best[1], "t": bt}
        return best
    c = state.SESSION.get("cursor")
    return (c["gx"], c["gy"]) if c else None


def cursor_sample_age(node=None):
    """Age in seconds of the cached cursor sample cursor_pos(prefer_node=node) would return,
    or None if there's no sample at all. A STATIC monitor's sample never refreshes, so this
    can grow unbounded — callers (guard_user) use it to tell "genuinely live reading" from
    "frozen snapshot from whenever this monitor last painted," which cursor_pos() itself
    can't distinguish since it returns the pinned sample regardless of freshness."""
    with _LOCK:
        items = dict(_CURSOR)
    if node is not None and node in items:
        return time.monotonic() - items[node][2]
    if not items:
        return None
    return time.monotonic() - max(t for _, _, t in items.values())


def diag():
    """Capture-subsystem health for screen_diag: live pipelines + the probe-fed cursor cache
    (per-node frame px + monotonic age) and the resolved global cursor_pos."""
    with _LOCK:
        cache = {
            nid: {"frame_xy": [x, y], "age_s": round(time.monotonic() - t, 2)}
            for nid, (x, y, t) in _CURSOR.items()
        }
        pipes = list(_PIPES.keys())
    return {
        "live_pipelines": pipes,
        "cursor_quark": _CURSOR_QUARK,
        "probe_cache": cache,
        "cursor_pos": cursor_pos(),
        "last_nudge_result": dict(_NUDGE_DEBUG),
        "events": event_stats(),
    }


def draw_cursor(img, ox, oy):
    """Composite a simple pointer marker into a screenshot crop at the live cursor position
    (METADATA cursor mode doesn't bake the cursor into frames). No-op if the cursor is
    unknown or outside this crop. `img` is at real desktop px; (ox,oy) is its origin."""
    c = state.SESSION.get("cursor")
    if not c:
        return img
    lx, ly = c["gx"] - ox, c["gy"] - oy
    if not (0 <= lx < img.width and 0 <= ly < img.height):
        return img
    try:
        d = ImageDraw.Draw(img)
        a = [
            (lx, ly),
            (lx, ly + 22),
            (lx + 6, ly + 16),
            (lx + 11, ly + 24),
            (lx + 15, ly + 22),
            (lx + 10, ly + 14),
            (lx + 17, ly + 14),
        ]
        d.polygon(a, fill=(255, 255, 255), outline=(0, 0, 0))
    except Exception:
        pass
    return img


def grab(node_id, rebuild=True):
    """Pull the latest frame for one monitor node -> (w, h, ndarray HxWx3 uint8 RGB).

    rebuild=False skips the stale-pipeline teardown+rebuild path so an idle monitor
    fails fast (one build) instead of paying a second full pipeline build."""
    with state.stage("pull"):
        sink = _get_sink(node_id)
        sample = sink.emit("try-pull-sample", 2 * Gst.SECOND) or sink.props.last_sample
    if sample is None and rebuild:
        # Stale/half-dead pipeline (e.g. idle monitor never primed): rebuild once.
        _drop(node_id)
        sink = _get_sink(node_id)
        sample = sink.emit("try-pull-sample", 5 * Gst.SECOND) or sink.props.last_sample
    if sample is None:
        _note_pull(node_id, False, False)
        raise RuntimeError(
            f"no frame from node {node_id} (monitor may be off, or ON-but-static — GNOME "
            f"streams on damage, so an idle screen emits no frame until something changes)"
        )
    with state.stage("decode"):
        w, h, arr = _sample_to_rgb(sample)
    changed = _note_frame(
        node_id, arr
    )  # track freshness so screenshots can flag a possibly-stale frame
    _note_pull(node_id, True, changed)
    return w, h, arr


def _peek(node_id):
    """Cheap, non-blocking native (w,h) from a live pipeline's cached last_sample, or None.

    Never builds, drops, or blocks — used to detect a woken idle monitor before compositing."""
    ent = _PIPES.get(node_id)
    if ent is None:
        return None
    sample = ent["sink"].props.last_sample
    if sample is None:
        return None
    st = sample.get_caps().get_structure(0)
    return st.get_value("width"), st.get_value("height")


def grab_all(node_ids, rebuild=True):
    """Grab several monitor nodes concurrently -> {node_id: (w, h, arr)}.

    rebuild=False makes a no-frame node fail fast instead of paying the ~15s teardown+rebuild;
    the composite path uses this because ensure_geo() has already primed every live monitor, so
    a cached last_sample returns instantly and a still-dark node is simply skipped (left black)."""
    out = {}
    errs = {}

    def work(nid):
        try:
            out[nid] = grab(nid, rebuild=rebuild)
        except Exception as e:  # noqa: BLE001 — record per-node, surface after join
            errs[nid] = e

    threads = [threading.Thread(target=work, args=(nid,)) for nid in node_ids]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    if errs and not out:
        raise RuntimeError(f"grab_all: all nodes failed: {errs}")
    for nid, e in errs.items():
        state.log("WARN grab_all node", nid, "failed:", e)
    return out


def _power_verdicts(probed):
    """Map each probed monitor to 'on'/'off'/'unknown' using awareness.monitor_power().

    probed rows are [node, lpx, lpy, lw, lh, ...]; awareness reports active logical monitors
    in LOGICAL desktop coords. We match by logical position+size. A monitor we DON'T find in
    the active layout is 'off' (DPMS/disabled); if the probe returned nothing at all we can't
    tell, so 'unknown'. Best-effort: never raises."""
    try:
        import awareness

        active = awareness.monitor_power()
    except Exception:
        active = []
    if not active:
        return ["unknown"] * len(probed)
    out = []
    for row in probed:
        lpx, lpy = row[1], row[2]
        # Match on logical ORIGIN only. Origin uniquely identifies a monitor and both sides
        # report it identically; size is derived via different rounding paths (portal props vs
        # native/scale) and can differ by >2px under fractional scaling — matching on size too
        # would mis-label a powered-on scaled monitor as 'off' and skip the prime nudge.
        found = any(abs(a["x"] - lpx) <= 2 and abs(a["y"] - lpy) <= 2 for a in active)
        out.append("on" if found else "off")
    return out


def _nudge_prime(node_id, lpx, lpy, lw, lh, sx, sy):
    """Generate one damage event on a static-but-ON monitor to prime its first frame, then
    retry the grab once. Returns (w, h, arr) on success, or None.

    Mechanism: GNOME streams on damage, so we move the pointer to the monitor's center (a tiny
    wiggle = damage), wait briefly for the now-damaged frame, then RESTORE the pointer so the
    user isn't disrupted. Skipped if the user appears to be driving the pointer (takeover
    guard) or via MCP_SCREEN_NO_NUDGE=1. Lazy `import input` keeps capture's import graph
    acyclic (input imports state + lazily imports capture, not the reverse at module load)."""
    if os.environ.get("MCP_SCREEN_NO_NUDGE") == "1":
        _NUDGE_DEBUG[node_id] = "skipped: MCP_SCREEN_NO_NUDGE=1"
        return None
    prior = None
    inp = None
    try:
        import input as inp  # lazy: input lazily imports capture; importing it at top would cycle

        try:
            inp.guard_user()  # respect user takeover — don't fight for the pointer
        except Exception as e:
            _NUDGE_DEBUG[node_id] = f"guard_user blocked the nudge: {e}"
            return None
        prior = (
            state.SESSION.get("cmd_cursor") or cursor_pos()
        )  # restore target (real pos if unmoved this session)
        # Damage target in GLOBAL native px (the space _goto expects). Prefer wiggling IN PLACE at
        # the current pointer when it's already ON this monitor — a ±3px nudge is enough damage and
        # near-invisible, vs jumping to monitor center (disruptive, and this now runs per fresh
        # screenshot). Only fall back to center when the pointer is elsewhere / unknown.
        x0, y0 = round(lpx * sx), round(lpy * sy)
        mw, mh = round(lw * sx), round(lh * sy)
        if prior is not None and x0 <= prior[0] < x0 + mw and y0 <= prior[1] < y0 + mh:
            gx, gy = int(prior[0]), int(prior[1])
        else:
            gx, gy = int(x0 + mw / 2), int(y0 + mh / 2)
        wx = (
            gx + 3 if gx + 3 < x0 + mw else gx - 3
        )  # tiny wiggle: ensure a fresh damage region
        wy = gy + 3 if gy + 3 < y0 + mh else gy - 3
        # uinput abs-move is reliable for static monitors (kernel-level, bypasses portal coalescing).
        # Portal _goto is the fallback (unreliable on idle screens but requires no evdev dep).
        if inp._use_uinput():
            import uinput_backend as _ui

            _ui.move(gx, gy)
            if GLib is not None:
                GLib.usleep(20000)
            _ui.move(wx, wy)
        else:
            inp._goto(gx, gy)
            if GLib is not None:
                GLib.usleep(20000)
            inp._goto(wx, wy)
        sink = _get_sink(node_id)
        sample = None
        for _ in range(3):  # up to ~3s for the damaged frame to arrive
            sample = sink.emit("try-pull-sample", 1 * Gst.SECOND)
            if sample is not None:
                break
        if sample is None:
            _NUDGE_DEBUG[node_id] = (
                "wiggled the pointer but no sample arrived within ~3s"
            )
            return None
        _NUDGE_DEBUG[node_id] = "primed OK"
        return _sample_to_rgb(sample)
    except Exception as e:
        _NUDGE_DEBUG[node_id] = f"exception: {type(e).__name__}: {e}"
        return None
    finally:
        try:  # restore the pointer wherever the user/we last had it
            if prior is not None and inp is not None:
                if inp._use_uinput():
                    import uinput_backend as _ui

                    _ui.move(int(prior[0]), int(prior[1]))
                else:
                    inp._goto(int(prior[0]), int(prior[1]))
        except Exception:
            pass


def _grab_or_prime(m):
    """grab() one monitor (geo entry m); if it has no frame because the monitor is static,
    prime it once via a damage nudge and retry. Returns (w, h, arr). Raises if still no frame
    (e.g. the monitor is genuinely off). This is why a single-monitor / region capture of a
    STATIC monitor no longer fails where the full composite would have re-primed it."""
    try:
        return grab(m["node"], rebuild=False)
    except Exception:
        primed = _nudge_prime(
            m["node"],
            m["lpx"],
            m["lpy"],
            m["lw"],
            m["lh"],
            m.get("sx", 1.0) or 1.0,
            m.get("sy", 1.0) or 1.0,
        )
        if primed is not None:
            return primed
        return grab(
            m["node"]
        )  # last resort: full rebuild path (raises with the asleep msg)


# Per-node signature of the last frame we returned — lets us detect a keepalive RESEND (the
# byte-identical stale buffer pipewiresrc re-pushes for a damage-driven idle monitor) so a
# fresh grab can force a current frame. Cheap: a sparse byte sample, not a full hash.
_LAST_SIG = {}

# Per-node FRESHNESS tracking (separate from _LAST_SIG, which force_fresh_grab owns): when did
# this node's frame CONTENT last change? On a damage-driven static monitor the screencast stops
# sending frames, so a grab returns the last (possibly STALE) buffer — and if the real screen
# changed since, we'd silently report old pixels as current. We can't tell "old-but-accurate"
# from "old-and-wrong" without a fresh frame, so we surface the frame's AGE and let screenshots
# flag the risk (see _stale_note) instead of asserting staleness either way.
_CHG_SIG = {}  # node -> last frame signature (for change detection)
_LAST_CHANGE_T = {}  # node -> monotonic time the signature last changed
STALE_AGE_S = float(
    os.environ.get("MCP_SCREEN_STALE_AGE_S", "1.5")
)  # older => flag stale-risk


def _note_frame(node_id, arr):
    """Record when this node's frame content last changed (freshness). Returns whether the
    content changed (Probe C reads it). Cheap; never raises."""
    try:
        sig = _sig(arr)
    except Exception:
        return False
    if sig != _CHG_SIG.get(node_id):
        _CHG_SIG[node_id] = sig
        _LAST_CHANGE_T[node_id] = time.monotonic()
        return True
    if node_id not in _LAST_CHANGE_T:
        _LAST_CHANGE_T[node_id] = time.monotonic()
    return False


def frame_age(node_id):
    """Seconds since this node's frame content last changed, or None if never seen."""
    t = _LAST_CHANGE_T.get(node_id)
    return None if t is None else max(0.0, time.monotonic() - t)


def _stale_note(ox, oy, dw, dh):
    """Warning string if any monitor overlapping the captured rect [ox,oy,dw,dh] is STATIC with an
    old frame — its pixels may not reflect the current screen (GNOME streams only on change, and a
    grab can return a stale buffer). Empty when all covered monitors are fresh. This is the guard
    against silently reporting a stale frame as live."""
    geo = state.SESSION.get("geo") or []
    stale = []
    for i, m in enumerate(geo):
        if (
            ox + dw <= m["x"]
            or ox >= m["x"] + m["w"]
            or oy + dh <= m["y"]
            or oy >= m["y"] + m["h"]
        ):
            continue
        age = frame_age(m["node"])
        if age is not None and age >= STALE_AGE_S:
            stale.append(f"monitor {i} ~{int(age)}s")
    if not stale:
        return ""
    return (
        f"  ⚠ STALE-RISK ({', '.join(stale)} since last change): this monitor is STATIC, so the "
        f"frame may NOT reflect the live screen if it changed without the screencast catching it. "
        f"Do NOT assert this is current — pass fresh=true, or click/scroll that monitor to confirm."
    )


def _sig(arr):
    """Cheap content signature (sparse pixel sample) for staleness detection, or None."""
    try:
        return hash(arr[::64, ::64, :3].tobytes())
    except Exception:
        return None


def force_fresh_grab(m):
    """Grab one monitor, forcing a CURRENT frame on a damage-driven STATIC monitor.

    A plain grab() of an idle GNOME output returns the keepalive-RESENT last buffer, so if the
    screen changed since it last emitted a frame (a click switched views, a message arrived) the
    capture is STALE — the bug behind 'I clicked but the screenshot shows the old state'. Here we
    pull once; if the monitor looks static (geo live:false, or the pull is byte-identical to our
    previous pull of this node) we generate a damage event (_nudge_prime, which restores the
    pointer) and use the post-damage frame, which reflects NOW. Falls back to whatever we have if
    priming can't run (user driving the pointer, MCP_SCREEN_NO_NUDGE). Updates the signature cache."""
    nid = m["node"]
    w, h, arr = _grab_or_prime(m)
    sig = _sig(arr)
    if (not m.get("live")) or (sig is not None and sig == _LAST_SIG.get(nid)):
        primed = _nudge_prime(
            nid,
            m["lpx"],
            m["lpy"],
            m["lw"],
            m["lh"],
            m.get("sx", 1.0) or 1.0,
            m.get("sy", 1.0) or 1.0,
        )
        if primed is not None:
            w, h, arr = primed
            sig = _sig(arr)
            _note_frame(
                nid, arr
            )  # the damage-primed frame is current — reset its freshness age
    _LAST_SIG[nid] = sig
    return w, h, arr


def _prime_static(mons):
    """Damage-prime each STATIC monitor in mons so the next grab_all() returns a CURRENT frame
    (the primed frame stays in the appsink's last_sample). Used by the fresh composite path."""
    for m in mons:
        if not m.get("live"):
            try:
                _nudge_prime(
                    m["node"],
                    m["lpx"],
                    m["lpy"],
                    m["lw"],
                    m["lh"],
                    m.get("sx", 1.0) or 1.0,
                    m.get("sy", 1.0) or 1.0,
                )
            except Exception:
                pass


#: True once we have fallen back to plain X11 capture for this process.
X11_MODE = False


def _x11_geo():
    """Geometry from xrandr for the X11 fallback. Same shape the portal path produces, minus
    `node` (there are no PipeWire nodes) — scale is 1.0 because X11 reports device pixels."""
    mons = x11capture.geometry()
    geo = []
    for i, m in enumerate(mons):
        geo.append(
            {
                "node": None,
                "x": m["x"],
                "y": m["y"],
                "w": m["w"],
                "h": m["h"],
                "sx": 1.0,
                "sy": 1.0,
                "live": True,
                "power": "unknown",
            }  # fmt: skip
        )
    if not geo:
        return None
    state.SESSION["geo"] = geo
    state.SESSION["W"] = max(m["x"] + m["w"] for m in geo)
    state.SESSION["H"] = max(m["y"] + m["h"] for m in geo)
    return geo


def ensure_geo(force=False):
    """Compute (and cache) per-monitor native-pixel geometry. Runtime only.

    For each stream: read logical position/size from props, grab once for native
    frame size, derive scale, and place the monitor on the global native canvas.
    Stores state.SESSION['geo'] and the canvas bounds W/H.

    X11 FALLBACK: on a host with no working ScreenCast portal (measured on GNOME/X11 Zorin
    15.3: portal binary absent, 0 portal interfaces on the bus, GStreamer 1.14 without
    appsink `leaky-type`) the portal session cannot start at all. Rather than fail, fall
    back to plain X11 capture, which works there. Input is unaffected — it already rides
    kernel uinput, which is display-server agnostic."""
    global X11_MODE
    if state.SESSION["geo"] and not force:
        return state.SESSION["geo"]
    if X11_MODE:
        return _x11_geo() or state.SESSION["geo"]
    try:
        state.ensure_session()
    except Exception:
        if x11capture.available():
            X11_MODE = True
            state.log("portal unavailable; falling back to plain X11 capture")
            g = _x11_geo()
            if g:
                return g
        raise
    if state.SESSION["geo"] and not force:
        return state.SESSION["geo"]
    # Probe all streams CONCURRENTLY: each cold pipeline build blocks ~8s, and they no longer
    # share a lock during the build (see _get_sink), so N monitors cost ~8s total, not N*8s.
    streams = list(state.SESSION["streams"])
    probe_res = {}

    def _probe(idx, node_id):
        try:
            fw, fh, _arr = grab(node_id, rebuild=False)
            probe_res[idx] = (fw, fh, True)
        except Exception as e:  # noqa: BLE001  (off, or ON-but-static: no first frame yet)
            state.log(
                "WARN no frame from",
                node_id,
                ":",
                e,
                "(no frame; registering by metadata)",
            )
            probe_res[idx] = (None, None, False)

    threads = [
        threading.Thread(target=_probe, args=(i, nid))
        for i, (nid, _props) in enumerate(streams)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    probed = []
    for i, (node_id, props) in enumerate(streams):
        lpx, lpy = props.get("position", (0, 0))
        lw, lh = props.get("size", (0, 0))
        fw, fh, live = probe_res[i]
        probed.append([node_id, lpx, lpy, lw, lh, fw, fh, live])
    # Monitors usually share a scale; borrow it for any monitor that couldn't be grabbed.
    dsx = next((p[5] / p[3] for p in probed if p[7] and p[3]), 1.0)
    dsy = next((p[6] / p[4] for p in probed if p[7] and p[4]), 1.0)
    power = _power_verdicts(probed)

    def _publish():
        geo = []
        for (node_id, lpx, lpy, lw, lh, fw, fh, live), pw in zip(probed, power):
            if live:
                sx = fw / lw if lw else 1.0
                sy = fh / lh if lh else 1.0
            else:
                sx, sy = dsx, dsy
                fw, fh = round(lw * sx), round(lh * sy)
            geo.append(
                {
                    "node": node_id,
                    "x": round(lpx * sx),
                    "y": round(lpy * sy),
                    "w": fw,
                    "h": fh,
                    "sx": sx,
                    "sy": sy,
                    "lpx": lpx,
                    "lpy": lpy,
                    "lw": lw,
                    "lh": lh,
                    "live": live,
                    "power": pw,
                }
            )
        if not geo:
            raise RuntimeError("ensure_geo: no streams")
        state.SESSION["geo"] = geo
        state.SESSION["W"] = max(m["x"] + m["w"] for m in geo)
        state.SESSION["H"] = max(m["y"] + m["h"] for m in geo)
        return geo

    # Publish a PRELIMINARY geo first: the nudge below moves the pointer via input._goto, which
    # resolves coords through global_to_logical(state.SESSION['geo']). Without this, on a fresh
    # session geo is None and the nudge throws (fails open) — i.e. it never actually fired.
    geo = _publish()
    # A no-frame monitor that is powered ON (or power 'unknown') is likely ON-but-static, not
    # asleep: GNOME streams on damage. Nudge once to generate a damage event and prime a frame.
    nudged = False
    for row, pw in zip(probed, power):
        if row[7] or pw == "off":
            continue
        sx0 = dsx if row[3] else 1.0
        sy0 = dsy if row[4] else 1.0
        primed = _nudge_prime(row[0], row[1], row[2], row[3], row[4], sx0, sy0)
        if primed is not None:
            row[5], row[6], row[7] = primed[0], primed[1], True
            nudged = True
    # Republish with the real frame size of any primed monitor.
    return _publish() if nudged else geo


def monitors_for(region):
    """geo entries intersecting region [x,y,w,h] (global native px); all if None."""
    geo = ensure_geo()
    if not region:
        return geo
    rx, ry, rw, rh = region
    hit = [
        m
        for m in geo
        if not (
            rx + rw <= m["x"]
            or rx >= m["x"] + m["w"]
            or ry + rh <= m["y"]
            or ry >= m["y"] + m["h"]
        )
    ]
    return hit or geo


def _full_canvas(mons):
    """Composite the given monitors onto the full native canvas -> PIL RGB."""
    canvas = np.zeros((state.SESSION["H"], state.SESSION["W"], 3), dtype=np.uint8)
    # rebuild=False: ensure_geo already primed live monitors, so this returns cached frames
    # instantly instead of paying the ~15s rebuild penalty per static monitor (the old
    # full-desktop capture spent 10-30s almost entirely here).
    frames = grab_all([m["node"] for m in mons], rebuild=False)
    geo_by_node = {m["node"]: m for m in mons}
    for nid, (w, h, arr) in frames.items():
        m = geo_by_node[nid]
        ch = min(h, canvas.shape[0] - m["y"])
        cw = min(w, canvas.shape[1] - m["x"])
        if ch > 0 and cw > 0:
            canvas[m["y"] : m["y"] + ch, m["x"] : m["x"] + cw] = arr[:ch, :cw]
    return Image.fromarray(canvas, "RGB")


def asleep_hint(monitor=None):
    """If the relevant monitor(s) have no frame (live:false), return an agent/human-friendly
    explanation distinguishing genuinely-OFF (DPMS) from ON-but-static; else None.

    A no-frame monitor is NOT necessarily asleep: GNOME/Mutter streams on damage, so a
    powered-ON but idle screen yields no frame until something on it changes (we already tried
    nudging it once). We use the per-monitor power verdict to word the message correctly.
    `monitor=N` scopes the check to that one; otherwise reports any no-frame monitor."""
    geo = state.SESSION.get("geo") or []
    idle = [i for i, m in enumerate(geo) if not m.get("live")]
    if not idle:
        return None
    if monitor is not None and int(monitor) not in idle:
        return None
    sel = [int(monitor)] if monitor is not None else idle
    which = f"Monitor {int(monitor)}" if monitor is not None else f"Monitor(s) {idle}"
    powers = {geo[i].get("power", "unknown") for i in sel if i < len(geo)}
    # Debug: why did priming actually fail for these nodes, verbatim from _nudge_prime.
    dbg = "; ".join(
        f"node {geo[i]['node']}: {_NUDGE_DEBUG.get(geo[i]['node'], 'not attempted')}"
        for i in sel
        if i < len(geo)
    )
    if powers == {"off"}:
        return (
            f"{which} is ASLEEP (DPMS/power-save): a blanked Wayland output emits no frames, "
            f"so it can't be captured (expected, not a fault). Ask the user to wake that "
            f"monitor (move the mouse onto it or press a key) and bring the target app to the "
            f"foreground, then retry. Any awake monitor is still capturable. [debug: {dbg}]"
        )
    if powers == {"on"}:
        return (
            f"{which} is ON but STATIC — GNOME/Mutter only streams frames on change, so an "
            f"idle screen yields no capture frame until something on it changes. mcp-screen "
            f"will nudge it to refresh; if it persists, click/scroll on that monitor. "
            f"[debug: {dbg}]"
        )
    return (
        f"{which} produced no frame: it is either ASLEEP (DPMS — wake it: move the mouse onto "
        f"it or press a key) or ON but STATIC (GNOME streams on damage, so an idle screen "
        f"yields no frame until something changes — click/scroll on it). mcp-screen already "
        f"tried nudging it. Any awake monitor is still capturable. [debug: {dbg}]"
    )


def validate_scope(geo, W, H, region=None, monitor=None):
    """Raise if a monitor index or region cannot name real pixels. Pure, so it is testable
    without a portal session.

    An unvalidated scope did not fail loudly — it silently produced a crop that every
    caller then read as legitimate: screen_read_text answered `count:0` (indistinguishable
    from "the region exists and is empty") and screen_verify answered CONFIRMED/changed
    for a region that does not exist, i.e. it certified an action against nothing. Found
    by an adversarial-args probe, not by the suite."""
    if monitor is not None:
        mi = int(monitor)
        if not (0 <= mi < len(geo)):
            raise RuntimeError(
                f"monitor {mi} does not exist — this desktop has {len(geo)} "
                f"(valid: 0..{len(geo) - 1}). Call screen_list_monitors."
            )
    if region:
        rx, ry, rw, rh = [int(v) for v in region]
        if rw <= 0 or rh <= 0:
            raise RuntimeError(f"region {region} has non-positive width/height")
        if W and H and (rx >= W or ry >= H or rx + rw <= 0 or ry + rh <= 0):
            raise RuntimeError(
                f"region {region} lies entirely outside the desktop (0,0,{W},{H}) — "
                f"nothing there to capture. Call screen_list_monitors for the bounds."
            )


def capture_desktop(region=None, monitor=None, fresh=False):
    """Return (PIL RGB at real desktop pixels, origin_x, origin_y).

    monitor=index -> that monitor's frame (origin = its x,y).
    region within a single monitor -> fast single grab + crop.
    region spanning monitors / no region -> full composite then crop.

    fresh=True forces a CURRENT frame for the captured monitor(s) on a damage-driven static
    monitor (defeats the keepalive-resend stale-capture); see force_fresh_grab. Costs a pointer
    nudge per static monitor, so callers pass it when freshness matters (a normal screenshot),
    not for bulk/locate composites."""
    geo = ensure_geo()
    if X11_MODE:
        # No PipeWire nodes here: grab the root once and crop. Region/monitor semantics
        # match the portal path so callers and view transforms are identical.
        if isinstance(region, str):
            try:
                region = json.loads(region)
            except Exception:
                region = None
        if monitor is not None and region:
            m = geo[int(monitor)]
            rx, ry, rw, rh = (int(v) for v in region)
            rx, ry = max(0, rx), max(0, ry)
            rw, rh = max(1, min(rw, m["w"] - rx)), max(1, min(rh, m["h"] - ry))
            region, monitor = [m["x"] + rx, m["y"] + ry, rw, rh], None
        if monitor is not None:
            m = geo[int(monitor)]
            img = x11capture.grab_region(m["x"], m["y"], m["w"], m["h"])
            if img is None:
                raise RuntimeError("X11 capture failed for monitor %s" % monitor)
            return img, m["x"], m["y"]
        if region:
            rx, ry, rw, rh = (int(v) for v in region)
            img = x11capture.grab_region(rx, ry, rw, rh)
            if img is None:
                raise RuntimeError("X11 capture failed for region %s" % (region,))
            return img, rx, ry
        img = x11capture.grab_root()
        if img is None:
            raise RuntimeError("X11 root capture failed")
        return img, 0, 0
    # Single-monitor/region grabber. fresh=True nudges for a current frame. Otherwise use a
    # NON-DESTRUCTIVE grab (rebuild=False): it returns the new/last-retained frame and RAISES on a
    # cold monitor WITHOUT dropping+rebuilding the pipeline — the destructive rebuild (_grab_or_prime
    # → grab(rebuild=True)) cooled a static monitor's warm pipeline (clearing last_sample), which is
    # why repeated region reads of an idle monitor kept failing while the composite still worked.
    # On a raise, the caller falls back to cropping the composite (also non-destructive, tolerates
    # a no-frame monitor) instead of erroring.
    _grab1 = force_fresh_grab if fresh else (lambda m: grab(m["node"], rebuild=False))
    # A monitor registered idle (live:false) carries synthesized w/h from a borrowed scale.
    # If it has since woken, its cached last_sample now reports a real (and possibly different)
    # size; re-probe once so its true scale and the canvas bounds are recomputed before blit.
    for m in geo:
        if not m.get("live"):
            wh = _peek(m["node"])
            if wh and (wh[0] != m["w"] or wh[1] != m["h"]):
                geo = ensure_geo(force=True)
                break
    if isinstance(
        region, str
    ):  # tolerate a stringified "[x,y,w,h]" (e.g. an undeclared arg)
        try:
            region = json.loads(region)
        except Exception:
            region = None
    # `monitor` returned early and silently DROPPED `region`: asking for
    # region=[0,0,600,300] with monitor=0 handed back the whole 3840x2160 monitor with no
    # error — a plausible-but-wrong result, the worst kind (found driving Grok Build).
    # Together they now mean "this box, relative to that monitor's origin", which is what
    # the combination reads as and is strictly more useful than ignoring one of them.
    if monitor is not None and region:
        validate_scope(
            geo, state.SESSION.get("W") or 0, state.SESSION.get("H") or 0, None, monitor
        )
        m = geo[int(monitor)]
        rx, ry, rw, rh = (int(v) for v in region)
        # Clip to the named monitor. Without this an oversized or offset box silently
        # spills onto the neighbouring monitor and the caller gets pixels from a screen
        # it did not ask for — worse than an error, because it looks like a valid crop.
        rx, ry = max(0, rx), max(0, ry)
        rw = max(1, min(rw, m["w"] - rx))
        rh = max(1, min(rh, m["h"] - ry))
        region, monitor = [m["x"] + rx, m["y"] + ry, rw, rh], None
    validate_scope(
        geo, state.SESSION.get("W") or 0, state.SESSION.get("H") or 0, region, monitor
    )
    if monitor is not None:
        m = geo[int(monitor)]
        try:
            w, h, arr = _grab1(m)
            return Image.fromarray(arr, "RGB"), m["x"], m["y"]
        except Exception:
            # Static-monitor fallback: the single-monitor grab can fail (and its rebuild path goes
            # COLD) where the composite — which never rebuilds and tolerates a no-frame monitor —
            # still returns that node's last frame. Crop the native composite instead of erroring.
            return (
                _full_canvas(geo).crop(
                    (m["x"], m["y"], m["x"] + m["w"], m["y"] + m["h"])
                ),
                m["x"],
                m["y"],
            )
    if region:
        rx, ry, rw, rh = [int(v) for v in region]
        mons = monitors_for([rx, ry, rw, rh])
        if not mons:
            raise RuntimeError(
                f"region {region} does not intersect any monitor. "
                f"Call screen_list_monitors for the bounds."
            )
        if len(mons) == 1:
            m = mons[0]
            try:
                w, h, arr = _grab1(m)
                img = Image.fromarray(arr, "RGB")
                cx, cy = rx - m["x"], ry - m["y"]
                return (
                    img.crop((max(0, cx), max(0, cy), cx + rw, cy + rh)),
                    max(rx, m["x"]),
                    max(ry, m["y"]),
                )
            except Exception:
                pass  # fall through to the composite crop (robust for a static monitor)
        if fresh:
            _prime_static(mons)
        return _full_canvas(mons).crop((rx, ry, rx + rw, ry + rh)), rx, ry
    if fresh:
        _prime_static(geo)
    return _full_canvas(geo), 0, 0


try:  # OpenCV is already a grounding dependency; optional here so capture degrades alone
    import cv2 as _cv2
except Exception:  # pragma: no cover - host-dependent
    _cv2 = None


def _downscale(img, w, h):
    """Downscale a PIL image to (w, h) — the single hottest CPU stage in a screenshot.

    cv2.INTER_AREA over PIL LANCZOS: 18.8ms vs 287.5ms on a real 3840x2160 -> 2576x1449
    frame (15x). INTER_AREA is also the principled filter for MINIFICATION — it averages
    the source pixels each output pixel covers, so it antialiases without the ringing a
    cubic/lanczos kernel puts on text edges.

    Legibility was the reason not to touch this, so it was measured rather than assumed:
    OCR against known rendered text at 9/10/11/12/13/14/16/20px scored PIL-LANCZOS,
    INTER_AREA, INTER_LANCZOS4 and INTER_CUBIC at 92-93% mean and 91-92% across the three
    smallest sizes — indistinguishable. An earlier, narrower eval put LANCZOS 1pp ahead and
    concluded "don't swap the filter"; that gap did not survive more sizes and small fonts.

    Falls back to PIL when cv2 is missing, so capture never hard-depends on grounding's stack."""
    if _cv2 is None:
        return img.resize((w, h), LANCZOS)
    arr = np.asarray(img)
    out = _cv2.resize(arr, (w, h), interpolation=_cv2.INTER_AREA)
    return Image.fromarray(out, img.mode)


def encode_store(img, ox, oy, label, t0, max_edge=None, max_out_kb=None):
    """Downscale to <=max_edge (default state.MAX_EDGE) long edge, remember the view->desktop
    transform, encode WebP. Pass a smaller max_edge for tour thumbnails (fewer tokens). For
    lossy thumbnails (max_edge < MAX_EDGE) we use WebP q=80 to shrink payload further.

    Returns MCP content list: a text summary + the WebP image."""
    dw, dh = img.size
    le = max(dw, dh)
    me = int(max_edge) if max_edge else state.MAX_EDGE
    scale = min(1.0, me / le) if le else 1.0
    with state.stage("resize"):
        out = (
            img
            if scale >= 1.0
            else _downscale(img, max(1, round(dw * scale)), max(1, round(dh * scale)))
        )
    vid = state.next_view_id()
    state.SESSION["view"] = {
        "ox": ox,
        "oy": oy,
        "scale": scale,
        "dw": dw,
        "dh": dh,
        "id": vid,
    }
    buf = io.BytesIO()
    _enc = state.stage("encode")
    _enc.__enter__()
    if max_edge and me < state.MAX_EDGE:
        out.convert("RGB").save(buf, format="WEBP", quality=80, method=4)
    else:
        out.convert("RGB").save(
            buf,
            format="WEBP",
            lossless=True,
            method=WEBP_METHOD,
            quality=WEBP_EFFORT,
        )
    _enc.__exit__(None, None, None)
    raw = buf.getvalue()
    with state.stage("fit"):
        # Reserve the text we actually emit alongside the image. The header alone is ~300B,
        # but a stale-note or an annotate element list can be far larger than the default
        # envelope — under-reserving pushes the whole tool result back over the client cap.
        _reserve = 2048 + len(_stale_note(ox, oy, dw, dh).encode()) + 512
        raw, budget_note, (fw, fh) = budget.fit_to_budget(
            out, raw, _downscale, max_out_kb=max_out_kb, reserve_bytes=_reserve
        )
    # A fitted image is SMALLER than `out`, so the view transform stamped above no longer
    # describes what the client receives. Restate it against the shipped pixels: advertising
    # the pre-shrink scale makes every view-space click miss by that ratio, and view_id
    # cannot catch it because the id never changed. Verified: a 2576x1449/scale-0.6708 shot
    # shipped as 526x296 under a 20KB cap — clicks landed ~4.9x short.
    if (fw, fh) != out.size:
        scale = (fw / dw) if dw else scale
        state.SESSION["view"]["scale"] = scale
    ms = int((time.time() - t0) * 1000)
    txt = (
        f"{label}: view#{vid} {fw}x{fh} (scale {scale:.4f}) covering desktop "
        f"origin=({ox},{oy}) size={dw}x{dh}. {len(raw) // 1024}KB, {ms}ms. "
        f"Click with space='view' using coords as seen here (pass view_id={vid} to bind "
        f"the click to THIS screenshot)."
    )
    txt += budget_note
    txt += _stale_note(
        ox, oy, dw, dh
    )  # flag a possibly-stale static monitor — never report old pixels as live
    return [
        {"type": "text", "text": txt},
        {
            "type": "image",
            "data": base64.b64encode(raw).decode(),
            "mimeType": "image/webp",
        },
    ]


def shutdown():
    """Tear down all persistent pipelines and clear the stream cache."""
    with _LOCK:
        for ent in _PIPES.values():
            try:
                ent["pipe"].set_state(Gst.State.NULL)
            except Exception:  # noqa: BLE001
                pass
            try:
                os.close(ent["fd"])
            except Exception:  # noqa: BLE001
                pass
        _PIPES.clear()
        _LAST_SIG.clear()
        _CHG_SIG.clear()
        _LAST_CHANGE_T.clear()
