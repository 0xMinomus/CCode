#!/usr/bin/env python3
"""mcp-screen v0.9 — modular MCP server: see + drive the desktop.

Thin MCP stdio loop wiring the modules:
  state      session/portal plumbing
  capture    persistent PipeWire capture, per-monitor crops, encode (view-space)
  input      pointer/keyboard via RemoteDesktop portal (per-stream logical coords)
  grounding  optional Set-of-Marks (OCR + icons) annotation
  awareness  focused-window / window-list (GNOME Shell ext + AT-SPI fallback)
  reliability stable-frame / verify / action log
  recorder   session record + replay
  prereqs    prerequisite / capability matrix (screen_diag)

Coordinate model: every screenshot downscales to the model's native image size and
the server stores the view->desktop transform; click/type use space='view' (default)
with the pixel coords you see. No monitor guessing.

OPS NOTES (hard-won; read before changing capture/input/cursor code):
  * Hot-reload: screen_reload re-execs in place (os.execv) — picks up code edits AND new
    tools (via notifications/tools/list_changed) with NO /mcp reconnect. Use it after edits.
  * screen_diag dumps live session/geo/cursor/grounding health — reach for it first when
    something's off. Keep it; don't treat diagnostics as throwaway scaffolding.
  * Fractional scaling: NotifyPointerMotionAbsolute coords are LOGICAL and LOCAL to each
    stream (0..monitor_logical_size), keyed by node_id. Do NOT add a global logical origin
    or the portal clamps ("Invalid position"). See input.global_to_logical.
  * Cursor position: cursor_mode=METADATA(4) (state.py) means the cursor is NOT baked into
    frames; pipewiresrc attaches it as a "cursor" ROI meta on its SRC pad. videoconvert
    STRIPS that meta, and PyGObject can't downcast it anyway — so capture.py reads it with a
    ctypes pad-probe on the pipewiresrc src pad (offsets are x86-64). We composite a marker
    back into plain screenshots so the pointer stays visible.
  * User-takeover guard: input.guard_user compares the live pointer to where WE last
    commanded it (cmd_cursor); >GUARD_THRESH px ⇒ the user grabbed the mouse ⇒ STOP. Pass
    force=true to bypass / take control back. Our own moves keep cmd_cursor in sync so they
    never trip it. Fails open if the cursor can't be read.
  * GPU is hard-disabled (CUDA_VISIBLE_DEVICES="" below); grounding is CPU-only by design.
  * Unicode typing: the portal keysym path drops non-ASCII, so input.type_text auto-pastes
    any non-ASCII string via wl-copy + Ctrl+V (clipboard saved/restored). DEPENDENCY:
    `wl-clipboard` (pacman) — falls back to ASCII-only keysyms if absent. ASCII still uses
    keysyms (no clipboard pollution). xdotool/XTEST can NOT reach native-Wayland apps.
  * On any tool exception the dispatcher writes the full traceback to /tmp/screen_err.txt
    (the JSON-RPC error only carries the message) — read it to debug crashes.
  * Self-learning (Sense->Remember->Act), all CPU-only, fail-open, ambient on every call:
      sense.py      per-frame signals (settle/activity, scroll-from-pair, element diff with
                    stable fingerprints, modal detect) off a 1-frame history in SESSION['sense'];
                    surfaced as the `SENSE` hint block appended by _sense_block.
      worldmodel.py write-through element cache keyed by tolerant dHash + window context (sqlite
                    at ~/.local/share/mcp-screen/world/map.db). observe() learns on every
                    annotate; recall() (use_cache=true) returns cached elements to skip OCR;
                    a missed element-click penalize()s and self-heals stale coords.
      autoloop.py   scroll_to_reveal (screen_read_page): one call reads a whole scrollable view,
                    guard re-checked each iteration. Deterministic reflexes live here, NOT an LLM.
"""

import sys
import os
import json
import time

os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")  # hard no-GPU: grounding is CPU-only
import numpy as np

import state
import x11capture
import atspi_tree
import budget
import capture
import input as inp
import grounding
import awareness
import reliability
import recorder
import sense
import worldmodel
import autoloop
from version import __version__

REC = recorder.REC
MAX_WAIT_MS = int(os.environ.get("MCP_SCREEN_MAX_WAIT_MS", "30000"))


def _txt(s):
    return {"type": "text", "text": s}


def _sense_block(raw_img, elements_list, post_action=False):
    """Ambient self-learning: diff this frame against the last one the agent saw and append
    a compact SENSE signal + human hint so it adapts WITHOUT being told (new buttons appeared,
    a modal opened, the click did nothing). Then stash this frame as the new baseline.
    `post_action` gates the no-op/misclick hint (only meaningful right after an action).
    Returns a content text item or None. Fail-open + env kill-switch MCP_SCREEN_AMBIENT=0."""
    if os.environ.get("MCP_SCREEN_AMBIENT") == "0":
        return None
    try:
        view = state.SESSION.get("view")
        sig = sense.compute(raw_img, view, elements_list)
        sense.stash(raw_img, view, elements_list)
        # Publish the normalized cross-layer signal for screen_sense / os_verify.
        state.SESSION["last_pixel"] = sense.to_pixel_signal(sig)
    except Exception:
        return None
    parts = []
    ch = sig.get("change") if sig else None
    if ch and ch.get("new_count"):
        labels = [
            repr(e.get("label") or e.get("role"))
            for e in ch.get("new", [])
            if (e.get("label") or e.get("role"))
        ][:3]
        parts.append(
            f"{ch['new_count']} new element(s)"
            + (": " + ", ".join(labels) if labels else "")
            + (f"; {ch['removed']} removed" if ch.get("removed") else "")
        )
    ov = sig.get("overlay") if sig else None
    if ov and ov.get("present"):
        parts.append(
            f"a {ov['kind']} opened (region {ov.get('region')}) — deal with it first"
        )
    st = sig.get("settle") if sig else None
    if post_action and st and st.get("activity") == "none":
        parts.append("nothing changed — last action may have been a no-op/misclick")
    if not parts:
        return None
    return _txt(
        "SENSE "
        + json.dumps(sig, separators=(",", ":"))
        + "\nhints: "
        + "; ".join(parts)
    )


def _maybe_shot(args, content, _t0):
    """Append a post-action screenshot if shot=true (defaults to re-showing last view area)."""
    if not args.get("shot"):
        return content
    settle = min(MAX_WAIT_MS, float(args.get("settle", 350))) / 1000.0
    if settle > 0:
        # WAIT for the frame to change, don't sleep a flat 350ms. The blind sleep was wrong
        # in both directions — it charged every fast action the full delay and still grabbed
        # a pre-change frame when the UI was slower. `settle` is now the CEILING, not the
        # cost. Same fix already applied to read_selection's clipboard wait. This is also
        # the only place MCP_SCREEN_WAIT_MODE=hybrid can matter for an agent: the
        # change-gate in tool_screenshot needs a screenshot within 1.5s of an action, which
        # separate tool calls never are.
        base = state.SESSION.get("last_input_hash")
        node = state.SESSION.get("last_input_node")
        waited = False
        if base is not None and node is not None:
            try:
                armed = {"ev": capture.arm_damage(node)}

                def _wd(budget, _n=node, _a=armed):
                    ok = capture.wait_damage(_a["ev"], budget)
                    _a["ev"] = capture.arm_damage(_n)
                    return ok

                reliability.wait_for_changed_frame(
                    lambda n: capture.grab(n),
                    node,
                    base,
                    timeout=settle,
                    mode=capture.WAIT_MODE,
                    wait_fn=_wd,
                    note_fn=capture.note_wake,
                )
                waited = True
            except Exception:
                waited = False
        if not waited:
            time.sleep(settle)
    region = args.get("region")
    monitor = args.get("monitor")
    if region is None and monitor is None and state.SESSION.get("view"):
        v = state.SESSION["view"]
        region = [v["ox"], v["oy"], v["dw"], v["dh"]]
    ts = time.time()
    # Default to a plain (cheap, non-disruptive) grab: an action that changed the screen already
    # generated the damage that produces a current frame, so we rarely need to force one — and
    # forcing nudges the pointer (visible flashing). Opt in with fresh=true only when you suspect
    # the result shot is stale on a static monitor.
    fresh = (
        bool(args.get("fresh", False))
        and args.get("settle") != 0
        and os.environ.get("MCP_SCREEN_NO_FRESH") != "1"
    )
    img, ox, oy = capture.capture_desktop(region, monitor, fresh=fresh)
    raw = (
        img  # un-marked frame for ambient SENSE diffing (shows what the action changed)
    )
    try:
        capture.cursor_pos()
        img = capture.draw_cursor(img, ox, oy)
    except Exception:
        pass
    shot = capture.encode_store(img, ox, oy, "after", ts)
    sblock = _sense_block(raw, None, post_action=True)
    if sblock:
        shot = shot + [sblock]
    if REC.active():
        REC.log_frame(img, "after", state.SESSION.get("view"))
    return content + shot


def _verify(args, fn):
    """Optional post-action verify: warn if a click/type produced no on-screen change.

    Handles two shapes: coordinate actions (click/scroll/drag) diff a small region around
    the point; keyboard-only actions (key/type — which never carry x/y) diff the whole
    watched node by frame hash instead of silently skipping verification. Root-caused
    2026-07-24: `screen_key`/`screen_type` never carry x/y, so `resolve_xy(args)` raised
    a KeyError that the old bare `except Exception: return fn(args)` swallowed — verify=true
    was a documented safety check that silently did nothing for either tool."""
    if not args.get("verify"):
        return fn(args)
    has_xy = {"x", "y"} <= set(args)
    node = x = y = None
    if has_xy:
        try:
            x, y = inp.resolve_xy(args)
            node, _, _ = inp.global_to_logical(x, y)
        except Exception:
            has_xy = False
    if node is None:
        try:
            node = _watch_node(args)
        except Exception:
            return fn(args)
    try:
        before = capture.grab(node)[2]
    except Exception:
        return fn(args)
    res = fn(args)
    reliability.wait_for_stable_frame(lambda n: capture.grab(n), node)
    try:
        after = capture.grab(node)[2]
        if has_xy:
            m = next((g for g in state.SESSION["geo"] if g["node"] == node), None)
            changed = True  # can't localize without geo -> don't false-warn
            if m:
                lx, ly = x - m["x"], y - m["y"]
                bb = [max(0, lx - 80), max(0, ly - 80), 160, 160]
                changed, _ = reliability.region_diff(before, after, bb)
        else:
            changed = reliability.frame_hash(before) != reliability.frame_hash(after)
        if not changed:
            near = " near the click" if has_xy else ""
            res["content"].insert(
                0,
                _txt(
                    f"WARN: no screen change{near} — likely a misclick, unchanged "
                    f"content, or focus didn't transfer."
                ),
            )
            if (
                args.get("element") is not None
            ):  # a cached coord missed -> self-heal THAT state's row
                try:
                    worldmodel.MAP.penalize(state.SESSION.get("elements_state_id"))
                except Exception:
                    pass
    except Exception:
        pass
    return res


