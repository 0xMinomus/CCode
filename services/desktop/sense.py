"""sense.py — ambient perception signals for mcp-screen (v1.2).

Turns the frames + element lists the server already produces into cheap, structured
signals so a consuming agent adapts WITHOUT being told: "something opened", "there's more
below — scroll", "these buttons are new", "a modal grabbed focus". Computed on every tool
call from a one-frame history kept in state.SESSION['sense']; adds NO new perception pass
(the expensive OCR/OmniParser only runs when the agent already asked for annotate=true).

Design rules (match reliability.py): imports `state` (+ grounding._iou for icon matching)
only — never server/capture/input, so it stays unit-testable on synthetic arrays. Every
public entry is fail-open: on any error it returns an empty/None-ish result, never raises.
All numpy ops are cheap (strided downsample, single boolean reductions)."""

from typing import Any

import numpy as np

import state

try:
    from grounding import _iou as _iou  # reuse the IoU already defined for merge/dedup
except Exception:  # pragma: no cover

    def _iou(a, b):  # minimal fallback
        ax1, ay1, ax2, ay2 = a
        bx1, by1, bx2, by2 = b
        ix1, iy1 = max(ax1, bx1), max(ay1, by1)
        ix2, iy2 = min(ax2, bx2), min(ay2, by2)
        iw, ih = ix2 - ix1, iy2 - iy1
        if iw <= 0 or ih <= 0:
            return 0.0
        inter = iw * ih
        ua = (
            max(0, ax2 - ax1) * max(0, ay2 - ay1)
            + max(0, bx2 - bx1) * max(0, by2 - by1)
            - inter
        )
        return inter / ua if ua > 0 else 0.0


DS_EDGE = 256  # history-frame long edge for cheap diffs


