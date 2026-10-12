"""Client tool-output budget fitting — runs EVERYWHERE, including headless CI.

budget.py imports only stdlib + Pillow, so unlike capture.py it needs no gi/GStreamer/D-Bus
and conftest never stubs it. That is the entire point of the split: this logic previously
lived in capture.py and therefore had ZERO CI coverage, because a headless run substitutes a
stub `capture` module that has none of these attributes.

Grok Build truncates an MCP tool result at 20KB. A base64 image cut mid-string fails its
integrity check and the whole image is dropped, so the model sees NOTHING — strictly worse
than a low-fidelity image.
"""

import base64
import io

import pytest
from PIL import Image

import budget


def _downscale(img, w, h):
    """Stand-in for capture._downscale (cv2 INTER_AREA with a PIL fallback)."""
    return img.resize((w, h), Image.Resampling.LANCZOS)


def _lossless(img):
    b = io.BytesIO()
    img.convert("RGB").save(b, format="WEBP", lossless=True, method=0, quality=20)
    return b.getvalue()


def _shot(w=2576, h=1449):
    """Structured content, not noise — noise is incompressible and unrepresentative."""
    img = Image.new("RGB", (w, h), (18, 18, 22))
    for y in range(0, h, 40):
        for x in range(0, w, 160):
            img.paste((200, 200, 210), (x, y, min(x + 120, w), min(y + 18, h)))
    return img


@pytest.fixture
def restore_cap():
    prev = budget.MAX_OUT_KB
    yield
    budget.MAX_OUT_KB = prev


# --- the no-op path (what Claude takes) ------------------------------------------------


def test_uncapped_is_byte_identical_noop(restore_cap):
    budget.MAX_OUT_KB = 0
    img = _shot()
    raw = _lossless(img)
    out, note, _size = budget.fit_to_budget(img, raw, _downscale)
    assert out is raw, "uncapped must return the SAME object, not a re-encode"
    assert note == ""


def test_payload_already_under_cap_is_untouched(restore_cap):
    budget.MAX_OUT_KB = 20
    img = _shot(400, 200)
    raw = _lossless(img)
    assert budget.b64_len(len(raw)) <= 20 * 1024 - budget.ENVELOPE_BYTES
    out, note, _size = budget.fit_to_budget(img, raw, _downscale)
    assert out is raw and note == ""


def test_explicit_cap_argument_overrides_module_state(restore_cap):
    budget.MAX_OUT_KB = 0
    img = _shot()
    raw = _lossless(img)
    out, note, _size = budget.fit_to_budget(img, raw, _downscale, max_out_kb=20)
    assert out is not raw and "shrunk" in note


# --- the fitting path -----------------------------------------------------------------


def test_oversized_payload_is_fitted_and_still_decodes(restore_cap):
    budget.MAX_OUT_KB = 20
    img = _shot()
    raw = _lossless(img)
    assert budget.b64_len(len(raw)) > 20 * 1024, "fixture must exceed the cap"

    out, note, _size = budget.fit_to_budget(img, raw, _downscale)

    assert budget.b64_len(len(out)) <= 20 * 1024 - budget.ENVELOPE_BYTES
    assert "shrunk" in note and "region=" in note, (
        "must tell the agent how to get detail"
    )
    Image.open(io.BytesIO(out)).load()  # a truncated image would raise here


def test_fit_is_guaranteed_even_for_incompressible_input(restore_cap):
    """Noise is the adversarial case: a downscale can encode LARGER than predicted, so the
    estimator alone is not enough and the halving fallback must still land under the cap.
    An earlier implementation gave up after 4 corrections and returned 23040 > 18432 —
    exactly the over-budget payload this function exists to prevent."""
    budget.MAX_OUT_KB = 20
    img = Image.effect_noise((2576, 1449), 90).convert("RGB")
    out, _, _size = budget.fit_to_budget(img, _lossless(img), _downscale)
    assert budget.b64_len(len(out)) <= 20 * 1024 - budget.ENVELOPE_BYTES
    Image.open(io.BytesIO(out)).load()


def test_fitted_payload_uses_the_budget_rather_than_collapsing(restore_cap):
    """A fixed ladder overshot the cliff and wasted half the budget on a needlessly blurry
    image. The analytic estimate should land near the cap, not far under it."""
    budget.MAX_OUT_KB = 20
    img = _shot()
    out, _, _size = budget.fit_to_budget(img, _lossless(img), _downscale)
    usable = 20 * 1024 - budget.ENVELOPE_BYTES
    assert budget.b64_len(len(out)) > usable * 0.4


def test_tiny_cap_degrades_instead_of_raising(restore_cap):
    """A cap smaller than the envelope reserve must not crash or loop forever."""
    budget.MAX_OUT_KB = 1
    img = _shot()
    out, note, _size = budget.fit_to_budget(img, _lossless(img), _downscale)
    assert isinstance(out, bytes) and out
    assert note == "" or "WARNING" in note or "shrunk" in note


def test_downscaler_is_injected_not_imported(restore_cap):
    """budget.py must never reach for capture's downscaler itself — that would drag in
    gi/GStreamer and put this logic back outside CI's reach."""
    budget.MAX_OUT_KB = 20
    calls = []

    def spy(img, w, h):
        calls.append((w, h))
        return img.resize((w, h), Image.Resampling.LANCZOS)

    img = _shot()
    budget.fit_to_budget(img, _lossless(img), spy)
    assert calls, "the injected downscaler must actually be used"


