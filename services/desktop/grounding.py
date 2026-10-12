"""grounding.py — Set-of-Marks UI grounding layer for mcp-screen (v1.2).

Given a screenshot, detect candidate UI elements (text via OCR, icon/widget regions
via classical CV) and return both a copy of the image with numbered red boxes drawn on
it (Set-of-Marks) and a flat element list whose bboxes are in NATIVE image pixels, so a
numbered mark maps 1:1 to a click coordinate.

DEGRADES GRACEFULLY: the optional backends (rapidocr, opencv) are imported lazily at
module load inside try/except. If a backend is missing, it is silently skipped. If no
backend is available at all, `annotate()` returns the image unchanged with an empty
element list — it never raises. This keeps the core server runnable on a box that has
only numpy + Pillow installed.

No imports from server.py / state.py here (avoids circular deps)."""

import os
import threading
from typing import Any, cast

import numpy as np
from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------------------------
# Optional backends — imported lazily and defensively. A failure here must NOT
# prevent the module (and therefore the core server) from importing.
# ---------------------------------------------------------------------------
try:
    import cv2  # type: ignore

    _HAVE_CV = True
except Exception:  # pragma: no cover - depends on host deps
    cv2 = cast(Any, None)
    _HAVE_CV = False

try:
    from rapidocr import RapidOCR  # type: ignore

    _HAVE_OCR = True
except Exception:  # pragma: no cover - depends on host deps
    RapidOCR = cast(Any, None)
    _HAVE_OCR = False

# OmniParser icon_detect (YOLOv8 exported to ONNX) — CPU-only, NO torch. Bundled at
# models/onnx/model.onnx. This is the primary interactable-element detector; the
# classical-CV path is only a fallback when this model/onnxruntime is unavailable.
_OMNI_MODEL = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "models", "onnx", "model.onnx"
)
try:
    import onnxruntime as _ort  # type: ignore

    _HAVE_OMNI = os.path.exists(_OMNI_MODEL)
except Exception:
    _ort = cast(Any, None)
    _HAVE_OMNI = False

# Module-level singletons, lazily constructed on first use. Each heavyweight session
# (OCR, OmniParser ONNX) has its own lock so first-use under concurrent tool calls
# double-checks safely without two threads building two sessions in parallel — and so
# OCR and OmniParser cold-starts can still run in parallel (they're independent).
_OCR = None  # type: ignore
_FONT = None  # type: ignore
_OMNI_SESS = None  # type: ignore
_OCR_LOCK = threading.Lock()
# Shared ONNX thread cap for BOTH the OCR engine and the OmniParser session.
#
# DO NOT set this to the core count, and do not remove it. onnxruntime's default (-1 = one
# thread per core) makes its threads spin-wait rather than progress. Measured on a 24-core
# box, one uncached 4K screen_read_text:
#   threads=auto(24)  55.5s wall   610s CPU   <- default, pathological
#   threads=4         32.2s wall   137s CPU
#   threads=6         25.9s wall   161s CPU   <- knee
#   threads=8         26.9s wall   210s CPU
#   threads=12        33.7s wall   334s CPU
# Past 6 both wall AND CPU get worse. The 610s figure also starved the rest of the
# desktop, so this is a politeness fix as much as a speed one. 6 was already the
# OmniParser default here; OCR simply never got the same cap.
_CPU_THREADS = int(os.environ.get("MCP_SCREEN_CPU_THREADS", "6"))
_SPIN_PATCHED = False
_OMNI_LOCK = threading.Lock()


