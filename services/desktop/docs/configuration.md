# Configuration

screen-mcp is mostly zero-config after portal consent. Optional environment variables tune guards, capture, and grounding.

## Common variables

| Variable | Effect |
|---|---|
| `MCP_SCREEN_GUARD=1` | Enable the reliability **ack gate** (close combos / destructive keywords / allowlist). See [Guards](guards.md). |
| `MCP_SCREEN_APPS` | With guard on: comma-list of allowed focused apps (e.g. `firefox,terminal`). |
| `MCP_SCREEN_GUARD_PX=40` | User-takeover threshold: live pointer vs last-commanded position (pixels). |
| `MCP_SCREEN_AMBIENT=0` | Disable the ambient `SENSE` hint block on responses. |
| `MCP_SCREEN_CPU_THREADS=6` | ONNX intra-op thread count for OmniParser. |
| `MCP_SCREEN_MAX_EDGE=2576` | Screenshot downscale target (long edge). |

## Capture & focus

| Variable | Effect |
|---|---|
| `MCP_SCREEN_NO_FRESH=1` | Disable forced fresh-frame capture on static monitors. |
| `MCP_SCREEN_NO_NUDGE=1` | Disable the pointer damage-nudge that primes a static monitor's frame. |
| `MCP_SCREEN_FOCUS_SETTLE_MS=150` | Delay after `screen_focus` activates a window. |
| `MCP_SCREEN_NO_UINPUT=1` | Force portal input; do not open `/dev/uinput`. |
| `MCP_SCREEN_MAP_HAMMING` | World-model dHash Hamming distance (default **5**). Higher = more aggressive cache reuse, more sibling-page confusion. |

## Audit

| Variable | Effect |
|---|---|
| `MCP_SCREEN_AUDIT_FRAMES=1` | Add pre/post frame hash + `changed_bbox` to each audit line (~100–500 ms per action). |

## Data paths

| Path | What |
|---|---|
| `~/.config/mcp-screen/token` | Portal restore token (one-time consent). |
| `~/.local/share/mcp-screen/world/map.db` | World-model cache (per-screen learned elements). |
| `~/.local/share/mcp-screen/sessions/<sid>/` | Recorder trajectories, frames, `replay.html`. |
| `~/.local/state/mcp-screen/actions.jsonl` | Reliability audit log (one JSON line per action). |
| `/tmp/screen_err.txt` | Last unhandled tool traceback (dev diagnostic). |

## Client wiring

Example MCP server entry (Claude Code / compatible clients):

```json
{
  "screen": {
    "command": "/path/to/screen-mcp/.venv/bin/python",
    "args": ["/path/to/screen-mcp/server.py"],
    "env": {
      "MCP_SCREEN_GUARD": "1",
      "MCP_SCREEN_APPS": "firefox,terminal"
    }
  }
}
```

Plugin installs usually inject the command path for you; set `env` in the client config when you want the ack gate or app allowlist.

## Version

Distribution version is rolling calver (`YEAR.MONTH.<commit-count>`) from `version.py`, exposed as `server.__version__` / MCP `serverInfo.version`.
