# screen-mcp

Linux Wayland computer-use MCP for Claude Code and Grok — screenshot, click, type, scroll, drag, read any desktop app.

[![plugin-validate](https://github.com/88plug/screen-mcp/actions/workflows/plugin-validate.yml/badge.svg)](https://github.com/88plug/screen-mcp/actions/workflows/plugin-validate.yml)
[![License: FSL-1.1-ALv2](https://img.shields.io/badge/license-FSL--1.1--ALv2-blue?style=flat)](https://github.com/88plug/screen-mcp/blob/main/LICENSE)
[![Claude Code plugin](https://img.shields.io/badge/Claude%20Code-plugin-8A2BE2?style=flat)](https://github.com/88plug/claude-code-plugins)
[![Docs](https://img.shields.io/badge/docs-online-2ea44f?style=flat)](https://88plug.github.io/screen-mcp/)

screen-mcp is an MCP server and plugin for Claude Code and Grok that lets an agent see and operate your **GNOME/Wayland** desktop. Capture goes through PipeWire. Pointer and keyboard go through the `xdg-desktop-portal` RemoteDesktop portal (or a kernel `uinput` backend when available). Optional OCR (RapidOCR) and OmniParser ONNX ground on-screen elements. Pure Python. CPU-only. Built for agents that need real computer-use on native desktop apps — not just a browser.

## Install

### Claude Code

```text
/plugin marketplace add 88plug/claude-code-plugins
/plugin install screen-mcp@88plug
```

### Grok Build

```text
grok plugin marketplace add 88plug/claude-code-plugins
grok plugin install screen-mcp@88plug --trust
```

One-time **system** packages (PipeWire + GStreamer + portal) then **Python** deps.
The marketplace cannot install these. Full detail: [Install](install.md).

```bash
# --- system (pick your distro) ---
# Debian / Ubuntu
sudo apt install python3-gi python3-gi-cairo gir1.2-gstreamer-1.0 \
  gstreamer1.0-tools gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
  gstreamer1.0-libav pipewire pipewire-pulse xdg-desktop-portal-gnome \
  wl-clipboard fonts-dejavu

# Arch / Manjaro
sudo pacman -S python-gobject gobject-introspection \
  gstreamer gst-plugins-base gst-plugins-good gst-libav \
  pipewire pipewire-pulse xdg-desktop-portal-gnome \
  wl-clipboard ttf-dejavu

# --- Python ---
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

On first use the desktop portal asks which monitor(s) to share. Pick one, then:

```text
Take a screenshot of my desktop and tell me which window is focused.
```

You get a labeled capture plus the focused-window name. The portal restore token is cached at `~/.config/mcp-screen` so later runs are silent.

!!! important
    Linux + Wayland + GNOME only. Grounding is CPU-only by design. Read [Install & prerequisites](install.md) before expecting clicks to work.

## Start here

| Page | When to open it |
|---|---|
| [Install & prerequisites](install.md) | First setup, missing portal / GStreamer / uinput |
| [Tool loop](tool-loop.md) | How to drive the desktop without misclicks |
| [Tools](tools.md) | Full MCP tool list (matches `server.py` `TOOLS`) |
| [Guards (HIL)](guards.md) | User-takeover, destructive ack, audit log |
| [Pairing with os-control](pairing.md) | GUI + system-service stack |
| [Configuration](configuration.md) | Env vars and data paths |
| [Grounding research](v1.1-grounding-research.md) | Why OmniParser stays; what leaderboards mean for CPU |

## What you get

- **Screenshot** any monitor or region, with numbered Set-of-Marks overlays and click coordinates.
- **Click, type, scroll, drag** in any visible app — including native Wayland apps that `xdotool` / XTEST cannot reach.
- **Annotate** with OCR + OmniParser so the model clicks `element=<id>` instead of guessing pixels.
- **Focus** windows before typing (the #1 fix for "I typed but nothing happened").
- **Sense** changes: ambient diffs tell the agent when something opened or when an action was a no-op.
- **Cache** learned screens in a write-through world model so known UIs can skip OCR.
- **Gate** destructive actions with an opt-in ack guard, and **yield** the mouse the instant a human moves it.

Ships a `drive-screen` skill that encodes the locate → ground → act → confirm loop.

## The loop (one line)

```text
screen_screenshot()  →  annotate / region zoom  →  click|type|key  →  re-shot / SENSE
```

Details, coordinate rules, and gotchas: [Tool loop](tool-loop.md).

## Principles — The Agent Oath

screen-mcp is a reference **enforcer** of [The Agent Oath](https://theagentoath.com):

- **User-takeover guard** — yields control the instant a human moves the mouse (`STOPPED`). Human agency and oversight made executable: *don't fight the human for the mouse.*
- **Opt-in ack gate** — destructive combos / keywords need an explicit confirmation token.
- **On-screen visibility** — every action is visible on the real desktop.

See [Guards (HIL)](guards.md).

## Pairing

| Layer | Server | Job |
|---|---|---|
| Desktop (GUI eyes + hands) | **screen-mcp** (this project) | Capture + inject into visible apps |
| Host (services / power / journal) | [os-control-mcp](https://88plug.github.io/os-control-mcp/) | systemd, logind, journald, D-Bus |

They share a human-in-the-loop philosophy and complement each other. See [Pairing with os-control](pairing.md).

## Development

```bash
pytest -q          # no live D-Bus required (conftest stubs)
```

After editing server code, call `screen_reload` in the running session to re-exec in place (no `/mcp` reconnect). On tool exceptions the dispatcher writes the traceback to `/tmp/screen_err.txt`.

## License

[FSL-1.1-ALv2](https://github.com/88plug/screen-mcp/blob/main/LICENSE) © 2026 [88plug](https://github.com/88plug). Converts to Apache 2.0 two years after each release.

## Features

| Feature | Detail |
|---|---|
| Screenshot + Set-of-Marks | Capture any monitor or region with numbered overlays and click coordinates |
| Click / type / scroll / drag | Drive any visible app over xdg-desktop-portal, including native Wayland |
| OCR + icon grounding | Optional RapidOCR text read and OmniParser ONNX icon grounding |
| Ambient change sense | Frame diffs so the agent knows when something opened or an action no-op'd |
| World-model cache | Write-through screen memory skips OCR on recognized UIs |
| Ack guard | Opt-in gate blocks close-combos and destructive-keyword clicks until confirmed |
| `drive-screen` skill | Claude skill for the locate → ground → act → confirm computer-use loop |