# ---- tools ----
def tool_screenshot(args):
    t0 = time.time()
    state.stage_reset()
    if args.get("regeo"):
        capture.ensure_geo(force=True)
    region = args.get("region")
    monitor = args.get("monitor")
    # App-agnostic anti-stale: if input was injected very recently, the UI may still be
    # repainting. Settle the watched monitor before grabbing so we never return a pre-change
    # or mid-transition frame (the root cause of misread "nothing happened" loops). Skippable
    # via settle=0 or MCP_SCREEN_NO_AUTOSETTLE=1; bounded by _settle's own timeout.
    li = state.SESSION.get("last_input_t")
    recent_input = li is not None and (time.monotonic() - li) < 1.5
    changed = False  # did the post-action change-gate actually SEE the screen change?
    if (
        recent_input
        and args.get("settle") != 0
        and os.environ.get("MCP_SCREEN_NO_AUTOSETTLE") != "1"
    ):
        try:
            node = _watch_node(args)
            base = state.SESSION.get("last_input_hash")
            base_node = state.SESSION.get("last_input_node")
            # First wait for the frame to actually CHANGE vs the pre-action baseline (defeats
            # stale capture on a static monitor — a successful scroll/click is now SEEN), then
            # settle to a steady end state. If no baseline, fall back to stable-settle alone.
            if base is not None and base_node == node:
                # Probe A/B: arm the damage waiter BEFORE the first grab and re-arm on every
                # wake, so the grab->wait window is always covered and no damage is missed.
                # Inert in the default 'poll' mode.
                armed = {"ev": capture.arm_damage(node)}

                def _wait_damage(budget, _n=node, _a=armed):
                    ok = capture.wait_damage(_a["ev"], budget)
                    _a["ev"] = capture.arm_damage(_n)
                    return ok

                with state.stage("gate"):
                    changed, _ = reliability.wait_for_changed_frame(
                        lambda n: capture.grab(n),
                        node,
                        base,
                        timeout=min(MAX_WAIT_MS / 1000.0, 2.5),
                        mode=capture.WAIT_MODE,
                        wait_fn=_wait_damage,
                        note_fn=capture.note_wake,
                    )
            with state.stage("settle"):
                _settle(node, timeout=min(MAX_WAIT_MS / 1000.0, 2.0))
        except Exception:
            pass
        state.SESSION["last_input_t"] = (
            None  # consume: don't re-settle on the next shot
        )
        state.SESSION["last_input_hash"] = None
    # Anti-stale freshness, used SPARINGLY: forcing a fresh frame nudges the pointer to generate
    # a damage event (visible cursor movement / a recompose), so doing it on every screenshot
    # makes the screen "flash" during active driving. Only force it when it's actually needed —
    # right after an action whose effect the change-gate could NOT confirm (the genuinely-stuck
    # static-monitor case where content changed but no frame was emitted). Pure observation shots
    # (no recent input, or a change already seen) read the cached frame, which on static content
    # is identical to "now" anyway. Explicit fresh=true forces it; settle=0 / MCP_SCREEN_NO_FRESH=1
    # opt out.
    fresh = args.get("fresh", recent_input and not changed)
    fresh = (
        bool(fresh)
        and args.get("settle") != 0
        and os.environ.get("MCP_SCREEN_NO_FRESH") != "1"
    )
    try:
        img, ox, oy = capture.capture_desktop(region, monitor, fresh=fresh)
    except Exception:
        hint = capture.asleep_hint(monitor)
        if hint:
            return {"content": [_txt(hint)], "isError": True}
        raise
    raw = img  # keep the un-marked, cursor-free frame for ambient SENSE diffing + dHash
    sense_elements = None
    aware = "awareness: unavailable"
    try:
        with state.stage("aware"):
            aware = awareness.summary()
    except Exception:
        pass
    view_ctx = [ox, oy, raw.width, raw.height]  # geometry key for the world-model
    label = (
        f"Monitor {monitor}"
        if monitor is not None
        else "Region"
        if region
        else f"Full desktop ({len(capture.ensure_geo())} mon)"
    )
    extra = []
    if args.get("annotate"):
        hit = (
            worldmodel.MAP.recall(raw, aware, view_ctx)
            if args.get("use_cache")
            else None
        )
        if hit:  # known screen — reuse cached elements, skip OCR
            store = hit["elements"]
            state.SESSION["elements"] = store
            state.SESSION["elements_state_id"] = hit.get(
                "state_id"
            )  # so a misclick self-heals THIS row
            for eid in sorted(store):
                e = store[eid]
                extra.append(
                    f"[{eid}] {e.get('role')} {e.get('label')!r} @ desktop({e['x']},{e['y']})"
                )
            extra.append(
                f"(world-model cache hit — skipped OCR, {len(store)} elements)"
            )
            try:
                capture.cursor_pos()
                img = capture.draw_cursor(img, ox, oy)
            except Exception:
                pass
        else:
            try:
                with state.stage("ground"):
                    marked, elements = grounding.annotate(img)
                sense_elements = elements
                img = marked
                store = {}
                for e in elements:
                    x1, y1, x2, y2 = e["bbox"]
                    cx, cy = ox + (x1 + x2) // 2, oy + (y1 + y2) // 2
                    store[e["id"]] = {
                        "x": cx,
                        "y": cy,
                        "label": e["label"],
                        "role": e["role"],
                    }
                    extra.append(
                        f"[{e['id']}] {e['role']} {e['label']!r} @ desktop({cx},{cy})"
                    )
                state.SESSION["elements"] = (
                    store  # enables click-by-element-id (no coordinate guessing)
                )
                state.SESSION["elements_state_id"] = worldmodel.MAP.observe(
                    raw, store, aware, view_ctx
                )  # learn + remember which row
            except Exception as ex:
                extra.append(f"(annotate failed: {ex})")
    else:
        try:  # cursor isn't baked into frames anymore — composite it
            capture.cursor_pos()
            img = capture.draw_cursor(img, ox, oy)
        except Exception:
            pass
    content = capture.encode_store(img, ox, oy, label, t0)
    # This screenshot re-establishes ground truth for whatever window is currently on top —
    # clear the drift flag any pending focus() call set, so freshly-bound view coords are
    # trusted again (see resolve_xy's FocusDriftError).
    state.SESSION["focus_changed_since_view"] = False
    if args.get("annotate"):
        # Tag the elements this call (re)populated with the view id this same call just
        # minted, so a LATER screenshot (annotate or not) — which always mints a new view id
        # — makes _resolve_element's staleness check detect that cached element coords are
        # from an older, possibly-superseded frame.
        state.SESSION["elements_view_id"] = state.SESSION["view"]["id"]
    _sl = state.stage_line(int((time.time() - t0) * 1000))
    if _sl:
        content.insert(0, _txt(_sl))
    content.insert(0, _txt("awareness: " + aware))
    asleep = capture.asleep_hint(
        monitor
    )  # explain any black/sleeping monitor in this frame
    if asleep:
        content.append(_txt(asleep))
    if extra:
        content.append(
            _txt("elements (click the desktop() coords):\n" + "\n".join(extra))
        )
    sblock = _sense_block(raw, sense_elements)
    if sblock:
        content.append(sblock)
    if REC.active():
        REC.log_frame(img, "screenshot", state.SESSION.get("view"))
    return {"content": content}


def _text_match(needle, hay):
    """Substring match that tolerates OCR whitespace. OCR joins and drops spaces
    unpredictably — the same button reads "Launch installer" or "Launchinstaller" run to
    run — so a literal `in` test misses text that is plainly on screen. Compare both raw
    and whitespace-stripped; found live when wait_text timed out on a visible button."""
    h = str(hay or "").lower()
    n = str(needle or "").lower()
    if n in h:
        return True

    def squash(t):
        return "".join(t.split())

    return squash(n) in squash(h)


