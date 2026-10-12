# CLAUDE.md — mcp-screen

An MCP server that drives this machine's Wayland desktop (screenshot, click, type, scroll,
drag, multi-screen tour) over the xdg-desktop-portal RemoteDesktop + ScreenCast APIs. Pure
Python, CPU-only, no GPU. Distribution version is rolling calver (`YEAR.MONTH.<commit-count>`,
same formula as the 88plug hub) from `version.py` → `server.__version__`.

## How to run / test

- **Tests:** `pytest` from the repo root (config in `pyproject.toml`, `pythonpath=["."]`).
  Tests import project modules at top level and run on synthetic numpy arrays — no portal,
  no display needed. 78 tests as of v1.2.2.
- **The server** is launched by an MCP client over stdio (`python server.py`); it speaks
  JSON-RPC on stdin/stdout. Don't run it by hand to "test" — drive it through the MCP tools
  or write a pytest.
- After editing a module, `python -m py_compile <file>` is the fast sanity check.

## Architecture (one persistent portal session, per-monitor capture pipelines)

`state.py` owns the single combined RemoteDesktop+ScreenCast portal session, the D-Bus bus,
and the shared mutable `SESSION` dict. **Every other module imports `state`; `state` imports
no app module** (keeps the dep graph acyclic — preserve this).

Request flow: `server.main()` reads JSON-RPC lines from stdin (single-threaded loop) →
dispatches via `HANDLERS` → tool handler. The six action tools (`move/click/scroll/drag/
key/type`) route through `server._action` → `inp.guard_user` (takeover guard) → optional
`_verify` (no-op detection).

Module map:
- `state.py` — portal session, D-Bus, `SESSION`, `open_pw_fd()`. Foundation.
- `capture.py` — one **persistent** `pipewiresrc→appsink` GStreamer pipeline **per monitor
  node**, kept PLAYING. `grab()` pulls the freshest frame; `ensure_geo()` computes per-monitor
  native-px geometry + canvas bounds; `_full_canvas()` composites. Cursor position is read
  from `SPA_META_Cursor` via **ctypes at arch-selected struct offsets** (`get_cursor_meta_offsets()`,
  LP64 x86_64/aarch64; unknown arch fails open). PyGObject can't downcast the meta — load-bearing.
- `input.py` — pointer/keyboard injection. Prefers `uinput_backend` (kernel-level) when
  available, falls back to the portal `Notify*` path. Coordinate spaces: view (last screenshot
  px, default) → desktop (global native px) → logical (per-stream, what the portal wants).
  `resolve_xy` and `global_to_logical` are the converters.
- `uinput_backend.py` — kernel-level input via python-evdev: a true absolute pointer (ABS_X/Y
  mapped 1:1 to the full native desktop) + a separate relative wheel device + keyboard. Lands
  clicks/keys exactly regardless of monitor/scaling/static state, bypassing the portal's
  unreliable per-stream motion. Needs `/dev/uinput` writable (group `input` + udev rule) +
  python-evdev; reports unavailable otherwise. Opt out: `MCP_SCREEN_NO_UINPUT=1`.
- `grounding.py` — the ML perception layer: **OmniParser icon_detect (YOLOv8 ONNX, ~11.6MB,
  CPU) + RapidOCR v3 + OpenCV**. Detects UI elements → bounding boxes + click coords.
- `worldmodel.py` — **NOT an ML model.** A SQLite write-through cache of grounding output,
  keyed by `(app, title)` bucket × a 64-bit dHash of the frame. On revisit within
  `HAMMING_MAX` bits it returns cached element coords instead of re-running OCR. (See research:
  `docs/v1.1-grounding-research.md`.)
- `reliability.py` — frame-stability + no-op/misclick detection primitives (pure numpy,
  no capture import — the grabber is injected). Also the opt-in destructive-action ack gate
  (`needs_ack`, env `MCP_SCREEN_GUARD=1`): blocks window-close combos / destructive-keyword
  clicks until the caller passes a confirmation token. `wrap_call` is the integration wrapper
  (currently defined but not wired into the live server).
