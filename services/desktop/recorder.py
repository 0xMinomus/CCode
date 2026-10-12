"""recorder.py — session recording / replay / audit for mcp-screen (v1.2).

Fully self-hosted and local: nothing leaves the machine. A recording is a directory
under ~/.local/share/mcp-screen/sessions/<id>/ containing

  trajectory.jsonl   append-only event log (asciinema-style header + rrweb-style
                     structured events). One JSON object per line:
                       {v,type:"meta",...}        once at start, once at stop
                       {seq,ts,type:"action",...} every input tool call
                       {seq,ts,type:"screenshot"} every captured frame (deduped)
  frames/NNNNNN.webp content-addressed frame images (sha256 dedup: identical frames
                     reuse one file, referenced by image_ref)
  replay.html        self-contained vanilla-JS viewer dropped in on start()

The recorder is a passive sink. The server calls REC.start()/stop() and, while active,
REC.log_action()/REC.log_frame() around its existing tool handlers. Everything is guarded
by one lock, every method is a no-op when inactive, and nothing here ever raises into the
caller — a broken recorder must never break the desktop tools.

Coordinate model (shared with capture.py / input.py):
  A screenshot's `view` transform is {ox,oy,scale,dw,dh}. A click's `resolved_coords`
  are global NATIVE desktop pixels. To place the replay dot we go
  desktop -> view-pixel via (coord-o)*scale, then scale again by the ratio of the stored
  WebP's displayed size to the view's rendered size (dw*scale). replay.html does this.
"""

import os
import io
import json
import time
import shutil
import hashlib
import threading

from PIL import Image

# ---------------------------------------------------------------------------
# Config (env-overridable)
# ---------------------------------------------------------------------------
SESS_ROOT = os.path.expanduser("~/.local/share/mcp-screen/sessions")
REC_CAP = int(os.environ.get("MCP_SCREEN_REC_CAP", "30"))  # keep newest N sessions
REC_EDGE = int(os.environ.get("MCP_SCREEN_REC_EDGE", "1280"))  # frame long-edge px
REC_QUALITY = 80  # WebP quality (lossy)

LANCZOS = Image.Resampling.LANCZOS


def _now():
    return time.time()


def _ts_id():
    """Default session id: sortable local timestamp."""
    return time.strftime("%Y%m%d-%H%M%S", time.localtime())


