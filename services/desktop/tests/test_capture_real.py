"""Tests that execute the REAL capture path — no stubs.

Everything here was unreachable while conftest force-installed a stub `capture`, which is
why each of these bugs shipped and was caught by driving the desktop instead:

  * `_sample_to_rgb` returned an ndarray ALIASING the GstBuffer mapping and marked
    read-only, so the alpha write died with "assignment destination is read-only" and the
    data was a use-after-free once unmap ran.
  * a rename left one `_sample_to_rgba` call site behind in `_nudge_prime`.
  * the view transform is the click-accuracy invariant and had no round-trip test at all.

Skipped automatically where the real gi/GStreamer stack is absent (CI).
"""

import numpy as np
import pytest

import conftest

pytestmark = pytest.mark.skipif(
    not conftest.REAL_STACK, reason="needs real gi/GStreamer + session bus"
)


def _sample(w, h, pad=0, fill=None):
    """Build a genuine GstSample of RGB pixels, optionally with row padding so the stride
    trim in _sample_to_rgb is actually exercised."""
    from gi.repository import Gst

    stride = w * 3 + pad
    buf = bytearray(stride * h)
    for y in range(h):
        for x in range(w):
            r, g, b = fill(x, y) if fill else (x % 256, y % 256, (x + y) % 256)
            o = y * stride + x * 3
            buf[o], buf[o + 1], buf[o + 2] = r, g, b
    gbuf = Gst.Buffer.new_wrapped(bytes(buf))
    caps = Gst.Caps.from_string(f"video/x-raw,format=RGB,width={w},height={h}")
    return Gst.Sample.new(gbuf, caps, None, None)


def test_sample_to_rgb_decodes_exact_pixels():
    import capture

    w, h = 8, 5
    gw, gh, arr = capture._sample_to_rgb(_sample(w, h))
    assert (gw, gh) == (w, h)
    assert arr.shape == (h, w, 3)
    for y in range(h):
        for x in range(w):
            assert tuple(arr[y, x]) == (x % 256, y % 256, (x + y) % 256)


def test_sample_to_rgb_honours_row_padding():
    """A padded stride must be trimmed, not reshaped straight through — otherwise every row
    after the first is offset and the image shears."""
    import capture

    w, h = 7, 4
    _, _, arr = capture._sample_to_rgb(_sample(w, h, pad=13))
    for y in range(h):
        for x in range(w):
            assert tuple(arr[y, x]) == (x % 256, y % 256, (x + y) % 256)


def test_sample_to_rgb_result_is_writable_and_not_aliasing():
    """THE regression: np.frombuffer on the mapping is read-only, and ascontiguousarray on an
    already-contiguous view is a no-op — so the result aliased a buffer that unmap had
    released. It must be an owned, writable copy."""
    import capture

    _, _, arr = capture._sample_to_rgb(_sample(6, 3))
    assert arr.flags["WRITEABLE"], "must not hand back a read-only view of the mapping"
    assert arr.flags["OWNDATA"], "must own its data, not alias the unmapped GstBuffer"
    arr[0, 0, 0] = 123  # would raise ValueError on the pre-fix array
    assert arr[0, 0, 0] == 123


def test_grab_call_sites_resolve():
    """Guards the rename that ruff caught: every internal reference must exist."""
    import capture

    assert callable(capture._sample_to_rgb)
    assert not hasattr(capture, "_sample_to_rgba")


def test_downscale_size_mode_and_cv2_fallback(monkeypatch):
    import capture
    from PIL import Image

    src = Image.fromarray(
        np.random.default_rng(0).integers(0, 255, (240, 400, 3), dtype=np.uint8), "RGB"
    )
    out = capture._downscale(src, 260, 156)
    assert out.size == (260, 156) and out.mode == "RGB"

    monkeypatch.setattr(capture, "_cv2", None)  # PIL fallback must match geometry
    out2 = capture._downscale(src, 260, 156)
    assert out2.size == (260, 156) and out2.mode == "RGB"


def test_encode_store_view_transform_round_trips():
    """The click-accuracy invariant: a coordinate read off the returned image must map back
    to the desktop pixel it came from. encode_store derives scale from the pre-resize size,
    so a downscale must be reflected in the stored transform, not silently assumed 1:1."""
    import time

    import capture
    import input as inp
    import state
    from PIL import Image

    dw, dh = 3840, 2160
    img = Image.fromarray(np.zeros((dh, dw, 3), np.uint8), "RGB")
    capture.encode_store(img, 3840, 0, "test", time.time())

    v = state.SESSION["view"]
    assert (v["ox"], v["oy"]) == (3840, 0)
    assert (v["dw"], v["dh"]) == (dw, dh)
    assert v["scale"] == pytest.approx(state.MAX_EDGE / dw, rel=1e-6)

    # centre of the delivered image -> centre of the monitor in desktop px
    cx = round(dw * v["scale"]) / 2
    cy = round(dh * v["scale"]) / 2
    gx, gy = inp.resolve_xy({"x": cx, "y": cy, "space": "view"})
    assert gx == pytest.approx(3840 + dw / 2, abs=2)
    assert gy == pytest.approx(dh / 2, abs=2)