# ---------------------------------------------------------------------------
# Image normalization helpers
# ---------------------------------------------------------------------------
def _to_pil(image):
    """Accept a PIL.Image | ndarray | path and return an RGB PIL.Image.

    ndarrays are assumed to be RGB (or grayscale). For BGR ndarrays the caller
    should convert first; screenshots in this project flow through Pillow as RGB."""
    if isinstance(image, Image.Image):
        return image.convert("RGB")
    if isinstance(image, np.ndarray):
        arr = image
        if arr.ndim == 2:
            return Image.fromarray(arr).convert("RGB")
        if arr.ndim == 3 and arr.shape[2] == 4:
            return Image.fromarray(arr[:, :, :3]).convert("RGB")
        return Image.fromarray(arr).convert("RGB")
    if isinstance(image, (str, bytes, os.PathLike)):
        return Image.open(image).convert("RGB")
    raise TypeError(f"unsupported image type: {type(image)!r}")


def _pil_to_bgr(pil):
    """RGB PIL.Image -> contiguous BGR uint8 ndarray (the OpenCV / RapidOCR convention)."""
    rgb = np.asarray(pil.convert("RGB"))
    return np.ascontiguousarray(rgb[:, :, ::-1])


def _quad_to_bbox(quad):
    """A detection quad (4 points, possibly nested arrays) -> [x1,y1,x2,y2] ints."""
    pts = np.asarray(quad, dtype=float).reshape(-1, 2)
    x1, y1 = pts[:, 0].min(), pts[:, 1].min()
    x2, y2 = pts[:, 0].max(), pts[:, 1].max()
    return [int(round(x1)), int(round(y1)), int(round(x2)), int(round(y2))]


# ---------------------------------------------------------------------------
# OCR backend
# ---------------------------------------------------------------------------
def _patch_ort_spinning():
    """Turn OFF onnxruntime's intra-op spin-wait for RapidOCR's sessions.

    The thread cap below was a WORKAROUND, not the fix. ORT's threads busy-spin waiting for
    work, and that spin — not the arithmetic — is where the CPU went. Measured on one
    uncached 4K read, whole process tree, identical 118 boxes out of every arm:

        intra_op=-1 (ORT default)     819.9 CPU-s   158.4s wall
        intra_op=6, spinning ON       256.9 CPU-s   154.5s wall   <- the cap alone
        intra_op=6, spinning OFF      110.2 CPU-s   102.2s wall   <- this
        serial floor (intra=1, off)    84.8 CPU-s              (i.e. ~85s is real work)

    So the default burned ~735 CPU-seconds of pure spin. Turning it off is another 2.3x on
    top of the cap AND faster in wall time.

    There is NO environment variable for this: `ORT_DISABLE_SPINNING` does not exist
    (verified against the shipped .so), and `OMP_WAIT_POLICY` applies only to the legacy
    onnxruntime-openmp build. It is only reachable as a session config entry, and RapidOCR
    builds its own SessionOptions from three keys with no hook for the rest — hence the
    monkeypatch. Also do NOT use `session.force_spinning_stop`: it only stops spinning
    after the LAST concurrent Run() returns, and measured no effect here.
    """
    global _SPIN_PATCHED
    if _SPIN_PATCHED:
        return
    try:
        from rapidocr.inference_engine.onnxruntime.main import (  # type: ignore[import-not-found]
            OrtInferSession,
        )
    except Exception:
        return
    orig = OrtInferSession._init_sess_opts

    @staticmethod
    def _patched(cfg):
        so = orig(cfg)
        try:
            so.add_session_config_entry("session.intra_op.allow_spinning", "0")
            so.add_session_config_entry("session.inter_op.allow_spinning", "0")
        except Exception:
            pass
        return so

    OrtInferSession._init_sess_opts = _patched  # type: ignore[method-assign]
    _SPIN_PATCHED = True