# ---------------------------------------------------------------------------
# Recorder
# ---------------------------------------------------------------------------
class Recorder:
    """Thread-safe append-only session recorder. One active session at a time.

    All public methods take the lock and no-op (or return a falsey value) when no
    session is active. No method raises into the caller; internal errors are swallowed
    after a best-effort note so recording can never break the tools it observes."""

    def __init__(self):
        self._lock = threading.Lock()
        self._dir: str | None = None  # active session dir, or None
        self._fh = None  # open trajectory.jsonl handle (line-buffered)
        self._seq = 0  # monotonic across actions + frames
        self._hashes = {}  # sha256 -> image_ref (frames/NNNNNN.webp) for dedup
        self._session = None  # active session id

    # -- lifecycle ---------------------------------------------------------
    def active(self):
        with self._lock:
            return self._fh is not None

    def start(self, sid=None):
        """Begin a session. Returns its directory (or None on failure).

        Creates <root>/<id>/frames/, opens trajectory.jsonl line-buffered, writes the
        meta header, prunes to the newest REC_CAP sessions, and drops replay.html in."""
        with self._lock:
            try:
                if self._fh is not None:
                    self._close_locked(reason="restart")
                sid = (sid or _ts_id()).strip() or _ts_id()
                sid = _safe_id(sid)
                d = os.path.join(SESS_ROOT, sid)
                os.makedirs(os.path.join(d, "frames"), exist_ok=True)
                fh = open(os.path.join(d, "trajectory.jsonl"), "a", buffering=1)
                self._dir = d
                self._fh = fh
                self._seq = 0
                self._hashes = {}
                self._session = sid
                self._write_locked(
                    {
                        "v": 1,
                        "type": "meta",
                        "session": sid,
                        "started": _now(),
                        "rec_edge": REC_EDGE,
                        "rec_quality": REC_QUALITY,
                    }
                )
                # Drop the viewer in (overwrite so it always matches this build).
                try:
                    with open(os.path.join(d, "replay.html"), "w") as rf:
                        rf.write(REPLAY_HTML)
                except Exception as e:  # noqa: BLE001
                    _warn("replay.html write failed:", e)
                self._prune_locked()
                return d
            except Exception as e:  # noqa: BLE001
                _warn("start failed:", e)
                self._dir = None
                self._fh = None
                return None

    def stop(self):
        """End the active session. Returns its directory (or None if none was active)."""
        with self._lock:
            if self._fh is None:
                return None
            d = self._dir
            self._close_locked(reason="stop")
            return d

    def _close_locked(self, reason="stop"):
        try:
            self._write_locked(
                {
                    "v": 1,
                    "type": "meta",
                    "session": self._session,
                    "ended": _now(),
                    "frames": len(self._hashes),
                    "events": self._seq,
                    "reason": reason,
                }
            )
        except Exception as e:  # noqa: BLE001
            _warn("close meta failed:", e)
        try:
            if self._fh is not None:
                self._fh.flush()
                self._fh.close()
        except Exception as e:  # noqa: BLE001
            _warn("close fh failed:", e)
        self._fh = None
        self._dir = None
        self._session = None
        self._hashes = {}

    # -- logging -----------------------------------------------------------
    def log_action(self, tool, args, result, ok, ms, resolved=None, view=None):
        """Append an action event. No-op when inactive; never raises."""
        with self._lock:
            if self._fh is None:
                return
            try:
                self._write_locked(
                    {
                        "seq": self._next_seq_locked(),
                        "ts": _now(),
                        "type": "action",
                        "tool": tool,
                        "args": _sanitize_args(args),
                        "resolved_coords": list(resolved)
                        if resolved is not None
                        else None,
                        "result": (str(result)[:500] if result is not None else None),
                        "ok": bool(ok),
                        "ms": int(ms) if ms is not None else None,
                        "view": _copy_view(view),
                    }
                )
            except Exception as e:  # noqa: BLE001
                _warn("log_action failed:", e)

    def log_frame(self, pil_img, tool, view=None):
        """Downscale -> WebP q80 -> content-addressed store -> screenshot event.

        Identical frames (by sha256 of the encoded bytes) reuse one file. No-op when
        inactive; never raises. Returns the image_ref (or None)."""
        with self._lock:
            if self._fh is None:
                return None
            try:
                img = pil_img.convert("RGB")
                w0, h0 = img.size
                le = max(w0, h0)
                scale = min(1.0, REC_EDGE / le) if le else 1.0
                if scale < 1.0:
                    img = img.resize(
                        (max(1, round(w0 * scale)), max(1, round(h0 * scale))), LANCZOS
                    )
                buf = io.BytesIO()
                img.save(buf, format="WEBP", quality=REC_QUALITY)
                raw = buf.getvalue()
                w, h = img.size
                sha = hashlib.sha256(raw).hexdigest()

                ref = self._hashes.get(sha)
                if ref is None:
                    d = self._dir
                    if d is None:
                        return None
                    fname = "frames/%06d.webp" % len(self._hashes)
                    with open(os.path.join(d, fname), "wb") as ff:
                        ff.write(raw)
                    self._hashes[sha] = fname
                    ref = fname

                self._write_locked(
                    {
                        "seq": self._next_seq_locked(),
                        "ts": _now(),
                        "type": "screenshot",
                        "tool": tool,
                        "image_ref": ref,
                        "sha256": sha,
                        "w": w,
                        "h": h,
                        "bytes": len(raw),
                        "view": _copy_view(view),
                    }
                )
                return ref
            except Exception as e:  # noqa: BLE001
                _warn("log_frame failed:", e)
                return None

    # -- internals (must hold lock) ---------------------------------------
    def _next_seq_locked(self):
        s = self._seq
        self._seq += 1
        return s

    def _write_locked(self, obj):
        fh = self._fh
        if fh is None:
            return
        fh.write(json.dumps(obj, separators=(",", ":")) + "\n")

    def _prune_locked(self):
        """Keep only the newest REC_CAP session dirs (by mtime). Never touches the
        currently active dir."""
        try:
            entries = []
            for name in os.listdir(SESS_ROOT):
                p = os.path.join(SESS_ROOT, name)
                if os.path.isdir(p):
                    entries.append((os.path.getmtime(p), p))
            entries.sort(reverse=True)
            for _mt, p in entries[REC_CAP:]:
                if p == self._dir:
                    continue
                shutil.rmtree(p, ignore_errors=True)
        except Exception as e:  # noqa: BLE001
            _warn("prune failed:", e)


