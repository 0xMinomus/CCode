"""Side-effect import registers the appsink GType; no symbols used directly."""

from typing import Any

def __getattr__(name: str) -> Any: ...
