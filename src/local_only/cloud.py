"""Pinned ownership-boundary patches for the standalone runtime."""
import re

from . import replace_once

MAIN = "out/main/index.js"
HOST = "out/host/index.js"
# Account, analytics and remote-control services owned by the host registry.
# Off-peak scheduling stays: its task records live in the local SQLite database.
CLOUD_SERVICES = ("eD", "Rm", "Ml", "xl", "Ol", "ea", "Dl")


def drop_registers(text, symbols):
    """Drop ``.register(sym, factory)`` calls from a service registry chain."""
    for sym in symbols:
        marker = f'.register({sym},'
        while True:
            start = text.find(marker)
            if start < 0:
                break
            end = start + len(marker)
            depth = 1
            while depth:
                char = text[end]
                if char in "\"'`":
                    quote = char
                    end += 1
                    while text[end] != quote:
                        end += 2 if text[end] == "\\" and text[end + 1] in (quote, "\\") else 1
                elif char in "([{":
                    depth += 1
                elif char in ")]}":
                    depth -= 1
                    if not depth:
                        break
                end += 1
            text = text[:start] + text[end + 1:]
    return text


def _split_top_level(body):
    """Split a function body into top-level comma-separated expressions."""
    items = []
    depth = 0
    current = []
    index = 0
    while index < len(body):
        char = body[index]
        if char in "\"'`":
            quote = char
            current.append(char)
            index += 1
            while body[index] != quote:
                escaped = body[index] == "\\" and body[index + 1] in (quote, "\\")
                current.append(body[index])
                if escaped:
                    current.append(body[index + 1])
                index += 2 if escaped else 1
            current.append(body[index])
        elif char in '([{':
            depth += 1
            current.append(char)
        elif char in ')]}':
            depth -= 1
            current.append(char)
        elif char == ',' and depth == 0:
            items.append(''.join(current))
            current = []
        else:
            current.append(char)
        index += 1
    items.append(''.join(current))
    return items


def _remote_ipc(text):
    """Keep local main-process handlers; drop remote control, OAuth and telemetry."""
    start = 'function Ik(e){'
    end = 's(Ik,"registerRemoteIpcHandlers");'
    first = text.index(start)
    last = text.index(end, first)
    open_brace = first + len(start) - 1
    depth = 0
    index = open_brace
    while True:
        char = text[index]
        if char in '"\'`':
            quote = char
            index += 1
            while text[index] != quote:
                index += 2 if text[index] == "\\" and text[index + 1] in (quote, "\\") else 1
        elif char == '{':
            depth += 1
        elif char == '}':
            depth -= 1
            if not depth:
                break
        index += 1
    kept = []
    for item in _split_top_level(text[open_brace + 1:index]):
        head = item.lstrip()
        cloud = (
            'reportRemoteUsageEvent' in head
            or 'armsCustomContext' in head
            or 'ScopedServicePortReady' in head
            or head.startswith('Rk({')
            or head.startswith('fe.on(k.OAuth')
            or head.startswith('fe.on(k.RendererReady,')
            or head.startswith('fe.on(k.SyncTelemetryContext,')
            or head.startswith('fe.handle(k.Report')
            or head.startswith('fe.handle(k.ConnectRemote,')
            or head.startswith('fe.handle(k.CancelPendingRemoteConnection,')
            or head.startswith('fe.handle(k.BindRemoteWorkspaceSessionContext,')
            or head.startswith('fe.handle(k.DisposeRemoteSession,')
            or 'FinalArmsCustomEventsE2E' in head
        )
        if head and not cloud:
            kept.append(head)
    kept.append('xa.handle(k.GetWebRemoteControlStatus,()=>({status:"idle"}))')
    # Community/update/telemetry channels lost their Z.ai owners: answer locally
    # instead of leaving the renderer without a handler.
    kept.append('fe.handle(k.CanOpenCommunity,()=>!1)')
    kept.append('fe.handle(k.GetUpdateState,()=>({kind:"idle"}))')
    kept.append('fe.handle(k.ReportTelemetryEvent,async()=>{})')
    kept.append('fe.handle(k.ReportArmsCustomEvent,async()=>{})')
    return text[:open_brace + 1] + ','.join(kept) + text[index:]


