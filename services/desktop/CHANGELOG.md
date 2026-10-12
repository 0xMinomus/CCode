# Changelog

Calver headings match the 88plug hub (`YEAR.MONTH.<commit-count>` on `main`).

## Unreleased

- **New `x11capture.py`: plain X11 capture as a fallback when the portal is unusable.**
  Measured on GNOME/X11 (Zorin OS 15.3): no `xdg-desktop-portal`, 0 portal interfaces on the
  bus, GStreamer 1.14 without appsink `leaky-type` — our pipeline cannot start there, but
  `import -window root` captured a real frame and `/dev/uinput` was writable, so INPUT
  already worked unchanged. `ensure_geo()` now falls back to X11 (xrandr geometry, root grab
  + crop) instead of failing. Zero new dependencies: Pillow's XCB grab first, else an
  external grabber that was already installed. gi-free so CI executes it.
  `available()` is a REAL probe, not a PATH check — on Xwayland a grabber exists but the root
  rejects XGetImage, which made a PATH-only check claim availability while every grab
  returned None. Opt out with `MCP_SCREEN_NO_X11=1`.
- **New `atspi_tree.py`: AT-SPI as an opt-in accelerator, never the primary path.** Measured
  first: 0 apps exposed with `toolkit-accessibility=false`, still 0 right after enabling it
  (running apps read it at startup), and a full widget tree for an app launched afterwards.
  So it needs a global toggle AND an app restart — useless for the already-open desktop
  screen-mcp exists to drive. `_perceive` now tries it before OCR and falls through on an
  empty result; where an app does expose a11y it yields exact roles, labels and clickable
  desktop centres (verified: 110 elements from one app) against a multi-second OCR pass.
  `screen_diag` reports WHY the tree is empty so an empty list is never read as an empty
  screen. Opt out with `MCP_SCREEN_ATSPI=0`.
- **Two latent process-killing aborts fixed, both found by running the suite headless.**
  `Gio.Settings.new()` calls `abort()` when dconf is unavailable, and `Atspi.init()` calls
  `abort()` when the accessibility bus is missing — neither raises, so no `try/except` helps
  and either would have taken the whole MCP server down on a `screen_diag` from a headless
  or minimal-desktop host. The toggle is now read via `gsettings` out-of-process, and
  `Atspi.init()` is never reached unless a D-Bus probe confirms `org.a11y.Bus` has an owner.
  Both pinned by regression tests.