def _build_ocr():
    """The ONLY place RapidOCR is constructed. warmup() previously called RapidOCR() with
    no params and, running first at startup, won the double-checked init — so the thread
    cap below never applied in the live server and only showed up in benchmarks that
    happened to call ocr_boxes first. One constructor, no second uncapped path.

    Cap ONNX threads, exactly as _omni_session() does. Left at RapidOCR's default
    (intra_op=-1 -> one thread per core) a single 4K read burned 610 CPU-SECONDS for 55s of
    wall: the threads spin-wait rather than progress, so it was both slower AND starving the
    rest of the desktop. Measured on 24 cores: auto=55.5s wall/610s cpu,
    6 threads=25.9s wall/161s cpu. Fewer threads is faster here."""
    _patch_ort_spinning()
    params = {
        "EngineConfig.onnxruntime.intra_op_num_threads": _CPU_THREADS,
        "EngineConfig.onnxruntime.inter_op_num_threads": 1,
        # Screen text is upright; the angle classifier is ~5% of CPU and pure waste here.
        "Global.use_cls": False,
    }
    params.update(_v6_tiny_params())
    return RapidOCR(params=params)


def _v6_tiny_params():
    """Pin PP-OCRv6 TINY when the installed RapidOCR offers it.

    Measured against the shipped default (v4 mobile) on a synthetic 1600x900 frame of 48
    known UI strings — real labels, paths, shell prompts — at 13/15/18/22px:

        model       CPU     wall   exact match   CER
        v4_mobile   24.8s   3.8s     28/48      0.323   <- what we shipped
        v6_tiny      9.5s   1.0s     32/48      0.313   <- this
        v6_small    38.5s   6.0s     36/48      0.272

    So tiny is 2.6x cheaper AND more accurate here. That is worth stating plainly because
    Baidu's own table reports v6_tiny English at 77.3% vs v6_small 86.3%, which predicted a
    regression on English UI text; on this workload it did not appear. v6_small is the most
    accurate but costs MORE than the v4 baseline, so it is not a default — set
    MCP_SCREEN_OCR_MODEL=small if accuracy matters more than latency.

    TINY must be requested EXPLICITLY: RapidOCR 3.9.2 defaults model_type to "small", so a
    plain version bump silently lands on the slowest option. Params are Enums; passing
    strings raises TypeError. Returns {} on older RapidOCR (v6 first appears in 3.9.2), so
    the engine simply keeps its previous defaults.
    """
    want = os.environ.get("MCP_SCREEN_OCR_MODEL", "tiny").lower()
    try:
        from rapidocr import ModelType, OCRVersion  # type: ignore[import-not-found]

        # getattr, not attribute access: on rapidocr < 3.9.2 these members do not exist at
        # all (the installed 3.8.1 has only PPOCRV4/PPOCRV5), so naming them statically is
        # both a type error and a runtime AttributeError waiting for an older install.
        version = getattr(OCRVersion, "PPOCRV6", None)
        model = getattr(ModelType, "SMALL" if want == "small" else "TINY", None)
        if version is None or model is None:
            return {}
    except Exception:
        return {}
    return {
        "Det.ocr_version": version,
        "Rec.ocr_version": version,
        "Det.model_type": model,
        "Rec.model_type": model,
    }


def ocr_boxes(bgr):
    """Run text detection+recognition on a BGR ndarray.

    Returns a list of {text, bbox:[x1,y1,x2,y2], conf}. Returns [] if OCR is
    unavailable or the engine produced nothing. Never raises."""
    global _OCR
    if not _HAVE_OCR:
        return []
    try:
        if _OCR is None:
            with _OCR_LOCK:  # double-checked: a second concurrent caller must not build a second engine
                if _OCR is None:
                    _OCR = _build_ocr()
        res = _OCR(bgr)
    except Exception:
        return []
    if res is None:
        return []

    out = []
    # RapidOCR v3 returns a RapidOCROutput object with .boxes/.txts/.scores.
    boxes = getattr(res, "boxes", None)
    txts = getattr(res, "txts", None)
    scores = getattr(res, "scores", None)
    if boxes is not None and txts is not None:
        if scores is None:
            scores = [None] * len(txts)
        for quad, text, score in zip(boxes, txts, scores):
            try:
                bbox = _quad_to_bbox(quad)
            except Exception:
                continue
            conf = float(score) if score is not None else 0.0
            out.append({"text": str(text), "bbox": bbox, "conf": conf})
        return out

    # Older versions: tuple-return of [ (quad, text, score), ... ] (possibly
    # wrapped as (result, elapse)).
    try:
        rows: Any = res[0] if isinstance(res, tuple) else res
    except Exception:
        return []
    if not rows:
        return []
    for row in rows:
        try:
            quad, text, score = row[0], row[1], row[2]
            bbox = _quad_to_bbox(quad)
        except Exception:
            continue
        try:
            conf = float(score)
        except Exception:
            conf = 0.0
        out.append({"text": str(text), "bbox": bbox, "conf": conf})
    return out