def _perceive(img, ox, oy, aware):
    """Elements for a frame as [{label, role, abs:(x,y)}], world-model first.

    Shared by screen_wait_text and screen_verify so both get the same recall-then-OCR
    behaviour and both LEARN what they ground — wait_text originally read the cache without
    writing it and could never warm up. Returns (elements, used_ocr)."""
    hit = worldmodel.MAP.recall(img, aware, [ox, oy, img.width, img.height])
    if hit:
        return [
            {"label": v.get("label"), "role": v.get("role"), "abs": (v["x"], v["y"])}
            for v in hit["elements"].values()
        ], False
    # AT-SPI fast path: when the focused app exposes accessibility we get exact roles,
    # labels and DESKTOP-absolute centres for ~nothing, against a multi-second OCR +
    # icon-detection pass. Usually returns nothing (the toggle is off, or the app started
    # before it was on) — an empty list means "no information", so we fall through to OCR
    # rather than reporting an empty screen.
    with state.stage("atspi"):
        acc = [
            {"label": e["text"], "role": e["role"], "abs": (e["x"], e["y"])}
            for e in atspi_tree.elements()
            if ox <= e["x"] < ox + img.width and oy <= e["y"] < oy + img.height
        ]
    if acc:
        return acc, False
    try:
        with state.stage("ground"):
            _m, raw = grounding.annotate(img)
    except Exception:
        return [], True
    mid = lambda b: (ox + (b[0] + b[2]) // 2, oy + (b[1] + b[3]) // 2)  # noqa: E731
    try:
        worldmodel.MAP.observe(
            img,
            {
                e["id"]: {
                    "x": mid(e["bbox"])[0],
                    "y": mid(e["bbox"])[1],
                    "label": e.get("label"),
                    "role": e.get("role"),
                }
                for e in raw
            },
            aware,
            [ox, oy, img.width, img.height],
        )
    except Exception:
        pass
    return [
        {"label": e.get("label"), "role": e.get("role"), "abs": mid(e["bbox"])}
        for e in raw
    ], True


def tool_verify(args):
    """Did the last action actually do what you expected? Returns a VERDICT, not pixels.

    Replaces the screenshot-and-eyeball loop after an action. Verdicts match
    os-control-mcp's os_verify vocabulary (CONFIRMED | PARTIAL | NO_OP | DIVERGED) so a
    GUI verdict and an OS verdict read the same way, and the `pixel` block it returns is
    the same contract os_verify consumes.

    NO_OP is the one worth having: the screen never changed, so the click missed or the
    key went to the wrong window — the failure a screenshot makes you infer by eye."""
    t0 = time.time()
    state.stage_reset()
    want_text = args.get("expect_text")
    want_gone = args.get("expect_gone")
    timeout = min(MAX_WAIT_MS / 1000.0, float(args.get("timeout", 5)))
    interval = max(0.05, float(args.get("interval", 0.25)))
    region, monitor = args.get("region"), args.get("monitor")
    # Baseline: the pre-action frame _action stamped, when it is still relevant. Falling
    # back to "now" would compare the post-action screen against itself and always say
    # NO_OP.
    # The baseline is a hash of the WHOLE stamped node frame. Comparing it against a hash
    # of a REGION crop is comparing different images, so it always differs and every action
    # grades CONFIRMED-changed — including a mouse move, which cannot change the screen at
    # all (the cursor is METADATA, never baked into frames). Caught live. So the change
    # check re-grabs that same node; with no baseline node, `changed` is UNKNOWN (null)
    # and excluded from the verdict rather than invented.
    base = state.SESSION.get("last_input_hash")
    base_node = state.SESSION.get("last_input_node")
    if base_node is None:
        base = None
    try:
        aware = awareness.summary()
    except Exception:
        aware = "unavailable"
    deadline = time.monotonic() + timeout
    last_hash, grabs, ocr = None, 0, 0
    changed, found_text, gone_ok, hit = False, None, None, None
    while True:
        try:
            with state.stage("capture"):
                img, ox, oy = capture.capture_desktop(region, monitor, fresh=False)
            grabs += 1
        except RuntimeError as e:
            return {"content": [_txt(f"verify: {e}")], "isError": True}
        if base is not None and not changed:
            try:  # compare like-for-like: the same node the baseline came from
                if reliability.frame_hash(capture.grab(base_node)[2]) != base:
                    changed = True
            except Exception:
                pass
        h = reliability.frame_hash(np.asarray(img))
        if h != last_hash:
            last_hash = h
            if want_text or want_gone:
                els, used = _perceive(img, ox, oy, aware)
                ocr += 1 if used else 0
                if want_text:
                    hit = next(
                        (e for e in els if _text_match(want_text, e.get("label"))), None
                    )
                    found_text = hit is not None
                if want_gone:
                    gone_ok = not any(
                        _text_match(want_gone, e.get("label")) for e in els
                    )
        checks = {
            "changed": changed if base is not None else None,
            "expect_text": found_text,
            "expect_gone": gone_ok,
        }
        wanted = [v for k, v in checks.items() if v is not None and _wanted(k, args)]
        done = bool(wanted) and all(wanted)
        if done or time.monotonic() >= deadline:
            met = sum(1 for v in wanted if v)
            if wanted and met == len(wanted):
                verdict = "CONFIRMED"
            elif met:
                verdict = "PARTIAL"
            elif base is not None and not changed:
                verdict = "NO_OP"
            else:
                verdict = "DIVERGED"
            ms = int((time.time() - t0) * 1000)
            body = {
                "verdict": verdict,
                "checks": checks,
                "ms": ms,
                "grabs": grabs,
                "ocr_passes": ocr,
                "pixel": {"changed": bool(changed)},
            }
            if hit:
                body["at"] = {
                    "text": hit.get("label"),
                    "x": hit["abs"][0],
                    "y": hit["abs"][1],
                }
            out = [_txt(json.dumps(body, separators=(",", ":")))]
            sl = state.stage_line(ms)
            if sl:
                out.append(_txt(sl))
            return {"content": out}
        time.sleep(interval)


def _wanted(key, args):
    """Was this check actually asked for? An unasked check must not count toward the
    verdict — otherwise a caller who only passed expect_text gets graded on `changed`."""
    if key == "changed":
        return bool(args.get("expect_change", True))
    return args.get(key) is not None


def tool_wait_text(args):
    """Block until `text` appears on screen, or timeout. Returns its click coords.

    Naive polling would be useless here: grounding costs ~7.7s on a cold screen, so an
    OCR-per-iteration loop cannot poll at any useful rate. The measured shape of this
    system makes it cheap instead — a grab is ~35ms while OCR is the expensive part — so
    this polls the frame HASH and only pays for perception when the pixels actually
    changed. On a static screen the loop costs a grab; on a changing one it costs one OCR
    per distinct frame.

    Use instead of screenshotting in a loop to see whether something finished."""
    t0 = time.time()
    state.stage_reset()
    needle = str(args.get("text") or "").strip()
    if not needle:
        return {"content": [_txt("wait_text: `text` is required")], "isError": True}
    timeout = min(MAX_WAIT_MS / 1000.0, float(args.get("timeout", 10)))
    interval = max(0.05, float(args.get("interval", 0.25)))
    region, monitor = args.get("region"), args.get("monitor")
    deadline = time.monotonic() + timeout
    last_hash, ocr_passes, grabs = None, 0, 0
    try:
        aware = awareness.summary()  # cached; part of the world-model recall key
    except Exception:
        aware = "unavailable"
    while True:
        try:
            with state.stage("capture"):
                img, ox, oy = capture.capture_desktop(region, monitor, fresh=False)
            grabs += 1
        except RuntimeError as e:
            return {"content": [_txt(f"wait_text: {e}")], "isError": True}
        h = reliability.frame_hash(np.asarray(img))
        if h != last_hash:  # pixels moved — only now is perception worth paying for
            last_hash = h
            # World-model recall before OCR. It is dHash-keyed, so it can only hit on a
            # screen we have already learned — a screen we are still WAITING to change
            # cannot match, which is what makes this safe here. Turns "the text is already
            # there" from a ~7.2s OCR into ~50ms.
            els, used = _perceive(img, ox, oy, aware)
            ocr_passes += 1 if used else 0
            found = els
            for e in found:
                if _text_match(needle, e.get("label")):
                    cx, cy = e["abs"]
                    ms = int((time.time() - t0) * 1000)
                    body = json.dumps(
                        {
                            "found": True,
                            "text": e.get("label"),
                            "role": e.get("role"),
                            "x": cx,
                            "y": cy,
                            "ms": ms,
                            "grabs": grabs,
                            "ocr_passes": ocr_passes,
                        },
                        separators=(",", ":"),
                    )
                    out = [_txt(body)]
                    sl = state.stage_line(ms)
                    if sl:
                        out.append(_txt(sl))
                    return {"content": out}
        if time.monotonic() >= deadline:
            ms = int((time.time() - t0) * 1000)
            body = json.dumps(
                {
                    "found": False,
                    "waited_ms": ms,
                    "grabs": grabs,
                    "ocr_passes": ocr_passes,
                },
                separators=(",", ":"),
            )
            out = [_txt(f"{body}\ntimed out — {needle!r} never appeared")]
            sl = state.stage_line(ms)
            if sl:
                out.append(_txt(sl))
            return {"content": out}
        time.sleep(interval)


def tool_read_text(args):
    """Return what is ON the screen as TEXT — no image block.

    A screenshot costs a FIXED ceil(w/28)*ceil(h/28) visual tokens (4784 for a 4K monitor)
    no matter how fast the encode gets. Every latency win this session left that number
    untouched. For navigate-by-text work — find a label, read a value, confirm a string
    appeared — the pixels are not what the caller needs; the text is, and it is ~10x cheaper.

    Same perception path as screenshot(annotate=true), minus the encode and the image:
    world-model recall first (skips OCR entirely on a screen we have seen), else grounding.
    Coordinates come back in DESKTOP space, so they can be clicked directly."""
    t0 = time.time()
    state.stage_reset()
    region = args.get("region")
    monitor = args.get("monitor")
    try:
        with state.stage("capture"):
            img, ox, oy = capture.capture_desktop(region, monitor, fresh=False)
    except RuntimeError as e:
        hint = capture.asleep_hint(monitor)
        return {"content": [_txt(hint or str(e))], "isError": True}
    aware = "unavailable"
    try:
        with state.stage("aware"):
            aware = awareness.summary()
    except Exception:
        pass
    view_ctx = [ox, oy, img.width, img.height]
    elements, cached = [], False
    hit = (
        worldmodel.MAP.recall(img, aware, view_ctx)
        if args.get("use_cache", True)
        else None
    )
    if hit:
        cached = True
        for eid in sorted(hit["elements"]):
            e = hit["elements"][eid]
            elements.append(
                {
                    "id": eid,
                    "role": e.get("role"),
                    "text": e.get("label"),
                    "x": e["x"],
                    "y": e["y"],
                }
            )
    else:
        try:
            with state.stage("ground"):
                _marked, found = grounding.annotate(img)
            store = {}
            for e in found:
                x1, y1, x2, y2 = e["bbox"]
                cx, cy = ox + (x1 + x2) // 2, oy + (y1 + y2) // 2
                store[e["id"]] = {
                    "x": cx,
                    "y": cy,
                    "label": e["label"],
                    "role": e["role"],
                }
                elements.append(
                    {
                        "id": e["id"],
                        "role": e["role"],
                        "text": e["label"],
                        "x": cx,
                        "y": cy,
                    }
                )
            state.SESSION["elements"] = store
            state.SESSION["elements_state_id"] = worldmodel.MAP.observe(
                img, store, aware, view_ctx
            )
        except Exception as ex:  # noqa: BLE001 — perception is fail-open everywhere else
            return {"content": [_txt(f"read_text failed: {ex}")], "isError": True}
    if args.get("contains"):
        want = str(args["contains"])
        elements = [e for e in elements if _text_match(want, e.get("text"))]
    out = {
        "origin": [ox, oy],
        "size": [img.width, img.height],
        "focused": aware,
        "cached": cached,
        "count": len(elements),
        "elements": elements,
    }
    body = json.dumps(out, separators=(",", ":"))
    content = [_txt(body)]
    sl = state.stage_line(int((time.time() - t0) * 1000))
    if sl:
        content.append(_txt(sl))
    return {"content": content}


def tool_diag(args):
    """Live health dump: session/geo, the cursor probe cache + guard state, grounding
    backends, and prereqs matrix. Permanent ops tool — first thing to check when
    capture/clicks/cursor act up."""
    import prereqs

    d = {
        "version": __version__,
        "prereqs": prereqs.check_all(),
        "session": {
            "started": bool(state.SESSION.get("handle")),
            "streams": len(state.SESSION.get("streams") or []),
            "geo": state.SESSION.get("geo"),
            "bounds": [state.SESSION.get("W"), state.SESSION.get("H")],
            "view": state.SESSION.get("view"),
            "elements_cached": len(state.SESSION.get("elements") or {}),
        },
        "cursor": capture.diag(),
        "atspi": atspi_tree.diag(),
        "x11": x11capture.diag(),
        "guard": {
            "cmd_cursor": state.SESSION.get("cmd_cursor"),
            "threshold_px": inp.GUARD_THRESH,
        },
        "uinput": inp.ui.diag(),
        "grounding": grounding.diag(),
        "world_model": worldmodel.MAP.stats(),
    }
    return {"content": [_txt(json.dumps(d, default=str, indent=2))]}


def tool_list_monitors(args):
    geo = capture.ensure_geo(force=bool(args.get("regeo")))
    lines = [
        f"{i}: origin=({m['x']},{m['y']}) size={m['w']}x{m['h']} scale={m['sx']:g}"
        for i, m in enumerate(geo)
    ]
    lines.append(f"desktop bounds: {state.SESSION['W']}x{state.SESSION['H']}")
    try:
        wins = awareness.list_windows()
        if wins:
            lines.append(
                "windows: "
                + ", ".join(
                    f"{w.get('app') or w.get('wm_class')}:{w.get('title', '')[:30]}"
                    for w in wins[:12]
                )
            )
    except Exception:
        pass
    return {"content": [_txt("\n".join(lines))]}


_ACTIONS = {
    "move": inp.move,
    "click": inp.click,
    "scroll": inp.scroll,
    "drag": inp.drag,
    "key": inp.key,
    "type": inp.type_text,
}


def _resolve_element(args):
    """If args has `element` (id from the last annotate=true shot), resolve it to exact
    desktop coords — the agent clicks what the eyes detected, never a guessed pixel."""
    eid = args.get("element")
    if eid is None:
        return args
    # Staleness guard, same idea as resolve_xy's StaleViewError for view_id: elements are
    # tagged with the view id the annotate=true call that populated them minted. Any LATER
    # screenshot (annotate=true or not) mints a new view id without touching elements_view_id,
    # so a mismatch here means the UI may have changed since these coords were captured —
    # exactly the "clicked element 3, but the layout shifted and element 3 is now something
    # else" failure mode that had no guard before.
    view = state.SESSION.get("view") or {}
    tagged = state.SESSION.get("elements_view_id")
    if tagged is not None and view.get("id") is not None and tagged != view["id"]:
        raise inp.StaleViewError(
            f"element {eid} was captured under an earlier screenshot (view#{tagged}); the "
            f"current view is view#{view['id']}. Re-screenshot(annotate=true) and use the "
            f"fresh element ids."
        )
    el = (state.SESSION.get("elements") or {}).get(int(eid))
    if not el:
        raise RuntimeError(
            f"element {eid} not found; take a screenshot(annotate=true) first"
        )
    return {**args, "x": el["x"], "y": el["y"], "space": "desktop"}


def _redact_args(name, args):
    """Strip sensitive fields before audit-logging. The actions.jsonl lands on disk at
    ~/.local/state/mcp-screen/ and `screen_type` text is frequently a password or token
    — log a length placeholder instead of the literal characters."""
    if name == "screen_type" and isinstance(args.get("text"), str):
        return {**args, "text": f"<{len(args['text'])} chars redacted>"}
    return args


def _audit_node(args):
    """Pick which monitor's frame to hash for the pre/post audit. Returns the node id
    or None on failure. Uses the click target's monitor if coords are present, else the
    same watch-node logic screen_wait uses (region/view center)."""
    try:
        if {"x", "y"} <= set(args):
            x, y = inp.resolve_xy(args)
            node, _, _ = inp.global_to_logical(x, y)
            return node
        return _watch_node(args)
    except Exception:
        return None


def _click_bbox(node, args):
    """Local bbox in node-frame px around the click point, for region_diff. None if no
    coords (keyboard tools) or the monitor can't be found."""
    if not ({"x", "y"} <= set(args)):
        return None
    try:
        x, y = inp.resolve_xy(args)
        m = next(
            (g for g in (state.SESSION.get("geo") or []) if g["node"] == node), None
        )
        if not m:
            return None
        lx, ly = x - m["x"], y - m["y"]
        return [max(0, lx - 80), max(0, ly - 80), 160, 160]
    except Exception:
        return None


def _do_focus(spec):
    """Raise + keyboard-focus a window so injected keys/clicks land in it. `spec` is a window id
    (int/str), an app name (str), or a dict {app?, title?, id?}. Tries the window-info extension's
    ActivateWindow first (exact, fast); falls back to the GNOME overview (type the name) when the
    extension isn't installed yet. Returns (ok: bool, detail: str). Never raises.

    Root-caused 2026-07-24: this used to report success as soon as ActivateWindow's D-Bus call
    (or the overview keystroke sequence) merely completed, with no check that the window it
    ACTUALLY raised matched the request — with multiple windows of the same app open, that
    let a wrong-window raise report clean success, and every following click landed on the
    wrong window/tab. Both paths now verify against awareness.focused_window() before
    claiming success, and any real raise attempt (verified or not) marks
    state.SESSION['focus_changed_since_view'] so resolve_xy refuses to click stale
    screenshot coordinates until a fresh screenshot is taken post-focus (see FocusDriftError)."""
    if isinstance(spec, dict):
        wid, app, title = spec.get("id"), spec.get("app"), spec.get("title")
    elif isinstance(spec, (int, float)) or (
        isinstance(spec, str) and str(spec).isdigit()
    ):
        wid, app, title = spec, None, None
    else:
        wid, app, title = None, (spec or None), None
    # Establish the portal session + desktop bounds first: focus may be the FIRST call after a
    # reload/reconnect (before any screenshot), and input injection needs a live session handle
    # (portal path) or known W/H (uinput path) — without it both backends fail.
    try:
        capture.ensure_geo()
    except Exception:
        pass

    def _matches_request(fw, want_id, want_app, want_title):
        if not fw:
            return False
        if want_id is not None and fw.get("id") is not None:
            try:
                return int(fw["id"]) == int(want_id)
            except (TypeError, ValueError):
                pass
        hay = f"{fw.get('app') or ''} {fw.get('wm_class') or ''} {fw.get('title') or ''}".lower()
        if want_app and want_app.lower() in hay:
            return True
        if want_title and want_title.lower() in hay:
            return True
        return False

    # Extension path (needs the user to have logged out/in once after install).
    try:
        if wid is None and (app or title):
            w = awareness.find_window(app=app, title=title)
            if w:
                wid = w.get("id")
        if wid is not None and awareness.activate_window(wid):
            time.sleep(
                float(os.environ.get("MCP_SCREEN_FOCUS_SETTLE_MS", "150")) / 1000.0
            )
            state.SESSION["focus_changed_since_view"] = True
            fw = awareness.focused_window()
            if fw is None:
                # Extension can raise but its GetFocusedWindow didn't answer — activate_window's
                # own boolean is the only confirmation we have; report success but flag it.
                return True, f"focused window id={wid} via extension (unverified)"
            if _matches_request(fw, wid, app, title):
                return True, f"focused window id={wid} via extension (confirmed)"
            return False, (
                f"focus MISMATCH: activated window id={wid} but the compositor now reports "
                f"{fw.get('app') or fw.get('wm_class')!r} / {fw.get('title')!r} focused — "
                f"re-screenshot to see what's actually on top before clicking"
            )
    except Exception:
        pass
    # Fallback: overview search by name (no extension required; works today).
    name = app or title or (str(wid) if wid is not None else None)
    if name:
        issued, verified = inp.activate_via_overview(name)
        if issued:
            state.SESSION["focus_changed_since_view"] = True
            if verified:
                return True, f"activated '{name}' via overview (confirmed)"
            return True, (
                f"activated '{name}' via overview (UNVERIFIED — window-info extension "
                f"unavailable, and/or multiple windows match '{name}'; re-screenshot before "
                f"clicking to confirm the right window came forward)"
            )
    return False, "focus failed: window-info extension not loaded and no name to search"


def tool_focus(args):
    """screen_focus handler: focus a window before typing/clicking into it."""
    spec = {"id": args.get("id"), "app": args.get("app"), "title": args.get("title")}
    has_target = any(v is not None for v in spec.values())
    ok, detail = _do_focus(spec if has_target else "")
    return {"content": [_txt(detail)], "isError": not ok}


def _action(name, fn, args):
    """Reliability-wrapped action dispatch:
    1. Resolve element-id -> coords.
    2. User-takeover guard.
    3. Populate _focused_app from awareness so the MCP_SCREEN_APPS allowlist works.
    4. Ack gate (opt-in via MCP_SCREEN_GUARD=1) — blocks close-combos / destructive
       keyword matches / out-of-allowlist actions unless `ack=<reason>` is passed.
    5. Run the handler (with optional verify post-check).
    6. Append a redacted record to the actions.jsonl audit log.
    7. Optional auto-screenshot."""
    t0 = time.time()
    state.stage_reset()
    args = _resolve_element(args)
    # Stale-view pre-check: if the caller bound coords to a superseded screenshot, reject up front
    # (before any pointer motion / focus change) so a misbound click never lands on the wrong spot.
    _pre = None
    if {"x", "y"} <= set(args):
        _pre = args
    elif {"x1", "y1"} <= set(args):
        _pre = {
            "x": args["x1"],
            "y": args["y1"],
            "space": args.get("space", "view"),
            "view_id": args.get("view_id"),
        }
    if _pre is not None:
        try:
            inp.resolve_xy(_pre)
        except inp.StaleViewError as e:
            return {"content": [_txt(f"STALE VIEW: {e}")], "isError": True}
        except Exception:
            pass
    try:
        inp.guard_user(bool(args.get("force")))
    except inp.UserControlError as e:
        return {"content": [_txt(f"STOPPED: {e}")], "isError": True}
    # Optional pre-action focus: keyboard events go to the COMPOSITOR-focused window, which a
    # background / static-monitor app doesn't have — so `screen_type`/`screen_key` silently land
    # in the wrong window. Pass focus={app|title|id} (or focus="slack") on any action to raise +
    # keyboard-focus the target first. Opt-in; never steals focus unless asked.
    # A focus failure/mismatch must BLOCK the action rather than be silently discarded — the
    # old bare `except Exception: pass` here swallowed _do_focus's (ok, detail) return, so a
    # reported focus failure never stopped the click/type that followed (root cause of several
    # wrong-window clicks tonight). Any successful raise attempt also marks
    # focus_changed_since_view, so resolve_xy below will refuse this same call's own stale
    # (x,y) if the caller aimed at a screenshot taken before this focus.
    if args.get("focus") is not None:
        fok, fdetail = _do_focus(args["focus"])
        if not fok:
            return {"content": [_txt(f"FOCUS FAILED: {fdetail}")], "isError": True}
    # Populate focused-app context (read-only; degrades silently when awareness is down).
    if "_focused_app" not in args:
        try:
            fw = awareness.focused_window()
            if fw:
                args = {**args, "_focused_app": fw.get("app") or fw.get("wm_class")}
        except Exception:
            pass
    reason = reliability.needs_ack(name, args, args.get("_ocr_near_target"))
    if reason and args.get("ack") != reason:
        res = {
            "content": [
                _txt(
                    f"BLOCKED: this action needs confirmation ({reason}). "
                    f"Re-issue with ack='{reason}' to proceed."
                )
            ],
            "isError": True,
            "ack_reason": reason,
        }
        try:
            reliability.log_action(
                {
                    "tool": name,
                    "args": _redact_args(name, args),
                    "warn": f"blocked:{reason}",
                    "ms": int((time.time() - t0) * 1000),
                }
            )
        except Exception:
            pass
        return res
    # Opt-in pre/post frame capture for the audit log — gives forensic hashes +
    # changed_bbox per action. Default OFF: two extra grab() calls per action add
    # ~100-500ms of portal latency, which the lightweight wiring path doesn't pay.
    audit_frames = os.environ.get("MCP_SCREEN_AUDIT_FRAMES") == "1"
    pre_hash = post_hash = changed = changed_bbox = None
    pre_frame = pre_node = None
    if audit_frames:
        pre_node = _audit_node(args)
        if pre_node is not None:
            try:
                pre_frame = capture.grab(pre_node)[2]
                pre_hash = reliability.frame_hash(pre_frame)
            except Exception:
                pre_frame = pre_hash = None
    # Anti-stale baseline: hash the watched node BEFORE the action so a follow-up screenshot can
    # wait for the frame to actually CHANGE (not merely be "stable", which a repeated stale frame
    # on a static monitor satisfies instantly). Best-effort; never blocks the action.
    try:
        bn = _watch_node(args)
        state.SESSION["last_input_node"] = bn
        state.SESSION["last_input_hash"] = reliability.frame_hash(capture.grab(bn)[2])
    except Exception:
        state.SESSION["last_input_node"] = state.SESSION["last_input_hash"] = None
    res = _verify(args, fn)
    if audit_frames and pre_frame is not None:
        try:
            after = capture.grab(pre_node)[2]
            post_hash = reliability.frame_hash(after)
            bbox = _click_bbox(pre_node, args)
            if bbox is not None:
                changed, changed_bbox = reliability.region_diff(pre_frame, after, bbox)
            else:
                # Keyboard tool / no coords: whole-frame hash equality is the signal.
                changed = pre_hash != post_hash
        except Exception:
            pass
    # Audit log: best-effort, never breaks the action path.
    try:
        coords = None
        if {"x", "y"} <= set(args):
            try:
                coords = list(inp.resolve_xy(args))
            except Exception:
                coords = None
        reliability.log_action(
            {
                "tool": name,
                "args": _redact_args(name, args),
                "resolved_coords": coords,
                "pre_hash": pre_hash,
                "post_hash": post_hash,
                "changed": changed,
                "changed_bbox": changed_bbox,
                "ms": int((time.time() - t0) * 1000),
                "warn": "error"
                if (isinstance(res, dict) and res.get("isError"))
                else None,
            }
        )
    except Exception:
        pass
    out = _maybe_shot(args, res["content"], t0)
    _sl = state.stage_line(int((time.time() - t0) * 1000))
    if _sl:
        out = list(out) + [_txt(_sl)]
    return {"content": out}


def _watch_node(args):
    """Pick the monitor node to watch for change: the region/view center's monitor, else
    the first. Used by screen_wait + the wait_stable batch action."""
    geo = capture.ensure_geo()
    region = args.get("region")
    if region:
        cx, cy = region[0] + region[2] / 2.0, region[1] + region[3] / 2.0
    elif state.SESSION.get("view"):
        v = state.SESSION["view"]
        cx, cy = v["ox"] + v["dw"] / 2.0, v["oy"] + v["dh"] / 2.0
    else:
        return geo[0]["node"]
    for m in geo:
        if m["x"] <= cx < m["x"] + m["w"] and m["y"] <= cy < m["y"] + m["h"]:
            return m["node"]
    return geo[0]["node"]


def _settle(node, timeout=5.0, window=2, thresh=0.5):
    """Block until `node` stops changing (window consecutive sub-thresh diffs) or timeout.
    Returns (stable, last_diff, ms)."""
    t0 = time.time()
    stable, last = reliability.wait_for_stable_frame(
        lambda n: capture.grab(n),
        node,
        timeout=timeout,
        window=int(window),
        thresh=float(thresh),
    )
    return stable, last, int((time.time() - t0) * 1000)


def tool_wait(args):
    """Wait until the watched area stops changing (settles) or `timeout`s elapse, then
    optionally screenshot. Use this after an action that kicks off an async / htmx update
    instead of guessing a fixed delay — it returns as soon as the UI is stable."""
    try:
        node = _watch_node(args)
    except Exception:
        return {
            "content": [_txt("wait: no session/geo yet — take a screenshot first")],
            "isError": True,
        }
    stable, last, ms = _settle(
        node,
        timeout=min(MAX_WAIT_MS / 1000.0, float(args.get("timeout", 5.0))),
        window=args.get("window", 2),
        thresh=args.get("thresh", 0.5),
    )
    msg = (
        f"settled in {ms}ms"
        if stable
        else f"still changing after {ms}ms (timeout; last_diff {last:.2f})"
    )
    return {"content": _maybe_shot(args, [_txt("wait: " + msg)], time.time())}


def tool_tour(args):
    """Visit several UI states in ONE call, returning a labeled thumbnail after each — the
    fix for the round-trip bottleneck (collapses N navigate->screenshot turns into 1).

    stops=[{label, steps:[{action,...}], region?, monitor?, settle?}]. Each stop runs its
    steps (same actions as screen_do: click/scroll/key/type/move/wait, element ids ok),
    settles, then captures a thumbnail (downscaled to shot_max_edge, default 1280). The
    user-takeover guard applies per step; a takeover stops the whole tour (force to bypass)."""
    stops = args.get("steps") or args.get("stops") or []
    default_settle = float(args.get("settle", 400))
    force = args.get("force")
    max_edge = int(args.get("shot_max_edge", 1280))
    # The client cap applies to the WHOLE tool result, but this handler emits one image per
    # stop. Fitting each to the full cap ships N x cap and the client truncates everything.
    # Split it evenly, and once the budget is spent keep returning each stop's TEXT with an
    # explicit note instead of silently emitting images that will be truncated away.
    _per_image_cap = (
        max(4, budget.MAX_OUT_KB // max(1, len(stops))) if budget.MAX_OUT_KB else None
    )
    _img_budget_left = budget.MAX_OUT_KB if budget.MAX_OUT_KB else None
    capture.ensure_geo()  # self-initialize so the first step's click has geo (no warm-up shot needed)
    content, errs, t_all = [], [], time.time()
    _shots_emitted = 0
    for si, stop in enumerate(stops):
        label = stop.get("label", f"stop{si}")
        for step in (dict(s) for s in stop.get("steps", [])):
            action = step.pop("action", None)
            if action == "wait":
                time.sleep(min(MAX_WAIT_MS, float(step.get("ms", 300))) / 1000.0)
                continue
            if action == "wait_stable":
                try:
                    _settle(
                        _watch_node(step),
                        timeout=min(
                            MAX_WAIT_MS / 1000.0, float(step.get("timeout", 5.0))
                        ),
                    )
                except Exception:
                    pass
                continue
            fn = _ACTIONS.get(action)
            if not fn:
                errs.append(f"{label}: unknown action {action!r}")
                continue
            try:
                step = _resolve_element(step)
                focus_spec = step.pop("focus", None)
                if focus_spec is not None:
                    # screen_tour never actually applied per-step focus before — it was
                    # documented (see the `focus` field on the batched action tools) but the
                    # loop here never read it, so a tour step's click fired against whatever
                    # window the compositor happened to have focused.
                    fok, fdetail = _do_focus(focus_spec)
                    if not fok:
                        errs.append(f"{label}: FOCUS FAILED: {fdetail}")
                        continue
                inp.guard_user(step.get("force", force))
                fn(step)
            except inp.UserControlError as e:
                content.insert(0, _txt(f"TOUR STOPPED at '{label}': {e}"))
                return {"content": content, "isError": True}
            except Exception as e:  # noqa: BLE001 — record + keep touring
                errs.append(f"{label}: {e}")
        settle = min(MAX_WAIT_MS, float(stop.get("settle", default_settle))) / 1000.0
        if settle > 0:
            time.sleep(settle)
        region, monitor = stop.get("region"), stop.get("monitor")
        if region is None and monitor is None and state.SESSION.get("view"):
            v = state.SESSION["view"]
            region = [v["ox"], v["oy"], v["dw"], v["dh"]]
        t0 = time.time()
        img, ox, oy = capture.capture_desktop(region, monitor)
        try:
            capture.cursor_pos()
            img = capture.draw_cursor(img, ox, oy)
        except Exception:
            pass
        # The client cap applies to the WHOLE tool result, but this handler emits one
        # image per stop. Fitting each to the full cap ships N x cap and the client
        # truncates the lot. Divide it, with a floor so a long tour still returns
        # something legible rather than N unreadable specks.
        if _img_budget_left is not None and _img_budget_left < 4:
            content.append(
                {
                    "type": "text",
                    "text": (
                        f"{label}: image omitted — this client's "
                        f"{budget.MAX_OUT_KB}KB result cap is spent after "
                        f"{_shots_emitted} thumbnails. Re-run screen_tour with fewer "
                        f"stops, or screen_screenshot that stop alone, for pixels."
                    ),
                }
            )
        else:
            _blocks = capture.encode_store(
                img, ox, oy, label, t0, max_edge=max_edge, max_out_kb=_per_image_cap
            )
            content += _blocks
            _shots_emitted += 1
            if _img_budget_left is not None:
                _spent = sum(len(b.get("data", "")) for b in _blocks) // 1024
                _img_budget_left -= max(1, _spent)
        if REC.active():
            REC.log_frame(img, f"tour:{label}", state.SESSION.get("view"))
    head = (
        f"TOUR ({len(stops)} stops, {int((time.time() - t_all) * 1000)}ms total): "
        + " -> ".join(s.get("label", f"stop{i}") for i, s in enumerate(stops))
    )
    if errs:
        head += "  | errors: " + "; ".join(errs)
    content.insert(0, _txt(head))
    return {"content": content}


def tool_do(args):
    """Batched ordered actions: steps=[{action, ...args}]. One optional final screenshot."""
    # screen_do deliberately bypasses _action, which is what normally primes geometry —
    # so on the FIRST call after a reload SESSION["geo"] was still None and the first
    # pointer step died with a bare TypeError from global_to_logical. Same shape as the
    # documented focus-after-reload bug. Prime once, here.
    try:
        capture.ensure_geo()
    except Exception:
        pass
    steps = args.get("steps", [])
    stop_on_error = args.get("stop_on_error", True)
    force = args.get("force")
    out = []
    for i, step in enumerate(dict(s) for s in steps):
        action = step.pop("action", None)
        fn = _ACTIONS.get(action)
        if action == "wait":
            time.sleep(min(MAX_WAIT_MS, float(step.get("ms", 300))) / 1000.0)
            out.append(f"[{i}] wait")
            continue
        if action == "wait_stable":
            try:
                _stable, _d, _ms = _settle(
                    _watch_node(step),
                    timeout=min(MAX_WAIT_MS / 1000.0, float(step.get("timeout", 5.0))),
                )
                out.append(
                    f"[{i}] wait_stable ({'settled' if _stable else 'timeout'} {_ms}ms)"
                )
            except Exception as _e:
                out.append(f"[{i}] wait_stable skipped ({_e})")
            continue
        if not fn:
            out.append(f"[{i}] ERROR unknown action {action!r}")
            if stop_on_error:
                return {"content": [_txt("\n".join(out))], "isError": True}
            continue
        try:
            step = _resolve_element(step)
            inp.guard_user(
                step.get("force", force)
            )  # stop the batch if the user took the mouse
            if (
                step.get("focus") is not None
            ):  # per-step pre-focus (batch bypasses _action)
                # Must actually check the result — the old bare except-pass here let a
                # failed/mismatched focus silently fall through to the click anyway,
                # letting a multi-step batch click through several wrong windows with
                # zero error surfaced.
                fok, fdetail = _do_focus(step["focus"])
                if not fok:
                    out.append(f"[{i}] FOCUS FAILED: {fdetail}")
                    if stop_on_error:
                        return {"content": [_txt("\n".join(out))], "isError": True}
                    continue
            step.pop("shot", None)
            r = _verify(step, fn)
            out.append(f"[{i}] {r['content'][0]['text']}")
        except inp.UserControlError as e:
            out.append(f"[{i}] STOPPED: {e}")
            return {"content": [_txt("\n".join(out))], "isError": True}
        except Exception as ex:
            out.append(f"[{i}] ERROR {ex}")
            if stop_on_error:
                return {"content": [_txt("\n".join(out))], "isError": True}
    content = [_txt("\n".join(out))]
    return {"content": _maybe_shot(args, content, time.time())}


_REGION = {
    "type": "array",
    "items": {"type": "number"},
    "description": (
        "[x,y,w,h] to crop/zoom. Desktop-absolute px on its own; when `monitor` is also "
        "given the box is RELATIVE to that monitor's origin and is clipped to it."
    ),
}
_SHOT = {"type": "boolean", "description": "return a screenshot after the action"}
_SPACE = {
    "type": "string",
    "description": "'view' (default): coords are pixels in the last screenshot; 'desktop': raw px; 'norm': 0-1000",
}
_VERIFY = {
    "type": "boolean",
    "description": "after the action, warn if the screen didn't change (catches misclicks)",
}
_ELEM = {
    "type": "number",
    "description": "click the element id from the last screen_screenshot(annotate=true) — server resolves exact coords (no guessing)",
}
_FORCE = {
    "type": "boolean",
    "description": "bypass the user-takeover guard; also use to take control back after a STOPPED result (the user moved the mouse)",
}
_VIEWID = {
    "type": "number",
    "description": "bind these view-space coords to the screenshot they were read from (the view#N in that shot's text). If a later screenshot has since rebound the transform, the action is rejected instead of landing on the wrong spot. Strongly recommended whenever you take more than one screenshot before clicking.",
}
_FOCUS = {
    "type": "string",
    "description": "raise + keyboard-focus this app/window BEFORE the action (e.g. 'slack', 'firefox') so injected keys/clicks land in it, not whatever's focused. Keyboard events go to the focused window — a background or static-monitor app won't get them otherwise. Uses the window-info extension if loaded, else the GNOME overview.",
}
_POS = {
    "x": {"type": "number"},
    "y": {"type": "number"},
    "element": _ELEM,
    "space": _SPACE,
    "view_id": _VIEWID,
    "focus": _FOCUS,
    "shot": _SHOT,
    "verify": _VERIFY,
    "force": _FORCE,
    "region": _REGION,
    "monitor": {"type": "number"},
    "settle": {"type": "number"},
}

_RO = {"readOnlyHint": True, "destructiveHint": False}
_ACT = {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False}
_DEST = {"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False}


def tool_sense(a):
    """Return the normalized cross-layer pixel signal from the most recent frame diff —
    {changed, opened, modal, no_op, activity} — for feeding a verifier's `pixel` arg
    (e.g. os-control-mcp's os_verify). Read-only; reflects the last action's SENSE."""
    px = state.SESSION.get("last_pixel") or {
        "changed": False,
        "opened": False,
        "modal": False,
        "no_op": True,
        "activity": "none",
    }
    return [_txt(json.dumps({"pixel": px}))]


TOOLS = [
    {
        "name": "screen_screenshot",
        "title": "Capture Screen",
        "annotations": _RO,
        "description": "Capture the desktop, lossless, auto-sized to the model's native resolution. Use to LOCATE targets (never assume which monitor) or to re-read after an action. No args = full multi-monitor overview; region=[x,y,w,h] or monitor=<i> zooms in crisp. annotate=true overlays numbered Set-of-Marks + click coords. use_cache=true (with annotate) reuses learned elements for a known screen, skipping OCR. Returns image + text (focused window, SENSE line: new elements / modal / no-op).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "region": _REGION,
                "monitor": {"type": "number"},
                "annotate": {"type": "boolean"},
                "use_cache": {
                    "type": "boolean",
                    "description": "with annotate: reuse learned elements for a known screen (skips OCR)",
                },
                "regeo": {"type": "boolean"},
                "fresh": {
                    "type": "boolean",
                    "description": "force a CURRENT frame on a static monitor (default true; defeats stale keepalive-resent captures). Set false (or settle=0) for the instantaneous cached frame.",
                },
            },
        },
    },
    {
        "name": "screen_list_monitors",
        "title": "List Monitors",
        "annotations": _RO,
        "description": "List monitors (origin, size, scale), desktop bounds, and open windows. Use first when choosing where to screenshot or click. Returns monitor geometry plus window list.",
        "inputSchema": {"type": "object", "properties": {"regeo": {"type": "boolean"}}},
    },
    {
        "name": "screen_move_mouse",
        "title": "Move Mouse",
        "annotations": _ACT,
        "description": "Move mouse to x,y (view-space default) or dx,dy relative. Use before click when you need an explicit hover position. Returns after the pointer settles.",
        "inputSchema": {
            "type": "object",
            "properties": {**_POS, "dx": {"type": "number"}, "dy": {"type": "number"}},
        },
    },
    {
        "name": "screen_click",
        "title": "Click",
        "annotations": _ACT,
        "description": "Click at x,y (view-space; mapped to the real screen). Omit x,y to click in place. Use for single UI activations. button: left|right|middle; double:bool. Returns action result (and optional post-click shot).",
        "inputSchema": {
            "type": "object",
            "properties": {
                **_POS,
                "button": {"type": "string"},
                "double": {"type": "boolean"},
            },
        },
    },
    {
        "name": "screen_scroll",
        "title": "Scroll",
        "annotations": _ACT,
        "description": "Scroll the wheel (direction up|down|left|right, amount notches). Use to reveal off-screen content before screenshot. Optional x,y to position first. Returns after scroll settles.",
        "inputSchema": {
            "type": "object",
            "properties": {
                **_POS,
                "direction": {"type": "string"},
                "amount": {"type": "number"},
            },
        },
    },
    {
        "name": "screen_drag",
        "title": "Drag",
        "annotations": _ACT,
        "description": "Press-drag from (x1,y1) to (x2,y2) in view-space. Use for sliders, reorder, selection. button: left|middle|right. modifiers=['shift'] holds keys for the whole gesture — REQUIRED to select text in a terminal running a TUI (Claude Code, vim, htop), which otherwise eats the drag itself and leaves nothing to copy. Returns after drag completes.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "x1": {"type": "number"},
                "y1": {"type": "number"},
                "x2": {"type": "number"},
                "y2": {"type": "number"},
                "space": _SPACE,
                "view_id": _VIEWID,
                "button": {"type": "string"},
                "modifiers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "keys held for the whole drag, e.g. ['shift'] to force a terminal selection past a TUI's mouse grab",
                },
                "shot": _SHOT,
                "force": _FORCE,
                "region": _REGION,
                "settle": {"type": "number"},
            },
            "required": ["x1", "y1", "x2", "y2"],
        },
    },
    {
        "name": "screen_key",
        "title": "Press Key",
        "annotations": _ACT,
        "description": "Press a key/combo: 'Ctrl+L', 'Enter', 'Alt+Tab', 'F5'. Use for shortcuts and confirmations. Keys go to the FOCUSED window — pass focus='appname' first (a background/static-monitor app won't receive keys otherwise). Returns action result (optional post-shot).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "keys": {"type": "string"},
                "focus": _FOCUS,
                "shot": _SHOT,
                "verify": _VERIFY,
                "force": _FORCE,
                "region": _REGION,
                "settle": {"type": "number"},
            },
            "required": ["keys"],
        },
    },
    {
        "name": "screen_type",
        "title": "Type Text",
        "annotations": _ACT,
        "description": "Type text (Unicode ok); enter:true presses Enter after. Use to fill inputs/search boxes. Text goes to the FOCUSED window — pass focus='appname' (or call screen_focus first). Returns action result (optional post-shot).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "enter": {"type": "boolean"},
                "focus": _FOCUS,
                "shot": _SHOT,
                "verify": _VERIFY,
                "force": _FORCE,
                "region": _REGION,
                "settle": {"type": "number"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "screen_verify",
        "title": "Verify Last Action",
        "annotations": _RO,
        "description": "Did the last action actually do what you expected? Returns a VERDICT instead of pixels: CONFIRMED | PARTIAL | NO_OP | DIVERGED — the same vocabulary as os-control-mcp's os_verify, and the `pixel` block it returns is what os_verify consumes. NO_OP is the valuable one: the screen never changed, so the click missed or the keys went to the wrong window. Pass expect_text (should appear), expect_gone (should disappear), expect_change (default true). Cheaper than a screenshot and it grades the outcome for you.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "expect_text": {
                    "type": "string",
                    "description": "text that should now be on screen",
                },
                "expect_gone": {
                    "type": "string",
                    "description": "text that should no longer be on screen",
                },
                "expect_change": {
                    "type": "boolean",
                    "description": "require the screen to have changed at all (default true)",
                },
                "timeout": {"type": "number", "description": "seconds, default 5"},
                "interval": {
                    "type": "number",
                    "description": "poll seconds, default 0.25",
                },
                "region": _REGION,
                "monitor": {"type": "number"},
            },
        },
    },
    {
        "name": "screen_wait_text",
        "title": "Wait for Text",
        "annotations": _RO,
        "description": "Block until `text` appears on screen (or timeout), then return its click coords. Use instead of screenshotting in a loop to see whether something finished. Polls the frame HASH and only runs OCR when the pixels actually changed — grounding costs seconds, a grab costs ~35ms, so a static screen is nearly free to wait on. Returns JSON {found,text,x,y,ms,grabs,ocr_passes}.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "substring to wait for (case-insensitive)",
                },
                "timeout": {"type": "number", "description": "seconds, default 10"},
                "interval": {
                    "type": "number",
                    "description": "poll seconds, default 0.25",
                },
                "region": _REGION,
                "monitor": {"type": "number"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "screen_read_text",
        "title": "Read Screen Text (No Image)",
        "annotations": _RO,
        "description": "Return what is on screen as TEXT + click coords, with NO image. A screenshot costs a fixed ceil(w/28)*ceil(h/28) visual tokens (4784 for a 4K monitor) regardless of encoding; this returns just the elements. Measured on a 4K monitor: ~1350 tokens unfiltered (104 elements, 3.5x cheaper) and ~95 tokens with contains= (50x cheaper), at 67ms vs 412ms. Use it to find a label, read a value, or confirm a string appeared — then click by the desktop coords it returns. use_cache=true (default) reuses learned elements for a known screen and skips OCR entirely. contains='foo' filters to matching text. Returns JSON {origin,size,focused,cached,count,elements[{id,role,text,x,y}]}.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "region": _REGION,
                "monitor": {"type": "number"},
                "contains": {
                    "type": "string",
                    "description": "only return elements whose text contains this (case-insensitive)",
                },
                "use_cache": {
                    "type": "boolean",
                    "description": "reuse learned elements for a known screen, skipping OCR (default true)",
                },
            },
        },
    },
    {
        "name": "screen_read_selection",
        "title": "Read Selection (Exact Text)",
        "annotations": _ACT,
        "description": "Copy the FOCUSED window's selection and return it verbatim — the lossless way to read text. Prefer this over screenshot+OCR whenever you need characters to be exact: a full-monitor shot downscales 4K to 2576px and drops ~8% of characters on small code, while a copy is exact and ~100x faster than an annotate pass. Select first (click/drag, or select_all:true). combo defaults to ctrl+c — TERMINALS need combo='ctrl+shift+c'. The user's clipboard is saved and restored. Returns the selected text.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "select_all": {
                    "type": "boolean",
                    "description": "send ctrl+a first to grab the whole buffer",
                },
                "combo": {
                    "type": "string",
                    "description": "copy combo; default 'ctrl+c', terminals need 'ctrl+shift+c'",
                },
                "focus": _FOCUS,
                "force": _FORCE,
            },
        },
    },
    {
        "name": "screen_focus",
        "title": "Focus Window",
        "annotations": _ACT,
        "description": "Raise + give KEYBOARD FOCUS to a window so injected keys/clicks land in it. Use before screen_type/screen_key on an app you haven't clicked into (the #1 reason 'I typed but nothing happened'). Match by app ('slack', 'firefox'), title substring, or window id from screen_list_monitors. Returns focus result / matched window.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "app": {"type": "string"},
                "title": {"type": "string"},
                "id": {"type": ["string", "number"]},
            },
        },
    },
    {
        "name": "screen_do",
        "title": "Batch Actions",
        "annotations": _DEST,
        "description": "Run an ordered batch of actions in one call to cut round-trips. Use when a multi-step UI flow would otherwise need N tool calls. steps=[{action:'move|click|scroll|drag|key|type|wait|wait_stable', ...}]. 'wait' sleeps fixed ms; 'wait_stable' blocks until settle. shot=true optional final screenshot. Stops mid-batch if you take the mouse (force=true to override). Returns per-step results.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "steps": {"type": "array", "items": {"type": "object"}},
                "stop_on_error": {"type": "boolean"},
                "shot": _SHOT,
                "force": _FORCE,
                "region": _REGION,
                "monitor": {"type": "number"},
                "settle": {"type": "number"},
            },
            "required": ["steps"],
        },
    },
    {
        "name": "screen_read_page",
        "title": "Read Page",
        "annotations": _ACT,
        "description": "Read a whole scrollable view in ONE call: auto-scrolls down until content stops moving, annotating each screen. Use instead of N rounds of scroll+screenshot. Returns full interactable inventory + a final screenshot; leaves current screen clickable by [id]. region defaults to last view; max_pages caps it; force bypasses takeover guard.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "region": _REGION,
                "max_pages": {"type": "number"},
                "amount": {"type": "number"},
                "settle_ms": {"type": "number"},
                "force": _FORCE,
            },
        },
    },
    {
        "name": "screen_tour",
        "title": "Tour UI States",
        "annotations": _DEST,
        "description": "Visit several UI states in ONE call and get a labeled thumbnail of each. Use to survey/navigate without N navigate→screenshot round-trips. steps=[{label, steps:[{action:'click|scroll|key|type|move|wait', ...}], region?, settle?}]. shot_max_edge (default 1280) sizes thumbnails. Returns labeled thumbnails + step results.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "steps": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "ordered stops: [{label, steps:[actions], region?, settle?}]",
                },
                "settle": {"type": "number"},
                "shot_max_edge": {"type": "number"},
                "force": _FORCE,
            },
            "required": ["steps"],
        },
    },
    {
        "name": "screen_wait",
        "title": "Wait for Settle",
        "annotations": _RO,
        "description": "Wait until the screen stops changing (settles) or timeout, then optionally screenshot. Use after an async/htmx update instead of guessing a fixed delay. Also usable as a 'wait_stable' step inside screen_do/screen_tour. Args: timeout (s, default 5), region/monitor, shot. Returns when stable or on timeout.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "timeout": {"type": "number"},
                "thresh": {"type": "number"},
                "window": {"type": "number"},
                "region": _REGION,
                "monitor": {"type": "number"},
                "shot": _SHOT,
            },
        },
    },
    {
        "name": "screen_watch",
        "title": "Watch (1 fps human-eye)",
        "annotations": _RO,
        "description": "Human-eye observation at ~1 fps (default). A single screenshot is a glance — this WATCHES for seconds and reports settled | evolving | jitter | unstable. Use after loaders, canvases, force-directed graphs, maps, or any UI that can thrash so you catch 'looks crazy' the way a human would. Args: region/monitor, fps (default 1), seconds (default 6), annotate (first+last OCR only), shot (final frame, default true), force. Returns timeline + verdict + final screenshot.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "region": _REGION,
                "monitor": {"type": "number"},
                "fps": {
                    "type": "number",
                    "description": "samples per second (default 1.0, clamp 0.2–10)",
                },
                "seconds": {
                    "type": "number",
                    "description": "watch window seconds (default 6, clamp 1–60)",
                },
                "annotate": {
                    "type": "boolean",
                    "description": "OCR/OmniParser on first+last samples only (default false)",
                },
                "shot": _SHOT,
                "force": _FORCE,
            },
        },
    },
    {
        "name": "screen_session",
        "title": "Record Session",
        "annotations": _ACT,
        "description": "Session recording/replay: op=start|stop|list|status|replay-path. Use to capture a trajectory of actions+screenshots for later replay. Returns status or path for the op.",
        "inputSchema": {
            "type": "object",
            "properties": {"op": {"type": "string"}, "id": {"type": "string"}},
        },
    },
    {
        "name": "screen_reload",
        "title": "Reload Server",
        "annotations": _DEST,
        "description": "Hot-reload this MCP server's own code in place (re-exec, preserving the connection). Use after editing server code so tools update WITHOUT /mcp reconnect. Returns after re-exec.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "screen_diag",
        "title": "Diagnostics",
        "annotations": _RO,
        "description": "Health dump: prereqs matrix (portal, window-info, uinput, gstreamer, …) with next_step hints, plus session/geo, cursor/guard state, grounding backends. Use first when capture, clicks, or the cursor guard misbehave. Returns the full capability/session report.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "screen_sense",
        "title": "Cross-Layer Pixel Signal",
        "annotations": _RO,
        "description": 'Return the normalized change signal from the most recent frame diff — {changed, opened, modal, no_op, activity} — so a verifier can fuse the GUI layer with the OS layer. Call right after a screen action, then pass the `pixel` object to os-control-mcp\'s os_verify (action=end, pixel=...). This is the pixel half of cross-layer action verification: it lets the agent catch a GUI that changed while the underlying service did not (or vice-versa). Passive — it reads whatever the LAST action already left behind and does not wait; use screen_verify when the GUI effect may lag. Returns {"pixel": {changed, opened, modal, no_op, activity}}. Read-only.',
        "inputSchema": {"type": "object", "properties": {}},
    },
]
HANDLERS = {
    "screen_screenshot": tool_screenshot,
    "screen_list_monitors": tool_list_monitors,
    "screen_move_mouse": lambda a: _action("screen_move_mouse", inp.move, a),
    "screen_click": lambda a: _action("screen_click", inp.click, a),
    "screen_scroll": lambda a: _action("screen_scroll", inp.scroll, a),
    "screen_drag": lambda a: _action("screen_drag", inp.drag, a),
    "screen_key": lambda a: _action("screen_key", inp.key, a),
    "screen_type": lambda a: _action("screen_type", inp.type_text, a),
    "screen_read_selection": lambda a: _action(
        "screen_read_selection", inp.read_selection, a
    ),
    "screen_focus": tool_focus,
    "screen_do": tool_do,
    "screen_tour": tool_tour,
    "screen_read_page": autoloop.scroll_to_reveal,
    "screen_wait": tool_wait,
    "screen_watch": autoloop.watch_1fps,
    "screen_session": recorder.tool_session,
    "screen_read_text": tool_read_text,
    "screen_wait_text": tool_wait_text,
    "screen_verify": tool_verify,
    "screen_diag": tool_diag,
    "screen_sense": tool_sense,
}

