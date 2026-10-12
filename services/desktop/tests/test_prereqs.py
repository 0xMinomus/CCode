"""Tests for prereqs.check_all() — no live portal or display required."""

import os

import prereqs


def test_check_all_returns_expected_names():
    out = prereqs.check_all()
    assert "prereqs" in out and "summary" in out
    names = {p["name"] for p in out["prereqs"]}
    assert "python_deps" in names
    assert "window_info" in names
    assert "portal_token" in names
    for p in out["prereqs"]:
        assert p["status"] in ("ok", "warn", "fail")
        assert "detail" in p


def test_portal_token_ok_when_file_exists(tmp_path, monkeypatch):
    tok = tmp_path / "token"
    tok.write_text("x")
    monkeypatch.setattr(prereqs, "_TOKEN_FILE", str(tok))
    e = prereqs.check_portal_token()
    assert e["status"] == "ok"


def test_portal_token_warn_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(prereqs, "_TOKEN_FILE", str(tmp_path / "missing"))
    e = prereqs.check_portal_token()
    assert e["status"] == "warn"
    assert e["next_step"]


def test_window_info_loaded(monkeypatch):
    monkeypatch.setattr(
        "awareness.extension_state",
        lambda: {"installed": True, "loaded": True, "hint": None},
    )
    e = prereqs.check_window_info()
    assert e["status"] == "ok"


def test_window_info_installed_not_loaded(monkeypatch):
    monkeypatch.setattr(
        "awareness.extension_state",
        lambda: {"installed": True, "loaded": False, "hint": "relogin"},
    )
    e = prereqs.check_window_info()
    assert e["status"] == "warn"
    assert "log out" in e["next_step"].lower()


def test_awareness_extension_state_installed_not_loaded(monkeypatch):
    import awareness

    monkeypatch.setattr(awareness, "_call", lambda _m: None)
    monkeypatch.setattr(os.path, "isfile", lambda p: str(p).endswith("extension.js"))
    monkeypatch.setattr(
        os.path,
        "expanduser",
        lambda p: "/fake/window-info@local" if "gnome-shell/extensions" in p else p,
    )
    st = awareness.extension_state()
    assert st["installed"] is True
    assert st["loaded"] is False
    assert "log out" in st["hint"]
