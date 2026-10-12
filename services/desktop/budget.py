"""budget.py — fit an encoded screenshot to a client's tool-output cap.

Pure image/arithmetic logic: imports only stdlib + Pillow, NEVER gi/GStreamer/state. That
is deliberate and load-bearing, the same reason `reliability.py` takes an injected grabber:
capture.py cannot be imported without a real gi + GStreamer + D-Bus session, so anything
living there is invisible to CI (conftest substitutes a stub `capture`). This logic had no
CI coverage at all while it sat in capture.py. Keep the downscaler INJECTED so this module
stays importable anywhere.

Why any of this exists: some MCP clients hard-cap tool-result size. Grok Build truncates at
20KB, which cuts a base64 image mid-string; the client then rejects the whole image
("integrity check failed: image bytes are truncated") and the model sees NOTHING — strictly
worse than a low-fidelity image. So shrink until it fits.
"""

import io
import os


def _env_int(name, default):
    """A malformed env value must degrade, not crash the server at import time."""
    try:
        return max(0, int(os.environ.get(name, "") or default))
    except (TypeError, ValueError):
        return default


#: 0 = unlimited (Claude's limit is 10MB/image, far above any shot we produce). Set from the
#: `initialize` handshake's clientInfo by server._apply_client_limits, or via the env var.
#: This module owns the value; capture and server both read/write it HERE so there is one
#: source of truth rather than two drifting copies.
MAX_OUT_KB = _env_int("MCP_SCREEN_MAX_OUTPUT_KB", 0)

#: Default headroom for the accompanying text block + JSON envelope. Callers that know how
#: much text they will emit alongside the image should pass `reserve_bytes` instead — an
#: annotated screenshot can carry one line per detected element, which on a busy 4K desktop
#: far exceeds this default and would push the whole result back over the client's cap.
ENVELOPE_BYTES = 2048

_START_QUALITY = 60


def b64_len(n):
    """Encoded size of n raw bytes — the number the client's cap actually applies to."""
    return ((n + 2) // 3) * 4


def fit_to_budget(out, raw, downscale, max_out_kb=None, reserve_bytes=None):
    """Shrink `out` until its base64 fits the cap. Returns (raw_bytes, note, (w, h)).

    The returned (w, h) is the size of the image ACTUALLY encoded, and callers MUST use it
    to restate their view->desktop transform. Shipping a shrunk image while advertising the
    pre-shrink scale makes every view-space click miss by that ratio — the stale-view guard
    cannot catch it, because the view id never changed.

    `downscale(img, w, h) -> img` is injected (capture passes its cv2/PIL implementation).
    Returns `raw` unchanged, and an empty note, when no cap applies or it already fits —
    that no-op path must stay byte-identical, since it is what Claude takes.

    Lossless WebP of a 4K desktop is ~900KB encoded; a 20KB cap needs ~45x less, so we go
    lossy AND smaller. Degrading is the whole point: a blurry overview the model can see
    beats a crisp one the client throws away. Region shots are usually already under the
    cap and skip this entirely.
    """
    cap = MAX_OUT_KB if max_out_kb is None else max_out_kb
    if not cap:
        return raw, "", out.size
    reserve = ENVELOPE_BYTES if reserve_bytes is None else max(reserve_bytes, 512)
    # Never let the reserve swallow the whole cap: a small cap used to make `budget` <= 0,
    # which returned the FULL over-cap payload unshrunk — the exact drop this prevents.
    # Floor the usable budget at a quarter of the cap and shrink into it instead.
    budget = max(cap * 1024 - reserve, (cap * 1024) // 4)
    if b64_len(len(raw)) <= budget:
        return raw, "", out.size

    ow, oh = out.size
    q = _START_QUALITY

    def enc(scale):
        """Encode at `scale` of the ORIGINAL size. Always measured from `out`, never from a
        previous candidate — chaining scales off a mutated size is what made the earlier
        estimate-then-grow version undershoot to 8% of the allowed budget."""
        w, h = max(1, round(ow * scale)), max(1, round(oh * scale))
        im = out if scale >= 1.0 else downscale(out, w, h)
        b = io.BytesIO()
        im.convert("RGB").save(b, format="WEBP", quality=q, method=4)
        return b.getvalue(), w, h

    # Binary search for the LARGEST scale that fits. Monotone in scale, so ~9 encodes pin it
    # to ~0.2% precision — and unlike a one-way estimate it cannot undershoot on
    # hard-to-compress content (noise, photos), where encoded size does not track pixel
    # count the way a single probe predicts.
    lo, hi = 0.0, 1.0
    best = None
    for _ in range(9):
        mid = (lo + hi) / 2
        cand, w, h = enc(mid)
        if b64_len(len(cand)) <= budget:
            best = (cand, w, h)
            lo = mid
        else:
            hi = mid
        if min(w, h) <= 8 and best is None:
            break

    if best is not None:
        cand, w, h = best
        return (
            cand,
            (
                f" [shrunk to {len(cand) // 1024}KB ({w}x{h}, q{q}) to fit this "
                f"client's {cap}KB tool-output cap — use region=[x,y,w,h] for a "
                f"crisp zoom]"
            ),
            (w, h),
        )

    # Nothing fits, even at the floor: send the smallest we produced and say so, rather
    # than silently shipping something the client will drop.
    cand, w, h = enc(max(8 / max(ow, 1), 8 / max(oh, 1)))
    return (
        cand,
        (
            f" [WARNING: {b64_len(len(cand)) // 1024}KB still exceeds the {cap}KB cap; "
            f"the client may drop this image — use region=[x,y,w,h] to capture less]"
        ),
        (w, h),
    )
