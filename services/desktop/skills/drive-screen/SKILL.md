---
name: drive-screen
description: >-
  See and operate the user's real, physical Linux desktop through the mcp-screen MCP — screenshot any monitor and click/type/scroll/drag any visible app. Prefer screen_watch (~1 fps) after graphs/maps/canvases/loaders so thrashing UIs are caught like a human watches, not one freeze-frame. Use whenever the user points at something on their monitor(s) or wants you to read/drive a real GUI (Slack, browser, terminal, dashboards). Prefer over app/web APIs when looking at the real screen. NOT for pasted images, local files, shell-only, or remote SSH/TUI. Encodes locate → ground → act → confirm/watch plus hard-won gotchas.
---

# Driving the desktop with mcp-screen

A loop, not a single call: **locate → ground → act → confirm (watch)**. The tools are `screen_screenshot`, `screen_click`, `screen_type`, `screen_key`, `screen_scroll`, `screen_drag`, `screen_move_mouse`, `screen_read_page`, `screen_do` (batch), `screen_tour`, `screen_wait`, **`screen_watch`**, `screen_diag`, `screen_reload`, `screen_session`.

## Human eyes, not a single glance

screen-mcp is supposed to see like a human. Humans do **not** decide a UI is fine from one freeze-frame — they watch for a beat. A force-directed graph with 500 nodes, a spinning loader, or a canvas thrashing looks "ok" in one shot and **crazy** over 3–6 seconds.

**Default confirm path after anything that can thrash** (graphs, maps, canvases, loaders, animated dashboards, connection clouds):

```text
screen_watch(region=[…], fps=1, seconds=6)
```

| Verdict | Meaning | Agent must |
|---|---|---|
| `settled` | Quiet at end of window | Safe to act / pass visual QA |
| `evolving` | Navigation/layout mid-watch | Re-ground on the **final** frame |
| **`jitter`** | Sustained local motion | **Fail visual QA** — fix the product (cap nodes, freeze sim). Do not report "looks good" |
| `unstable` | Mixed noise | Watch longer or re-ground |

Do **not** ship or declare a UI fix verified on a single screenshot when the surface is animated. That is how connection clouds "look crazy" slip past agents.

## The efficient loop

1. **Locate (once):** `screen_screenshot()` with no args = full multi-monitor overview. Use it ONLY to find where the target is and which monitor. It's the slowest shot — don't loop on it.
2. **Ground:** `screen_screenshot(region=[x,y,w,h])` to zoom in crisp, or add `annotate=true` to get OmniParser-numbered elements with exact `desktop(x,y)` click coords. A small region shot is the fastest and sharpest read.
3. **Act:** `screen_click`/`screen_type`/etc. Default `space='view'` uses the coords as seen in the **latest** screenshot. To click a grounded element, pass `element=<id>` from the last `annotate=true` (server resolves exact coords — no guessing). **The screenshot is ground truth: whatever is shown at a pixel, a click at that pixel lands there (1:1, verified).** A click that seems to "miss" is almost never the app and never a coordinate offset — it's acting on coords from an *older* screenshot than the one currently in effect (see "Coords belong to ONE screenshot").
4. **Confirm:**
   - Simple control toggle → one post-shot + `SENSE` line is enough.
   - **Anything that can thrash → `screen_watch` at ~1 fps (default).** Verdict `jitter` = catch it like a human.
   - After an action the capture **auto-settles** before a one-shot; if a *static-monitor* read looks stale, `fresh=true`.

## Speed & accuracy rules (learned the hard way)

- **Region-first, always.** `region=[x,y,w,h]` shots are ~100–300ms and razor-sharp; the full composite is ~1s and downscaled. Locate with full, then work in regions.
- **Trust the auto-settle.** Don't add manual `screen_wait`/sleeps after an action before screenshotting — the screenshot already settled the frame (and force-refreshes once if a static monitor didn't emit the post-action frame). Use `settle=0` for the raw instantaneous frame. Forcing freshness nudges the pointer (a visible flash), so it's deliberately sparing — reach for `fresh=true` only when a static-monitor read actually looks stale, not routinely.
- **Ground before clicking when precision matters.** For dense UIs, `annotate=true` + `element=<id>` beats eyeballing pixel coords. Re-ground if a `SENSE` "nothing changed" comes back.
- **Read long/scrollable content in ONE call:** `screen_read_page` auto-scrolls and accumulates — don't hand-loop scroll+screenshot.
- **Batch known sequences** with `screen_do=[...]` to cut round-trips; survey several screens with `screen_tour`.
- **`screen_diag` first** whenever capture/clicks/cursor act up — it shows live geo, per-monitor `power`/`live`, cursor, and grounding health.

## Coords belong to ONE screenshot (the #1 generic failure)

Every screenshot prints a `view#N` in its text and maps view-space coords through *that* shot's origin/scale. The transform is a single slot that **every new screenshot overwrites**. So coords you read from `view#7` are only valid until the next screenshot rebinds the view to `view#8` — apply them afterward and they map through the wrong origin/scale and land somewhere else (a region-zoom vs full-overview mismatch can be off by a thousand pixels, even the wrong monitor). This, not "the app rejected it," is what's behind nearly every click that doesn't land.