# --- server handlers: previously ZERO coverage, validated only by driving the desktop ---


def _server():
    pytest.importorskip("gi")
    import server

    return server


def _capture():
    pytest.importorskip("gi")
    import capture

    return capture


def test_text_match_is_the_real_function_not_a_copy():
    """This test previously RE-IMPLEMENTED _text_match instead of importing it, so it
    could not fail when the shipped function broke — the vacuous-test failure mode.
    OCR renders the same button as 'Launch installer' or 'Launchinstaller' between runs."""
    m = _server()._text_match
    assert m("Launch installer", "Launchinstaller")
    assert m("Launchinstaller", "Launch installer")
    assert m("launch", "Launchinstaller")
    assert not m("Launch installer", "Reboot now")


def test_wanted_excludes_checks_the_caller_never_asked_for():
    """A caller passing only expect_text must not be graded on `changed` — otherwise
    screen_verify reports PARTIAL for a check nobody requested."""
    w = _server()._wanted
    assert w("expect_text", {"expect_text": "x"})
    assert not w("expect_text", {})
    assert w("changed", {})  # expect_change defaults true
    assert not w("changed", {"expect_change": False})


def test_every_registered_handler_is_callable():
    """HANDLERS is the dispatch table; a rename that lands there but not on the function
    is a runtime AttributeError on first use, not an import error."""
    srv = _server()
    assert len(srv.HANDLERS) >= 20
    for name, fn in srv.HANDLERS.items():
        assert name.startswith("screen_"), name
        assert callable(fn), name


def test_every_declared_tool_has_a_handler_and_annotations():
    """A tool in TOOLS with no HANDLERS entry advertises itself and then fails when
    called — the MCP-compliance gap the 88plug checklist calls schema drift."""
    srv = _server()
    declared = {t["name"] for t in srv.TOOLS}
    handled = set(srv.HANDLERS) | {
        "screen_reload"
    }  # reload is special-cased pre-dispatch
    assert declared - handled == set(), f"declared but unhandled: {declared - handled}"
    for t in srv.TOOLS:
        assert t.get("title"), t["name"]
        assert t.get("annotations"), t["name"]
        assert "Returns" in t["description"] or "returns" in t["description"], t["name"]


# --- scope validation: an unvalidated region certified actions against nothing ---

GEO2 = [{"node": 1}, {"node": 2}]
DESK = (7680, 2160)


def _vs(**kw):
    return _capture().validate_scope(GEO2, *DESK, **kw)


def test_monitor_index_out_of_range_names_the_valid_range():
    with pytest.raises(RuntimeError, match=r"monitor 99 does not exist.*valid: 0\.\.1"):
        _vs(monitor=99)
    _vs(monitor=0)
    _vs(monitor=1)  # both real indices must pass


def test_region_entirely_offscreen_raises_instead_of_returning_empty():
    """THE probe finding: an off-screen region used to yield a crop that screen_read_text
    reported as count:0 and screen_verify graded CONFIRMED/changed — certifying an action
    against pixels that do not exist."""
    with pytest.raises(RuntimeError, match="entirely outside the desktop"):
        _vs(region=[99000, 99000, 10, 10])
    with pytest.raises(RuntimeError, match="entirely outside the desktop"):
        _vs(region=[-500, 0, 100, 100])  # fully left of the desktop


def test_region_partially_onscreen_is_allowed():
    """Clamping a partly-visible region is legitimate; only a wholly absent one is an error."""
    _vs(region=[-50, -50, 200, 200])
    _vs(region=[7600, 2100, 500, 500])


def test_region_with_nonpositive_size_raises():
    for bad in ([0, 0, 0, 10], [0, 0, 10, 0], [0, 0, -5, 10]):
        with pytest.raises(RuntimeError, match="non-positive"):
            _vs(region=bad)


def test_validate_scope_is_lenient_when_bounds_unknown():
    """Before the first geo probe W/H are 0; refusing every region then would break the
    cold path that has to capture in order to learn the bounds."""
    _capture().validate_scope(GEO2, 0, 0, region=[99000, 99000, 10, 10])