# ---------------------------------------------------------------------------
# Classical CV backend (icon / widget region proposals)
# ---------------------------------------------------------------------------
def cv_regions(bgr):
    """Propose icon/widget regions from a BGR ndarray via Canny + dilate + contours.

    Returns a list of {label, role, bbox:[x1,y1,x2,y2]}. Returns [] if OpenCV is
    unavailable. Never raises. Filters out tiny, huge and extreme-aspect boxes."""
    if not _HAVE_CV:
        return []
    try:
        g = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(g, 50, 150)
        kernel = np.ones((3, 3), np.uint8)
        dil = cv2.dilate(edges, kernel, iterations=2)
        contours, _ = cv2.findContours(dil, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    except Exception:
        return []

    H, W = bgr.shape[:2]
    img_area = float(H * W)
    min_area = 200.0
    max_area = 0.4 * img_area
    out = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        area = float(w * h)
        if area < min_area or area > max_area:
            continue
        if h <= 0:
            continue
        aspect = w / float(h)
        if aspect < 0.05 or aspect > 20.0:
            continue
        out.append(
            {
                "label": "icon",
                "role": "icon",
                "bbox": [int(x), int(y), int(x + w), int(y + h)],
            }
        )
    return out


# ---------------------------------------------------------------------------
# OmniParser hook (stubbed / optional)
# ---------------------------------------------------------------------------
def _omni_session():
    global _OMNI_SESS
    if _OMNI_SESS is None:
        with _OMNI_LOCK:  # double-checked: avoid two ONNX sessions racing on first call
            if _OMNI_SESS is None:
                so = _ort.SessionOptions()
                so.intra_op_num_threads = _CPU_THREADS
                so.inter_op_num_threads = 1
                _OMNI_SESS = _ort.InferenceSession(
                    _OMNI_MODEL, sess_options=so, providers=["CPUExecutionProvider"]
                )
    return _OMNI_SESS


def diag():
    """Grounding-subsystem health for screen_diag: which backends loaded + whether the
    (lazy) OCR / OmniParser sessions have been warmed yet."""
    return {
        "have_omni": _HAVE_OMNI,
        "have_ocr": _HAVE_OCR,
        "have_cv": _HAVE_CV,
        "omni_model": _OMNI_MODEL,
        "omni_warmed": _OMNI_SESS is not None,
        "ocr_warmed": _OCR is not None,
        "cpu_threads": _CPU_THREADS,
    }


def warmup():
    """Pre-build the OCR + OmniParser sessions so the FIRST annotate() isn't a cold
    multi-second model load (RapidOCR graph build + ONNX session init). Safe to call
    from a background thread at startup; never raises."""
    global _OCR
    try:
        if _HAVE_OMNI:
            _omni_session()  # self-locks via _OMNI_LOCK
    except Exception:
        pass
    try:
        if _HAVE_OCR and _OCR is None:
            with (
                _OCR_LOCK
            ):  # match ocr_boxes()' double-checked init so warmup races safely
                if _OCR is None:
                    _OCR = _build_ocr()
                    _OCR(np.zeros((48, 48, 3), dtype=np.uint8))  # prime det+rec graphs
    except Exception:
        pass


def omni_regions(bgr, conf=0.05, iou=0.45, imgsz=640):
    """OmniParser icon_detect (YOLOv8 single-class, ONNX, CPU) -> interactable boxes.

    Returns [{label:'icon', role:'icon', bbox:[x1,y1,x2,y2], conf}]. Trained on real
    clickable UI elements, so it yields a small clean set (unlike CV contours). Needs
    OpenCV for letterbox/NMS. Returns [] and never raises on any failure."""
    if not _HAVE_OMNI or not _HAVE_CV:
        return []
    try:
        sess = _omni_session()
        H, W = bgr.shape[:2]
        r = min(imgsz / float(H), imgsz / float(W))
        nh, nw = int(round(H * r)), int(round(W * r))
        canvas = np.full((imgsz, imgsz, 3), 114, dtype=np.uint8)
        top, left = (imgsz - nh) // 2, (imgsz - nw) // 2
        canvas[top : top + nh, left : left + nw] = cv2.resize(bgr, (nw, nh))
        rgb = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        x = np.ascontiguousarray(np.transpose(rgb, (2, 0, 1))[None])
        out = cast(Any, sess.run(None, {sess.get_inputs()[0].name: x}))[
            0
        ]  # (1,5,N) = cx,cy,w,h,conf
        pred = out[0].T
        pred = pred[pred[:, 4] > conf]
        if len(pred) == 0:
            return []
        cx, cy, bw, bh, sc = pred[:, 0], pred[:, 1], pred[:, 2], pred[:, 3], pred[:, 4]
        x1, y1 = cx - bw / 2, cy - bh / 2
        idxs = cv2.dnn.NMSBoxes(
            np.stack([x1, y1, bw, bh], 1).tolist(), sc.tolist(), conf, iou
        )
        if idxs is None or len(idxs) == 0:
            return []
        out_els = []
        for i in np.array(idxs).flatten():
            ox1, oy1 = (x1[i] - left) / r, (y1[i] - top) / r
            ox2, oy2 = (x1[i] + bw[i] - left) / r, (y1[i] + bh[i] - top) / r
            out_els.append(
                {
                    "label": "icon",
                    "role": "icon",
                    "conf": float(sc[i]),
                    "bbox": [
                        int(max(0, ox1)),
                        int(max(0, oy1)),
                        int(min(W, ox2)),
                        int(min(H, oy2)),
                    ],
                }
            )
        return out_els
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Merge / dedup
# ---------------------------------------------------------------------------
def _iou(a, b):
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = ix2 - ix1, iy2 - iy1
    if iw <= 0 or ih <= 0:
        return 0.0
    inter = iw * ih
    area_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
    area_b = max(0, bx2 - bx1) * max(0, by2 - by1)
    union = area_a + area_b - inter
    if union <= 0:
        return 0.0
    return inter / float(union)


def _contains(outer, inner):
    """True if the center of `inner` falls within `outer`."""
    cx = (inner[0] + inner[2]) / 2.0
    cy = (inner[1] + inner[3]) / 2.0
    return outer[0] <= cx <= outer[2] and outer[1] <= cy <= outer[3]


def merge(*lists, iou=0.6):
    """Merge element lists, dropping later boxes that overlap an already-kept box by
    >= `iou`. Lists are processed in argument order, so pass icon/CV lists FIRST and
    text LAST to bias toward keeping the icon/widget proposals. Does not assign ids."""
    kept = []
    for lst in lists:
        for el in lst or []:
            bbox = el.get("bbox")
            if not bbox:
                continue
            if any(_iou(bbox, k["bbox"]) >= iou for k in kept):
                continue
            kept.append(el)
    return kept


# ---------------------------------------------------------------------------
# Set-of-Marks overlay
# ---------------------------------------------------------------------------
def _get_font():
    global _FONT
    if _FONT is not None:
        return _FONT
    for path in (
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "DejaVuSans-Bold.ttf",
    ):
        try:
            _FONT = ImageFont.truetype(path, 16)
            return _FONT
        except Exception:
            continue
    _FONT = ImageFont.load_default()
    return _FONT


def draw_som(pil, elements):
    """Draw numbered red Set-of-Marks boxes on a COPY of `pil` and return the copy.

    Each element gets a red rectangle (width 2) plus a filled red label tag in the
    top-left corner containing its white id number."""
    img = pil.convert("RGB").copy()
    draw = ImageDraw.Draw(img)
    font = _get_font()
    red = (255, 0, 0)
    white = (255, 255, 255)
    for el in elements:
        x1, y1, x2, y2 = el["bbox"]
        draw.rectangle([x1, y1, x2, y2], outline=red, width=2)
        label = str(el["id"])
        try:
            left, top, right, bottom = draw.textbbox((0, 0), label, font=font)
            tw, th = right - left, bottom - top
        except Exception:
            left = top = 0
            tw, th = 8 * len(label), 16
        pad = 2
        tag_w = tw + 2 * pad
        tag_h = th + 2 * pad
        # Place the tag at the box top-left, nudged up so it clears the border; clamp
        # to the image so it stays visible for boxes flush against the top edge.
        ty1 = y1 - tag_h
        if ty1 < 0:
            ty1 = y1
        tx1 = x1
        draw.rectangle([tx1, ty1, tx1 + tag_w, ty1 + tag_h], fill=red)
        # Subtract the glyph offset (l, t) so text sits snugly inside the tag.
        draw.text((tx1 + pad - left, ty1 + pad - top), label, fill=white, font=font)
    return img


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def annotate(image, use_ocr=True, use_cv=None, use_omni=True):
    """Detect UI elements and draw a Set-of-Marks overlay.

    Args:
        image: PIL.Image | ndarray | path. Processed at NATIVE resolution.
        use_ocr: run the OCR text backend (if available).
        use_cv: run the classical-CV icon/region backend (if available).
        use_omni: run the optional OmniParser hook (if available).

    Returns:
        (annotated_image: PIL.Image RGB, elements: list[dict]) where each element is
        {id:int, label:str, role:str, bbox:[x1,y1,x2,y2]} in image pixels. `id` is the
        index in the returned list, assigned after merge.

    Graceful degradation: if no backend is available (or all are disabled) this returns
    (image_unchanged_as_RGB, []) and never raises."""
    pil = _to_pil(image)

    want_ocr = bool(use_ocr) and _HAVE_OCR
    want_omni = bool(use_omni) and _HAVE_OMNI
    # Classical-CV contours over-segment dense UIs (hundreds of junk boxes), so use them
    # ONLY as a fallback when the OmniParser detector isn't available.
    want_cv = _HAVE_CV and (bool(use_cv) if use_cv is not None else (not want_omni))
    if not (want_ocr or want_cv or want_omni):
        return pil, []

    bgr = _pil_to_bgr(pil)

    text_els = []
    if want_ocr:
        for t in ocr_boxes(bgr):
            text_els.append(
                {"label": t.get("text", ""), "role": "text", "bbox": t["bbox"]}
            )

    icon_els = omni_regions(bgr) if want_omni else (cv_regions(bgr) if want_cv else [])

    # Name each interactable box by the OCR text inside it (icon -> button "Save").
    for ic in icon_els:
        names = [
            t["label"]
            for t in text_els
            if t.get("label") and _contains(ic["bbox"], t["bbox"])
        ]
        if names:
            ic["label"] = " ".join(names)[:60]
            ic["role"] = "button"
    # Standalone text = text NOT inside any interactable box (tabs, links, table cells).
    standalone = [
        t
        for t in text_els
        if not any(_contains(ic["bbox"], t["bbox"]) for ic in icon_els)
    ]

    merged = merge(icon_els, standalone, iou=0.5)
    elements = []
    for i, el in enumerate(merged):
        elements.append(
            {
                "id": i,
                "label": el.get("label", ""),
                "role": el.get("role", "element"),
                "bbox": [int(v) for v in el["bbox"]],
            }
        )

    annotated = draw_som(pil, elements)
    return annotated, elements