- **Click from the screenshot you just took.** The simplest rule: screenshot → read coords → click, with no other screenshot in between. A full screenshot always shows you exactly where to click/type/scroll/drag — use *that* shot's coords.
- **Bind the coords: pass `view_id=N`.** When you take more than one screenshot before acting (locate-full then zoom-region, or a tour), pass `view_id=<the N from the shot you read>` on the click/move/scroll/drag. If a later screenshot has superseded it, the action is **rejected** with `STALE VIEW: …` instead of landing wrong — re-screenshot and use fresh coords. This makes "where I clicked" unambiguous.
- **Or use `space='desktop'`** with absolute global px — those are transform-independent and never go stale (the `desktop(x,y)` coords from `annotate=true`, or `element=<id>`, already are absolute).

## Known gotchas

- **"ON but STATIC" monitor → just WAKE IT like a human: click or scroll a safe spot on it, then read.** GNOME streams only on *damage*, so an idle monitor emits no frame until something on it changes — that's not a wall, it's the same as a human glancing at a dark-ish screen and nudging it. The reflex when a capture returns the `ON but STATIC` hint: do ONE interaction ON that monitor — `screen_scroll` a notch (guaranteed damage, content moves) or `screen_click` something that visibly repaints (a message, a button — NOT dead whitespace, which doesn't repaint), then screenshot. It's now live. If a region grab still 404s a frame (cold pipeline after a reload/long idle), `screen_screenshot(regeo=true)` re-probes + rewarms the pipelines and the full composite comes back. `live:false` in `screen_diag` = "no frame seen yet," not "off." Only call it genuinely ASLEEP/DPMS (ask the user to wake it) if interaction + regeo BOTH fail — don't jump to that.
- **You can't drive a sleeping monitor.** Capture and input both need the monitor awake and the target app foregrounded. If the app isn't on screen, ask the user to bring it up — don't fabricate what you can't see.
- **The user-takeover guard will STOP you** if the live cursor drifts from where you last commanded it (the user grabbed the mouse). Re-issue with `force=true` to take control back — but only when the user has handed control back.
- **If a click "doesn't work," check coord-staleness FIRST, not the app.** Before concluding "this view isn't navigable" or "the app rejected it," confirm you clicked coords from the *current* `view#N` (pass `view_id` and watch for `STALE VIEW`). A fresh full or region screenshot followed immediately by a click on what you see there works in essentially every app. Only after that's ruled out should you consider an app quirk (e.g. a list row that genuinely needs a double-click, or a digest pane with no row handler) — and then switch to the app's primary navigation (sidebar entry, or its search/quick-switcher like Ctrl+K) rather than re-clicking the same spot.
- **Keyboard goes to the FOCUSED window — CLICK into the app first (universal, no setup).** `screen_type`/`screen_key` land in whatever window holds keyboard focus, NOT the one you're looking at — a background/static-monitor app gets nothing, your keys go elsewhere. The reliable, works-everywhere fix is **click-to-focus**: `screen_click` into the target window (its message area / an empty content spot) right before typing — a real click focuses the window on any Wayland compositor, and also wakes a static monitor (the click is damage). This is the fix for "I typed but nothing happened" — it's a focus problem, not a frame-throttle (idle outputs still receive input). After clicking, screenshot to confirm before the burst.
- **`screen_focus(app=..)` / `focus="app"` are conveniences — not required.** They activate a window by name (handy when it isn't visible to click). They use an optional GNOME-shell helper if present, else the overview (which RAISES the window but may not reliably keyboard-focus it on a multi-monitor static setup). So if keys still don't land after `screen_focus`, fall back to the universal path: surface the window (it's now raised), then `screen_click` into it to take keyboard focus, then type. Never tell the user to install anything or re-login — the tool must work with their session as-is.
- **Read the WHOLE window, not one region, before concluding content is missing.** A maximized app window spans the full monitor (e.g. 0–2160 px tall), but a `region` shot only shows the slice you asked for. If you read the lower half of a chat/list and scrolling "does nothing," the rest is likely in the half you didn't capture — widen the region to the full window (or capture top and bottom halves) before deciding the content is short or the scroll failed. Pair this with `screen_diag` geo to know the window/monitor bounds.
- **One app can have several distinct windows — pick the right one.** The same app may run as multiple windows with different purposes (e.g. a notifications-only window vs the full workspace; or a web app open in one of many browser windows). If a window looks like the app but lacks the view you need, it's probably the wrong window — locate the right one in the `Super` overview (its hover tooltip shows the window title) and activate that. When focusing via search, search the *application* (e.g. the browser) name, not the page title.
- **Scroll works in any app (Electron, GTK, browsers)** via the unified uinput device — it positions the cursor over the target (giving the surface pointer focus) then emits the wheel on the same device, which is what Electron/Chromium require. Pass `x,y` (or rely on the last view's center) so it scrolls the pane you mean. After scrolling, the screenshot waits for the frame to actually CHANGE before returning, so you see the post-scroll content (not a stale frame). If a scroll truly doesn't move (rare), re-ground and confirm you're over the scrollable pane, not a fixed header.
- **Input backend:** when `screen_diag` shows `uinput.available:true`, clicks/keys/scroll go through a kernel-level unified pointer device (exact landing, monitor-state-independent, scroll lands in Electron). Otherwise the portal path is used (less reliable for motion/scroll on static monitors). Needs `/dev/uinput` writable + python-evdev.
- **After editing mcp-screen's own code**, `screen_reload` re-execs the server in place (no `/mcp` reconnect needed) to pick up changes.

## Honesty

Report what's actually on screen. If the target app isn't visible, the monitor's asleep, or a view won't navigate, say so and ask the user for the one physical action only they can do (wake a monitor, foreground an app) — don't guess or invent content.