INSTRUCTIONS = (
    "Drive this machine's desktop like human eyes + hands.\n"
    "Loop: (1) screen_screenshot() overview to locate (never assume which monitor). "
    "(2) region zoom / annotate=true to ground. "
    "(3) click/type with space='view' from the LATEST shot (pass view_id; or element=<id>). "
    "(4) CONFIRM — not with one glance only: after loaders, canvases, graphs, maps, animations, "
    "or any UI that can thrash, call screen_watch (default ~1 fps × 6s). Verdicts: settled | "
    "evolving | jitter | unstable. jitter means continuous motion a human would call 'crazy' "
    "(e.g. force-directed graphs with hundreds of nodes) — fix the UI, don't declare pass.\n"
    "FRESH FRAMES: post-action screenshots auto-settle. Pass settle=0 for instantaneous. "
    "Region shots are fastest; full-desktop is for locate only.\n"
    "MONITOR FRAMES: GNOME damage-only streams — ON-but-STATIC needs a nudge; ASLEEP needs the human. "
    "Opt out of auto-nudge: MCP_SCREEN_NO_NUDGE=1.\n"
    "SELF-LEARNING: SENSE line on responses; use_cache=true with annotate; screen_read_page for long "
    "scrollables; screen_tour for multi-state surveys; screen_diag for health.\n"
    "HUMAN OVERSIGHT: takeover guard yields on human mouse move (STOPPED → re-plan, don't force). "
    "Agent Oath §2 agency / §11 oversight — human stays in control of their desktop."
)