def _host(text):
    return drop_registers(text, CLOUD_SERVICES)


def _renderer(text):
    # Account-driven login gate off; provider setup stays reachable from settings.
    text = replace_once(text, 'enabled:Okn({isWebRemoteControlRoot:Ge})', 'enabled:!1')
    text = replace_once(text, '(0,Q.useEffect)(()=>{z&&I(`provider-request`)},[z]);', '(0,Q.useEffect)(()=>{void z},[z]);')
    # The account restore hook is gone, so the startup "restoring session" flags
    # must be cleared locally or the workspace never leaves the loading gate.
    text = replace_span(text, 'function jjn({accountIntentKey', 'function Mjn({enabled:e,isDesktop:t,platform:n,theme:r})',
                        'function jjn({setIsRestoringOAuthSession:e,setOAuthPollingActive:t}){e(!1),t(!1)}\n')
    # Z.ai entitlements: off-peak gray rollout and coding-plan support are account services.
    text = replace_once(text, 'r.getOffPeakClientConfig({forceRefresh:!0}).catch(e=>(J.warn(`[off-peak] gray config load failed`,_1(e)),null))', 'Promise.resolve(null)')
    # Provider family domain comes from local model selection, not an account session.
    text = replace_once(text, 'let n=a(await e.oauthService.getActiveProvider()),r=null;', 'let n=null,r=null;')
    # Coding-plan support and dynamic-workflow rollouts are Z.ai services; report
    # them as unavailable locally instead of calling a removed channel.
    text = replace_once(text, 'let i=await n.getCodingPlanSupport();', 'let i={supported:!1};')
    text = replace_once(text, 'let r=await e.getDynamicWorkflowClientConfig(t);n({status:`ready`,enabled:r.enabled===!0,config:r})',
                        'n({status:`ready`,enabled:!1,config:null})')
    # Suggested prompts come from the cloud scenes service, and the marketing
    # banner from the marketing-touch service; both are account surfaces.
    text = replace_once(text, 'let r=Ovt(e,{enabled:t})', 'let r=Ovt(e,{enabled:!1})')
    text = replace_once(text, 'let e=n.marketingTouchService;if(!e||f)return null;', 'return null;')
    # Coding-plan usage snapshots are Z.ai account data; the widget shows nothing locally.
    text = replace_once(text, 'YCn(a,{enabled:!e&&!!c,', 'YCn(a,{enabled:!1,')
    # The plan badge/pricing widget polls a billing discount from the account
    # service; keep the guard's unavailable branch by passing no service.
    text = replace_once(text, 'function EQe(){return DQe(Og()?.codingPlanSubscriptionService)}', 'function EQe(){return DQe(void 0)}')
    text = replace_once(text, 'nr=DQe(De.codingPlanSubscriptionService)', 'nr=DQe(void 0)')
    # The sidebar account trigger has no login flow left; drop both shell props so
    # the shell stops rendering an inert "Connect" button.
    trigger = 'onLogin:w?void 0:Ft'
    if text.count(trigger) != 2:
        raise ValueError(f'Renderer account trigger changed ({text.count(trigger)} matches)')
    text = text.replace(trigger, 'onLogin:void 0')
    # The footer menu keeps locale/theme/zoom/settings, but its trigger is no
    # longer an account entry: local label, local test id, no sign-in item.
    text = replace_once(text, 'function Ein(e,t){return e?Tin(e):t({id:`sidebar.profile.notLoggedIn`})}',
                        'function Ein(e){return e?Tin(e):`ZCode on Steroids`}')
    text = replace_once(text, 'Ein(u,v.formatMessage)', 'Ein(u)')
    text = replace_once(text, '"data-testid":fe,"aria-label":D,', '"data-testid":`app-menu`,"aria-label":D,')
    return text




def replace_span(text, start, end, replacement):
    """Replace one bounded upstream region, retaining its end anchor."""
    if text.count(start) != 1 or text.count(end) != 1:
        raise ValueError(f"Cloud boundary is not unique: {start!r} / {end!r}")
    first = text.index(start)
    last = text.index(end, first + len(start))
    return replace_once(text, text[first:last], replacement)


