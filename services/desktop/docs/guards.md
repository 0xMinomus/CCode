# Guards (human-in-the-loop)

screen-mcp can move the real mouse and keyboard. Two independent guards keep a human in charge. Neither is "security theater" — both are operational brakes for a live desktop.

## 1. User-takeover guard (always on)

**Idea:** *Don't fight the human for the mouse.*

Before mutating actions, `input.guard_user` compares the **live** pointer (from PipeWire cursor metadata) to the last position **the server commanded**. If they diverge beyond a threshold, the action aborts:

```text
STOPPED: … re-issue with force=true to take control back.
```

| Detail | Value |
|---|---|
| Default threshold | 40 px (`MCP_SCREEN_GUARD_PX`) |
| Bypass | `force=true` on the tool call |
| Batch tools | `screen_do` / `screen_tour` stop mid-batch on takeover |
| Fail-open | When force is set, or when a reliable cursor reading is unavailable |

### Operator practice

1. Move the mouse yourself when you want the agent to stop — you get `STOPPED` immediately.
2. When you hand control back, the agent re-issues the action with `force=true` (or you move the pointer out of the way and the next unforced command succeeds if the baseline still matches).
3. Agents should only use `force=true` after a clear handoff — not to steamroll an active user.

This is the executable form of Agent Oath human agency / oversight: the human can reclaim the desktop without killing the MCP process.

## 2. Destructive ack gate (opt-in)

**Off by default.** Enable with:

```bash
export MCP_SCREEN_GUARD=1
```

When on, `reliability.needs_ack` may require an explicit `ack=<reason>` token before the action runs. First matching reason wins:

| Reason token | Trigger |
|---|---|
| `window-close` | `screen_key` combo in `Alt+F4`, `Ctrl+W`, `Ctrl+Q`, `Cmd+Q` (aliases normalized) |
| `keyword:<word>` | OCR text near the click target matches a destructive verb (`delete`, `remove`, `close`, `quit`, `submit`, `pay`, `purchase`, `confirm`, `send`, `discard`, `format`, …) |
| `out-of-allowlist` | `MCP_SCREEN_APPS` is set and the focused app is not in the comma-list |

Blocked response shape:

```text
Re-issue with ack='<reason>' to proceed.
```

Plus `ack_reason` on the error payload for structured clients.

### App allowlist

```bash
export MCP_SCREEN_GUARD=1
export MCP_SCREEN_APPS="firefox,terminal,slack"
```

With both set, actions outside the allowlist need `ack='out-of-allowlist'`.

### Wiring note

The gate runs inside the live action path in `server.py` (`_action` → `reliability.needs_ack`). It is independent of the user-takeover guard.

## 3. Misclick / no-op detection

Not a hard block — a **warning** path:

- Pass `verify=true` on an action to warn if the screen did not change.
- Ambient **`SENSE`** lines on responses report "nothing changed" after a no-op so the agent re-grounds instead of looping blindly.
- Optional audit frames: `MCP_SCREEN_AUDIT_FRAMES=1` adds pre/post frame hash + `changed_bbox` to each audit line (~100–500 ms per action).

## Audit log

Every action can be appended as one JSON line to:

```text
~/.local/state/mcp-screen/actions.jsonl
```

Use this for post-mortems and trajectory review alongside `screen_session` recordings under `~/.local/share/mcp-screen/sessions/`.

## Comparison with os-control

| Concern | screen-mcp | [os-control-mcp](https://88plug.github.io/os-control-mcp/) |
|---|---|---|
| Human reclaim | Pointer divergence → `STOPPED` | MCP elicitation / `force`+`confirm` for mutations |
| Hard floor | — (GUI only) | Never sever dbus/logind/init even with force |
| Destructive ack | Opt-in `MCP_SCREEN_GUARD` + `ack=` | Elicitation-first; flag fallback |
| Audit | `actions.jsonl` | `$XDG_STATE_HOME/os-control-mcp/audit.jsonl` |

Together they implement the same principle on different surfaces: **the human remains the authority**. Details: [Pairing with os-control](pairing.md).

## Agent Oath mapping

| Mechanism | Oath theme |
|---|---|
| User-takeover → `STOPPED` | Human agency & oversight |
| Opt-in ack gate | Don't bypass safety / don't rush irreversible UI |
| Visible desktop actions | Transparency |
| Audit log | Accountability |

Rationale: [theagentoath.com](https://theagentoath.com). The **operator's configuration** is the authority on this host — env flags and physical mouse ownership.