# --- arithmetic -----------------------------------------------------------------------


def test_b64_len_matches_real_base64():
    for n in (0, 1, 2, 3, 4, 100, 1023, 4096, 900_000):
        assert budget.b64_len(n) == len(base64.b64encode(b"x" * n))


def test_budget_module_imports_without_gi():
    """The load-bearing property: importable with no desktop stack."""
    import sys

    assert "gi" not in getattr(budget, "__dict__", {})
    src = open(budget.__file__).read()
    for banned in ("import gi", "import state", "import capture", "gi.repository"):
        assert banned not in src, f"budget.py must not reference {banned!r}"
    assert sys.modules.get("budget") is budget


# --- regressions from the max code review ---------------------------------------------


def test_fit_reports_the_size_actually_encoded(restore_cap):
    """The caller restates its view->desktop transform from this size. Returning the
    pre-shrink size shipped a 526x296 image while advertising 2576x1449 / scale 0.6708,
    so every view-space click missed by ~4.9x and view_id could not detect it."""
    budget.MAX_OUT_KB = 20
    img = _shot()
    out, _, size = budget.fit_to_budget(img, _lossless(img), _downscale)
    assert size == Image.open(io.BytesIO(out)).size, (
        "reported size must equal the encoded image"
    )
    assert size != img.size, "fixture must actually shrink"


def test_noop_reports_original_size(restore_cap):
    budget.MAX_OUT_KB = 0
    img = _shot(400, 200)
    raw = _lossless(img)
    out, note, size = budget.fit_to_budget(img, raw, _downscale)
    assert out is raw and note == "" and size == img.size


def test_reserve_bytes_shrinks_the_usable_budget(restore_cap):
    """An annotate=true response can carry one text line per detected element. If the
    reserve stays at the 2KB default, the image fits but the COMBINED result does not."""
    budget.MAX_OUT_KB = 20
    img = _shot()
    raw = _lossless(img)
    small, _, _ = budget.fit_to_budget(img, raw, _downscale, reserve_bytes=15000)
    big, _, _ = budget.fit_to_budget(img, raw, _downscale, reserve_bytes=512)
    assert budget.b64_len(len(small)) <= 20 * 1024 - 15000
    assert budget.b64_len(len(small)) < budget.b64_len(len(big))


def test_reserve_bytes_has_a_floor(restore_cap):
    """A caller passing 0 must not get the whole cap and overflow the envelope."""
    budget.MAX_OUT_KB = 20
    img = _shot()
    out, _, _ = budget.fit_to_budget(img, _lossless(img), _downscale, reserve_bytes=0)
    assert budget.b64_len(len(out)) <= 20 * 1024 - 512


def test_tiny_cap_still_shrinks_instead_of_shipping_the_full_payload(restore_cap):
    """A cap at or below the envelope reserve made `budget` go negative, and the early
    `budget <= 0` return then shipped the FULL over-cap payload unshrunk — the exact drop
    this module exists to prevent. The usable budget is now floored at cap/4."""
    budget.MAX_OUT_KB = 2  # == ENVELOPE_BYTES, so cap - reserve == 0
    img = _shot()
    raw = _lossless(img)
    out, note, size = budget.fit_to_budget(img, raw, _downscale)
    assert out is not raw, "must not return the full payload for a tiny cap"
    assert budget.b64_len(len(out)) < budget.b64_len(len(raw))
    assert size != img.size
    Image.open(io.BytesIO(out)).load()


def test_budget_utilisation_holds_for_incompressible_content(restore_cap):
    """The one-way estimate undershot to 8% of the allowed budget on noise, shipping a
    needlessly unreadable image. The binary search must use most of the cap regardless of
    how well the content compresses."""
    budget.MAX_OUT_KB = 20
    usable = 20 * 1024 - budget.ENVELOPE_BYTES
    for label, img in (
        ("noise", Image.effect_noise((2576, 1449), 90).convert("RGB")),
        ("structured", _shot()),
    ):
        out, _, _ = budget.fit_to_budget(img, _lossless(img), _downscale)
        got = budget.b64_len(len(out))
        assert got <= usable, f"{label} exceeded the cap"
        assert got > usable * 0.6, (
            f"{label} used only {100 * got // usable}% of the budget"
        )


def test_malformed_env_does_not_crash_at_import(monkeypatch):
    """A bare int() on the env var took the whole server down at import time."""
    for bad in ("not-a-number", "", "12.5", "-3"):
        monkeypatch.setenv("MCP_SCREEN_MAX_OUTPUT_KB", bad)
        assert isinstance(budget._env_int("MCP_SCREEN_MAX_OUTPUT_KB", 0), int)
    monkeypatch.setenv("MCP_SCREEN_MAX_OUTPUT_KB", "-5")
    assert budget._env_int("MCP_SCREEN_MAX_OUTPUT_KB", 0) >= 0


def test_per_call_cap_override_beats_module_state(restore_cap):
    """Multi-image handlers (screen_tour) must be able to divide the result-wide cap across
    the images they emit. Fitting each image to the FULL cap ships N x cap and the client
    truncates the whole result."""
    budget.MAX_OUT_KB = 20
    img = _shot()
    raw = _lossless(img)
    whole, _, _ = budget.fit_to_budget(img, raw, _downscale)
    split, _, _ = budget.fit_to_budget(img, raw, _downscale, max_out_kb=5)
    assert budget.b64_len(len(split)) <= 5 * 1024
    assert budget.b64_len(len(split)) < budget.b64_len(len(whole))