- `awareness.py` — focused-app/title + window list + **window activation** via the optional
  `window-info@local` gnome-shell extension (degrades to "unavailable" without it). `find_window`
  + `activate_window` drive the extension's `ActivateWindow(id)` (Mutter `activate()` = raise +
  KEYBOARD focus). The extension must be installed AND the user must log out/in ONCE (Wayland
  can't hot-load a new extension); until then awareness is unavailable and focus uses the
  overview fallback (`inp.activate_via_overview`).
- `recorder.py` — replayable session recording. `autoloop.py` — `screen_read_page` scroll
  capture. `sense.py` — per-frame element-diff "SENSE" signal in tool responses.
- `server.py` — MCP protocol, tool schemas, dispatch, `main()`.

## Invariants & gotchas (don't regress these)

- **Each persistent pipeline needs its OWN PipeWire fd** (`state.open_pw_fd()`); sharing one
  starves concurrent streams. `capture.shutdown()` must run on **every** server exit path
  (stdin EOF, signals, atexit) or the pipelines leak and keep pulling 4K buffers — this was
  the v1.0 live bug. Don't remove the try/finally + signal handlers + `os._exit(0)` in `main()`.
- **`worldmodel` ≠ ML model.** It's a dHash + SQLite cache. `HAMMING_MAX` default is **5**
  (tightened from 10 in v1.0 — looser values confuse sibling sub-pages of the same app and
  return wrong cached coords). Env override: `MCP_SCREEN_MAP_HAMMING`.
- **The takeover guard baseline** (`SESSION["cmd_cursor"]`) is set to the COMMANDED coords
  (not a cursor readback): `cursor_mode=METADATA` only updates the cursor on a fresh frame, so
  on a static monitor a readback is stale/cross-monitor and false-fired `UserControlError`,
  silently aborting clicks/scrolls. `guard_user` pins its read to `cmd_node` and fails open on
  a cross-monitor reading. (v1.2 — was the readback before.)
- **View transform is stamped + stale-guarded (`view_id`).** Screenshot→click is 1:1 (verified):
  the click lands at the pixel shown. `SESSION["view"]` (origin/scale) is a SINGLE slot that
  every `encode_store` overwrites, and `resolve_xy` always uses the latest — so coords read from
  screenshot A, applied after screenshot B rebound the view, map through B's transform and land
  wrong (wrong monitor, even). Each shot now carries a monotonic `id` (`state.next_view_id()`,
  echoed as `view#N`); a view/norm-space action may pass `view_id=N` and `resolve_xy` raises
  `StaleViewError` (surfaced as `STALE VIEW:` by `_action`'s pre-check) if a later screenshot
  superseded it. Guard is inert without an explicit `view_id` (back-compat) and ignored for
  `space='desktop'`. This is the #1 generic cause of "I clicked where I saw it but it missed" —
  not app behavior. Don't collapse the per-shot id back to a bare transform.
- **ONE unified uinput device** (pointer + buttons + keyboard + wheel), tagged
  `INPUT_PROP_POINTER`. Do NOT split pointer and wheel onto separate devices: under Wayland a
  scroll is routed to the seat's pointer-FOCUSED surface (set by a prior `enter` from pointer
  motion), so a wheel device whose own pointer never moved has no focus and Electron/Chromium
  drops its axis (GTK is laxer — that mismatch is why a terminal scrolled but an Electron pane
  didn't). `scroll()` positions the cursor (the enter) then emits the wheel on the SAME device:
  `REL_WHEEL_HI_RES ±120` + legacy `REL_WHEEL ±1` per notch, like a real hi-res mouse. Release
  the device on `screen_reload` (`inp.ui.shutdown()`) so reloads don't leak/confuse routing.
  This is GENERIC — it makes scroll/click/keys land in any app (Electron, GTK, browsers),
  not a Slack-specific patch.
- **Change-gated capture, not just stable-gated (anti-stale, app-agnostic).** After an action,
  `tool_screenshot` waits for the watched frame's hash to DIFFER from a pre-action baseline
  (`reliability.wait_for_changed_frame`) before settling — because on a damage-driven static
  monitor `wait_for_stable_frame` is satisfied instantly by a REPEATED stale frame, and a
  keepalive resend carries old pixels with a fresh timestamp. Without this, a SUCCESSFUL
  action looked like a no-op (we read the pre-action frame). `_action` stamps
  `last_input_hash`/`last_input_node` before running the handler. This fixed the "nothing
  happened" misreads everywhere, not just Slack.
- **Fresh-frame capture defeats the keepalive-resend stale read (v1.2.2, app-agnostic).** The
  change-gate above only runs right AFTER an action; a plain `screen_screenshot` (or `shot=true`
  result shot) of a damage-driven static monitor would still return the keepalive-RESENT
  byte-identical PRE-change buffer — `grab()` SUCCEEDS with a stale frame, so `_grab_or_prime`
  never primes. `capture.force_fresh_grab` fixes it: pull once, and if the monitor looks static
  (`live:false`, or the pull is byte-identical to the last `_LAST_SIG` sample) generate a damage
  event (`_nudge_prime`, which restores the pointer) and use the post-damage frame. Wired as
  `capture_desktop(fresh=...)`. **Used SPARINGLY, not on every shot (v1.2.3):** forcing a fresh
  frame MOVES THE POINTER (a damage nudge) — doing it per screenshot makes the screen visibly
  "flash"/jitter during active driving (the v1.2.2 regression: `fresh` defaulted ON everywhere).
  Now `tool_screenshot` defaults `fresh` ON only right after an action whose effect the change-gate
  could NOT confirm (`recent_input and not changed` — the genuinely-stuck static case); `_maybe_shot`
  defaults it OFF (an action that changed the screen already produced a current frame). Pure
  observation shots read the cached frame (on static content == "now" anyway). Explicit `fresh=true`
  forces it; `settle=0`/`MCP_SCREEN_NO_FRESH=1` opt out. `_nudge_prime` wiggles ±3px IN PLACE when
  the pointer is already on the target monitor (vs jumping to center). Generic: ANY app on ANY idle
  monitor. NOTE: this fixes CAPTURE staleness (seeing results), NOT keyboard landing — see below.
- **Keyboard lands in the FOCUSED window — `screen_focus` is the fix, not timing (v1.3).** Keyboard
  events carry no position; the compositor routes them to the keyboard-FOCUSED surface. A
  background / static-monitor app does NOT have keyboard focus, so `screen_type`/`screen_key`
  silently land in the wrong window — this (NOT a frame-throttle; Mutter delivers input to idle
  outputs unthrottled, MR !1915) is "I typed but nothing happened." **PRIMARY FIX = click-to-focus:
  a real pointer CLICK on a window focuses it on any Wayland compositor — zero setup, works
  everywhere.** So the rule is: click into an app (or its message area) before a keyboard burst.
  The bug that broke this on static monitors was the takeover guard FALSE-FIRING: the uinput input
  paths set `cmd_cursor` but NOT `cmd_node`, so `guard_user`'s cross-monitor fail-open (which needs
  `cmd_node`) was skipped, the stale cross-monitor cursor readback tripped the 40px threshold, and
  it both aborted the action AND aborted capture's `_nudge_prime` (→ stale frames). Fixed (v1.3.1):
  `inp._set_cmd(Gx,Gy)` sets BOTH on every uinput move/click/scroll/drag (mirrors `_goto`). Keep it.
  `screen_focus`/`focus="app"` are conveniences that activate by name — they use the OPTIONAL
  `window-info` extension's `ActivateWindow` (`Meta.Window.activate(get_current_time_roundtrip())`;
  the roundtrip ts is load-bearing) IF it's loaded, else fall back to the overview (Super→type→Enter,
  which RAISES but doesn't reliably keyboard-focus). **The extension is NEVER required and is NOT
  installed by default** (loading a new gnome-shell extension needs a Wayland re-login, which we do
  NOT assume) — design principle: the tool must work with the running session as-is. `_do_focus`/
  `tool_focus` call `capture.ensure_geo()` first (focus may be the FIRST call after a reload; input
  needs a live handle / known W/H or both backends throw `GLib.Variant ... None`).
