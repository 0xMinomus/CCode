"""autoloop.py — server-side self-adaptive micro-loops for mcp-screen (v1.2).

These are deterministic loops that need NO model in the loop, so any consuming CLI gets
them for free and they cost zero LLM round-trips.

- `scroll_to_reveal` — read a long page in one call (scroll until no new content).
- `watch_1fps` — human-eye observation: sample the screen at ~1 fps and report what
  a human would notice over time (settled UI vs continuous jitter / force-sim chaos /
  navigations). Default path after animations, canvases, graphs, maps, loaders.

Imports the sibling modules directly (capture/input/grounding/sense/state) — none import
this, so no cycle. Fail-open: errors degrade to whatever was gathered so far."""

import time

import state
import capture
import input as inp
import grounding
import sense


def _txt(s):
    return {"type": "text", "text": s}


# ---------------------------------------------------------------------------
# Human-eye watch (1 fps default) — pure verdict helpers (unit-tested)
# ---------------------------------------------------------------------------

# Sustained "local" frame activity is the signature of force-directed graphs,
# spinners, and other continuous animations that a single screenshot misses.
_JITTER_FRAC = 0.55  # ≥55% of inter-frame gaps are local activity → jitter
_EVOLVING_MAJOR = 1  # at least one major/panel transition → evolving
_SETTLE_TAIL = 2  # last N gaps must be "none" to call it settled


