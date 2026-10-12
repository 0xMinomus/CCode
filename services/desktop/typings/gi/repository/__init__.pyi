"""gi.repository namespace — real symbols live in per-module stubs (GLib, Gio, …)."""

from typing import Any

def __getattr__(name: str) -> Any: ...
