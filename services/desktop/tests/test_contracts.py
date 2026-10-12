"""Contract guards for the three bug CLASSES that actually shipped this cycle.

Each of these is a pure unit test — no desktop, no portal, milliseconds — and each one
would have caught a defect that instead escaped to production and was found later by an
adversarial review. They assert CONTRACTS (what the caller is promised), not that a
function returned without raising, which is the distinction that failed us.
"""

import ast
import base64
import io
import pathlib
from typing import Any, cast

import pytest
from PIL import Image

import budget

ROOT = pathlib.Path(__file__).resolve().parent.parent


# --- class 1: the shipped image must match the advertised transform -------------------


@pytest.mark.parametrize(
    "dw,dh,cap",
    [
        (3840, 2160, 20),
        (3840, 2160, 0),
        (2576, 1449, 20),
        (1920, 1080, 5),
        (800, 600, 0),
    ],
)
def test_advertised_scale_equals_the_scale_of_the_bytes_actually_shipped(dw, dh, cap):
    """THE 5x BUG. encode_store stamped SESSION["view"]["scale"] and the response text
    BEFORE the budget fitter re-encoded the image smaller, so a client received a 526x296
    image while being told it was 2576x1449 at scale 0.6708. Every view-space click was
    then divided by the wrong scale and missed by that ratio; view_id could not catch it
    because the id never changed.

    The only honest assertion is on the BYTES THAT LEAVE: decode them, and require the
    advertised scale to equal shipped_width / desktop_width.
    """
    img = _synthetic(dw, dh)
    raw = _lossless(img)
    out, note, (fw, fh) = budget.fit_to_budget(
        img, raw, _downscale, max_out_kb=cap or None
    )

    shipped = Image.open(io.BytesIO(out)).size
    assert (fw, fh) == shipped, (
        f"reported size {(fw, fh)} != decoded size {shipped} — the caller restates its "
        "view transform from the reported size, so a mismatch here IS the 5x bug"
    )

    scale = fw / dw
    if cap and note:
        assert scale < 1.0, "a fitted image must advertise a reduced scale"
    # A click at the centre of the shipped image must map back to the desktop centre.
    assert abs((shipped[0] / 2) / scale - dw / 2) < 2.0


def test_noop_path_reports_the_untouched_size():
    """Claude's path. If the no-op ever started re-encoding, every Claude click would
    silently shift — so pin that it returns the same object AND the same size."""
    img = _synthetic(800, 600)
    raw = _lossless(img)
    out, note, size = budget.fit_to_budget(img, raw, _downscale, max_out_kb=None)
    assert out is raw and note == "" and size == img.size


def test_base64_of_a_fitted_image_still_decodes():
    """The whole failure mode being defended against is a client receiving base64 that is
    cut mid-string. Round-trip through base64 exactly as the MCP layer does."""
    img = _synthetic(2576, 1449)
    out, _, _ = budget.fit_to_budget(img, _lossless(img), _downscale, max_out_kb=20)
    blob = base64.b64decode(base64.b64encode(out).decode())
    Image.open(io.BytesIO(blob)).load()


# --- class 2: a perf fix must apply to the SHIPPED path -------------------------------


def test_ocr_engine_has_exactly_one_construction_site():
    """THE INERT-PERF-FIX BUG. The ONNX thread cap was applied in ocr_boxes(), but
    warmup() built RapidOCR() separately with no params and — running first at startup —
    won the double-checked init. The cap therefore never applied in the live server, while
    a benchmark that happened to call ocr_boxes() first measured the capped path and
    reported a 2.2x win that production never saw.

    Static guard: RapidOCR may be constructed in exactly ONE place.
    """
    src = (ROOT / "grounding.py").read_text()
    tree = ast.parse(src)
    sites = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "RapidOCR"
    ]
    assert len(sites) == 1, (
        f"RapidOCR constructed at {len(sites)} sites (lines "
        f"{[n.lineno for n in sites]}) — every engine must come from one factory, or a "
        "config change silently misses whichever path runs first"
    )


def test_warmup_and_ocr_share_the_one_factory(monkeypatch):
    """Behavioural half of the same guard: warmup() and ocr_boxes() must both obtain the
    engine from _build_ocr, so whatever the factory configures applies to both."""
    import grounding as g

    built = []

    def spy():
        built.append(1)
        return object()

    monkeypatch.setattr(g, "_HAVE_OCR", True)
    monkeypatch.setattr(g, "_HAVE_OMNI", False)
    monkeypatch.setattr(g, "_build_ocr", spy)
    monkeypatch.setattr(g, "_OCR", None)

    g.warmup()
    assert built, "warmup must use the shared factory, not construct its own engine"
    warmed = g._OCR
    g.ocr_boxes(__import__("numpy").zeros((8, 8, 3), dtype="uint8"))
    assert g._OCR is warmed, "ocr_boxes must reuse warmup's engine, not build a second"
    assert len(built) == 1, f"factory ran {len(built)}x — two engines, two configs"


