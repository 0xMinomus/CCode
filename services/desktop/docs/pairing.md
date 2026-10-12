# Pairing with os-control

[os-control-mcp](https://88plug.github.io/os-control-mcp/) is the **system-service motor cortex**: systemd, logind, journald, D-Bus, power, host resources. **screen-mcp** is the **GUI eyes and hands**: capture the Wayland desktop and inject pointer/keyboard into visible apps.

Use them together for a full-stack local agent.

## Split of responsibility

| Job | Use | Avoid |
|---|---|---|
| Read or click a GUI (Slack, browser, settings, terminal window chrome) | **screen-mcp** | Parsing pixels when a journal query would answer |
| Restart a unit, read logs, check load, reboot, notify | **os-control-mcp** | Driving `gnome-system-monitor` by click when `os_resources` exists |
| "Is the build green in that terminal window?" | screen-mcp (or shell if you already own the PTY) | — |
| "Why did `foo.service` fail?" | `os_journal` / `os_services` | Screenshotting Cockpit unless you must |

```text
sense host (os_diag / os_journal / os_resources)
    → act on services (os_service) when the change is systemic
    → drive the desktop (screen_*) when the work is in a GUI
    → confirm (re-read journal OR re-screenshot + SENSE)
```

## Shared philosophy

Both servers are Agent Oath **enforcers**, not just "tools that can do damage":

| Theme | screen-mcp | os-control-mcp |
|---|---|---|
| Human agency | Mouse move → `STOPPED` | Elicitation / human approval for destructive ops |
| Hard limits | Portal consent + physical display | Unbypassable floor on dbus/logind/init |
| Transparency | Actions visible on-screen; audit JSONL | `dry_run`; audit JSONL |
| Prefer structured APIs | Portal / uinput over XTEST hacks | systemctl / journalctl / busctl over `kill` |

Install both when the agent should operate **the machine and the desktop session**. Install only screen-mcp when the scope is pure GUI automation.

## Install both (Claude Code)

```text
/plugin marketplace add 88plug/screen-mcp
/plugin install screen-mcp@screen-mcp

/plugin marketplace add 88plug/os-control-mcp
/plugin install os-control-mcp@os-control-mcp
```

Confirm with `/mcp` that servers `screen` and `os` both list tools.

!!! warning "Privilege"
    os-control can stop services and power off the box. Treat it as privileged. screen-mcp can type into any shared monitor — treat portal consent and the takeover guard as your session boundary.

## Example workflows

### Restart a service, then verify in a GUI dashboard

1. `os_diag` — privilege and backend health.
2. `os_service(op=restart, unit=foo.service)` — with human approval / `force` per os-control rules.
3. `os_wait` or `os_journal` until healthy.
4. `screen_screenshot` → ground the dashboard → confirm the UI shows the new state.

### GUI is stuck; check whether the host is the problem

1. `screen_diag` — portal, monitors, cursor guard.
2. If the whole session is wedged: `os_session`, `os_pressure`, `os_processes`.
3. If a user unit is dead: `os_services` / `os_journal` with `scope=user`.
4. Only then click through recovery UI with screen-mcp.

### Notify the human after a long GUI task

1. Finish the screen loop.
2. `os_notify(summary=…, body=…)` so the human gets a desktop notification without watching every click.

## Skills

| Server | Skill | Loop |
|---|---|---|
| screen-mcp | `drive-screen` | locate → ground → act → confirm |
| os-control-mcp | `control-os` | sense → act → confirm |

Teach the model: **GUI content → screen**; **host state and sanctioned mutations → os**.

## Links

- os-control docs: [88plug.github.io/os-control-mcp](https://88plug.github.io/os-control-mcp/)
- os-control repo: [github.com/88plug/os-control-mcp](https://github.com/88plug/os-control-mcp)
- This project's [Guards](guards.md) and [Tool loop](tool-loop.md)