- **`screen_diag` no longer misdiagnoses non-Wayland sessions.** The session check hard-failed
  anything without `WAYLAND_DISPLAY` as "screen-mcp targets GNOME on Wayland only", which
  hides the actual blocker. Measured on a real GNOME/**X11** box (Zorin OS 15.3): what stops
  us there is `xdg-desktop-portal` being absent (0 ScreenCast/RemoteDesktop interfaces on
  the bus), GStreamer 1.14 lacking appsink `leaky-type` (our exact pipeline errors with
  `no property "leaky-type"`), and Python 3.8 vs our 3.10 floor — none of which is "X11".
  Capture rides the portal and input rides uinput; neither is Wayland-specific. The session
  row is now informational (`ok` on Wayland, `warn` + a pointer on X11) and the portal /
  GStreamer / uinput rows remain the real gate. X11 is still not claimed as supported — it
  is untested end-to-end, and that is now what the tool says rather than a wrong reason.
- **The client cap now applies to the whole tool RESULT, not each image.** `screen_tour`
  emits one thumbnail per stop in a single result; fitting each to the full cap shipped
  N x cap and the client truncated the lot. The cap is split across stops, and once the
  budget is spent each remaining stop returns its TEXT plus an explicit note rather than
  images that would be silently truncated away.
- **CI now runs the capture-side tests instead of skipping them.** conftest stubs `gi`
  (adding `Gst`/`GstApp`/`GLib.quark_from_string`) and then imports the REAL `capture`
  against it, rather than substituting a 2-function fake module. Region/monitor translation
  and client-cap detection are executed headless; only tests that need a live pipeline stay
  behind `REAL_STACK`. Headless went 163 -> 177 passed, skips 28 -> 15.
- **The OCR thread cap was INERT in the live server.** `warmup()` constructed `RapidOCR()`
  with no params and, running first at startup, won the double-checked `_OCR` init — so the
  cap only ever applied in benchmarks that happened to call `ocr_boxes` first. There is now
  one constructor, `_build_ocr()`, used by both paths; verified that a warmup-built engine
  reports `intra_op_num_threads = 6`. Re-measured fairly on the production path (loadavg 25,
  same frame, back to back): uncapped 31.2s wall / 346s CPU vs capped 14.1s wall / 92s CPU,
  123 boxes either way — **2.2x wall, 3.8x CPU**. The previously reported "85s -> 40.6s live"
  was measured through a path production did not take and was largely load variance.
- **A non-dict `params` killed the server mid-handshake.** `_apply_client_limits` ran
  outside any try/except in the stdin loop, so `{"clientInfo": "grok"}` raised AttributeError
  before `initialize` was answered — the client hung on a server that exited with no
  diagnostic. Now fully defensive and fail-open.
- **`fit_to_budget` now binary-searches the scale.** The one-way estimate could only step
  down, so hard-to-compress content collapsed to 8% of the allowed budget — a needlessly
  unreadable image. Searching for the largest fitting scale against the ORIGINAL image gets
  97-99% utilisation on noise, structured UI, and photo-like frames alike.
- **A cap at or below the envelope reserve shipped the full payload.** `budget = cap - reserve`
  went negative and the early `budget <= 0` return handed back the unshrunk image — exactly
  the drop this module prevents. Usable budget is floored at cap/4.
- **`MCP_SCREEN_MAX_OUTPUT_KB` / `MCP_SCREEN_CPU_THREADS` no longer crash on bad input.**
  A bare `int()` at import time took the server down; malformed values now degrade.
- **`region` + `monitor` is clipped to that monitor.** The translation added the origin but
  never bounded the box, so an oversized or offset region silently read the neighbouring
  monitor's pixels — a valid-looking crop of the wrong screen. The `_REGION` tool schema now
  documents the monitor-relative meaning instead of contradicting it.
- **`run-python.sh` can no longer stop the server from starting.** Provisioning runs with
  errexit disabled: a leftover `.venv` made `.venv/bin/python -m pip` invoke a binary that
  does not exist, and the launcher died 127 with no diagnostic — permanently, since every
  relaunch re-entered the same branch. Also: the hard deps install synchronously while the
  ~200MB grounding backends finish in the background (inline they ran past the MCP client's
  startup timeout); explicit `EIGHTYEIGHT_PYTHON` / `PLUGIN_PYTHON` / `SCREEN_PYTHON`
  overrides are honoured outright rather than being discarded for lacking `gi`; and a
  pre-existing venv without `--system-site-packages` is left ALONE (never deleted) and
  bypassed via `--target`.
- **Fitted screenshots advertised the WRONG view transform — every capped-client click
  missed by the shrink ratio.** `encode_store` stamped `SESSION["view"]` (scale/dw/dh) and
  the response text BEFORE `fit_to_budget` re-encoded the image smaller, so the client
  received a 526x296 image while both the text and the transform claimed 2576x1449 at
  scale 0.6708. A model clicking what it saw had its coords divided by the pre-shrink
  scale — landing ~4.9x short — and `view_id` could not catch it because the id never
  changed. This is the exact "I clicked where I saw it but it missed" class the view_id
  machinery exists to prevent, introduced by the cap-fitting work itself. `fit_to_budget`
  now returns the size it actually encoded and `encode_store` restates the transform from
  it. Verified live: a click at the shipped image's centre now maps to (1920, 1083) of a
  3840x2160 desktop. Found by the max code review; two finders reached it independently.
- **`screen_reload` silently lost a client-derived output cap.** The cap is learned from
  the `initialize` handshake, but `os.execv` keeps only the environment and the client does
  not re-send `initialize` over the preserved stdio connection — so after any reload a Grok
  session fell back to uncapped and its next screenshot was dropped again. The resolved cap
  is now pinned into `MCP_SCREEN_MAX_OUTPUT_KB` before the exec.
- **The envelope reserve is no longer a fixed 2 KB.** `fit_to_budget` takes `reserve_bytes`
  (floored at 512) and `encode_store` passes what it will actually emit, including the
  stale-risk note. An `annotate=true` response carries a line per detected element, which
  on a busy 4K desktop far exceeds 2 KB and would push the combined result back over the cap.
- **`scripts/run-python.sh`: the no-Python diagnostic was unreachable.** Under
  `set -euo pipefail` the retry assignment inside `|| { ... }` aborts the script on its own
  failure, so a box with no usable Python got a bare non-zero exit instead of the install
  hint. Reproduced standalone, fixed with `|| true` + an `if !` guard.
- **`scripts/run-python.sh`: an existing venv without `--system-site-packages` was adopted.**
  `[ -d "$VENV" ]` short-circuited creation, so a tree left by an interrupted run got the
  stamp written and permanently locked the server onto an interpreter that cannot import
  `gi`. It is now probed for `gi` and rebuilt when it fails.
- **`requirements.txt` named an OCR package the code cannot import.** It listed
  `rapidocr-onnxruntime>=1.4` labelled "(RapidOCR v3)", but `grounding.py` does
  `from rapidocr import RapidOCR` and that distribution ships `rapidocr_onnxruntime`
  instead — verified in a clean container: `ModuleNotFoundError: No module named
  'rapidocr'`. Anyone installing from requirements.txt therefore got a server with OCR
  silently disabled (the import is try/except-guarded, so it degraded quietly). Now
  `rapidocr>=3.0`, matching the import and requirements-runtime.txt.
- **CI moved 3.12 -> 3.13.** The pin existed solely because `rapidocr-onnxruntime`
  declares `requires_python <3.13`; the package we actually use, `rapidocr` v3, declares
  `<4,>=3.8`. Verified on PyPI and by installing the CI dep set plus rapidocr on 3.13 in a
  container. Stale references removed from README and docs/install.md too.
- **Output-budget fitting moved to `budget.py` so CI actually executes it.** The logic sat
  in `capture.py`, which cannot be imported without a real gi/GStreamer/D-Bus session — a
  headless run substitutes a stub `capture`, so the tests raised `AttributeError` and CI was
  red on every commit from `ce7534d` to `3736ab4` while passing locally. `budget.py` imports
  only stdlib + Pillow and takes the downscaler INJECTED, the same discipline
  `reliability.py` already uses for its grabber. `budget.MAX_OUT_KB` is now the single source
  of truth (capture reads it, `server._apply_client_limits` writes it) instead of two copies
  that could drift. 11 budget tests now run headless (156 passed / 28 skipped, up from
  146 / 33) and are mutation-checked: shortening the fit loop fails them.
- **OCR grounding is 2.1x faster and burns 3.8x less CPU — `screen_read_text` on an
  uncached 4K monitor went 85 s → 40.6 s.** Profiling the stages (not guessing) put 98.3%
  of the cost in OCR (ocr 56327 ms vs omni 721 ms, cv 221 ms), and splitting OCR put it in
  recognition, not detection (det 3482 ms, det+rec 56072 ms). Two plausible fixes were
  measured and both were WRONG: more threads / bigger rec batch made it worse
  (50.7 s → 69.4 s → 84.1 s), and downscaling the frame saved 12% while losing 54% of the
  text. The real signal was 55 s wall against **610 s of process CPU** — onnxruntime's
  default `intra_op_num_threads=-1` spawns a thread per core and they spin-wait instead of
  progressing. Fewer threads is faster: 24→55.5 s/610 s, 4→32.2 s/137 s, **6→25.9 s/161 s**
  (knee), 8→26.9 s/210 s, 12→33.7 s/334 s. `_omni_session` already capped at 6; `ocr_boxes`
  never got the same treatment, so both ONNX consumers now share one `_CPU_THREADS`
  (`MCP_SCREEN_CPU_THREADS`). The 610 s also starved the rest of the desktop, so this is a
  politeness fix as much as a speed one. Regression test is mutation-checked.
- **Screenshots are no longer DROPPED on clients that cap tool output.** Grok Build
  truncates an MCP tool result at 20 KB; our ~900 KB of base64 was cut mid-string, failed
  its image integrity check ("image bytes are truncated"), and the image was discarded
  entirely — screen-mcp was effectively blind under Grok, while the tool call still looked
  successful. `encode_store` now fits the payload to the cap, sized analytically (encoded
  size tracks pixel count, so one lossy probe predicts the scale) with a halving fallback
  so fitting is guaranteed. The cap comes from the `initialize` handshake's `clientInfo`,
  so nothing needs configuring; Claude stays uncapped on a byte-identical no-op path.
  A real 4K shot lands ~15 KB and stays legible; region shots (~3 KB) were never affected.
- **`region` + `monitor` together no longer silently drops the region.** `capture_desktop`
  returned early on `monitor is not None`, before the `region` branch, so asking for
  `region=[0,0,600,300] monitor=0` handed back the whole 3840x2160 monitor with no error —
  a plausible-but-wrong result. They now mean "this box, relative to that monitor's origin";
  `region` alone stays desktop-absolute. Both contracts pinned by tests.
- **A fresh clone now provisions its whole runtime itself.** `pyproject.toml` declared no
  dependencies and the launcher looked for a `.venv` nothing ever created, so users hit a
  server that would not import. `scripts/run-python.sh` now provisions the full runtime set
  by default (a server that starts with no OCR reads as broken, not as a missing extra).
  Six failures found by running it in a clean container, none visible on a working desktop:
  `evdev` has no wheel and its failure sank the entire install (now separate, best-effort,
  prefers `evdev-binary`); the first interpreter on PATH usually lacks `gi` (selection now
  prefers a gi-capable one); Debian ships `venv` separately (falls back to
  `pip install --target` + PYTHONPATH); that interpreter often has no pip or ensurepip
  (pip's `--python` lets any pip-capable python populate the target with the right ABI);
  a FAILED venv leaves a partial tree that hid `gi` and won selection (removed on failure,
  and a venv is only adopted if it kept `gi`); and `rapidocr` pulls non-headless opencv so
  `cv2` died on `libGL` (headless force-reinstalled last). Satisfaction checks use
  `find_spec` rather than importing — importing onnxruntime per start cost ~3 s (3.4 s →
  0.65 s). Measured: **musl is not viable** — onnxruntime publishes no musl wheel, so an
  Alpine build silently loses OmniParser grounding; glibc/manylinux stays. PyGObject,
  GStreamer and PipeWire remain the one layer that cannot ship with us (no wheel; they bind
  the host typelibs and running compositor), so the launcher now prints the exact
  pacman/apt/dnf command instead of a generic error.

- **WebP lossless encode is ~19x cheaper — a plain screenshot went 4194 ms → 1286 ms.**
  Encoding was 85% of a shot's wall time (3564 ms of it), measured on a real 2576x1449
  frame. libwebp's `method`/`quality` only trade CPU for bytes in lossless mode — the
  pixels are identical at every setting — so `method=0, quality=20` is a free win:
  195 ms for 140 KB more. Those bytes cost nothing, because an image is billed at
  `ceil(w/28) * ceil(h/28)` visual tokens (4784 here) regardless of encoded size, and
  759 KB of base64 is far under the API's 10 MB per-image cap. Env-overridable via
  `MCP_SCREEN_WEBP_METHOD` / `MCP_SCREEN_WEBP_EFFORT`; `tests/test_encode.py` asserts
  pixel-exact round-trips at every method/effort combination so the lossless guarantee
  cannot silently regress.

- **Adversarial-args probe: three defects, one root cause, fixed at the source.**
  A read-only sweep of hostile inputs found that `capture_desktop` validated nothing:
  `monitor=99` leaked a raw `list index out of range`, an entirely off-screen region
  returned a crop that `screen_read_text` reported as `count:0` (indistinguishable from
  "the region exists and is empty"), and — worst — `screen_verify` graded that same
  nonexistent region **CONFIRMED / changed:true**, certifying an action against pixels
  that do not exist. Fixed once in a pure `capture.validate_scope()` so all three tools
  inherit it, with the error naming the valid range. Mutation-checked: disabling the
  off-screen guard fails the suite.

- **`screen_do` failed on the first call after a reload.** It deliberately bypasses
  `_action`, which is what normally primes monitor geometry, so `SESSION["geo"]` was still
  None and the first pointer step died with a bare `TypeError: 'NoneType' object is not
  iterable`. Same shape as the documented focus-after-reload bug. `tool_do` now primes geo
  once, and `global_to_logical` raises an actionable error instead of a TypeError. Found by
  a cold-start probe — earlier `screen_do` calls only worked because a screenshot had
  already primed geo.

- **`_maybe_shot` waits for the frame to change instead of sleeping a flat 350ms.**
  `settle` is now a CEILING, not a cost. The blind sleep was wrong in both directions —
  it charged every fast action the full delay and still grabbed a pre-change frame when the
  UI was slower. This is also the only place `MCP_SCREEN_WAIT_MODE=hybrid` can matter for
  an agent: the change-gate in `tool_screenshot` requires a screenshot within 1.5s of an
  action, which separate tool calls from a model never are. Third instance of the same
  defect class this session (see also the clipboard wait).

- **Cross-layer verification proven end-to-end with os-control-mcp's `os_verify`.**
  `screen_verify`'s `pixel` block is exactly the contract `os_verify` consumes, so the two
  compose with no code changes — confirmed by running both quadrants against the live
  desktop: a GUI-only action (hover) with an untouched unit returns `DIVERGED` /
  `cross_layer: "pixel-changed-os-static"` / `reconciled: false`, and an action inert at
  both layers returns `NO_OP` / `reconciled: true`. The integration gap was documentation,
  not plumbing: os-control's `cross-layer-verify` skill predated `screen_verify` and taught
  only the passive `screen_sense`. It now teaches both and says when each applies —
  `screen_verify` polls and grades (use when the GUI effect may lag), `screen_sense` reads
  what the last action already left behind (use when it is instantaneous).

- **New `screen_verify` — grade the last action instead of eyeballing a screenshot.**
  Returns CONFIRMED | PARTIAL | NO_OP | DIVERGED, the same vocabulary as os-control-mcp's
  `os_verify`, and the `pixel` block it returns is exactly what `os_verify` consumes — so
  the GUI and OS verdicts compose. NO_OP is the one worth having: the screen never changed,
  so the click missed or the keys went to the wrong window — the failure a screenshot makes
  you infer by eye. (Steal from QuickDesk's `verify_action_result`.)

  Its first eval found a false-CONFIRMED: the baseline is a hash of the whole stamped node
  frame, and hashing a REGION crop against it compares different images, so it always
  differed and every action graded as changed — including a mouse move, which cannot change
  the screen at all (the cursor is METADATA, never baked into frames). The change check now
  re-grabs the same node; with no baseline node, `changed` is reported null and excluded
  from the verdict rather than invented. Same false-CONFIRMED class os-control had just
  fixed in `os_verify`. Post-fix: inert mouse move → NO_OP, hover highlight → CONFIRMED in
  23ms.

  `wait_text` and `verify` now share one `_perceive()` (recall → OCR → learn), so neither
  can drift back into reading the world-model cache without writing it.

- **New `screen_wait_text` — block until text appears, then return its click coords.**
  Replaces screenshotting in a loop to see whether something finished. Naive polling was a
  non-starter (grounding costs ~7.7s on a cold screen), so it uses the shape this session
  measured: a grab is ~35ms while OCR is the expensive part, so it polls the frame HASH and
  only pays for perception when pixels actually changed — measured 11 grabs / 1 OCR pass
  over a 10s wait on a static screen. It also recalls from **and writes to** the world model,
  so a repeat wait on a learned screen skips OCR entirely: **8574ms → 41ms (209x)**.
  (Steal from QuickDesk's `wait_for_text`.)

- **OCR matching is whitespace-tolerant in `screen_wait_text` and `screen_read_text`.**
  Found by the first eval of wait_text, which timed out on a button that was plainly on
  screen: OCR renders it `Launch installer` or `Launchinstaller` depending on the run, so a
  literal substring test misses it. Both tools now compare raw and whitespace-stripped.

- **New `screen_read_text` — read the screen as text + click coords, no image.** Every
  latency win this session left the token cost untouched: an image bills a FIXED
  `ceil(w/28)*ceil(h/28)` visual tokens (4784 for a 4K monitor) regardless of how small the
  encode gets. For navigate-by-text work the pixels are not what the caller needs. Measured
  on a 4K monitor: 4784 tokens / 412ms for a screenshot vs **~1350 tokens / 67ms** unfiltered
  (104 elements) and **~95 tokens** with `contains=`. Reuses the existing perception path —
  world-model recall first, which skips OCR entirely on a known screen (7747ms → 42ms
  measured) — so it was almost entirely wiring, not new machinery. Coordinates return in
  desktop space and are directly clickable. (Steal from QuickDesk's `get_ui_state`.)

  The first draft of the tool description claimed "~10x cheaper". Measuring it gave 3.5x
  unfiltered and 50x filtered, so the description now carries the real numbers.

- **`screen_read_selection` waits for the clipboard instead of guessing 140ms.** It slept a
  fixed `GLib.usleep(140000)` after sending the copy combo, then read. That was wrong in both
  directions: it charged every fast app the full delay, and any app slower than it read back
  EMPTY — which, since we clear the clipboard first, is indistinguishable from "nothing was
  copied" and surfaced as a false negative. Now polls at 15ms until non-empty or
  `MCP_SCREEN_SELECTION_TIMEOUT_S` (default 1.5s). Clearing first is what makes polling sound:
  non-empty can only mean this copy landed. Verified live — the terminal under test took
  ~1.3s to publish the selection, i.e. the old fixed sleep would have failed it.
  (Steal from QuickDesk's `wait_for_clipboard_change`.)

- **Encode re-swept and left alone — it is already at the floor (negative result).**
  With the shipped `m=0 q=20` at 202ms median (9 reps) on the current RGB/INTER_AREA output,
  nothing beats it: higher lossless effort is 237-251ms, `method=1` is 344-613ms, PNG is
  343-768ms, and **lossy WebP is SLOWER** (228-307ms) because it runs rate-distortion
  analysis while lossless method=0 is fast entropy coding. So the lossless guarantee costs
  no speed at all — it is not a quality/latency tradeoff, and there is no reason to weaken
  it. Recorded as a DO-NOT-RE-TUNE block in `capture.py` next to the constants.

  Method note: a 3-rep bench made `q=40` look 8% faster and 8% smaller; at 9 reps it is 24%
  SLOWER. Third time this session a small-sample bench pointed the wrong way (see also the
  offline LANCZOS figure and the first filter eval) — medians, repeats, and measuring the
  live path are the only things that have held up.

- **Test harness is REAL-FIRST — the suite now executes capture.py instead of a stub.**
  `tests/conftest.py` unconditionally installed stub `gi`/`state`/`capture` modules into
  `sys.modules`, so 144 passing tests never ran a line of the shipped capture path. Every
  capture bug this session was caught by driving the real desktop instead: an ndarray
  aliasing an unmapped GstBuffer (read-only + use-after-free), a missed `_sample_to_rgba`
  rename, and a handler returning a bare `str` where the dispatcher indexes `["content"]`.
  conftest now probes for real gi + Gst + a session bus and only stubs what genuinely will
  not import, exposing `REAL_STACK` so tests can gate. New `tests/test_capture_real.py`
  covers the real `_sample_to_rgb` (exact pixels, row-padding stride trim, and that the
  result is writable and owns its data), `_downscale` incl. the PIL fallback, and a
  **view-transform round-trip** — the click-accuracy invariant, previously untested.
  150 pass locally against the real stack; 144 pass + 6 skip in CI where gi is absent.

  The new tests were mutation-checked rather than assumed: reintroducing the alias bug fails
  2, adding a broken stride trim fails 3, and forcing the view transform to 1:1 fails 4.

  Re-ran legibility end-to-end through the real `encode_store` (real downscale, real WebP
  settings, real transform) rather than an offline approximation: 92% mean / 91% across the
  three smallest fonts — matching the offline cv2 INTER_AREA figures exactly.

- **Screenshot downscale moved to cv2 INTER_AREA — 15x faster than PIL LANCZOS.**
  287.5ms → 18.8ms on a real 3840x2160 → 2576x1449 frame; live shot 528ms → 412ms with
  the resize stage at 84ms (was 408ms two commits ago). INTER_AREA is also the principled
  filter for minification: it averages the source pixels each output pixel covers, so it
  antialiases without the ringing a cubic/lanczos kernel leaves on text edges. The encoded
  payload got *smaller* too (538KB → 502KB) — less high-frequency ringing to compress.
  Falls back to PIL when cv2 is absent, so capture never hard-depends on grounding's stack.

  This also **reverses an earlier call in this changelog**. A narrower eval had LANCZOS 1pp
  ahead of the alternatives and concluded "don't swap the filter". Re-run against known
  rendered text at 9/10/11/12/13/14/16/20px, PIL-LANCZOS / INTER_AREA / INTER_LANCZOS4 /
  INTER_CUBIC all score 92-93% mean and 91-92% across the three smallest sizes — the gap
  was never real, and 15x was being paid for nothing.

  It also kills a planned GStreamer `videoscale` change. videoscale-lanczos measured 78.5ms
  net, genuinely faster than PIL — but it would have required teaching every coordinate path
  that frame px != desktop px (the documented click-accuracy hazard), and pipeline scaling is
  EAGER: it runs on every damage frame (~3.5/s) rather than only frames we pull. cv2 is
  lazy, 4x faster still, and touches no coordinates.

- **Alpha plane dropped end-to-end — pipeline negotiates RGB, not RGBA.** The stage timer
  showed resize was 68% of a shot (408ms of 601ms), and it was resizing a channel nothing
  reads: the alpha byte was forced to a constant 255, carried through LANCZOS, then encoded.
  videoconvert now emits 24-bit RGB, so the decode copies 24.9MB instead of 33.2MB and the
  resize works on 3 channels — measured 471ms → 298ms (1.58x) on a real frame. Encode is
  ~18ms slower on RGB but the output is byte-for-byte the same size (745KB), because a
  constant alpha plane compresses to nothing. Net ~155ms/shot; live shot 601ms → 528ms with
  resize 408 → 264. Colors verified live after the caps change.

- **Per-stage timing on every screenshot and action (`stages: …ms`).** Stage stamps live in
  `state.py` (the one module everything imports, so no cycle) and cover pull, decode, resize,
  encode, aware, ground, gate and settle, plus an explicit `other` remainder so unexplained
  time is visible rather than hidden. This exists because benching stages OFFLINE kept
  producing numbers that did not transfer — an isolated LANCZOS bench read 553ms while the
  whole live shot was 603ms — and guessing which stage dominated is how ~46ms/grab of memcpy
  and a 264ms-per-shot subprocess both survived an entire optimization pass. First real
  breakdown of a 601ms monitor shot: `resize 408, encode 173, decode 19, aware 1` with `pull`
  under 1ms. Resize is 68% and the current top cost.

- **Awareness probe cached — it was spawning a Python subprocess on every screenshot.**
  `awareness.summary()` runs per shot. When the optional window-info extension isn't loaded
  it fell through to `atspi_titles()`, which spawns a fresh interpreter (measured 263.6ms)
  purely to render the text line "awareness: unavailable". Whether the extension is loaded
  only changes on a Wayland re-login or a `screen_reload`, so the negative verdict is now
  cached (`MCP_SCREEN_AWARENESS_TTL_S`, default 30s) rather than re-probed every frame.
  A plain monitor shot went 1084ms -> 603ms.

- **Two hidden 33MB copies removed from every grab.** `_sample_to_rgba` ran on every frame
  pull — including every poll of the settle and change-gate loops — and did `bytes(mi.data)`
  (a full memcpy of the mapped 4K frame, 9.7ms) followed by `arr[..., [2,1,0,3]]` (a fancy-index
  allocation to swap BGRx→RGBA, 36.7ms). `mi.data` is already a buffer, so `np.frombuffer`
  wraps it as a view for free; and the pipeline now negotiates **RGBA** directly, so
  videoconvert does the channel order in C and there is nothing left to swap. The old
  "BGRx on the wire for speed" comment was backwards once the cost landed in numpy. ~46ms
  saved per grab; a plain monitor shot went 1286ms → 1084ms, and the poll loops that grab
  5–9 times per action save proportionally more. Colors verified live after the caps change.

  The copy must be `.copy()`, not `ascontiguousarray`: with RGBA the trimmed view is already
  contiguous, so `ascontiguousarray` returned it unchanged — leaving the array aliasing the
  buffer after `unmap` (use-after-free) and read-only, which killed the alpha write with
  "assignment destination is read-only" on the first live grab.

  Still open, measured but not wired: a region shot converts the whole frame then discards
  ~95% of it, which is why a 1500x130 region can cost *more* than a full-monitor grab
  (87.9ms vs 3.9ms cropping first). Cropping in `_sample_to_rgba` would make `_note_frame`'s
  per-monitor freshness signature region-scoped, so it needs its own path.

- **`screen_drag` takes `modifiers`, held for the whole press-move-release.** Without it,
  `screen_read_selection` could not be used where it matters most: a terminal running a TUI
  (Claude Code, vim, htop) enables mouse tracking and consumes the drag itself, so no
  terminal-level selection is ever made and the copy returns nothing. `modifiers: ["shift"]`
  makes the terminal emulator bypass the app's mouse grab and select on its own. Verified
  live end-to-end — shift+drag over a TUI pane then `ctrl+shift+c` returned the line
  verbatim, box-drawing glyphs, em-dash and spacing intact, matching the pixels on screen.
  Modifiers press inside the same device lock as the drag and release in a `finally` on both
  the uinput and portal paths, because a stuck Shift would corrupt every later keystroke.

- **New `screen_read_selection` — read text exactly, without OCR.** Copies the focused
  window's selection and returns it verbatim. An OCR-based read of a full 4K monitor
  loses ~8% of characters on sub-12px code (measured against known rendered text across
  a font-size sweep — an artifact of the 4K→2576 downscale, not of the filter: LANCZOS
  beat box/bilinear/nearest at every size and stays the default). The clipboard is
  **cleared before** the copy combo is sent: without that, an app that ignores the combo
  leaves the prior clipboard in place and the tool would return the user's unrelated
  clipboard contents labelled as screen-read text. The user's clipboard is saved and
  restored regardless. Terminals need `combo='ctrl+shift+c'`.

- **Post-action change-gate can wait on damage events instead of polling.**
  `MCP_SCREEN_WAIT_MODE=poll|event|hybrid` (default `poll`, byte-identical to before).
  Damage arrives every ~270–550 ms on an active desktop while the gate polls every 60 ms,
  so most poll iterations grab and convert a 4K frame to learn nothing. `hybrid` blocks on
  a real damage event with the poll interval kept as a backstop, so an absent event
  degrades to today's behavior rather than stalling. `screen_diag` now reports damage
  cadence, keepalive-resend counts and wake stats under `cursor.events`.

- **Focus verification — root-cause fix for clicks landing on the wrong window/tab.**
  `screen_focus`/`focus=` no longer report success without confirming the correct
  window actually got raised: both the window-info-extension path (`activate_window`)
  and the no-extension GNOME Overview fallback (`activate_via_overview`) now check
  `awareness.focused_window()` before claiming success, instead of trusting a bare
  boolean or "the keystrokes were sent." Any real focus/activation attempt now also
  marks the current view stale — `resolve_xy` raises a new `FocusDriftError`
  (a `StaleViewError` subclass) rather than silently clicking screenshot coordinates
  that may no longer match what's on top, until a fresh screenshot is taken.
  `_action`, `screen_do`, and `screen_tour` now all check and act on a focus
  failure instead of discarding it (`screen_tour` previously never applied
  per-step `focus` at all — a complete no-op).
- Element-id staleness guard: `element=<id>` (from an annotated screenshot) now
  raises the same class of stale error when a later screenshot has superseded the
  cached elements, instead of silently resolving to a renumbered/wrong element.
- `verify=true` on `screen_key`/`screen_type` now actually performs a whole-frame
  diff instead of silently no-op'ing — it previously only worked for
  coordinate-bearing tools (click/scroll/drag).
- uinput's fractional-scale miscalibration warning now surfaces into
  `screen_click`/`move`/`scroll`/`drag`'s own returned text instead of sitting
  only in an internal log file the caller never reads.
- Removed `reliability.wrap_call` — fully dead code (zero call sites); its
  ack-gate/hash/diff primitives are already composed directly by server.py's
  `_action`/`_verify`.
- 8 new regression tests (`tests/test_input.py`) covering the above.
- **`screen_watch` — human-eye 1 fps observation (default confirm for thrashy UIs).**
  Samples a region/monitor at `fps` (default 1) for `seconds` (default 6) and
  returns `settled | evolving | jitter | unstable`. Sustained local motion
  without navigation → `jitter` (the "looks crazy" case: force-directed graphs,
  canvas thrash). Drive-screen skill + server `instructions` + docs now make
  watch the default confirm path after graphs/maps/canvases/loaders — a single
  screenshot is a glance, not a visual QA pass.
- Unit tests: `tests/test_watch.py` for verdict classification.
- **`screen_sense` + `sense.to_pixel_signal()` — the pixel half of cross-layer
  verification.** Normalizes the rich SENSE dict into the compact
  `{changed, opened, modal, no_op, activity}` contract and exposes it as a
  read-only tool, so an agent can hand the `pixel` object to os-control-mcp's
  `os_verify` and catch a GUI that changed while the underlying service did not.
  7 new `to_pixel_signal` unit tests.

## 2026.7.24

- 88plug compliance: dual Grok install on docs/install; MkDocs-relative doc links
  (drop 404 `blob/main/*.md` paths); Manual MCP docs use `bin/screen-mcp` (T1
  launcher, not bare python3); document CI Python 3.12 pin (rapidocr wheels);
  unknown-tool `tools/call` returns MCP `isError` result; ruff format clean.

## 2026.7.23

- Fixed the takeover guard false-firing forever on a STATIC monitor: `cursor_pos(prefer_node=...)`
  pins to a per-node cursor sample that never refreshes once a monitor stops repainting, so
  `guard_user` compared every subsequent commanded click against ONE frozen point and raised
  `UserControlError` with the IDENTICAL "live" position every time — also blocking the
  `_nudge_prime` frame-refresh path that would have fixed it (it calls `guard_user()` too).
  Added `capture.cursor_sample_age()` and a `MCP_SCREEN_GUARD_STALE_S` (default 3.0s) cutoff:
  a sample older than that is treated as "can't be read" and fails open, same as today's
  existing no-cursor fail-open path.

## 2026.7.21

- `prereqs` matrix in `screen_diag` + `setup.sh` bootstrap (status + `next_step` per dependency).
- `awareness.extension_state()` — distinguish window-info installed-but-not-loaded vs not installed.
- `server.__version__` derives rolling calver (matches hub); guard test keeps `plugin.json` version-less.

## 2026.6.23

- Initial release: MCP server that gives a model eyes and hands on a Linux
  Wayland desktop — screenshot any monitor and click, type, scroll, drag, and
  read any visible app over xdg-desktop-portal (RemoteDesktop + ScreenCast),
  with optional OCR and OmniParser icon grounding. Ships the `drive-screen`
  skill that encodes the locate-ground-act-confirm loop.
