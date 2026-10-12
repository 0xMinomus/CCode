# Failure ledger — 2026-07-25/26

What went wrong in this working block, why, and what the corrected approach is. Kept
because several of these were *shipped* and only caught later by an adversarial review or a
headless run — the pattern matters more than the individual bugs.

## Shipped defects (found after the fact, not before)

| # | Defect | How it escaped | Caught by |
|---|--------|----------------|-----------|
| 1 | Fitted screenshots advertised the PRE-shrink scale, so every view-space click on a capped client missed by the shrink ratio (~5x). `view_id` could not catch it because the id never changed. | Verified the image *arrived*; never verified the coordinate contract still held. | max code review (2 finders independently) |
| 2 | OCR thread cap was **inert in production** — `warmup()` built `RapidOCR()` uncapped and won the double-checked init. My benchmark called `ocr_boxes` first, so it measured a path production never took. | Benchmarked a code path instead of the shipped path. | max code review |
| 3 | `screen_reload` lost a clientInfo-derived output cap (execv keeps env, not state; client never re-sends `initialize`). | Never tested the reload path with a capped client. | max code review |
| 4 | `region` + `monitor` silently returned the whole monitor. | Tested `region` alone, saw it work, dismissed the report. | driving Grok, which isolated the exact condition |
| 5 | `region` + `monitor` was later unclipped — an oversized box read the neighbouring monitor. | Fixed the precedence bug without bounding the result. | max code review |
| 6 | `requirements.txt` named `rapidocr-onnxruntime`, which does not provide the `rapidocr` module the code imports. Anyone installing from it got OCR silently disabled. | Never installed from my own requirements file in a clean env. | 88plug validation pass |
| 7 | CI was RED for four consecutive commits. Tests passed locally (real desktop) and failed headless because conftest substituted a stub `capture`. | Verified locally; never looked at the CI runs. | 88plug validation pass |
| 8 | `Gio.Settings.new()` and `Atspi.init()` **abort()** rather than raise when dconf / the a11y bus is missing — latent server-killers on any headless or minimal-desktop host. | Assumed `try/except` was sufficient for FFI calls. | luck (a headless test run dumped core) |
| 9 | Cap applied per-image, not per tool RESULT — a multi-stop `screen_tour` shipped N x the client limit. | Modelled the limit at the wrong granularity. | max code review |
| 10 | Overwrote `requirements.txt` with `cat >` without reading it, destroying 41 lines of system-dependency documentation. | Did not read before overwriting. | `git diff` after the fact |

## Process failures

- **Verified the wrong layer.** Repeatedly confirmed "the call succeeded" rather than "the
  contract still holds" (#1, #2, #3). A tool call returning 200 is not evidence the
  coordinate space, the shipped path, or the reload path is intact.
- **Local-green treated as green.** Four red-CI commits (#7). This box has a full desktop
  stack; CI does not. Green here proves nothing about there.
- **Dismissed a correct external report.** Grok reported "region didn't stick"; I tested the
  wrong variant, concluded it was the client's fault, and moved on (#4).
- **Asserted an inherited limit.** `prereqs` hard-failed X11 with "targets GNOME on Wayland
  only" — never measured, and wrong about the actual blocker.
- **Claimed a number from the wrong path.** Reported "85s -> 40.6s live, 2.1x" for a fix
  that was inert in production; the improvement was largely load variance (#2).
- **Chased a dead end before checking what was already there.** Reached for a VNC client
  library (blocked by PEP 668) when QEMU's own QMP socket did screendump + input with the
  stdlib.
- **Wrote a poll loop whose heredoc never exported its variable** and let it spin for ten
  minutes doing nothing.

## Closed since

- **The X11 backend now runs end-to-end on a real X11 session** (Ubuntu 24.04 / GNOME 46 /
  Xorg, in `tests/vmbed`): geometry `[{0,0,1280,800}]`, pixel-validated `available`, a
  1280x800 grab at stddev 18.7, and a working region crop. `./verify.sh both` reproduces it.
- That run immediately found a defect the unit tests could not: the pipeline hard-coded
  `leaky-type=downstream`, which does not exist before GStreamer 1.28, so it failed to parse
  on the **current Ubuntu LTS**. A note in `capture.py` claimed `drop=` had been removed in
  1.28 — it had not; 1.28 exposes both. Property is now chosen at runtime.
- **AT-SPI needs no app restart.** The conclusion recorded here earlier was wrong: both VM
  beds expose apps (6 and 13) with `toolkit-accessibility=false`. This host reported 0 only
  because it sets `NO_AT_BRIDGE=1` / `GTK_A11Y=none` in `/etc/environment`. The measurement
  was real; the inference was not.

## Still unverified

- Pixels have not been pulled through the in-guest PipeWire ScreenCast stream. The portal
  interfaces and `AvailableSourceTypes` are proven on both beds; the frame path is not.
- `/dev/uinput` is not writable in the guests, so the uinput input backend is untested there.
- AT-SPI has still only been exercised against a small app mix, not a browser under load.

## Corrective principles

1. Test the SHIPPED path, not a path that reaches the same function.
2. Verify the CONTRACT (coordinates, freshness, identity), not just that a call returned.
3. Headless/CI is a different machine — run the suite the way CI runs it before pushing.
4. An external bug report is evidence; reproduce the exact stated condition before dismissing.
5. FFI/GLib calls may `abort()`; probe preconditions instead of relying on `try/except`.
6. Prefer the mechanism already installed over a new dependency.