def classify_watch_timeline(activities):
    """activities: list of activity labels between consecutive samples
    ('none'|'local'|'panel'|'major'|'unknown').

    Returns a verdict dict:
      verdict: settled | evolving | jitter | unstable | empty
      reason: short human-readable why
      stats: counts
    """
    acts = [a for a in (activities or []) if a]
    if not acts:
        return {
            "verdict": "empty",
            "reason": "no inter-frame samples",
            "stats": {"n": 0},
        }
    n = len(acts)
    counts = {k: acts.count(k) for k in ("none", "local", "panel", "major", "unknown")}
    local_frac = counts["local"] / n
    majorish = counts["panel"] + counts["major"]
    tail = acts[-_SETTLE_TAIL:] if n >= _SETTLE_TAIL else acts
    tail_settled = all(a == "none" for a in tail)

    if local_frac >= _JITTER_FRAC and majorish == 0:
        return {
            "verdict": "jitter",
            "reason": (
                f"sustained local motion ({counts['local']}/{n} gaps) without "
                "navigation — looks like continuous animation/force-sim/jitter "
                "a human would see as 'crazy'"
            ),
            "stats": {"n": n, **counts, "local_frac": round(local_frac, 3)},
        }
    if majorish >= _EVOLVING_MAJOR and not tail_settled:
        return {
            "verdict": "evolving",
            "reason": (
                f"UI still changing (panel/major={majorish}) and not settled "
                "at end of watch window"
            ),
            "stats": {"n": n, **counts, "local_frac": round(local_frac, 3)},
        }
    if majorish >= _EVOLVING_MAJOR and tail_settled:
        return {
            "verdict": "evolving",
            "reason": (
                f"navigation/layout change mid-watch (panel/major={majorish}) "
                "then settled — re-read the final frame as ground truth"
            ),
            "stats": {"n": n, **counts, "local_frac": round(local_frac, 3)},
        }
    if tail_settled and counts["local"] + majorish <= max(1, n // 5):
        return {
            "verdict": "settled",
            "reason": "screen quiet at end of watch; no sustained motion",
            "stats": {"n": n, **counts, "local_frac": round(local_frac, 3)},
        }
    return {
        "verdict": "unstable",
        "reason": (
            f"mixed activity without a clear settle (local={counts['local']}, "
            f"panel={counts['panel']}, major={counts['major']}, none={counts['none']})"
        ),
        "stats": {"n": n, **counts, "local_frac": round(local_frac, 3)},
    }


def scroll_to_reveal(args):
    """Read a whole scrollable view in one call. Scrolls down until content stops moving
    (or max_pages), annotating each screen and accumulating unique interactables.

    args: region [x,y,w,h] (default last view), max_pages (12), amount (per-scroll notches,
    10), force (bypass guard), settle_ms (250). Returns the discovered element inventory +
    a final screenshot; leaves SESSION['elements'] set to the LAST screen so click-by-id
    works on what's currently visible."""
    t0 = time.time()
    region = args.get("region")
    if region is None and state.SESSION.get("view"):
        v = state.SESSION["view"]
        region = [v["ox"], v["oy"], v["dw"], v["dh"]]
    max_pages = int(args.get("max_pages", 12))
    amount = int(args.get("amount", 10))
    settle = float(args.get("settle_ms", 250)) / 1000.0
    force = args.get("force")

    cx = (region[0] + region[2] // 2) if region else None
    cy = (region[1] + region[3] // 2) if region else None

    seen = {}  # (role, norm_label) -> {"role","label","count"}
    pages = 0
    reached_end = False
    prev_small = None
    last_img = last_ox = last_oy = None
    last_store = {}
    stopped = None

    for i in range(max_pages):
        try:
            inp.guard_user(force)
        except inp.UserControlError as e:
            stopped = str(e)
            break

        img, ox, oy = capture.capture_desktop(region)
        last_img, last_ox, last_oy = img, ox, oy
        cur_small = sense.downsample(img)

        # On the 2nd+ screen, stop if the last scroll didn't move content (end of page).
        if prev_small is not None:
            if not sense.scroll_from_pair(prev_small, cur_small)["moved"]:
                reached_end = True
                break

        # Annotate this screen, fold its interactables into the running inventory.
        try:
            _marked, els = grounding.annotate(img)
            store = {}
            for e in els:
                x1, y1, x2, y2 = e["bbox"]
                store[e["id"]] = {
                    "x": ox + (x1 + x2) // 2,
                    "y": oy + (y1 + y2) // 2,
                    "label": e["label"],
                    "role": e["role"],
                }
                k = (
                    e.get("role", ""),
                    " ".join((e.get("label") or "").lower().split()),
                )
                rec = seen.get(k)
                if rec:
                    rec["count"] += 1
                else:
                    seen[k] = {
                        "role": e.get("role", ""),
                        "label": e.get("label", ""),
                        "count": 1,
                    }
            last_store = store
        except Exception:
            pass

        prev_small = cur_small
        pages += 1

        # Scroll down for the next screen.
        if cx is not None:
            inp.scroll(
                {
                    "x": cx,
                    "y": cy,
                    "space": "desktop",
                    "direction": "down",
                    "amount": amount,
                }
            )
        else:
            inp.scroll({"direction": "down", "amount": amount})
        if settle > 0:
            time.sleep(settle)

    # Current screen's elements remain clickable by id (not tied to a world-model row).
    if last_store:
        state.SESSION["elements"] = last_store
        state.SESSION["elements_state_id"] = None

    # Build the report.
    items = sorted(seen.values(), key=lambda r: (r["role"], r["label"]))
    lines = [
        f"  {r['role']}: {r['label']!r}" + (f" x{r['count']}" if r["count"] > 1 else "")
        for r in items
        if r["label"]
    ]
    head = (
        f"READ_PAGE: {pages} screen(s) scrolled, reached_end={reached_end}, "
        f"{len(items)} unique interactables, {int((time.time() - t0) * 1000)}ms total."
    )
    if stopped:
        head += f"  STOPPED (user takeover): {stopped}"
    body = (
        "discovered interactables (current screen is clickable by [id]; scroll back to reach off-screen ones):\n"
        + "\n".join(lines)
    )
    content = [_txt(head), _txt(body)]

    # Final screenshot of where we ended up (with cursor marker), so the agent sees the state.
    if last_img is not None:
        try:
            capture.cursor_pos()
            shot_img = capture.draw_cursor(last_img, last_ox, last_oy)
        except Exception:
            shot_img = last_img
        content += capture.encode_store(
            shot_img, last_ox, last_oy, "read_page", time.time()
        )
    return {"content": content, "isError": bool(stopped)}


def watch_1fps(args):
    """Human-eye 1 fps observation of a region/monitor.

    A single screenshot is a glance. Humans catch crazy UIs (force-directed
    graphs thrashing, loaders, canvas jitter) by *watching* over time. This
    tool samples at `fps` (default **1.0**) for `seconds` (default **6**) and
    returns a timeline + verdict:

      settled   — quiet at end; safe to act on the last frame
      evolving  — navigation / layout change mid-watch
      jitter    — continuous local motion (the "looks crazy" case)
      unstable  — mixed activity without a clear settle

    Args:
      region [x,y,w,h] | monitor — what to watch (default last view / full)
      fps (default 1.0) — samples per second (clamped 0.2–10)
      seconds (default 6) — total watch window (clamped 1–60)
      annotate (bool, default false) — OCR/OmniParser on first+last sample only
      force — bypass takeover guard
      shot (default true) — include final screenshot

    Returns text timeline + verdict; final image when shot=true. Does NOT move
    the pointer except optional monitor-prime via capture path. Takeover guard
    re-checked every sample.
    """
    t0 = time.time()
    fps = float(args.get("fps", 1.0) or 1.0)
    fps = max(0.2, min(10.0, fps))
    seconds = float(args.get("seconds", 6.0) or 6.0)
    seconds = max(1.0, min(60.0, seconds))
    interval = 1.0 / fps
    n_samples = max(2, int(round(seconds * fps)) + 1)
    force = args.get("force")
    do_annotate = bool(args.get("annotate"))
    want_shot = args.get("shot", True)
    if want_shot is None:
        want_shot = True

    region = args.get("region")
    monitor = args.get("monitor")
    # Resolve crop once (desktop px)
    crop = None
    if region is not None:
        crop = list(region)
    elif monitor is not None:
        try:
            capture.ensure_geo()
            geo = state.SESSION.get("geo") or []
            mi = int(monitor)
            if 0 <= mi < len(geo):
                g = geo[mi]
                crop = [g["x"], g["y"], g["w"], g["h"]]
        except Exception:
            crop = None
    elif state.SESSION.get("view"):
        v = state.SESSION["view"]
        crop = [v["ox"], v["oy"], v["dw"], v["dh"]]

    samples = []  # {t_ms, activity_from_prev, changed_fraction}
    activities = []
    prev_small = None
    first_img = last_img = None
    last_ox = last_oy = 0
    first_els = last_els = None
    stopped = None

    for i in range(n_samples):
        try:
            inp.guard_user(force)
        except inp.UserControlError as e:
            stopped = str(e)
            break

        try:
            img, ox, oy = capture.capture_desktop(crop)
        except Exception as e:
            return {
                "content": [_txt(f"WATCH: capture failed on sample {i}: {e}")],
                "isError": True,
            }

        last_img, last_ox, last_oy = img, ox, oy
        if first_img is None:
            first_img = img

        cur_small = sense.downsample(img)
        act = "none"
        frac = 0.0
        if prev_small is not None:
            act_info = sense.classify_activity(prev_small, cur_small)
            act = act_info.get("activity") or "unknown"
            frac = act_info.get("changed_fraction") or 0.0
            activities.append(act)
        samples.append(
            {
                "i": i,
                "t_ms": int((time.time() - t0) * 1000),
                "activity_from_prev": act if prev_small is not None else "—",
                "changed_fraction": frac,
            }
        )

        if do_annotate and (i == 0 or i == n_samples - 1):
            try:
                _marked, els = grounding.annotate(img)
                if i == 0:
                    first_els = els
                last_els = els
            except Exception:
                pass

        prev_small = cur_small

        # sleep until next sample (except after last)
        if i + 1 < n_samples:
            # account for work time so average rate ≈ fps
            elapsed = time.time() - t0
            target = (i + 1) * interval
            delay = target - elapsed
            if delay > 0:
                # re-check guard in small slices so takeover is snappy
                end = time.time() + delay
                while time.time() < end:
                    try:
                        inp.guard_user(force)
                    except inp.UserControlError as e:
                        stopped = str(e)
                        break
                    time.sleep(min(0.05, max(0.0, end - time.time())))
                if stopped:
                    break

    verdict = classify_watch_timeline(activities)
    total_ms = int((time.time() - t0) * 1000)

    # Element churn first→last when annotated
    el_note = ""
    if first_els is not None and last_els is not None:
        try:
            d = sense.diff_elements(first_els, last_els)
            el_note = (
                f" element_churn: +{len(d.get('new') or [])} "
                f"-{d.get('removed', 0)} moved={d.get('moved', 0)}"
            )
        except Exception:
            pass

    head = (
        f"WATCH: fps={fps:g} samples={len(samples)} window≈{seconds:g}s "
        f"total={total_ms}ms verdict={verdict['verdict']}."
    )
    if stopped:
        head += f" STOPPED (user takeover): {stopped}"

    timeline_lines = []
    for s in samples:
        afp = s["activity_from_prev"]
        if afp == "—":
            timeline_lines.append(f"  t={s['t_ms']:5d}ms  sample#{s['i']}  (baseline)")
        else:
            cf = s["changed_fraction"]
            timeline_lines.append(
                f"  t={s['t_ms']:5d}ms  sample#{s['i']}  "
                f"Δ={afp} frac={cf if cf is not None else '?'}"
            )

    body = (
        f"verdict: {verdict['verdict']}\n"
        f"reason: {verdict['reason']}\n"
        f"stats: {verdict.get('stats')}\n"
        f"{el_note.strip()}\n"
        f"timeline (human-eye {fps:g} fps):\n" + "\n".join(timeline_lines) + "\n\n"
        "HOW TO USE: jitter → fix continuous animation / cap graph nodes before "
        "declaring UI ok. evolving → re-ground on last frame. settled → act. "
        "A single screenshot is a glance; this is watching."
    )

    content = [_txt(head), _txt(body)]

    if want_shot and last_img is not None:
        try:
            capture.cursor_pos()
            shot_img = capture.draw_cursor(last_img, last_ox, last_oy)
        except Exception:
            shot_img = last_img
        # Store transform so follow-up clicks on the final frame work
        content += capture.encode_store(
            shot_img, last_ox, last_oy, "watch", time.time()
        )

    return {
        "content": content,
        "isError": bool(stopped),
        # structured for tests / programmatic clients (MCP still carries text)
        "_watch": {
            "verdict": verdict,
            "samples": samples,
            "fps": fps,
            "seconds": seconds,
        },
    }
