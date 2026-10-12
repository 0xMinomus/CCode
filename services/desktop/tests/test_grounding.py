"""Unit tests for grounding pure helpers + the lazy-init lock contract.

The headline test is the concurrent-init race: the patches at grounding.py wrap
_OCR / _OMNI_SESS first-use in double-checked locks, so 20+ concurrent annotate-style
callers must each see EXACTLY one constructed engine. The fake backends below sleep
inside __init__ to widen the race window, so an unlocked implementation would build
the engine multiple times and the test would fail."""

import os
import threading
import time
import types

import numpy as np
import pytest

import grounding


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------
def test_iou_identical_is_one():
    assert grounding._iou([0, 0, 10, 10], [0, 0, 10, 10]) == 1.0


def test_iou_disjoint_is_zero():
    assert grounding._iou([0, 0, 10, 10], [50, 50, 60, 60]) == 0.0


def test_iou_partial_overlap():
    # 10x10 each = 100; overlap 5x5 = 25; union = 100 + 100 - 25 = 175.
    assert grounding._iou([0, 0, 10, 10], [5, 5, 15, 15]) == pytest.approx(25 / 175)


def test_iou_handles_degenerate_box():
    assert grounding._iou([0, 0, 0, 0], [0, 0, 10, 10]) == 0.0


def test_contains_uses_inner_center():
    assert grounding._contains([0, 0, 100, 100], [40, 40, 60, 60]) is True
    assert grounding._contains([0, 0, 100, 100], [120, 40, 140, 60]) is False


def test_quad_to_bbox_axis_aligned_quad():
    assert grounding._quad_to_bbox([[1, 2], [9, 2], [9, 8], [1, 8]]) == [1, 2, 9, 8]


def test_quad_to_bbox_handles_floats():
    bbox = grounding._quad_to_bbox([[0.4, 0.4], [9.6, 0.4], [9.6, 9.6], [0.4, 9.6]])
    assert bbox == [0, 0, 10, 10]


def test_merge_drops_overlapping_later():
    a = [{"bbox": [0, 0, 10, 10]}]
    b = [{"bbox": [1, 1, 11, 11]}]  # IoU > 0.6, dropped
    assert grounding.merge(a, b, iou=0.6) == a


def test_merge_keeps_when_iou_threshold_unmet():
    a = [{"bbox": [0, 0, 10, 10]}]
    b = [{"bbox": [1, 1, 11, 11]}]
    assert len(grounding.merge(a, b, iou=0.95)) == 2


def test_merge_skips_elements_without_bbox():
    a = [{"label": "no bbox"}, {"bbox": [0, 0, 10, 10]}]
    assert grounding.merge(a) == [a[1]]


def test_annotate_degraded_path_returns_unchanged_image(monkeypatch):
    monkeypatch.setattr(grounding, "_HAVE_OCR", False)
    monkeypatch.setattr(grounding, "_HAVE_CV", False)
    monkeypatch.setattr(grounding, "_HAVE_OMNI", False)
    arr = np.zeros((20, 20, 3), dtype=np.uint8)
    img, elements = grounding.annotate(arr)
    assert elements == []
    assert img.size == (20, 20) and img.mode == "RGB"


# ---------------------------------------------------------------------------
# Concurrent lazy-init contract (the patched race)
# ---------------------------------------------------------------------------
class _CountingOCR:
    """Stand-in for RapidOCR that counts constructions and sleeps to widen the race."""

    count = 0
    _lock = threading.Lock()

    def __init__(self, *args, **kwargs):
        # Must accept kwargs: ocr_boxes constructs RapidOCR(params={...}) to cap ONNX
        # threads. A no-arg stub raises TypeError, which ocr_boxes swallows, and the
        # test then silently measures nothing (count==0) instead of the race.
        self.kwargs = kwargs
        with _CountingOCR._lock:
            _CountingOCR.count += 1
        time.sleep(0.05)  # widen the window so an unlocked impl will lose the race

    def __call__(self, *_a, **_kw):
        return None


