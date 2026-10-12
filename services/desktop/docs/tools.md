# Tools

Source of truth: `TOOLS` in [`server.py`](https://github.com/88plug/screen-mcp/blob/main/server.py). Titles and descriptions below match the live schemas. Annotation hints: **RO** = read-only, **ACT** = mutates, **DEST** = treated as destructive in the schema.

Shared optional args on position-bearing actions are documented once in [Tool loop → Shared action knobs](tool-loop.md#shared-action-knobs).

## Capture & geometry

### `screen_screenshot` — Capture Screen (RO)

Capture the desktop, lossless, auto-sized to the model's native resolution. Use to **locate** targets (never assume which monitor) or to re-read after an action.

| Arg | Type | Notes |
|---|---|---|
| `region` | `[x,y,w,h]` | Desktop px crop/zoom |
| `monitor` | number | Zoom to monitor index |
| `annotate` | bool | Numbered Set-of-Marks + click coords |
| `use_cache` | bool | With annotate: reuse learned elements (skips OCR) |
| `regeo` | bool | Re-probe geometry / rewarm pipelines |
| `fresh` | bool | Force a **current** frame on a static monitor (default true). `false` / `settle=0` for instantaneous cached frame |

**Returns:** image + text (focused window, `SENSE` line: new elements / modal / no-op).

No args = full multi-monitor overview.

### `screen_list_monitors` — List Monitors (RO)

List monitors (origin, size, scale), desktop bounds, and open windows. Use first when choosing where to screenshot or click.

| Arg | Type |
|---|---|
| `regeo` | bool |

### `screen_wait` — Wait for Settle (RO)

Wait until the screen stops changing (or timeout), then optionally screenshot. Use after async UI instead of guessing a fixed delay. Also usable as `wait_stable` inside `screen_do` / `screen_tour`.

| Arg | Type | Notes |
|---|---|---|
| `timeout` | number | Seconds (default 5) |
| `thresh` | number | Stability threshold |
| `window` | number | Stability window |
| `region` / `monitor` | | Scope settle |
| `shot` | bool | Return screenshot when done |

### `screen_watch` — Watch at 1 fps (human-eye) (RO)

**Default visual confirm for thrashy UIs.** Samples the region/monitor at ~1 fps for several seconds and returns a timeline + verdict (`settled` \| `evolving` \| `jitter` \| `unstable`). Catches continuous animation / force-sim chaos that a single screenshot misses.

| Arg | Type | Notes |
|---|---|---|
| `region` / `monitor` | | What to watch (default last view) |
| `fps` | number | Default **1.0** (clamp 0.2–10) |
| `seconds` | number | Default **6** (clamp 1–60) |
| `annotate` | bool | OCR on first+last only (default false) |
| `shot` | bool | Final frame (default true) |
| `force` | bool | Bypass takeover guard |

**When:** graphs, maps, canvases, connection clouds, loaders, animated dashboards — or any time a human would stare for a second before saying “looks fine.”

**vs `screen_wait`:** wait returns when *stable once*; watch scores *sustained* motion over a window (jitter = fail visual QA).

## Pointer & keyboard

### `screen_move_mouse` — Move Mouse (ACT)

Move mouse to `x,y` (view-space default) or `dx,dy` relative. Use before click when you need an explicit hover position.

### `screen_click` — Click (ACT)

Click at `x,y` (view-space; mapped to the real screen). Omit `x,y` to click in place.

| Arg | Type | Notes |
|---|---|---|
| `x`, `y` | number | Target (view space default) |
| `element` | number | Id from last annotate |
| `button` | string | `left` \| `right` \| `middle` |
| `double` | bool | Double-click |
| + shared knobs | | `space`, `view_id`, `focus`, `shot`, `verify`, `force`, … |

### `screen_scroll` — Scroll (ACT)

Wheel scroll by direction and amount. Use to reveal off-screen content before screenshot. Optional `x,y` to position first.

| Arg | Type | Notes |
|---|---|---|
| `direction` | string | `up` \| `down` \| `left` \| `right` |
| `amount` | number | Notches |
| `x`, `y` | number | Optional position first |

### `screen_drag` — Drag (ACT)

Press-drag from `(x1,y1)` to `(x2,y2)` in view-space. Use for sliders, reorder, selection.

| Arg | Type | Notes |
|---|---|---|
| `x1`, `y1`, `x2`, `y2` | number | **Required** |
| `button` | string | `left` \| `middle` \| `right` |
| `modifiers` | array | Keys held for the whole gesture, e.g. `["shift"]` |
| `space`, `view_id`, `shot`, `force`, `region`, `settle` | | |

`modifiers` is what makes text selection work in a terminal running a TUI. Claude Code,
vim and htop enable mouse tracking, so they consume the drag themselves and no terminal
selection is ever made — a `screen_read_selection` afterwards then copies nothing.
`modifiers: ["shift"]` makes the terminal emulator bypass the app's mouse grab and do its
own selection. Modifiers release in a `finally`; a stuck Shift would corrupt later keys.

### `screen_key` — Press Key (ACT)

Press a key or combo: `Ctrl+L`, `Enter`, `Alt+Tab`, `F5`. Keys go to the **focused** window — pass `focus='appname'` first if needed.

| Arg | Type | Notes |
|---|---|---|
| `keys` | string | **Required** |
| `focus` | string | Raise + focus before key |
| `shot`, `verify`, `force`, `region`, `settle` | | |

### `screen_type` — Type Text (ACT)

Type text (Unicode ok via clipboard paste; ASCII via keysyms). `enter=true` presses Enter after. Text goes to the **focused** window.

| Arg | Type | Notes |
|---|---|---|
| `text` | string | **Required** |
| `enter` | bool | Press Enter after |
| `focus` | string | Raise + focus before type |
| `shot`, `verify`, `force`, `region`, `settle` | | |

### `screen_verify` — Verify Last Action (RO)

Did the last action actually do what you expected? Returns a **verdict**, not pixels.

| Verdict | Meaning |
|---|---|
| `CONFIRMED` | Every check you asked for passed |
| `PARTIAL` | Some passed |
| `NO_OP` | The screen never changed — the click missed, or keys went to the wrong window |
| `DIVERGED` | Something changed, but not what you expected |

| Arg | Type | Notes |
|---|---|---|
| `expect_text` | string | Text that should now be on screen |
| `expect_gone` | string | Text that should no longer be on screen |
| `expect_change` | bool | Require the screen to have changed at all (default true) |
| `timeout` / `interval` | number | Default 5 s / 0.25 s |
| `region` / `monitor` | | Scope |

Verdicts use the same vocabulary as os-control-mcp's `os_verify`, and the returned
`pixel` block is exactly what `os_verify` consumes — so a GUI verdict and an OS verdict
read the same way and compose.

!!! warning
    The change check re-grabs the **same monitor node** the pre-action baseline was taken
    from. Hashing a region crop against a whole-frame baseline compares different images,
    so it always differs — which made every action, including an inert mouse move, grade
    `CONFIRMED`. With no baseline node, `changed` is reported as `null` and excluded from
    the verdict rather than invented.

Measured: an inert mouse move → `NO_OP`; a hover that highlights a menu item →
`CONFIRMED` in 23 ms.

#### Cross-layer: pairing with `os_verify`

The `pixel` block this returns is the contract os-control-mcp's `os_verify` consumes, so
a GUI verdict and an OS verdict compose into one answer:

```
os_verify     action=begin  units=["nginx.service"]      -> token
screen_click  ...                                         (do the thing)
screen_verify expect_text="Restarted"                     -> {"verdict":..,"pixel":{"changed":true}}
os_verify     action=end    token=<token> pixel={"changed":true}
```

Verified live, both quadrants:

| GUI | OS | `os_verify` status | `cross_layer` | reconciled |
|---|---|---|---|---|
| changed | static | `DIVERGED` | `pixel-changed-os-static` | `false` |
| static | static | `NO_OP` | `null` | `true` |

`pixel-changed-os-static` is the one to care about: the button "worked" visually and did
nothing real.

### `screen_wait_text` — Wait for Text (RO)

Block until `text` appears on screen (or timeout), then return its click coords. Use
instead of screenshotting in a loop to see whether something finished.

| Arg | Type | Notes |
|---|---|---|
| `text` | string | **Required** — substring, case-insensitive, whitespace-tolerant |
| `timeout` | number | Seconds, default 10 |
| `interval` | number | Poll seconds, default 0.25 |
| `region` / `monitor` | | Scope the watch |

**Returns:** `{found,text,x,y,ms,grabs,ocr_passes}`.

Grounding costs seconds; a grab costs ~35 ms. So this polls the frame **hash** and only
pays for perception when the pixels actually changed — a static screen is nearly free to
wait on (measured: 11 grabs, 1 OCR pass over 10 s). It also recalls from and writes to the
world model, so a repeat wait on a learned screen skips OCR entirely: **8574 ms → 41 ms**.

!!! note
    Matching is whitespace-tolerant on purpose. OCR renders the same button as
    `Launch installer` or `Launchinstaller` between runs, so a literal substring test
    misses text that is plainly on screen.

### `screen_read_text` — Read Screen Text (No Image) (RO)

Return what is on screen as **text + click coords**, with no image block.

A screenshot costs a fixed `ceil(w/28) * ceil(h/28)` visual tokens — **4784 for a 4K
monitor** — no matter how small the encoded file gets. For navigate-by-text work the pixels
are not what you need. Measured on a 4K monitor:

| Read | Tokens | Latency |
|---|---|---|
| `screen_screenshot` | 4784 | 412 ms |
| `screen_read_text` (104 elements) | ~1350 | 67 ms |
| `screen_read_text` + `contains=` | ~95 | 67 ms |

| Arg | Type | Notes |
|---|---|---|
| `region` | array | `[x,y,w,h]` desktop px |
| `monitor` | number | |
| `contains` | string | Only elements whose text contains this (case-insensitive) |
| `use_cache` | bool | Reuse learned elements for a known screen, skipping OCR (default true) |

Same perception path as `screen_screenshot(annotate=true)` minus the encode and the image:
world-model recall first (a cache hit skips OCR entirely — 7747 ms → 42 ms measured), else
grounding. Coordinates come back in **desktop** space, so they are directly clickable.

### `screen_read_selection` — Read Selection (Exact Text) (ACT)

Copy the **focused** window's current selection and return it verbatim. Prefer this over
screenshot + OCR whenever characters must be exact: a full-monitor shot downscales 4K to
2576 px and measurably drops ~8% of characters on sub-12px code, while a copy is lossless
and skips the grounding pass entirely.

Select first (click/drag, or `select_all=true`). The clipboard is **cleared before** the
combo is sent, so an empty read proves nothing was copied rather than silently returning
whatever the clipboard already held. The user's clipboard is saved and restored either way.

| Arg | Type | Notes |
|---|---|---|
| `select_all` | bool | Send `ctrl+a` first to grab the whole buffer |
| `combo` | string | Copy combo; default `ctrl+c`. **Terminals need `ctrl+shift+c`** |
| `focus` | string | Raise + focus before copying |
| `force` | bool | Bypass the takeover guard |

Needs `wl-clipboard`. A TUI that grabs the mouse (Claude Code, vim, htop) swallows
drag-select — hold Shift while dragging to force a real terminal selection.

### `screen_focus` — Focus Window (ACT)

Raise and give **keyboard focus** to a window so injected keys/clicks land in it. Use before `screen_type` / `screen_key` on an app you have not clicked into (the #1 reason typing appears to do nothing).

| Arg | Type | Notes |
|---|---|---|
| `app` | string | e.g. `slack`, `firefox` |
| `title` | string | Title substring |
| `id` | string \| number | Window id from `screen_list_monitors` |

## Multi-step helpers

### `screen_do` — Batch Actions (DEST)

Run an ordered batch of actions in one call to cut round-trips.

| Arg | Type | Notes |
|---|---|---|
| `steps` | array | **Required.** `[{action:'move\|click\|scroll\|drag\|key\|type\|wait\|wait_stable', ...}]` |
| `stop_on_error` | bool | Stop mid-batch on failure |
| `shot` | bool | Final screenshot |
| `force` | bool | Batch-level takeover bypass |
| `region` / `monitor` / `settle` | | |

Stops mid-batch if the human takes the mouse (`force=true` to override). Returns per-step results.

### `screen_read_page` — Read Page (ACT)

Auto-scroll a scrollable view until content stops moving, annotating each screen. Use instead of N rounds of scroll+screenshot. Leaves the current screen clickable by element id.

| Arg | Type | Notes |
|---|---|---|
| `region` | `[x,y,w,h]` | Defaults to last view |
| `max_pages` | number | Cap pages |
| `amount` | number | Scroll notches per step |
| `settle_ms` | number | Settle between pages |
| `force` | bool | Bypass takeover guard |

### `screen_tour` — Tour UI States (DEST)

Visit several UI states in one call; return a labeled thumbnail of each.

| Arg | Type | Notes |
|---|---|---|
| `steps` | array | **Required.** `[{label, steps:[{action:…}], region?, settle?}]` |
| `settle` | number | Default settle between stops |
| `shot_max_edge` | number | Thumbnail long edge (default 1280) |
| `force` | bool | |

## Session, reload, diagnostics

### `screen_session` — Record Session (ACT)

Session recording / replay.

| Arg | Type | Notes |
|---|---|---|
| `op` | string | `start` \| `stop` \| `list` \| `status` \| `replay-path` |
| `id` | string | Session id where applicable |

Trajectories land under `~/.local/share/mcp-screen/sessions/<sid>/` (frames + `replay.html`).

### `screen_reload` — Reload Server (DEST)

Hot-reload this MCP server's own code in place (re-exec, preserving the connection). Use after editing server code so tools update without `/mcp` reconnect.

### `screen_diag` — Diagnostics (RO)

Health dump: prereqs matrix (portal, window-info, uinput, GStreamer, …) with `next_step` hints; session/geo; cursor/guard state; grounding backends. **First tool to call** when capture, clicks, or the cursor guard misbehave.

### `screen_sense` — Cross-Layer Pixel Signal (RO)

Return the normalized change signal from the most recent frame diff — `{changed, opened, modal, no_op, activity}` — so a verifier (os-control-mcp's `os_verify`) can fuse the GUI layer with the OS layer. Call right after a screen action, then pass the `pixel` object to `os_verify` (`action=end`). Catches a GUI that changed while the underlying service did not.

## Tool inventory (quick table)

| Tool | Title | Hint |
|---|---|---|
| `screen_screenshot` | Capture Screen | RO |
| `screen_list_monitors` | List Monitors | RO |
| `screen_move_mouse` | Move Mouse | ACT |
| `screen_click` | Click | ACT |
| `screen_scroll` | Scroll | ACT |
| `screen_drag` | Drag | ACT |
| `screen_key` | Press Key | ACT |
| `screen_type` | Type Text | ACT |
| `screen_read_text` | Read Screen Text (No Image) | RO |
| `screen_wait_text` | Wait for Text | RO |
| `screen_verify` | Verify Last Action | RO |
| `screen_read_selection` | Read Selection (Exact Text) | ACT |
| `screen_focus` | Focus Window | ACT |
| `screen_do` | Batch Actions | DEST |
| `screen_read_page` | Read Page | ACT |
| `screen_tour` | Tour UI States | DEST |
| `screen_wait` | Wait for Settle | RO |
| `screen_watch` | Watch (1 fps human-eye) | RO |
| `screen_session` | Record Session | ACT |
| `screen_reload` | Reload Server | DEST |
| `screen_diag` | Diagnostics | RO |
| `screen_sense` | Cross-Layer Pixel Signal | RO |

Eighteen tools. If this page and a live `tools/list` disagree, trust the running server and open an issue.