def reply(mid, result=None, error=None):
    m = {"jsonrpc": "2.0", "id": mid}
    if error:
        m["error"] = error
    else:
        m["result"] = result
    sys.stdout.write(json.dumps(m) + "\n")
    sys.stdout.flush()


# Per-client tool-output caps, applied from the `initialize` handshake so the user never
# has to configure anything. Grok Build truncates a tool result at 20KB, which cuts a base64
# image mid-string; it then rejects the whole image ("integrity check failed: image bytes are
# truncated") and the model sees nothing. Detect it and fit the payload instead.
# Verified against Grok Build 0.2.112. An explicit env override always wins.
_CLIENT_OUT_KB = {"grok": 20}


def _apply_client_limits(params):
    """Never raise: this runs INSIDE the stdin loop before `initialize` is answered, so an
    exception here kills the server mid-handshake with no reply and no diagnostic. `params`
    and `clientInfo` come straight off the wire and are not guaranteed to be dicts."""
    try:
        if os.environ.get("MCP_SCREEN_MAX_OUTPUT_KB"):
            return  # operator set it explicitly — don't second-guess
        info = params.get("clientInfo") if isinstance(params, dict) else None
        name = str(info.get("name", "") if isinstance(info, dict) else "").lower()
        for key, kb in _CLIENT_OUT_KB.items():
            if key in name:
                budget.MAX_OUT_KB = kb
                state.log(f"client '{name}': capping tool output at {kb}KB")
                return
    except Exception as e:  # noqa: BLE001 - fail open; a cap is an optimization
        state.log(f"client-limit detection skipped: {type(e).__name__}: {e}")