def _safe_id(sid):
    """Constrain a session id to a single safe path component."""
    sid = os.path.basename(sid)
    keep = "-_.abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    cleaned = "".join(c if c in keep else "_" for c in sid)
    return cleaned or _ts_id()


def _sanitize_args(args):
    """Copy args for the log, dropping the bulky/irrelevant 'shot' flag."""
    if not isinstance(args, dict):
        return args
    return {k: v for k, v in args.items() if k != "shot"}


def _copy_view(view):
    if not isinstance(view, dict):
        return None
    return {k: view[k] for k in ("ox", "oy", "scale", "dw", "dh") if k in view}


def _warn(*a):
    try:
        import sys

        print("recorder:", *a, file=sys.stderr, flush=True)
    except Exception:  # noqa: BLE001
        pass


# Module singleton.
REC = Recorder()


# ---------------------------------------------------------------------------
# MCP tool handler
# ---------------------------------------------------------------------------
def _txt(s):
    return {"content": [{"type": "text", "text": s}]}


def _list_sessions():
    out = []
    try:
        for name in sorted(os.listdir(SESS_ROOT)):
            p = os.path.join(SESS_ROOT, name)
            if not os.path.isdir(p):
                continue
            tj = os.path.join(p, "trajectory.jsonl")
            nlines = 0
            if os.path.exists(tj):
                try:
                    with open(tj) as f:
                        nlines = sum(1 for _ in f)
                except Exception:  # noqa: BLE001
                    pass
            out.append((name, nlines))
    except FileNotFoundError:
        pass
    return out


def tool_session(args):
    """Recording control tool. op in {start, stop, list, status, replay-path}."""
    op = (args or {}).get("op", "status")
    try:
        if op == "start":
            d = REC.start(args.get("sid"))
            if not d:
                return _txt("recording: start FAILED (see server log)")
            return _txt(f"recording -> {d}")

        if op == "stop":
            d = REC.stop()
            if not d:
                return _txt("recording: not active")
            return _txt(f"stopped {d}; open {os.path.join(d, 'replay.html')}")

        if op == "list":
            rows = _list_sessions()
            if not rows:
                return _txt(f"no sessions under {SESS_ROOT}")
            lines = [f"{name}  ({n} events)" for name, n in rows]
            lines.append(f"-- {len(rows)} session(s) in {SESS_ROOT}")
            return _txt("\n".join(lines))

        if op == "status":
            if REC.active():
                return _txt(f"recording active -> {REC._dir}")
            return _txt("recording: inactive")

        if op == "replay-path":
            d = REC._dir if REC.active() else None
            if not d:
                rows = _list_sessions()
                if not rows:
                    return _txt("no sessions to replay")
                d = os.path.join(SESS_ROOT, rows[-1][0])
            return _txt(os.path.join(d, "replay.html"))

        return _txt(f"unknown op '{op}' (use start|stop|list|status|replay-path)")
    except Exception as e:  # noqa: BLE001
        _warn("tool_session failed:", e)
        return _txt(f"recording: error: {e}")


