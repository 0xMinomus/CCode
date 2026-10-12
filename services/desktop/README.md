<div align="center">

# screen-mcp

Linux Wayland computer-use MCP for Claude Code and Grok — screenshot, click, type, scroll, drag, read any desktop app.

[![plugin-validate](https://github.com/88plug/screen-mcp/actions/workflows/plugin-validate.yml/badge.svg)](https://github.com/88plug/screen-mcp/actions/workflows/plugin-validate.yml)
[![License: FSL-1.1-ALv2](https://img.shields.io/badge/license-FSL--1.1--ALv2-blue?style=flat)](LICENSE)
[![Docs](https://img.shields.io/badge/docs-online-2ea44f?style=flat)](https://88plug.github.io/screen-mcp/)
[![Claude Code plugin](https://img.shields.io/badge/Claude%20Code-plugin-8A2BE2?style=flat)](https://github.com/88plug/claude-code-plugins)
[![DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/88plug/screen-mcp)

</div>

screen-mcp is an MCP server and plugin for Claude Code and Grok for desktop
automation on GNOME/Wayland. It captures any monitor through PipeWire, drives
pointer and keyboard via the `xdg-desktop-portal` RemoteDesktop portal, and
optionally reads the screen with OCR plus OmniParser icon grounding. Pure
Python, CPU-only — built for AI agents that need real computer-use on native
Linux apps, not just a browser.

It ships the MCP tools plus a `drive-screen` skill that encodes the locate →
ground → act → **confirm/watch** loop so the model uses screenshots and clicks
well out of the box. **`screen_watch` (default ~1 fps)** is how agents see like
humans: thrashing graphs, loaders, and canvases fail visual QA with a `jitter`
verdict instead of slipping past a single freeze-frame. Developers get
productivity tools that reach every visible window — including native Wayland
apps that `xdotool` and XTEST cannot touch.

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

Then install **system packages** (once per machine) and **Python deps** (plugin
venv). The marketplace cannot install these for you.

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

# --- Python (required: numpy + Pillow; optional OCR later) ---
# From the installed plugin root (or a clone):
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
# minimum only:  .venv/bin/pip install 'numpy>=1.26' 'Pillow>=10.0'
```

## Quickstart

On first use the desktop portal asks which monitor(s) to share. Pick one, then:

```text
Take a screenshot of my desktop and tell me which window is focused.
```

You get a labeled capture plus the focused-window name within a few seconds. The
portal restore token is cached at `~/.config/mcp-screen` so later runs are silent.

> [!IMPORTANT]
> screen-mcp runs on Linux + Wayland + GNOME only. Grounding is CPU-only by
> design. See [Requirements](#requirements) before installing.

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

## Principles — The Agent Oath

screen-mcp is a reference **enforcer** of [The Agent Oath](https://theagentoath.com).
The **user-takeover guard** yields the instant a human moves the mouse (`STOPPED`
result) — §2 human agency and §11 human oversight, executable. Opt-in ack gate
(§7) and on-screen visibility of every action (§5) round it out.

## MCP tools

Every action also accepts `space` (`view` / `desktop` / `norm`, default `view` —
coords as seen in the last screenshot), `shot: true` for a post-action shot,
`verify: true` to warn on no-change misclicks, `force: true` to bypass the
user-takeover guard, and `element: <id>` to click an element id from the last
annotated shot.

| Tool | What it does |
|---|---|
| `screen_screenshot` | Capture the desktop. `region` / `monitor` to zoom, `annotate=true` for numbered marks, `use_cache=true` to reuse learned elements, `fresh=true` to force a current frame on a static monitor. |
| `screen_list_monitors` | Monitors (origin/size/scale), desktop bounds, focused windows. |
| `screen_move_mouse` | Move the pointer to `x,y`. |
| `screen_click` | Click at `x,y` or in place. `button`, `double`. |
| `screen_scroll` | Wheel scroll by direction and amount. |
| `screen_drag` | Press-drag from one point to another. |
| `screen_key` | Press a key or combo, e.g. `Ctrl+L`, `Enter`, `Alt+Tab`. |
| `screen_type` | Type text into the focused window (Unicode via clipboard paste, ASCII via keysyms). |
| `screen_read_text` | Read the screen as text + click coords, no image (3.5x-50x fewer tokens). |
| `screen_wait_text` | Block until text appears, then return its click coords. |
| `screen_verify` | Grade the last action: CONFIRMED / PARTIAL / NO_OP / DIVERGED. |
| `screen_read_selection` | Copy the focused window's selection and return it verbatim — exact text, no OCR. |
| `screen_focus` | Raise and give keyboard focus to a window by app/title/id. |
| `screen_do` | Run a batch of ordered actions in one call. |
| `screen_tour` | Visit several UI states, return a labeled thumbnail of each. |
| `screen_read_page` | Auto-scroll a scrollable view and accumulate every interactable. |
| `screen_wait` | Block until the screen settles, then optionally screenshot. |
| `screen_session` | Recorder: `start` / `stop` / `list` / `status` / `replay-path`. |
| `screen_reload` | Hot-reload the server in place after edits. |
| `screen_diag` | Health dump: session, cursor, grounding backends, world-model stats. |
| `screen_sense` | Normalized cross-layer change signal from the last frame diff (`{changed, opened, modal, no_op, activity}`) — pass the `pixel` object to os-control-mcp's `os_verify` to catch a GUI that changed while the service did not. |

## Requirements

> [!IMPORTANT]
> screen-mcp targets a specific stack. It will not run elsewhere.

- Linux + Wayland + GNOME. The awareness layer uses a bundled GNOME Shell
  extension; AT-SPI is the fallback for GTK apps.
- Python 3.10+ runtime (tested on 3.14). CI pins **3.12** because optional
  the OCR backend is `rapidocr` (v3), which supports 3.8-3.x.
- GStreamer >= 1.28 (uses `leaky-type`; the older `drop=` was removed in 1.28).
- PipeWire and `xdg-desktop-portal-gnome`.
- `wl-clipboard` for the Unicode paste path in `screen_type`.
- A DejaVu Sans Bold font for Set-of-Marks labels (falls back to PIL's default).

Grounding is CPU-only by design: the server hard-disables the GPU
(`CUDA_VISIBLE_DEVICES=""`) for predictable latency and no driver flake.

<details>
<summary>System packages</summary>

Install the system deps before the Python deps. See
[requirements.txt](requirements.txt) for the full `pacman` / `apt` one-liners.

```bash
# Arch / Manjaro
sudo pacman -S python-gobject gobject-introspection \
               gstreamer gst-plugins-base gst-plugins-good gst-libav \
               pipewire pipewire-pulse xdg-desktop-portal-gnome \
               wl-clipboard ttf-dejavu

# Python deps
pip install -r requirements.txt
```

</details>

<details>
<summary>GNOME Shell extension (recommended)</summary>

The bundled `window-info` extension gives the awareness layer reliable
focused-window and window-list data, and lets `screen_focus` activate windows
directly. Installing it needs a one-time Wayland re-login.

```bash
gnome-shell-extension/window-info@local/install.sh
gnome-extensions enable window-info@local
```

</details>

<details>
<summary>Kernel input backend (optional)</summary>

For the kernel input backend, grant access to `/dev/uinput` by adding your user
to the `input` group. The launcher (`bin/screen-mcp`) fails with a clear message
if a required dep is missing, so a misconfigured install never silently
half-works.

</details>

## Manual MCP setup

If you are not using the plugin, wire the server via the launcher (resolves host
Python / `.venv` through `scripts/run-python.sh` — never bare `python3` on thin
Claude spawn PATH). Add to `~/.claude.json` under `mcpServers`:

```json
{
  "screen": {
    "command": "/path/to/screen-mcp/bin/screen-mcp"
  }
}
```

## Configuration

screen-mcp reads optional environment variables. A few common ones:

- `MCP_SCREEN_GUARD=1` — enable the ack gate. Destructive combos
  (`Ctrl+W`, `Alt+F4`), OCR-matched destructive keywords, and out-of-allowlist
  actions block unless the caller passes `ack=<reason>`.
- `MCP_SCREEN_APPS="firefox,terminal"` — with the guard on, restrict actions to
  this allowlist of focused apps.
- `MCP_SCREEN_AMBIENT=0` — disable the ambient `SENSE` hint block.
- `MCP_SCREEN_CPU_THREADS=6` — ONNX intra-op thread count for OmniParser.
- `MCP_SCREEN_MAX_EDGE=2576` — screenshot downscale target (long edge).

<details>
<summary>All environment variables and data paths</summary>

| Variable | Effect |
|---|---|
| `MCP_SCREEN_GUARD=1` | Enable the reliability ack gate (destructive combos / keywords / out-of-allowlist actions block until `ack`). |
| `MCP_SCREEN_APPS` | With guard on, allowlist of focused apps. |
| `MCP_SCREEN_AUDIT_FRAMES=1` | Add pre/post frame hash + `changed_bbox` to each audit line (~100-500ms per action). |
| `MCP_SCREEN_AMBIENT=0` | Disable the ambient `SENSE` hint block. |
| `MCP_SCREEN_GUARD_PX=40` | Threshold for the user-takeover guard (live pointer vs last-commanded). |
| `MCP_SCREEN_CPU_THREADS=6` | ONNX intra-op thread count for OmniParser. |
| `MCP_SCREEN_MAX_EDGE=2576` | Screenshot downscale target (long edge). |
| `MCP_SCREEN_NO_FRESH=1` | Disable forced fresh-frame capture on static monitors. |
| `MCP_SCREEN_FOCUS_SETTLE_MS=150` | Delay after `screen_focus` activates a window. |
| `MCP_SCREEN_NO_NUDGE=1` | Disable the pointer damage-nudge that primes a static monitor's frame. |

| Path | What |
|---|---|
| `~/.config/mcp-screen/token` | Portal restore token (one-time consent). |
| `~/.local/share/mcp-screen/world/map.db` | World-model cache (per-screen learned elements). |
| `~/.local/share/mcp-screen/sessions/<sid>/` | Recorder trajectories, frames, `replay.html`. |
| `~/.local/state/mcp-screen/actions.jsonl` | Reliability audit log (one JSON line per action). |
| `/tmp/screen_err.txt` | Last unhandled tool traceback (dev diagnostic). |

</details>

## Development

```bash
pytest -q          # tests run without a live D-Bus (conftest stubs)
```

Edit a `.py`, then call `screen_reload` in the running session to re-exec the
server in place while preserving the MCP connection. On any tool exception the
dispatcher writes the full traceback to `/tmp/screen_err.txt`; read it when
debugging crashes.

## Contributing

Issues and pull requests are welcome. Please run `pytest -q` before opening a PR.
See [CLAUDE.md](CLAUDE.md) for architecture notes and the hard-won ops details
behind the capture and input layers.

## License

[FSL-1.1-ALv2](LICENSE) © 2026 [88plug](https://github.com/88plug). The
Functional Source License converts to Apache 2.0 two years after each release.
