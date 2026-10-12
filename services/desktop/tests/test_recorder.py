"""Self-contained unit test for recorder.py — synthetic frames, no live capture.

Run: python3 tests/test_recorder.py
Exercises: start -> log_frame -> log_action -> stop, then asserts the JSONL has at
least meta+screenshot+action lines, that frames/*.webp + replay.html exist, and that
logging the same image twice dedups to a single file."""

import os
import sys
import glob
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image
import recorder
from recorder import REC


def main():
    sid = "test-sess"
    # Reset the per-test session dir BEFORE start(): recorder.start() opens
    # trajectory.jsonl in append mode and resets self._seq to 0, so a stale dir
    # from a prior run would produce non-monotonic seqs and break the asserts
    # below. The pytest wrapper redirects SESS_ROOT to tmp_path; standalone runs
    # use the real ~/.local/share/mcp-screen/sessions/test-sess and need this rmtree.
    import shutil

    stale = os.path.join(recorder.SESS_ROOT, sid)
    if os.path.isdir(stale):
        shutil.rmtree(stale, ignore_errors=True)
    d = REC.start(sid)
    assert d, "start() returned no dir"
    assert REC.active(), "recorder should be active after start"
    assert d == os.path.join(recorder.SESS_ROOT, sid), f"unexpected dir {d}"

    # A small synthetic frame + a fake action with a view transform.
    img = Image.new("RGB", (200, 120), (40, 90, 160))
    view = {"ox": 0, "oy": 0, "scale": 0.5, "dw": 400, "dh": 240}
    REC.log_frame(img, "screenshot", view=view)
    REC.log_action(
        "click",
        {"x": 50, "y": 30, "button": "left", "shot": True},
        "clicked left (100,60)",
        True,
        12,
        resolved=[100, 60],
        view=view,
    )

    # Dedup: same image again -> must reuse one frame file.
    REC.log_frame(img, "screenshot", view=view)
    # A genuinely different image -> a second frame file.
    img2 = Image.new("RGB", (200, 120), (200, 30, 30))
    REC.log_frame(img2, "screenshot", view=view)

    d2 = REC.stop()
    assert d2 == d, "stop() returned a different dir"
    assert not REC.active(), "recorder should be inactive after stop"

    # --- read back trajectory.jsonl ---
    tj = os.path.join(d, "trajectory.jsonl")
    with open(tj) as f:
        lines = [json.loads(ln) for ln in f if ln.strip()]
    types = [e.get("type") for e in lines]
    assert len(lines) >= 3, f"expected >=3 lines, got {len(lines)}: {types}"
    assert "meta" in types, "missing meta line"
    assert "screenshot" in types, "missing screenshot line"
    assert "action" in types, "missing action line"

    # meta header is first, has v/session/started; meta footer has ended.
    assert lines[0]["type"] == "meta" and lines[0]["v"] == 1, (
        "first line not meta header"
    )
    assert lines[0]["session"] == sid and "started" in lines[0]
    assert any(e.get("type") == "meta" and "ended" in e for e in lines), (
        "missing meta footer"
    )

    # action event shape: 'shot' sanitized out, coords + truncation present.
    act = next(e for e in lines if e.get("type") == "action")
    assert "shot" not in act["args"], "'shot' should be dropped from args"
    assert act["resolved_coords"] == [100, 60]
    assert act["ok"] is True and act["ms"] == 12
    assert len(act["result"]) <= 500
    assert act["view"] == view

    # screenshot event shape.
    shot = next(e for e in lines if e.get("type") == "screenshot")
    for key in ("seq", "ts", "image_ref", "sha256", "w", "h", "bytes", "view"):
        assert key in shot, f"screenshot missing {key}"

    # seq strictly increments across actions + frames.
    seqs = [e["seq"] for e in lines if "seq" in e]
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs), (
        f"seq not monotonic: {seqs}"
    )

    # --- frames + replay.html on disk ---
    webps = sorted(glob.glob(os.path.join(d, "frames", "*.webp")))
    assert webps, "no frames/*.webp written"
    assert os.path.exists(os.path.join(d, "replay.html")), "replay.html missing"

    # --- dedup: 3 frame events logged (img, img, img2) but only 2 files ---
    frame_events = [e for e in lines if e.get("type") == "screenshot"]
    assert len(frame_events) == 3, (
        f"expected 3 screenshot events, got {len(frame_events)}"
    )
    assert len(webps) == 2, f"dedup failed: expected 2 files, got {len(webps)}"
    # The two identical-image events share an image_ref; the third differs.
    refs = [e["image_ref"] for e in frame_events]
    assert refs[0] == refs[1], "identical images should share image_ref"
    assert refs[2] != refs[0], "different image should get its own ref"
    assert frame_events[0]["sha256"] == frame_events[1]["sha256"]
    assert frame_events[2]["sha256"] != frame_events[0]["sha256"]

    # --- inactive no-op safety: must not raise, must not write ---
    assert REC.stop() is None, "stop() on inactive should return None"
    REC.log_action("click", {"x": 1, "y": 1}, "x", True, 1)  # no-op, no raise
    REC.log_frame(img, "screenshot")  # no-op, no raise

    print("ALL ASSERTIONS PASSED")
    print("session dir:", d)
    print("events:", len(lines), "| types:", types)
    print("frame files:", len(webps), "->", [os.path.basename(w) for w in webps])


def test_recorder_smoke(tmp_path, monkeypatch):
    """pytest entry point. Redirects recorder.SESS_ROOT to a per-test tmp_path so each
    run gets a fresh recording dir — `recorder.start()` opens trajectory.jsonl in
    APPEND mode and resets self._seq to 0, so a stale dir would produce non-monotonic
    seqs and break main()'s asserts. The standalone runner (python3 tests/test_recorder.py)
    still uses ~/.local/share/mcp-screen/sessions/test-sess."""
    monkeypatch.setattr(recorder, "SESS_ROOT", str(tmp_path))
    main()


if __name__ == "__main__":
    main()