# ---------------------------------------------------------------------------
# Embedded replay viewer (written to each session dir on start).
#
# Vanilla JS/HTML/CSS, no deps. Renders the step list with safe DOM methods
# (textContent only — no innerHTML — so locally-logged strings cannot inject markup),
# fetches trajectory.jsonl + frames relative to its own directory, and overlays a red
# dot at each action's click point using the entry's/preceding frame's view transform.
# ---------------------------------------------------------------------------
REPLAY_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>mcp-screen replay</title>
<style>
  :root { --bg:#15171c; --panel:#1d2027; --line:#2c313c; --fg:#e6e9ef;
          --muted:#8b94a7; --accent:#5aa9ff; --ok:#3ecf8e; --bad:#ff6b6b; }
  * { box-sizing: border-box; }
  html,body { margin:0; height:100%; background:var(--bg); color:var(--fg);
              font:13px/1.45 ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,sans-serif; }
  #app { display:grid; grid-template-columns: 320px 1fr; grid-template-rows: auto 1fr;
         height:100vh; }
  header { grid-column:1 / 3; display:flex; align-items:center; gap:14px;
           padding:10px 14px; border-bottom:1px solid var(--line); background:var(--panel); }
  header h1 { font-size:14px; margin:0; font-weight:600; letter-spacing:.2px; }
  header .meta { color:var(--muted); font-size:12px; }
  header .grow { flex:1; }
  #scrub { width:100%; accent-color:var(--accent); }
  .scrubwrap { flex:2; display:flex; align-items:center; gap:10px; min-width:240px; }
  #pos { font-variant-numeric:tabular-nums; color:var(--muted); white-space:nowrap; }
  button { background:#2a2f3a; color:var(--fg); border:1px solid var(--line);
           border-radius:6px; padding:5px 10px; cursor:pointer; font-size:12px; }
  button:hover { background:#333a47; }
  #side { border-right:1px solid var(--line); overflow:auto; background:var(--panel); }
  .step { padding:8px 12px; border-bottom:1px solid var(--line); cursor:pointer;
          display:flex; gap:8px; align-items:baseline; }
  .step:hover { background:#23272f; }
  .step.sel { background:#2b3956; }
  .step .seq { color:var(--muted); font-variant-numeric:tabular-nums; min-width:30px; }
  .step .tool { font-weight:600; }
  .step .kind { font-size:10px; text-transform:uppercase; letter-spacing:.5px;
                color:var(--muted); border:1px solid var(--line); border-radius:4px;
                padding:0 4px; }
  .step .ok { color:var(--ok); } .step .bad { color:var(--bad); }
  .step .det { color:var(--muted); font-size:11px; flex:1;
               overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  #stage { position:relative; overflow:auto; display:flex; align-items:center;
           justify-content:center; padding:18px; }
  #imgwrap { position:relative; display:inline-block; max-width:100%; max-height:100%; }
  #shot { display:block; max-width:100%; max-height:calc(100vh - 120px);
          border:1px solid var(--line); border-radius:4px; background:#000; }
  #dot { position:absolute; width:18px; height:18px; margin:-9px 0 0 -9px; border-radius:50%;
         background:rgba(255,60,60,.35); border:2px solid #ff3c3c; display:none;
         box-shadow:0 0 0 2px rgba(255,60,60,.25); pointer-events:none;
         transition:left .08s linear, top .08s linear; }
  #empty { color:var(--muted); padding:40px; text-align:center; }
</style>
</head>
<body>
<div id="app">
  <header>
    <h1>mcp-screen replay</h1>
    <span class="meta" id="sessmeta"></span>
    <div class="grow"></div>
    <button id="prev">&larr;</button>
    <button id="next">&rarr;</button>
    <div class="scrubwrap">
      <input id="scrub" type="range" min="0" max="0" value="0">
      <span id="pos">0 / 0</span>
    </div>
  </header>
  <div id="side"></div>
  <div id="stage">
    <div id="imgwrap">
      <img id="shot" alt="frame">
      <div id="dot"></div>
    </div>
    <div id="empty" style="display:none">No trajectory loaded.</div>
  </div>
</div>
<script>
(function () {
  "use strict";
  // Resolve everything relative to THIS file's directory, so the viewer works whether
  // it's opened over file:// or served by `python -m http.server`.
  var base = new URL(".", location.href);
  var sideEl = document.getElementById("side");
  var imgEl = document.getElementById("shot");
  var dotEl = document.getElementById("dot");
  var scrubEl = document.getElementById("scrub");
  var posEl = document.getElementById("pos");
  var metaEl = document.getElementById("sessmeta");
  var emptyEl = document.getElementById("empty");

  var events = [];   // all parsed events in file order
  var steps = [];    // index list into `events` we expose as scrubber stops
  var cur = 0;

  function parseJSONL(text) {
    var out = [];
    var lines = text.split("\n");
    for (var i = 0; i < lines.length; i++) {
      var ln = lines[i].trim();
      if (!ln) continue;
      try { out.push(JSON.parse(ln)); } catch (e) { /* skip malformed line */ }
    }
    return out;
  }

  // The frame to show for a given event index: the screenshot at/just before it.
  function frameForIndex(i) {
    for (var j = i; j >= 0; j--) {
      if (events[j].type === "screenshot") return events[j];
    }
    return null;
  }

  function fmtArgs(a) {
    if (a == null) return "";
    try { return JSON.stringify(a); } catch (e) { return String(a); }
  }

  function buildSteps() {
    steps = [];
    for (var i = 0; i < events.length; i++) {
      var e = events[i];
      if (e.type === "action" || e.type === "screenshot") steps.push(i);
    }
  }

  // Build a step row purely with DOM nodes + textContent (no innerHTML).
  function span(cls, text) {
    var s = document.createElement("span");
    s.className = cls;
    s.textContent = text;
    return s;
  }

  function renderList() {
    sideEl.textContent = "";
    for (var k = 0; k < steps.length; k++) {
      (function (k) {
        var e = events[steps[k]];
        var row = document.createElement("div");
        row.className = "step";
        var det = "";
        if (e.type === "action") {
          det = fmtArgs(e.args);
          if (e.resolved_coords) det += "  @[" + e.resolved_coords.join(",") + "]";
        } else if (e.type === "screenshot") {
          det = (e.w || "?") + "x" + (e.h || "?") + "  " +
                (e.bytes ? Math.round(e.bytes / 1024) + "KB" : "");
        }
        row.appendChild(span("seq", e.seq != null ? String(e.seq) : String(k)));
        row.appendChild(span("kind", e.type === "action" ? "act" : "shot"));
        row.appendChild(span("tool", e.tool || e.type));
        row.appendChild(span("det", det));
        if (e.type === "action") {
          row.appendChild(span(e.ok ? "ok" : "bad", e.ok ? "ok" : "err"));
        }
        row.addEventListener("click", function () { goto(k); });
        sideEl.appendChild(row);
      })(k);
    }
  }

  function placeDot(e, frame) {
    // Only actions with resolved coords + a frame with a view transform get a dot.
    dotEl.style.display = "none";
    if (!e || e.type !== "action" || !e.resolved_coords) return;
    var view = e.view || (frame && frame.view);
    if (!view) return;
    var rx = e.resolved_coords[0], ry = e.resolved_coords[1];
    // desktop px -> view px: (coord - origin) * scale
    var vx = (rx - view.ox) * view.scale;
    var vy = (ry - view.oy) * view.scale;
    // view px -> stored-image px: the stored WebP was rendered from a
    // (dw*scale) x (dh*scale) view, then possibly downscaled again to REC_EDGE. So
    // scale by the displayed-image size over that rendered view size.
    var renderedW = view.dw * view.scale;
    var renderedH = view.dh * view.scale;
    var dispW = imgEl.clientWidth, dispH = imgEl.clientHeight;
    if (!renderedW || !renderedH || !dispW || !dispH) return;
    var px = vx * (dispW / renderedW);
    var py = vy * (dispH / renderedH);
    dotEl.style.left = px + "px";
    dotEl.style.top = py + "px";
    dotEl.style.display = "block";
  }

  function showFrame(frame, thenPlace) {
    if (!frame) { thenPlace(); return; }
    var url = new URL(frame.image_ref, base).href;
    if (imgEl.getAttribute("src") === url && imgEl.complete) {
      thenPlace();
      return;
    }
    imgEl.onload = function () { thenPlace(); };
    imgEl.src = url;
  }

  function goto(k) {
    if (!steps.length) return;
    cur = Math.max(0, Math.min(steps.length - 1, k));
    scrubEl.value = cur;
    posEl.textContent = (cur + 1) + " / " + steps.length;
    var rows = sideEl.children;
    for (var i = 0; i < rows.length; i++) rows[i].classList.toggle("sel", i === cur);
    if (rows[cur]) rows[cur].scrollIntoView({ block: "nearest" });
    var idx = steps[cur];
    var e = events[idx];
    var frame = frameForIndex(idx);
    showFrame(frame, function () { placeDot(e, frame); });
  }

  scrubEl.addEventListener("input", function () { goto(parseInt(scrubEl.value, 10)); });
  document.getElementById("prev").addEventListener("click", function () { goto(cur - 1); });
  document.getElementById("next").addEventListener("click", function () { goto(cur + 1); });
  window.addEventListener("keydown", function (ev) {
    if (ev.key === "ArrowLeft") goto(cur - 1);
    else if (ev.key === "ArrowRight") goto(cur + 1);
  });
  window.addEventListener("resize", function () { goto(cur); });

  fetch(new URL("trajectory.jsonl", base).href, { cache: "no-store" })
    .then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.text();
    })
    .then(function (text) {
      events = parseJSONL(text);
      var meta = events.find(function (e) { return e.type === "meta" && e.started; });
      if (meta) {
        var d = new Date(meta.started * 1000);
        metaEl.textContent = "session " + meta.session + " — " + d.toLocaleString();
      }
      buildSteps();
      if (!steps.length) { emptyEl.style.display = "block"; return; }
      renderList();
      scrubEl.max = steps.length - 1;
      goto(0);
    })
    .catch(function (err) {
      emptyEl.style.display = "block";
      emptyEl.textContent = "Failed to load trajectory.jsonl: " + err +
        " (serve this folder, e.g. python -m http.server)";
    });
})();
</script>
</body>
</html>
"""
