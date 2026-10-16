"""Local CCode desktop profile: text-first perception, element-accurate clicks, non-blocking pointer policy.

Loaded by server.py when MCP_SCREEN_PROFILE=ccode-fast, with the server's module globals as
`ns`, so this file is the only seam we edit: the vendored screen-mcp modules stay untouched.
"""
import json
import os
import time

# --- tuning knobs (env-overridable; defaults chosen for a shared desktop) -------------------
# A parked pointer is not a takeover: the user may move the mouse and leave it elsewhere while
# the agent works. Only continuous driving counts, and input is injected once the pointer is
# quiet. See classify_pointer_window.
IDLE_PX = float(os.environ.get("CCODE_CUA_IDLE_PX", "16"))
IDLE_MS = int(os.environ.get("CCODE_CUA_IDLE_MS", "600"))
TAKEOVER_MS = int(os.environ.get("CCODE_CUA_TAKEOVER_MS", "2500"))
POLL_S = float(os.environ.get("CCODE_CUA_POLL_S", "0.1"))

PERCEPTION_TOOLS = {
    "screen_read_text",
    "screen_wait_text",
    "screen_verify",
    "screen_sense",
}
ACTION_TOOLS = {"screen_focus"}
POST_SHOT_TOOLS = ["screen_click", "screen_scroll", "screen_drag", "screen_key", "screen_type", "screen_do"]


def classify_pointer_window(samples, idle_px=None, idle_ms=None, takeover_ms=None):
    """Is the user really driving the pointer, or did it just end up elsewhere?

    `samples` is [(t_ms, x, y)] in chronological order, starting where the guard first saw the
    pointer diverge from what we last commanded. Returns:

    - 'pending': the window is too short to judge, keep sampling.
    - 'idle':    the pointer stopped moving (parked, or a stray nudge): safe to inject input.
    - 'driving': the user kept moving it for the whole window: yield to them.
    """
    idle_px = IDLE_PX if idle_px is None else idle_px
    idle_ms = IDLE_MS if idle_ms is None else idle_ms
    takeover_ms = TAKEOVER_MS if takeover_ms is None else takeover_ms
    if len(samples) < 2:
        return "pending"
    last_move = samples[0][0]
    moved = False
    for (t0, x0, y0), (t1, x1, y1) in zip(samples, samples[1:]):
        if abs(x1 - x0) > idle_px or abs(y1 - y0) > idle_px:
            last_move, moved = t1, True
    span = samples[-1][0] - samples[0][0]
    quiet_for = samples[-1][0] - last_move
    if not moved:
        return "idle" if span >= idle_ms else "pending"
    if quiet_for >= idle_ms:
        return "idle"
    if span >= takeover_ms:
        return "driving"
    return "pending"


def install_pointer_policy(ns):
    """Wrap input.guard_user with the hysteresis policy above.

    The vendored guard aborts the moment the live pointer differs from the last position we
    commanded by more than GUARD_THRESH. That turns any stray mouse movement into a stopped
    task. Every caller reaches the guard through `inp.guard_user` (server, autoloop, capture's
    nudge, desktop_open_app), so replacing the module attribute covers all of them while the
    `force=True` escape hatch and the UserControlError contract stay intact.
    """
    inp = ns["inp"]
    state = ns["state"]
    capture = ns["capture"]
    original = inp.guard_user

    def guard_user(force=False):
        if force:
            return original(force)
        try:
            return original(False)
        except inp.UserControlError as exc:
            # `except ... as exc` unbinds at the end of the block, so keep our own reference.
            taken = exc
        node = state.SESSION.get("cmd_node")
        samples = []
        t0 = time.monotonic()
        while True:
            now = (time.monotonic() - t0) * 1000.0
            try:
                pos = (
                    capture.cursor_pos(prefer_node=node)
                    if node is not None
                    else capture.cursor_pos()
                )
            except Exception:
                pos = None
            if pos is not None:
                samples.append((now, float(pos[0]), float(pos[1])))
            verdict = classify_pointer_window(samples)
            if verdict == "idle":
                return
            if verdict == "driving":
                raise taken
            if now >= TAKEOVER_MS:
                # Undecidable window (cursor unreadable / too few samples): fail open, exactly
                # like the vendored guard does when it cannot read the pointer.
                return
            time.sleep(POLL_S)

    guard_user.policy = "ccode-fast-hysteresis"
    inp.guard_user = guard_user


