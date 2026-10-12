"""Unit tests for sense.diff_elements — locks in the removed-count patch.

The patched line at sense.py:177 now computes `removed = len(prev) - len(used)`
directly from the bookkeeping set, instead of the algebraic identity
`len(prev) - (len(cur) - len(new))`. The two forms agree whenever every match step
adds exactly one fresh id() to `used`; they diverge when prev contains the same
Python object referenced twice (pathological), in which case the direct form is
correct and the algebraic form drifts. These tests pin both the normal-case contract
and the pathological bound."""

import sense


def _el(role, label, cx, cy, w=20, h=20):
    return {
        "role": role,
        "label": label,
        "bbox": [cx - w // 2, cy - h // 2, cx + w // 2, cy + h // 2],
    }


def test_identical_lists_report_no_churn():
    r = sense.diff_elements(
        [_el("button", "Save", 100, 100)], [_el("button", "Save", 100, 100)]
    )
    assert r == {"new": [], "removed": 0, "moved": 0, "changed": []}


def test_one_removed_is_counted_once():
    r = sense.diff_elements(
        [_el("button", "Save", 100, 100), _el("button", "Cancel", 200, 100)],
        [_el("button", "Save", 100, 100)],
    )
    assert r["removed"] == 1
    assert r["new"] == [] and r["moved"] == 0


def test_one_added_is_new_not_removed():
    r = sense.diff_elements(
        [_el("button", "Save", 100, 100)],
        [_el("button", "Save", 100, 100), _el("button", "New", 300, 100)],
    )
    assert r["removed"] == 0
    assert len(r["new"]) == 1 and r["new"][0]["label"] == "New"


def test_moved_within_radius_is_moved_not_churn():
    # 20px shift; the default move_radius is 40, so this is a same-element move.
    r = sense.diff_elements(
        [_el("button", "Save", 100, 100)], [_el("button", "Save", 120, 120)]
    )
    assert r["moved"] == 1 and r["removed"] == 0 and r["new"] == []


def test_moved_beyond_radius_counts_as_new_plus_removed():
    r = sense.diff_elements(
        [_el("button", "Save", 100, 100)], [_el("button", "Save", 400, 400)]
    )
    assert r["moved"] == 0 and r["removed"] == 1 and len(r["new"]) == 1


def test_duplicate_prev_distinct_dicts_one_gone_reports_one_removed():
    """Two prev dicts with the same role+label (distinct objects, distinct positions);
    cur drops one. Each match consumes exactly one bucket slot, so removed=1."""
    prev = [_el("button", "Save", 100, 100), _el("button", "Save", 300, 300)]
    r = sense.diff_elements(prev, [_el("button", "Save", 100, 100)])
    assert r["removed"] == 1, f"expected 1 removed, got {r['removed']}"


def test_duplicate_prev_distinct_dicts_no_change_reports_nothing():
    prev = [_el("button", "Save", 100, 100), _el("button", "Save", 300, 300)]
    r = sense.diff_elements(prev, list(prev))
    assert r["removed"] == 0 and r["new"] == []


def test_removed_is_always_bounded_by_len_prev_even_for_repeated_id():
    """Regression contract: the patched form derives removed from `used` directly,
    so it cannot exceed len(prev) regardless of how oddly the matcher accounts."""
    shared = _el("button", "Save", 100, 100)
    r = sense.diff_elements(
        [shared, shared],
        [_el("button", "Save", 100, 100), _el("button", "Save", 100, 100)],
    )
    assert 0 <= r["removed"] <= 2


def test_empty_prev():
    r = sense.diff_elements([], [_el("button", "New", 50, 50)])
    assert r["removed"] == 0 and len(r["new"]) == 1


def test_empty_cur():
    r = sense.diff_elements(
        [_el("button", "Save", 100, 100), _el("button", "Cancel", 200, 100)], []
    )
    assert r["removed"] == 2 and r["new"] == []


def test_label_less_icon_iou_match_is_not_new():
    prev = [{"role": "icon", "label": "", "bbox": [10, 10, 50, 50]}]
    cur = [{"role": "icon", "label": "", "bbox": [12, 12, 52, 52]}]  # IoU ~ 0.85
    r = sense.diff_elements(prev, cur)
    assert r["new"] == [] and r["removed"] == 0


def test_fail_open_on_malformed_input():
    # Missing bbox -> function returns safe defaults instead of raising.
    r = sense.diff_elements([{"role": "x", "label": "y"}], [])
    assert r == {"new": [], "removed": 0, "moved": 0, "changed": []}


# --------------------------------------------------------------------------- #
# to_pixel_signal — the normalizer that feeds os_verify's `pixel` arg
# --------------------------------------------------------------------------- #
def test_pixel_signal_empty_is_noop():
    p = sense.to_pixel_signal(None)
    assert p["changed"] is False and p["no_op"] is True
    assert p == sense.to_pixel_signal({})


def test_pixel_signal_static_frame_is_noop():
    p = sense.to_pixel_signal({"settle": {"activity": "none"}})
    assert p["changed"] is False and p["no_op"] is True and p["activity"] == "none"


def test_pixel_signal_activity_means_changed():
    p = sense.to_pixel_signal({"settle": {"activity": "major"}})
    assert p["changed"] is True and p["no_op"] is False and p["activity"] == "major"


def test_pixel_signal_new_elements_means_opened():
    p = sense.to_pixel_signal(
        {"settle": {"activity": "minor"}, "change": {"new_count": 3}}
    )
    assert p["opened"] is True and p["changed"] is True


def test_pixel_signal_modal_overlay():
    p = sense.to_pixel_signal(
        {"settle": {"activity": "major"}, "overlay": {"present": True, "kind": "modal"}}
    )
    assert p["modal"] is True and p["changed"] is True


def test_pixel_signal_nonmodal_overlay_changes_but_not_modal():
    p = sense.to_pixel_signal(
        {
            "settle": {"activity": "minor"},
            "overlay": {"present": True, "kind": "banner"},
        }
    )
    assert p["changed"] is True and p["modal"] is False


def test_pixel_signal_scroll_counts_as_changed():
    p = sense.to_pixel_signal({"scroll": {"dy": 120}})
    assert p["changed"] is True