def test_thread_cap_is_shared_by_both_onnx_consumers():
    import grounding as g

    assert g._CPU_THREADS >= 1
    assert g.diag()["cpu_threads"] == g._CPU_THREADS


# --- class 3: CI and local must run the SAME code -------------------------------------


def test_conftest_exposes_which_tier_ran():
    """THE 4-RED-COMMITS BUG. conftest runs different code depending on whether the real
    gi stack imports, and silent skips made the divergence invisible: green locally, red in
    CI, four commits running. The tier must at minimum be introspectable so a CI job can
    assert which one it exercised."""
    import conftest

    assert hasattr(conftest, "REAL_STACK")
    assert isinstance(conftest.REAL_STACK, bool)


def test_gi_free_modules_stay_gi_free():
    """budget.py and x11capture.py are gi-free ON PURPOSE so CI executes them for real
    rather than against a stub — that is how the budget logic ended up with zero CI
    coverage while it lived in capture.py.

    reliability.py is deliberately NOT in this list: it imports `state` for stage timing,
    and state opens a D-Bus session bus at import. It takes its grabber injected, which is
    a different (and also good) property — but it is not import-clean without gi, and
    claiming otherwise here would be a test asserting a comfortable fiction."""
    for mod in ("budget", "x11capture"):
        src = (ROOT / f"{mod}.py").read_text()
        for banned in ("import gi", "gi.repository", "import state", "import capture"):
            assert banned not in src, f"{mod}.py must stay gi-free (found {banned!r})"


# --- helpers ---------------------------------------------------------------------------


def _downscale(img, w, h):
    return img.resize((w, h), Image.Resampling.LANCZOS)


def _lossless(img):
    b = io.BytesIO()
    img.convert("RGB").save(b, format="WEBP", lossless=True, method=0, quality=20)
    return b.getvalue()


def _synthetic(w, h):
    img = Image.new("RGB", (w, h), (18, 18, 22))
    for y in range(0, h, 40):
        for x in range(0, w, 160):
            img.paste((200, 200, 210), (x, y, min(x + 120, w), min(y + 18, h)))
    return img


def test_v6_model_type_is_requested_explicitly(monkeypatch):
    """RapidOCR 3.9.2 defaults model_type to "small", and v6_small measured SLOWER than the
    v4 baseline we are replacing (38.5s CPU vs 24.8s). So a plain version bump is a
    regression unless TINY is named explicitly. Pin that it always is."""
    import types

    import grounding as g

    fake = cast(Any, types.ModuleType("rapidocr"))
    fake.OCRVersion = types.SimpleNamespace(PPOCRV6="v6")
    fake.ModelType = types.SimpleNamespace(TINY="tiny", SMALL="small")
    monkeypatch.setitem(__import__("sys").modules, "rapidocr", fake)
    monkeypatch.delenv("MCP_SCREEN_OCR_MODEL", raising=False)

    p = g._v6_tiny_params()
    assert p["Det.model_type"] == "tiny", "TINY must be explicit; the default is small"
    assert p["Rec.model_type"] == "tiny"
    assert p["Det.ocr_version"] == "v6" and p["Rec.ocr_version"] == "v6"

    monkeypatch.setenv("MCP_SCREEN_OCR_MODEL", "small")
    assert g._v6_tiny_params()["Rec.model_type"] == "small", "override must be honoured"


def test_v6_params_degrade_on_older_rapidocr(monkeypatch):
    """v6 first appears in rapidocr 3.9.2. On anything older this must return {} so the
    engine keeps working defaults rather than raising at construction."""
    import types

    import grounding as g

    fake = cast(Any, types.ModuleType("rapidocr"))  # no OCRVersion/ModelType attributes
    monkeypatch.setitem(__import__("sys").modules, "rapidocr", fake)
    assert g._v6_tiny_params() == {}


def test_appsink_drop_property_is_chosen_at_runtime():
    """THE LTS-EXCLUSION BUG. The pipeline hard-coded `leaky-type=downstream`, making
    GStreamer >= 1.28 a silent hard requirement. Measured on a real GNOME/X11 VM
    (Ubuntu 24.04, GStreamer 1.24.2): appsink has `drop` but NOT `leaky-type`, and the
    pipeline failed to parse outright — "no property leaky-type in element appsink".
    1.28 exposes BOTH, so `drop` was never actually removed.

    Guard the source, not the runtime: the pipeline string must not name either property
    literally, and the chooser must offer both spellings."""
    src = (ROOT / "capture.py").read_text()
    launch = src[src.index("Gst.parse_launch(") : src.index("Gst.parse_launch(") + 500]
    assert "leaky-type=downstream" not in launch, (
        "the pipeline must not hard-code leaky-type — it excludes GStreamer < 1.28"
    )
    assert "_appsink_drop_prop()" in launch, "the property must be chosen at runtime"
    chooser = src[src.index("def _appsink_drop_prop") :][:1200]
    assert "leaky-type=downstream" in chooser and "drop=true" in chooser, (
        "the chooser must offer BOTH spellings"
    )
