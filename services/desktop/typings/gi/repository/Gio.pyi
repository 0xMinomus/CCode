from typing import Any

class BusType:
    SESSION: int
    SYSTEM: int
    STARTER: int
    NONE: int

class DBusCallFlags:
    NONE: int
    NO_AUTO_START: int
    ALLOW_INTERACTIVE_AUTHORIZATION: int

class DBusSignalFlags:
    NONE: int
    NO_MATCH_RULE: int
    MATCH_ARG0_NAMESPACE: int
    MATCH_ARG0_PATH: int

class DBusProxyFlags:
    NONE: int
    DO_NOT_LOAD_PROPERTIES: int
    DO_NOT_CONNECT_SIGNALS: int
    DO_NOT_AUTO_START: int

def bus_get_sync(bus_type: Any, cancellable: Any = None) -> Any: ...
def __getattr__(name: str) -> Any: ...
