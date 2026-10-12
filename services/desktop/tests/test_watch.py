"""Unit tests for human-eye watch verdict classification (autoloop.classify_watch_timeline)."""

from autoloop import classify_watch_timeline


def test_empty_timeline():
    r = classify_watch_timeline([])
    assert r["verdict"] == "empty"


def test_settled_quiet_tail():
    # mostly none with a quiet tail
    acts = ["none", "none", "local", "none", "none", "none"]
    r = classify_watch_timeline(acts)
    assert r["verdict"] == "settled"


def test_jitter_sustained_local():
    # force-sim / spinning canvas: almost every gap is local, no navigation
    acts = ["local"] * 8
    r = classify_watch_timeline(acts)
    assert r["verdict"] == "jitter"
    assert (
        "crazy" in r["reason"]
        or "jitter" in r["reason"].lower()
        or "force" in r["reason"]
    )


def test_jitter_threshold_fraction():
    # 6/10 local = 0.6 >= 0.55 → jitter
    acts = ["local"] * 6 + ["none"] * 4
    r = classify_watch_timeline(acts)
    assert r["verdict"] == "jitter"


def test_evolving_major_then_settle():
    acts = ["none", "major", "panel", "none", "none"]
    r = classify_watch_timeline(acts)
    assert r["verdict"] == "evolving"
    assert "settled" in r["reason"] or "navigation" in r["reason"].lower()


def test_evolving_still_changing():
    acts = ["none", "major", "local", "local"]
    r = classify_watch_timeline(acts)
    assert r["verdict"] == "evolving"


def test_mixed_unstable():
    # not enough local for jitter, no major, noisy tail
    acts = ["local", "none", "local", "none", "local"]
    r = classify_watch_timeline(acts)
    assert r["verdict"] in ("unstable", "jitter", "settled")