def install_observation_policy(ns):
    """Skip the post-action image when the action changed nothing on screen.

    A no-op action returns the same pixels; attaching them again costs ~1300-4800 visual
    tokens and invites the model to re-read a frame it already saw. The vendored SENSE block
    already states it ("nothing changed"), so the model still learns the action failed. We key
    off that block rather than the raw signal, because the raw signal reads as no_op when there
    is simply no baseline frame yet (first shot after startup).
    """
    text = ns["_txt"]
    original = ns["_maybe_shot"]

    def maybe_shot(args, content, t0):
        out = original(args, content, t0)
        if os.environ.get("CCODE_CUA_SKIP_UNCHANGED_SHOT", "1") == "0":
            return out
        noop = any(
            isinstance(item, dict)
            and item.get("type") == "text"
            and str(item.get("text", "")).startswith("SENSE ")
            and "nothing changed" in str(item.get("text", ""))
            for item in out
        )
        if not noop:
            return out
        kept = [item for item in out if not (isinstance(item, dict) and item.get("type") == "image")]
        kept.append(
            text(
                "shot skipped: the screen did not change after this action. Treat it as a no-op "
                "and pick another target, or take a screenshot only if you need the pixels."
            )
        )
        return kept

    maybe_shot.policy = "ccode-fast-noop-skip"
    ns["_maybe_shot"] = maybe_shot


def install_lazy_warmup(ns):
    """Skip the OCR/OmniParser model load at MCP startup unless explicitly asked.

    server.main() starts grounding.warmup() on a background thread to hide the model load
    from the first annotate(). The sessions are built on demand anyway (double-checked locks
    in ocr_boxes/_omni_session), so warming is a pure prefetch: it costs ~60 MB for every MCP
    session that never perceives anything. Set CCODE_CUA_WARMUP=1 to restore the prefetch for
    latency-sensitive use.
    """
    if os.environ.get("CCODE_CUA_WARMUP") == "1":
        return
    grounding = ns["grounding"]
    grounding.warmup = lambda *a, **k: None


def portal_denial_message(detail):
    """Actionable text for a portal input refusal.

    GNOME's portal answers NotifyPointer/NotifyKeyboard with 'Session is not allowed to call
    NotifyPointer methods (0)' when the granted session has no pointer/keyboard permission.
    Without this translation the agent sees a raw GDBus traceback and reports a vague
    "rejected by D-Bus", which is exactly what a human then cannot act on.
    """
    return (
        "Input was refused by the desktop portal: " + detail + "\n"
        "The portal session has no pointer/keyboard permission, so clicks, keys, and typing "
        "cannot be injected through it. Perception still works (screenshots, screen_read_text). "
        "Two fixes, either one is enough:\n"
        "1. Preferred: use the kernel input backend. /dev/uinput must be writable by this user — "
        "be in group `input` and add udev rule "
        'KERNEL=="uinput", SUBSYSTEM=="misc", GROUP="input", MODE="0660", then log out and back '
        "in.\n"
        "2. Or re-grant the portal: delete ~/.config/mcp-screen/token and approve the next dialog "
        "with remote control (pointer and keyboard) allowed.\n"
        "Do not retry the same call unchanged: it will be refused again until one of the two is "
        "done."
    )


def install_input_fallback_policy(ns):
    """Turn a refused portal input into an actionable error instead of a traceback.

    Seam discipline: the vendored input.py keeps raising its raw GError — the translation
    happens at the handler map, so the vendor file stays untouched.
    """
    handlers = ns["HANDLERS"]
    for name in (
        "screen_click",
        "screen_type",
        "screen_key",
        "screen_scroll",
        "screen_drag",
        "screen_move_mouse",
        "screen_do",
    ):
        original = handlers.get(name)
        if original is None:
            continue

        def wrapped(args, fn=original):
            try:
                return fn(args)
            except Exception as exc:
                text = str(exc)
                if "not allowed to call" not in text and "Notify" not in text:
                    raise
                return {"content": [ns["_txt"](portal_denial_message(text))], "isError": True}

        handlers[name] = wrapped