- **Capturing a truly-idle SECONDARY monitor on demand is an inherent GNOME limit, not a bug.**
  It streams only on damage; a cursor-nudge over a static page produces none, and no portal API
  forces a frame. In practice this is fine: an ACTION that changes the screen IS damage → the
  change-gate catches the resulting frame. The pure "observe an idle monitor that nothing changed"
  case is where capture can't get a current frame — surface the ON-but-STATIC hint, don't spin.
- **No-op retry RE-OBSERVES, never re-issues** the action (would double-type / double-click).
- **Wait steps are clamped** by `MAX_WAIT_MS` (default 30s, env `MCP_SCREEN_MAX_WAIT_MS`) —
  the stdin loop is single-threaded, so an unbounded `time.sleep` freezes the whole server.
- **No-frame monitors: ON-but-static vs DPMS-off.** GNOME/Mutter negotiates framerate 0/1
  (send-on-damage), so a monitor that is powered ON but STATIC (Slack idle, no cursor, no
  animation) emits NO PipeWire buffer until something on it changes — it is NOT asleep.
  `live:false` in `screen_diag` geo means "no frame seen", not "DPMS-off". `ensure_geo()`
  therefore probes real power state via `org.gnome.Mutter.DisplayConfig.GetCurrentState`
  (`awareness.monitor_power()`) and stores a per-monitor `power` field (on/off/unknown). For a
  no-frame monitor that is power=on/unknown it NUDGES the pointer onto that monitor (a damage
  event) and retries the grab once to prime the first frame — pointer is restored afterward,
  the takeover guard is respected, and it's opt-out via `MCP_SCREEN_NO_NUDGE=1`. keepalive-time
  only re-sends an EXISTING last buffer and resend-last is EOS-only, so neither primes a
  never-damaged source — the damage nudge is the only lever (no portal API forces a frame).
  `capture.asleep_hint()` words its message off `power`: "ASLEEP (DPMS)" ONLY when power=off,
  "ON but STATIC" when on, hedged when unknown. A genuinely DPMS-off output still can't be
  captured (nothing to capture, agent can't wake it) — don't regress that path into a cryptic
  error, and don't try to force frames from a truly blanked output.
- **Fail-open philosophy:** capture/cursor/guard failures return None/skip rather than raise,
  so a degraded subsystem never breaks the desktop tools. Keep new code in this style, but
  prefer signaling an error over returning plausible-but-wrong results.
- **Version is single-sourced** from `version.distribution_version()` → `server.__version__`
  (rolling calver; install-dir basename or `git rev-list --count`); both `serverInfo` and `screen_diag`
  reference it. Bump in one place.

## Conventions

- Default to **no comments**; add one only when the *why* is non-obvious (the ctypes offsets,
  the fd-per-pipeline rule, the guard-residual reasoning are good examples of warranted ones).
- Match the terse, dense style of the surrounding code and docstrings.
- Tunables are env-overridable module constants, not hard-coded magic numbers.
- `screen_diag` is the first thing to check when capture/clicks/cursor misbehave.

<!-- drift-detector:start -->
<!-- calibrated 2026-07-26 · last 50 sessions · 50 sampled · drift rate 40.1% -->

## Anti-drift (auto-calibrated from real session data)

Drift observed in 40.1% of turns across 50 recent sessions.

- **Verbosity (long sentences)** (fires in ~100% of drifted turns): Break sentences at conjunctions. Target ≤15 words/sentence.
- **Response length** (fires in ~100% of drifted turns): Lead with the answer; cut trailing restatements.
- **Sentence complexity** (fires in ~100% of drifted turns): Prefer parallel short clauses over embedded subordinates.
- **Filler / pleasantry words** (fires in ~19% of drifted turns): Cut openers: "Sure!", "Certainly!", "Of course!", "Great question!".
- **Hype** (fires in ~1% of drifted turns): Reduce this pattern.

<!-- drift-detector:end -->
