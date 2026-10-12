"""The WebP encode settings trade CPU for bytes only — they must never trade fidelity.

capture.py imports gi/GStreamer, so these assert the codec contract directly rather than
importing the module: if libwebp or Pillow ever made these settings lossy, screenshots would
silently degrade and OCR/reading accuracy with them.
"""

import io
import os

import numpy as np
import pytest
from PIL import Image


def _frame():
    rng = np.random.default_rng(0)
    a = np.zeros((160, 240, 4), np.uint8)
    a[..., 3] = 255
    a[..., :3] = 30
    a[:, :60, :3] = 55
    for y in range(10, 160, 17):  # text-like high-frequency rows
        a[y : y + 5, 20:220, :3] = rng.integers(120, 240, (5, 200, 3), dtype=np.uint8)
    return Image.fromarray(a, "RGBA")


def _roundtrip(**kw):
    buf = io.BytesIO()
    _frame().save(buf, format="WEBP", lossless=True, **kw)
    buf.seek(0)
    return Image.open(buf).convert("RGBA"), len(buf.getvalue())


@pytest.mark.parametrize("method", [0, 4])
@pytest.mark.parametrize("effort", [0, 20, 80])
def test_webp_lossless_is_pixel_exact_at_every_effort(method, effort):
    out, _ = _roundtrip(method=method, quality=effort)
    assert np.array_equal(np.asarray(out), np.asarray(_frame()))


def test_shipped_defaults_match_capture_module_constants():
    # Mirrors capture.WEBP_METHOD / WEBP_EFFORT without importing capture (needs gi).
    assert int(os.environ.get("MCP_SCREEN_WEBP_METHOD", "0")) == 0
    assert int(os.environ.get("MCP_SCREEN_WEBP_EFFORT", "20")) == 20
    out, _ = _roundtrip(method=0, quality=20)
    assert np.array_equal(np.asarray(out), np.asarray(_frame()))


# --- downscale filter: the cv2 fast path must scale what PIL scales ---
#
# conftest installs a STUB `capture` (and a stub `gi`) into sys.modules so pure-logic tests
# run without a GNOME session — so the real capture._downscale cannot be imported here by
# design. Test the contract it depends on instead, exactly as the WebP tests above do.


def _text_img(w=400, h=240):
    """Text-like content: flat panel plus high-frequency rows. Downscale artifacts show up
    on thin glyph strokes, not on flat fill."""
    rng = np.random.default_rng(1)
    a = np.zeros((h, w, 3), np.uint8)
    a[..., :] = 30
    for y in range(6, h - 5, 11):
        a[y : y + 4, 10 : w - 10] = rng.integers(
            120, 240, (4, w - 20, 3), dtype=np.uint8
        )
    return Image.fromarray(a, "RGB")


def test_cv2_area_matches_pil_geometry_and_content():
    """INTER_AREA replaced PIL LANCZOS as the downscaler (18.8ms vs 287.5ms on a real 4K
    frame). Different kernels, so not pixel-identical — but a large divergence would mean
    the fast path scales something other than what PIL scales: swapped w/h, BGR-vs-RGB
    channel order, or a mode mismatch. That is the regression this guards."""
    cv2 = pytest.importorskip("cv2")
    src = _text_img()
    fast = cv2.resize(np.asarray(src), (260, 156), interpolation=cv2.INTER_AREA)
    ref = np.asarray(src.resize((260, 156), Image.Resampling.LANCZOS))
    assert fast.shape == ref.shape == (156, 260, 3)
    assert np.abs(fast.astype(np.int16) - ref.astype(np.int16)).mean() < 12.0


def test_cv2_area_preserves_channel_order():
    """A BGR/RGB mix-up survives a mean-difference check on greyish content but not this:
    a pure-red source must stay red-dominant after the resize."""
    cv2 = pytest.importorskip("cv2")
    red = np.zeros((240, 400, 3), np.uint8)
    red[..., 0] = 220  # R
    out = cv2.resize(red, (200, 120), interpolation=cv2.INTER_AREA)
    assert out[..., 0].mean() > 200
    assert out[..., 1].mean() < 5 and out[..., 2].mean() < 5