def main():
    import threading
    import atexit
    import signal

    threading.Thread(
        target=grounding.warmup, daemon=True
    ).start()  # kill the cold-start model load
    # Persistent PipeWire pipelines must be released on EVERY exit path or they linger
    # (native GStreamer threads keep pulling screencast buffers + drive the compositor).
    atexit.register(capture.shutdown)
    atexit.register(inp.ui.shutdown)

    def _bye(*_a):
        try:
            capture.shutdown()
        finally:
            os._exit(0)

    for _sig in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
        try:
            signal.signal(_sig, _bye)
        except Exception:
            pass
    try:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except Exception:
                continue
            mid = msg.get("id")
            method = msg.get("method")
            if method == "initialize":
                _apply_client_limits(msg.get("params") or {})
                reply(
                    mid,
                    {
                        "protocolVersion": "2025-11-25",
                        "capabilities": {"tools": {"listChanged": True}},
                        "serverInfo": {"name": "mcp-screen", "version": __version__},
                        "instructions": INSTRUCTIONS,
                    },
                )
            elif method == "notifications/initialized":
                pass
            elif method == "ping":
                reply(mid, {})
            elif method == "tools/list":
                reply(mid, {"tools": TOOLS})
            elif method == "tools/call":
                name = msg["params"]["name"]
                args = msg["params"].get("arguments", {}) or {}
                if name == "screen_reload":
                    reply(
                        mid,
                        {
                            "content": [
                                _txt(
                                    "mcp-screen hot-reloaded in place (execv); tool list refreshed"
                                )
                            ]
                        },
                    )
                    try:
                        sys.stdout.write(
                            json.dumps(
                                {
                                    "jsonrpc": "2.0",
                                    "method": "notifications/tools/list_changed",
                                }
                            )
                            + "\n"
                        )
                        sys.stdout.flush()
                        capture.shutdown()
                        inp.ui.shutdown()  # release uinput devices so reload doesn't leak them
                    except Exception:
                        pass
                    # execv keeps os.environ but NOT interpreter state, and the client
                    # does not re-send `initialize` over the preserved stdio connection —
                    # so a cap learned from clientInfo would be silently lost and the very
                    # next screenshot would be dropped by the client again. Pin it into the
                    # environment, which _apply_client_limits then honours on restart.
                    if budget.MAX_OUT_KB:
                        os.environ["MCP_SCREEN_MAX_OUTPUT_KB"] = str(budget.MAX_OUT_KB)
                    os.execv(sys.executable, [sys.executable] + sys.argv)
                t0 = time.time()
                try:
                    handler = HANDLERS.get(name)
                    if handler is None:
                        reply(
                            mid,
                            {
                                "content": [_txt(f"unknown tool: {name}")],
                                "isError": True,
                            },
                        )
                        continue
                    res = handler(args)
                    reply(mid, res)
                    if REC.active():
                        try:
                            resolved = (
                                list(inp.resolve_xy(args))
                                if {"x", "y"} <= set(args)
                                else None
                            )
                        except Exception:
                            resolved = None
                        REC.log_action(
                            name,
                            args,
                            (res.get("content") or [{}])[0].get("text", ""),
                            not res.get("isError"),
                            int((time.time() - t0) * 1000),
                            resolved=resolved,
                            view=state.SESSION.get("view"),
                        )
                except Exception as e:
                    import traceback

                    tb = traceback.format_exc()
                    state.log(tb)
                    try:
                        open("/tmp/screen_err.txt", "w").write(tb)
                    except Exception:
                        pass
                    if REC.active():
                        REC.log_action(
                            name,
                            args,
                            f"ERROR: {e}",
                            False,
                            int((time.time() - t0) * 1000),
                        )
                    reply(mid, {"content": [_txt(f"ERROR: {e}")], "isError": True})
            elif mid is not None:
                reply(
                    mid,
                    {},
                    error={"code": -32601, "message": f"unknown method {method}"},
                )
    finally:
        capture.shutdown()
        os._exit(0)


if __name__ == "__main__":
    main()