# ---------------------------------------------------------------------------
# Frame helpers
# ---------------------------------------------------------------------------
def downsample(arr, edge=DS_EDGE):
    """Strided downsample an HxWx{3,4} uint8 frame to ~edge long-edge RGB. Cheap, no interp."""
    a = np.asarray(arr)
    if a.ndim != 3 or a.shape[0] == 0 or a.shape[1] == 0:
        return None
    a = a[..., :3]
    h, w = a.shape[:2]
    step = max(1, max(h, w) // edge)
    return np.ascontiguousarray(a[::step, ::step], dtype=np.uint8)


def _aligned(b, a):
    """Crop two small frames to a shared shape so diffs don't throw on a 1px mismatch."""
    if b is None or a is None or b.ndim != 3 or a.ndim != 3:
        return None, None
    h = min(b.shape[0], a.shape[0])
    w = min(b.shape[1], a.shape[1])
    if h == 0 or w == 0:
        return None, None
    return b[:h, :w], a[:h, :w]


def classify_activity(before_small, after_small, thresh=12):
    """How much changed between two downsampled frames -> activity bucket + fraction.

    none (<0.3%): a click that did nothing (likely misclick). local (<8%): a control
    toggled. panel (<30%): a section/dropdown opened. major (>=30%): navigation/new screen."""
    b, a = _aligned(before_small, after_small)
    if b is None or a is None:
        return {"activity": "unknown", "changed_fraction": None}
    frac = float(
        (np.abs(a.astype(np.int16) - b.astype(np.int16)).max(axis=2) > thresh).mean()
    )
    act = (
        "none"
        if frac < 0.003
        else "local"
        if frac < 0.08
        else "panel"
        if frac < 0.30
        else "major"
    )
    return {"activity": act, "changed_fraction": round(frac, 4)}


def change_bbox(before_small, after_small, view, thresh=12):
    """Bounding box of changed pixels between two small frames, scaled to raw/view px
    (the space element bboxes live in), or None. Lets us keep only the elements that sit
    where pixels ACTUALLY moved — dropping OCR re-read jitter elsewhere on the frame."""
    b, a = _aligned(before_small, after_small)
    if b is None or a is None or not view:
        return None
    mask = np.abs(a.astype(np.int16) - b.astype(np.int16)).max(axis=2) > thresh
    if not mask.any():
        return None
    sh, sw = b.shape[:2]
    dw, dh = view.get("dw") or sw, view.get("dh") or sh
    sx, sy = dw / float(sw), dh / float(sh)
    rows = np.where(np.any(mask, axis=1))[0]
    cols = np.where(np.any(mask, axis=0))[0]
    x0, x1 = cols[0], cols[-1]
    y0, y1 = rows[0], rows[-1]
    return [
        int(x0 * sx),
        int(y0 * sy),
        int((x1 - x0 + 1) * sx),
        int((y1 - y0 + 1) * sy),
    ]


def _in_bbox(center, bbox, pad=8):
    x, y, w, h = bbox
    return (x - pad) <= center[0] <= (x + w + pad) and (y - pad) <= center[1] <= (
        y + h + pad
    )


def scroll_from_pair(before_small, after_small, thresh=12):
    """Did content move between two frames (excluding sticky top/bottom strips)?

    Returns {moved: bool, frac: float}. Used after a real scroll to tell "it moved, there's
    more" from "nothing moved, you're at the end / it isn't scrollable"."""
    b, a = _aligned(before_small, after_small)
    if b is None or a is None:
        return {"moved": False, "frac": 0.0}
    h = b.shape[0]
    lo, hi = int(h * 0.12), int(h * 0.88)  # drop sticky header/footer bands
    if hi <= lo:
        lo, hi = 0, h
    frac = float(
        (
            np.abs(a[lo:hi].astype(np.int16) - b[lo:hi].astype(np.int16)).max(axis=2)
            > thresh
        ).mean()
    )
    return {"moved": frac > 0.02, "frac": round(frac, 4)}


# ---------------------------------------------------------------------------
# Element-set diff (stable identity across frames)
# ---------------------------------------------------------------------------
def _norm(s):
    return " ".join((s or "").lower().split())


def _center(b):
    return ((b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0)


def _key(el, grid=16):
    cx, cy = _center(el["bbox"])
    return (
        el.get("role", ""),
        _norm(el.get("label", "")),
        round(cx / grid),
        round(cy / grid),
    )


def diff_elements(prev, cur, move_radius=40):
    """Match cur elements against prev to surface what's NEW/removed/moved/changed.

    Identity ladder: exact (role+label+quantized-center) -> same; (role+label) within
    move_radius -> moved; empty-label icon with IoU>0.5 same role -> same; else NEW.
    Returns {new:[...], removed:int, moved:int, changed:[...]}. Fail-open to empty."""
    try:
        prev = prev or []
        cur = cur or []
        pkeys = {}
        for p in prev:
            pkeys.setdefault(_key(p), []).append(p)
        used = set()
        new, moved, changed = [], 0, []

        def _slim(e):
            return {
                "role": e.get("role"),
                "label": e.get("label"),
                "center": [int(c) for c in _center(e["bbox"])],
            }

        for c in cur:
            k = _key(c)
            bucket = pkeys.get(k)
            if bucket:  # exact match -> same element (mark consumed so move/IoU can't re-match it)
                used.add(id(bucket.pop()))
                if not bucket:
                    pkeys.pop(k, None)
                continue
            cl, crole = _norm(c.get("label", "")), c.get("role", "")
            ccx, ccy = _center(c["bbox"])
            hit = None
            for p in prev:
                if id(p) in used:
                    continue
                if (
                    crole == p.get("role", "")
                    and cl
                    and cl == _norm(p.get("label", ""))
                ):
                    pcx, pcy = _center(p["bbox"])
                    if abs(pcx - ccx) <= move_radius and abs(pcy - ccy) <= move_radius:
                        hit = p
                        break
            if hit is not None:
                used.add(id(hit))
                moved += 1
                continue
            if not cl:  # label-less icon: IoU match
                for p in prev:
                    if (
                        id(p) in used
                        or p.get("role", "") != crole
                        or _norm(p.get("label", ""))
                    ):
                        continue
                    if _iou(c["bbox"], p["bbox"]) > 0.5:
                        hit = p
                        break
                if hit is not None:
                    used.add(id(hit))
                    continue
            new.append(_slim(c))

        # `used` already tracks every prev element consumed by an exact / moved / IoU match,
        # so the unmatched prev count is just len(prev) - len(used). The previous form
        # (len(prev) - (len(cur) - len(new))) only holds when len(used) == len(cur)-len(new);
        # that identity breaks if any prev element is referenced twice in the list (its id
        # is added to `used` once, but it was popped from its key bucket twice), inflating
        # the reported removed count.
        removed = len(prev) - len(used)
        return {
            "new": new,
            "removed": int(removed),
            "moved": int(moved),
            "changed": changed,
        }
    except Exception:
        return {"new": [], "removed": 0, "moved": 0, "changed": []}


# ---------------------------------------------------------------------------
# Overlay / modal detection
# ---------------------------------------------------------------------------
def detect_overlay(before_small, after_small, new_elements, view_wh=None):
    """Heuristic modal/popover/toast detection. Two cheap fused cues:
      A) backdrop dim: a broad region got uniformly darker vs the prior frame.
      B) centered new-element cluster occupying 20-70% of the view.
    Returns {present, kind, confidence, region|None}. Fail-open to not-present."""
    try:
        present = False
        kind = "none"
        conf = 0.0
        region = None
        # Cue A: backdrop dim
        b, a = _aligned(before_small, after_small)
        if b is not None and a is not None:
            lb = b.astype(np.int16).mean(axis=2)
            la = a.astype(np.int16).mean(axis=2)
            darker = la < lb - 18
            dim_frac = float(darker.mean())
            if dim_frac > 0.25:
                present = True
                kind = "modal"
                conf = min(1.0, 0.4 + dim_frac)
        # A modal REQUIRES a dimmed backdrop (Cue A above). A centered new-element cluster
        # WITHOUT dimming is just inline content expanding (accordion/dropdown), NOT a modal —
        # claiming a popover there was a false positive seen in live operation. So we only flag
        # a corner toast (informational), never a blocking popover, when there's no dimming.
        ne = new_elements or []
        if not present and ne and view_wh:
            vw, vh = view_wh
            xs = [e["center"][0] for e in ne]
            ys = [e["center"][1] for e in ne]
            if len(ne) <= 3 and (
                max(ys) / max(1, vh) > 0.8 or max(xs) / max(1, vw) > 0.85
            ):
                kind = "toast"  # corner notification — informational, not blocking
        return {
            "present": present,
            "kind": kind,
            "confidence": round(conf, 2),
            "region": region,
        }
    except Exception:
        return {"present": False, "kind": "none", "confidence": 0.0, "region": None}


# ---------------------------------------------------------------------------
# History ring (one prior frame + element set per session)
# ---------------------------------------------------------------------------
def _hist() -> dict[str, Any]:
    h = state.SESSION.get("sense")
    if not isinstance(h, dict):
        new_h: dict[str, Any] = {"small": None, "view": None, "elements": None}
        state.SESSION["sense"] = new_h
        return new_h
    return h


def _same_view(v1, v2):
    if not v1 or not v2:
        return False
    return (
        v1.get("ox") == v2.get("ox")
        and v1.get("oy") == v2.get("oy")
        and abs((v1.get("scale") or 0) - (v2.get("scale") or 0)) < 1e-6
        and v1.get("dw") == v2.get("dw")
        and v1.get("dh") == v2.get("dh")
    )


def stash(img_arr, view, elements):
    """Remember this frame (downsampled) + elements as the new 'before' for next call."""
    try:
        h = _hist()
        h["small"] = downsample(img_arr)
        h["view"] = dict(view) if view else None
        h["elements"] = elements
    except Exception:
        pass


def to_pixel_signal(sig):
    """Normalize the rich SENSE dict into the compact cross-layer contract a verifier
    consumes (os-control-mcp's `os_verify` `pixel` arg): {changed, opened, modal, no_op,
    activity}. `changed` is the one field the fusion needs — did the screen move — with
    the rest as detail. Pure + fail-open: an empty/None sig reads as a no-op."""
    sig = sig or {}
    settle = sig.get("settle") or {}
    activity = settle.get("activity")
    change = sig.get("change") or {}
    overlay = sig.get("overlay") or {}
    opened = bool(change.get("new_count"))
    modal = bool(overlay.get("present")) and overlay.get("kind") == "modal"
    changed = bool(
        activity not in (None, "none")
        or opened
        or overlay.get("present")
        or sig.get("scroll")
    )
    return {
        "changed": changed,
        "opened": opened,
        "modal": modal,
        "no_op": not changed,
        "activity": activity or "none",
    }


def compute(img_arr, view, elements=None, scrolled=False):
    """Assemble the ambient SENSE signal dict by diffing against the stored prior frame.

    Only diffs when the prior frame shares the same view transform (never compares a region
    zoom against a full-desktop shot). `elements` (from annotate) enables change/overlay
    cues; without them only pixel signals are produced. Returns a compact dict; fail-open."""
    out = {}
    try:
        h = _hist()
        cur_small = downsample(img_arr)
        prev_small = h.get("small")
        comparable = prev_small is not None and _same_view(h.get("view"), view)
        new_elements = []
        if comparable:
            settle = classify_activity(prev_small, cur_small)
            out["settle"] = settle
            if scrolled:
                out["scroll"] = scroll_from_pair(prev_small, cur_small)
            # Element-diff + overlay are only TRUSTWORTHY where pixels actually moved. When the
            # frame is static (activity 'none'), any element delta is OCR nondeterminism jitter
            # between two annotate passes, and the overlay heuristic false-fires on it — so gate
            # both on real change. The pixel signal is ground truth.
            meaningful = settle.get("activity") not in (None, "none")
            cbbox = change_bbox(prev_small, cur_small, view) if meaningful else None
            if meaningful and elements is not None and h.get("elements") is not None:
                d = diff_elements(h["elements"], elements)
                new_el = d["new"]
                # Keep only genuinely-new elements that sit where pixels actually moved; this
                # drops OCR re-read jitter (same element re-detected with a slightly different
                # label elsewhere on the frame counted as new+removed).
                if cbbox:
                    new_el = [e for e in new_el if _in_bbox(e["center"], cbbox)]
                new_elements = new_el
                if new_el:
                    out["change"] = {
                        "new": new_el[:8],
                        "new_count": len(new_el),
                        "changed_region": cbbox,
                    }
            if meaningful:
                vw = vh = None
                if view:
                    # element centers are in full IMAGE px (annotate runs at native res), so the
                    # view box must be dw/dh — NOT the downscaled render size.
                    vw = int(view.get("dw") or 0)
                    vh = int(view.get("dh") or 0)
                ov = detect_overlay(
                    prev_small, cur_small, new_elements, (vw, vh) if vw else None
                )
                if ov["present"]:
                    out["overlay"] = ov
    except Exception:
        pass
    return out
