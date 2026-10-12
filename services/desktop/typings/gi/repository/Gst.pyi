from typing import Any

class State:
    VOID_PENDING: int
    NULL: int
    READY: int
    PAUSED: int
    PLAYING: int

class MapFlags:
    READ: int
    WRITE: int
    FLAG_LAST: int

class PadProbeType:
    INVALID: int
    IDLE: int
    BLOCK: int
    BUFFER: int
    BUFFER_LIST: int
    EVENT_DOWNSTREAM: int
    EVENT_UPSTREAM: int
    EVENT_FLUSH: int
    QUERY_DOWNSTREAM: int
    QUERY_UPSTREAM: int
    PUSH: int
    PULL: int
    BLOCKING: int
    DATA_DOWNSTREAM: int
    DATA_UPSTREAM: int
    DATA_BOTH: int
    BLOCK_DOWNSTREAM: int
    BLOCK_UPSTREAM: int
    EVENT_BOTH: int
    QUERY_BOTH: int
    ALL_BOTH: int
    SCHEDULING: int

class PadProbeReturn:
    DROP: int
    OK: int
    REMOVE: int
    PASS: int
    HANDLED: int

SECOND: int
MSECOND: int
USECOND: int
NSECOND: int

def init(argv: Any = None) -> None: ...
def parse_launch(pipeline_description: str) -> Any: ...
def __getattr__(name: str) -> Any: ...