class _CountingSession:
    """Stand-in for onnxruntime.InferenceSession."""

    count = 0
    _lock = threading.Lock()

    def __init__(self, *_a, **_kw):
        with _CountingSession._lock:
            _CountingSession.count += 1
        time.sleep(0.05)

    def run(self, *_a, **_kw):
        return [np.zeros((1, 5, 0), dtype=np.float32)]

    def get_inputs(self):
        return [types.SimpleNamespace(name="x")]


@pytest.fixture
def fake_backends(monkeypatch):
    """Wire grounding to fake backends and reset singletons + counters per-test."""
    _CountingOCR.count = 0
    _CountingSession.count = 0
    fake_ort = types.SimpleNamespace(
        SessionOptions=lambda: types.SimpleNamespace(
            intra_op_num_threads=0, inter_op_num_threads=0
        ),
        InferenceSession=_CountingSession,
    )
    monkeypatch.setattr(grounding, "_HAVE_OCR", True)
    monkeypatch.setattr(grounding, "_HAVE_OMNI", True)
    monkeypatch.setattr(grounding, "RapidOCR", _CountingOCR)
    monkeypatch.setattr(grounding, "_ort", fake_ort)
    monkeypatch.setattr(grounding, "_OCR", None)
    monkeypatch.setattr(grounding, "_OMNI_SESS", None)


def test_lazy_ocr_init_is_single_under_concurrent_callers(fake_backends):
    bgr = np.zeros((4, 4, 3), dtype=np.uint8)
    threads = [
        threading.Thread(target=lambda: grounding.ocr_boxes(bgr)) for _ in range(20)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert _CountingOCR.count == 1, f"race built OCR {_CountingOCR.count} times"


def test_lazy_omni_session_is_single_under_concurrent_callers(fake_backends):
    threads = [threading.Thread(target=grounding._omni_session) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert _CountingSession.count == 1, (
        f"race built OmniParser {_CountingSession.count} times"
    )


def test_warmup_initialises_each_backend_at_most_once(fake_backends):
    threads = [threading.Thread(target=grounding.warmup) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert _CountingOCR.count == 1
    assert _CountingSession.count == 1


def test_ocr_and_omni_locks_are_independent(fake_backends):
    """If we had used ONE shared lock, an OCR cold-start (~50ms) would serialise an
    OmniParser cold-start. With separate locks both inits run concurrently — total
    wall time should approach 50ms, not 100ms."""
    bgr = np.zeros((4, 4, 3), dtype=np.uint8)
    started = time.monotonic()
    t1 = threading.Thread(target=lambda: grounding.ocr_boxes(bgr))
    t2 = threading.Thread(target=grounding._omni_session)
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    elapsed = time.monotonic() - started
    assert elapsed < 0.09, f"OCR and OmniParser init serialised (took {elapsed:.3f}s)"


def test_ocr_engine_gets_a_bounded_thread_cap(monkeypatch):
    """onnxruntime's default (-1 = one thread per core) makes its threads spin-wait:
    measured 610 CPU-SECONDS for a single uncached 4K read, and SLOWER in wall-clock than
    6 threads. Regressing this to -1/unset is a 2x wall and 4x CPU loss, so pin it."""
    import grounding as g

    captured = {}

    class _Spy:
        def __init__(self, *a, **kw):
            captured.update(kw.get("params") or {})

        def __call__(self, *a, **kw):
            return None

    monkeypatch.setattr(g, "_HAVE_OCR", True)
    monkeypatch.setattr(g, "RapidOCR", _Spy)
    monkeypatch.setattr(g, "_OCR", None)
    g.ocr_boxes(np.zeros((8, 8, 3), dtype=np.uint8))

    intra = captured.get("EngineConfig.onnxruntime.intra_op_num_threads")
    assert intra is not None, "OCR engine must pin intra_op threads, not inherit -1"
    assert 1 <= intra <= 8, f"thread cap {intra} outside the measured sane band"
    assert captured.get("EngineConfig.onnxruntime.inter_op_num_threads") == 1


def test_omni_and_ocr_share_one_thread_cap():
    """One knob for both ONNX consumers — divergence is how OCR ended up uncapped while
    OmniParser was already limited to 6."""
    import grounding as g

    assert g._CPU_THREADS == int(os.environ.get("MCP_SCREEN_CPU_THREADS", "6"))
    assert g.diag()["cpu_threads"] == g._CPU_THREADS