def install(ns):
    from gi.repository import Gio

    # --- tool surface: cheap perception + accurate targeting -------------------------------
    # The vendored server exposes 21 tools; the fast profile used to keep only the 10
    # screenshot-and-guess ones. Re-adding the text/element tools is what removes most of the
    # model's pixel reasoning, because screen_read_text returns element ids and desktop
    # coordinates with no image at all (the image is a fixed ~1300-4800 visual tokens).
    allowed = {
        "screen_screenshot",
        "screen_list_monitors",
        "screen_move_mouse",
        "screen_click",
        "screen_scroll",
        "screen_drag",
        "screen_key",
        "screen_type",
        "screen_do",
    } | PERCEPTION_TOOLS | ACTION_TOOLS
    ns["TOOLS"][:]=[t for t in ns["TOOLS"] if t["name"] in allowed]
    for t in ns["TOOLS"]:
        if t["name"] == "screen_screenshot":
            t["description"] = (
                "Observe the desktop as an image. Screenshot only when you need to SEE layout, "
                'color, or an unlabelled control; screen_read_text answers "what is on screen" '
                "as text for far fewer tokens. No args = full desktop. annotate=true overlays "
                "numbered Set-of-Marks and returns element ids you can click with "
                "screen_click(element=<id>) instead of guessing coordinates. use_cache=true "
                "(with annotate) reuses elements already learned for this screen and skips OCR. "
                "region=[x,y,w,h] takes DESKTOP pixels, not view pixels: use it to zoom on small "
                "text instead of guessing. Coordinates you read from the image are view pixels: "
                'pass space="view" with view_id=<the view#N in the returned header>. '
                "The returned header states shipped size and scale; never compute it yourself."
            )
        if t["name"] == "screen_click":
            t["description"] = (
                "Click a target. Prefer element=<id> from the latest screen_read_text or "
                "screen_screenshot(annotate=true): the server resolves the exact coordinates and "
                "rejects ids captured under an older view, so you never guess a pixel. Otherwise "
                "pass x,y as view-space pixels with the matching view_id. Omit x,y to click in "
                "place. button: left|right|middle; double:bool. focus='app' raises and "
                "keyboard-focuses that window first. verify=true adds a warning when nothing on "
                "screen changed (catches a silent misclick). A post-action screenshot is included "
                "by default; inspect it instead of taking another one."
            )
        if t["name"] == "screen_read_text":
            t["description"] = (
                "Read the screen as TEXT plus clickable elements: no image, so it costs a "
                "fraction of a screenshot and is the default way to locate a target, read a "
                "value, or confirm that something appeared. Returns "
                "{origin,size,focused,count,elements:[{id,role,text,x,y}]} with desktop "
                "coordinates. Pass contains=<text> to return only matching elements (cheap: use "
                "it instead of dumping the whole screen). Pass elements straight to "
                "screen_click(element=<id>). use_cache=true (default) reuses the learned map of "
                "a screen you have already seen and skips OCR."
            )
        if t["name"] == "screen_wait_text":
            t["description"] = (
                "Wait until text appears or disappears, then return the match. Use this instead "
                "of taking screenshot after screenshot while a page loads or an app starts. "
                "Cheap, read-only, bounded wait."
            )
        if t["name"] == "screen_verify":
            t["description"] = (
                "Check whether the area around a point (or the watched window) actually changed, "
                "and report it as text. Use after an action whose effect you cannot see yet, so "
                "you do not have to pull a screenshot just to answer 'did that work'."
            )
        if t["name"] == "screen_sense":
            t["description"] = (
                "Return the change signal of the most recent action (changed / opened / modal / "
                "no_op / activity) as text. Cheap way to notice a no-op click without a "
                "screenshot. Passive: it does not wait for anything new."
            )
        if t["name"] == "screen_focus":
            t["description"] = (
                "Raise and keyboard-focus a window by app name, title substring, or window id "
                "(e.g. focus='firefox'). Keyboard input goes to the focused window, so call this "
                "before screen_type/screen_key when the target is not already focused. Reports an "
                "error instead of pretending when the focus did not transfer."
            )
        if t["name"] == "screen_do":
            t["description"] = (
                "Execute a predictable sequence in ONE call, then receive a final screenshot by "
                'default. steps=[{action:"key",keys:"Ctrl+L"},{action:"type",text:"https://'
                'example.com/"},{action:"key",keys:"Enter"}]. Batch only steps whose targets '
                "remain known; stop and observe when navigation is uncertain. Pass shot=false "
                "when you will verify with screen_read_text/screen_wait_text next. STOPPED means "
                "the user is using the machine: yield, never force."
            )
        if t["name"] == "screen_type":
            t["description"] += (
                " Pass enter=true to submit in the same call instead of a second round trip."
            )
        if t["name"] in POST_SHOT_TOOLS:
            t["description"] += (
                " A post-action screenshot and its SENSE line are included by default. If SENSE "
                "says nothing changed, treat the action as a no-op: do not repeat it, observe and "
                "pick another target. Set shot=false for an intermediate step you will verify "
                "with screen_read_text."
            )
    # Defaults are enforced in handlers, not merely advertised in JSON Schema.
    for name in POST_SHOT_TOOLS:
        original = ns["HANDLERS"][name]
        def wrap(args, fn=original):
            args=dict(args);args.setdefault('shot',True);args.setdefault('settle',250)
            return fn(args)
        ns["HANDLERS"][name]=wrap

    # Wait for real damage instead of polling every frame: the same settle ceiling is reached
    # sooner when the compositor tells us the frame changed, and the vendored hybrid mode keeps
    # a poll floor as a backstop. Revert by deleting this line (or MCP_SCREEN_WAIT_MODE=poll).
    if os.environ.get("MCP_SCREEN_WAIT_MODE") is None:
        ns["capture"].WAIT_MODE = "hybrid"

    install_pointer_policy(ns)
    install_observation_policy(ns)
    install_lazy_warmup(ns)
    install_input_fallback_policy(ns)

    def apps(query):
        q=query.casefold().strip();matches=[]
        for app in Gio.AppInfo.get_all():
            if not app.should_show():continue
            name=app.get_display_name() or app.get_name();aid=app.get_id() or ''
            if q==aid.casefold() or q==name.casefold():score=0
            elif q in name.casefold() or q in aid.casefold():score=1
            else:continue
            matches.append((score,aid,name,app))
        return sorted(matches,key=lambda x:(x[0],x[1]))
    def open_app(args):
        query=str(args.get('app','')).strip()
        if not query:return {'content':[ns['_txt']('app is required')],'isError':True}
        rows=apps(query)
        if not rows:return {'content':[ns['_txt']('No installed desktop application matches '+query)],'isError':True}
        best=[r for r in rows if r[0]==rows[0][0]]
        if len(best)>1:
            return {'content':[ns['_txt']('Choose an exact app id from '+json.dumps([{'id':r[1],'name':r[2]} for r in best[:12]]))]}
        row=best[0]
        # Only installed desktop apps; no shell commands, guessed executables, or software-store results.
        ns['inp'].guard_user(False)
        row[3].launch([],None)
        return {'content':[ns['_txt']('Opened '+row[2]+' ('+row[1]+'). Use screen_read_text or a screenshot to verify it is ready before input.') ]}
    ns['HANDLERS']['desktop_open_app']=open_app
    ns['TOOLS'].append({'name':'desktop_open_app','title':'Open Desktop App','description':'Open an already-installed real desktop application by name or exact .desktop id. Prefer this over searching the GNOME overview, which may show software-store entries. If ambiguous, returns exact ids without launching. After launch, confirm readiness with screen_wait_text or one screenshot. Does not type or navigate for you.','inputSchema':{'type':'object','properties':{'app':{'type':'string'}},'required':['app']}})
    ns['INSTRUCTIONS']='''Real Linux desktop control via Fedora portal. This IS the configured Computer Use backend.
PERCEPTION, cheapest first:
1. screen_read_text: what is on screen as TEXT plus element ids and desktop coordinates, no image. Use contains=<text> to fetch just the label you need. This is your default probe.
2. screen_click(element=<id>): click the exact element the last read_text or annotate screenshot found. Use it for every labelled target instead of guessing pixels.
3. screen_screenshot: only when you must SEE layout or an unlabelled control. annotate=true adds numbered marks plus element ids. region=[x,y,w,h] takes desktop pixels and zooms on small text without a re-guess.
ACTIONS: prefer keyboard shortcuts and screen_do for predictable sequences (Ctrl+L -> type URL -> Enter is one batch). Actions return a screenshot plus a SENSE line by default; if SENSE says nothing changed, the action was a no-op: do not repeat it, observe and choose another target. Pass shot=false when you will verify with screen_read_text next. screen_wait_text waits for a label; screen_verify and screen_sense report change as text; screen_focus raises a window before you type into it.
Coordinates: space="view" is the default and refers to pixels in the screenshot you just read. Never multiply or divide them yourself; the backend maps to the desktop. Pass view_id=<view#N> when you took the screenshot more than one step ago.
Use desktop_open_app for installed applications.
STOPPED means the user is using the machine right now (they kept moving the pointer). Yield to them, stop acting, and say so. Never pass force=true to defeat takeover; use force only when the user asks you to take control back.
A parked pointer is not takeover: the backend ignores stray movement and waits for the pointer to go idle before acting.
Observe after uncertain transitions and verify the requested result before reporting success.'''