def _main(text):
    text = replace_span(text, 'var Eg=Ns.init(', 'p();m();import{randomUUID as Mg}', '')
    text = replace_span(text, 'var jo=jm(', 'Z.on("browser-window-focus"', '')
    text = replace_once(text, 'VP(),fr(),us.focusWindow(mo(t))', 'fr(),us.focusWindow(mo(t))')
    text = replace_once(text, 'VP(),us.blurWindow(mo(t))', 'us.blurWindow(mo(t))')
    text = replace_span(text, 'GP=YC(', 'function jP(e)', 'GP=async()=>null,qP={shutdown:async()=>{}},Xu=void 0,ep=X||Z.getVersion();')
    text = replace_span(text, ',Gr=Hb(', 'var Qa=!1;', ';')
    text = replace_once(text, 'xb(w,{iconPath:qz});', '')
    text = _remote_ipc(text)
    text = replace_span(text, 'jo.flushPendingReports({timeoutMs:2e3}),', '(async()=>{try{await o?.dispose()}', '')
    text = replace_span(text, 'await Oy(Ve),SV(),Ly(', '(process.platform==="darwin"||process.platform==="win32")&&Z.clearRecentDocuments()', '')
    text = replace_span(text, 'Xu=jy({rollout:pV,', 'w.info("[startup] ', 'Ei.handle(k.GetRendererActionTraceConfig,()=>({enabled:!1})),Ik({logger:w}),')
    text = replace_once(text, 'webRemoteControlManager:Gr,', '')
    text = replace_once(text, 'restorePreviouslyEnabledWebRemoteControl:s((c,d)=>{Gr.restorePreviouslyEnabled(c,d)},"restorePreviouslyEnabledWebRemoteControl"),', '')
    text = replace_once(text, 'syncWebRemoteControlWorkspaces:s((c,d)=>{Gr.syncAvailableWorkspaces(c,d),Gr.restorePreviouslyEnabled(c,d)},"syncWebRemoteControlWorkspaces"),syncWebRemoteControlTasks:s((c,d)=>Gr.syncAvailableTasks(c,d),"syncWebRemoteControlTasks"),', '')
    text = replace_once(text, ',e.restorePreviouslyEnabledWebRemoteControl(n.id,o.data.map(i=>({workspacePath:i})))', '')
    text = replace_span(text, 'j.on(k.SyncWebRemoteControlWorkspaces,', 'j.on(k.SyncWindowUnreadCount,', '')
    text = replace_span(text, 'j.handle(k.CanOpenCommunity,', 'j.handle(k.GetDesktopSessionActivity,', '')
    text = replace_once(text, 'try{Dg(f)}catch{}', '')
    text = replace_once(text, 'typeof e.receivePreviewUpdates=="boolean"&&Xd(e.receivePreviewUpdates,"settings receivePreviewUpdates changed"),', '')
    text = replace_span(text, 'function cV(){', 's(cV,"resolveDesktopContextPromptEnabledForHost");', 'function cV(){return!1}')
    text = replace_span(text, 'function lV(){', 's(lV,"awaitFirstHostSpawnDecision");', 'function lV(){return Promise.resolve()}')
    # The @arms/rum-electron imports stay so their bindings resolve; the reporter
    # is never started, so nothing is exported.
    return text


def patch_archive(archive, replacements, renderer_asset):
    text = replacements.get(MAIN, archive.read(MAIN)).decode()
    replacements[MAIN] = _main(text).encode()
    text = replacements.get(HOST, archive.read(HOST)).decode()
    replacements[HOST] = _host(text).encode()
    text = replacements.get(renderer_asset, archive.read(renderer_asset)).decode()
    replacements[renderer_asset] = _renderer(text).encode()


def patch_agent(text):
    text = replace_span(text, 'let $=Vec(z),J=await N3e(', 'let ie=e.providerEndpointRoutingPort', 'let J=z,q;')
    text = replace_once(text, 'Ye.start(),I?.start(),L=DXo(Tt,Fe=>Ye.send(Fe),u),', 'Ye.start(),')
    text = replace_once(text, ',n("telemetry",()=>Iwt())', '')
    text = replace_once(text, 'zcodeBuiltinProviders:t.providers,', 'zcodeBuiltinProviders:uw.empty(),')
    return text
