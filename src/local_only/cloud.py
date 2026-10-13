"""Pinned ownership-boundary patches for the standalone runtime."""
import re

from . import replace_once

MAIN = "out/main/index.js"
HOST = "out/host/index.js"
INTL = "out/renderer/assets/IntlProvider-B-44tSXQ.js"
# Account, analytics and remote-control services owned by the host registry.
# Off-peak scheduling stays: its task records live in the local SQLite database.
CLOUD_SERVICES = ("eD", "Rm", "Ml", "xl", "Ol", "ea", "Dl")
# Channels the local plugin store and automation surfaces still read. Their cloud
# factories are swapped for local stubs so the caller gets an answer instead of a
# request timeout ("Unknown channel" in the host log).
CLOUD_SERVICE_STUBS = {
    'ea': '{getSnapshot:async()=>({pluginStoreOrder:null})}',
    'Dl': '{list:async()=>({code:0,data:[]})}',
    # The plan UI is deleted, but background hooks still ask for this channel:
    # answer with an explicit "unavailable" instead of a channel timeout.
    'Ol': '{codingPlanProviderId:()=>Ot.bigmodelIndividualCodingPlan,'
          'getStaticProducts:async()=>{throw new Error("Coding plans are unavailable in the standalone build")},'
          'getStaticTeamProducts:async()=>{throw new Error("Coding plans are unavailable in the standalone build")},'
          'batchPreview:async()=>{throw new Error("Coding plans are unavailable in the standalone build")},'
          'preview:async()=>{throw new Error("Coding plans are unavailable in the standalone build")},'
          'productInfo:async()=>{throw new Error("Coding plans are unavailable in the standalone build")},'
          'getBillingDiscount:async()=>{throw new Error("Coding plans are unavailable in the standalone build")},'
          'getStartPlanPreview:async()=>{throw new Error("Coding plans are unavailable in the standalone build")},'
          'getManualClaimPlanPreviews:async()=>{throw new Error("Coding plans are unavailable in the standalone build")},'
          'claimManualPlan:async()=>{throw new Error("Coding plans are unavailable in the standalone build")},'
          'getCaptchaConfig:async()=>{throw new Error("Coding plans are unavailable in the standalone build")},'
          'getEnterprisePricing:async()=>{throw new Error("Coding plans are unavailable in the standalone build")}}',
}
# Main-process bindings whose definitions this patch deletes. The window-close
# hook and the host telemetry port run during normal use, so a surviving
# reference is a main-process crash, not dead code: the build must stop here.
REMOVED_MAIN_SYMBOLS = ("Eg", "Gr", "jo", "Rk", "VP", "zP")
# Remote (account-owned) refresh of the built-in provider catalog. The settings
# facade is the only entry point and the synchronizer is what it delegates to;
# both must answer locally so no call path fetches from the removed endpoint.
BUILTIN_REFRESH_FACADE = ('refreshZCodeBuiltin(t){return this.#r?Promise.resolve("disposed"):'
                          'this.#e instanceof Ac?this.#e.refresh(t):this.#n?.refresh(t)??Promise.resolve("skipped")}')
BUILTIN_REFRESH_SYNC = 'refresh(t={}){if(this.#o)return Promise.resolve("disposed")'
# Model settings renders this when no provider is configured yet. It reuses the
# shipped labels (`settings.modelProvider.empty` / `.addProviderDescription`) and
# the same surface/border tokens as the neighbouring settings panes, so it stays
# one family with the rest of the UI without inventing new strings.
PROVIDER_EMPTY_STATE = '''
function ZCodeProviderEmptyState(){const{intl:e}=q();return $.jsx("div",{className:"flex min-h-[14rem] flex-col items-center justify-center gap-1.5 rounded-xl border border-dashed border-border bg-surface p-6 text-center","data-provider-empty-state":`true`,children:[$.jsx("p",{className:"text-ui-base font-medium text-foreground",children:e.formatMessage({id:`settings.modelProvider.empty`})}),$.jsx("p",{className:"text-ui-sm text-foreground-subtlest",children:e.formatMessage({id:`settings.modelProvider.addProviderDescription`})})]})}
'''


def guard_main(text):
    """Reject a patched main bundle that still calls a removed binding/service."""
    for name in REMOVED_MAIN_SYMBOLS:
        if re.search(r'(?<![\w$.])' + name + r'(?![\w$])', text):
            raise ValueError(f'Removed symbol {name} is still referenced in {MAIN}')
    if re.search(r'(?<![\w$])webRemoteControlManager(?![\w$])', text):
        raise ValueError(f'Web remote control manager is still referenced in {MAIN}')
    return guard_remote_ipc_dependencies(text)


def guard_remote_ipc_dependencies(text):
    """Every service the registered IPC handlers call must be passed to ``Ik()``.

    The registration call sits inside a replaced region, so dropping a local
    provider there leaves handlers calling ``e.<name>`` on undefined: the
    renderer sees "is not a function" instead of an answer.
    """
    start = text.find('function Ik(e){')
    end = text.find('s(Ik,"registerRemoteIpcHandlers");', start + 1)
    if start < 0 or end < 0:
        # _remote_ipc already fails the build when these anchors move.
        return text
    used = {m.group(1) for m in re.finditer(r'(?<![\w$.])e\.([A-Za-z_$][\w$]*)', text[start:end])}
    call = text.index('Ik({', end)
    depth = 0
    for index in range(call, len(text)):
        char = text[index]
        if char in '"\'`':
            quote = char
            index += 1
            while text[index] != quote:
                index += 2 if text[index] == '\\' and text[index + 1] in (quote, '\\') else 1
        elif char == '{':
            depth += 1
        elif char == '}':
            depth -= 1
            if not depth:
                break
    provided = {m.group(1) for m in re.finditer(r'(?<![\w$])([A-Za-z_$][\w$]*)\s*:', text[call:index])}
    missing = sorted(used - provided)
    if missing:
        raise ValueError(f'IPC handlers call services the patch does not pass to Ik(): {missing}')
    return text


def drop_balanced(text, anchor):
    """Remove the balanced expression starting at ``anchor`` plus a trailing comma."""
    start = text.index(anchor)
    if text.count(anchor) != 1:
        raise ValueError(f'Anchor is not unique ({text.count(anchor)} matches): {anchor[:60]}')
    depth = 0
    index = start
    while index < len(text):
        char = text[index]
        if char in "\"'`":
            quote = char
            index += 1
            while text[index] != quote:
                index += 2 if text[index] == "\\" and text[index + 1] in (quote, "\\") else 1
        elif char in '([{':
            depth += 1
        elif char in ')]}':
            depth -= 1
            if not depth and index >= start + len(anchor) - 1:
                break
        index += 1
    tail = index + 1
    while tail < len(text) and text[tail] in ' \n':
        tail += 1
    if tail < len(text) and text[tail] == ',':
        tail += 1
    return text[:start] + text[tail:]


def _skip_call(text, index):
    """Return the index of the ``)`` that closes a call whose arguments start at ``index``."""
    depth = 1
    while depth:
        char = text[index]
        if char in "\"'`":
            quote = char
            index += 1
            while text[index] != quote:
                index += 2 if text[index] == "\\" and text[index + 1] in (quote, "\\") else 1
        elif char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
            if not depth:
                break
        index += 1
    return index


def drop_registers(text, symbols):
    """Drop ``.register(sym, factory)`` calls from a service registry chain."""
    for sym in symbols:
        marker = f'.register({sym},'
        while True:
            start = text.find(marker)
            if start < 0:
                break
            text = text[:start] + text[_skip_call(text, start + len(marker)) + 1:]
    return text


def apply_service_boundary(text, stubs, dropped):
    """Bound cloud services in a registry chain.

    Stubbed symbols are answered by the local ``stubs[sym]`` object in every
    chain they appear in, ``dropped`` symbols are removed, and every other
    register call is left untouched.
    """
    for sym in dict.fromkeys((*stubs, *dropped)):
        marker = f'.register({sym},'
        search = 0
        while True:
            start = text.find(marker, search)
            if start < 0:
                break
            arguments = start + len(marker)
            replacement = f'.register({sym},{stubs[sym]})' if sym in stubs else ''
            text = text[:start] + replacement + text[_skip_call(text, arguments) + 1:]
            search = start + len(replacement)
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
    """Keep local handlers, drop cloud-owned ones, answer the rest locally."""
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
    # Remote workspaces (SSH/Docker/WSL) need the account client-config service
    # this build drops, so the feature answers unavailable instead of leaving the
    # renderer without a handler.
    kept.append('fe.handle(k.ConnectRemote,async()=>({success:!1,error:"Remote connections are unavailable in the standalone build."}))')
    kept.append('fe.handle(k.CancelPendingRemoteConnection,async()=>{})')
    kept.append('fe.handle(k.BindRemoteWorkspaceSessionContext,async()=>{})')
    kept.append('fe.handle(k.DisposeRemoteSession,async()=>{})')
    # Community, update and telemetry channels lost their Z.ai owners: answer locally
    # instead of leaving the renderer without a handler.
    kept.append('fe.handle(k.CanOpenCommunity,()=>!1)')
    kept.append('fe.handle(k.GetUpdateState,()=>({kind:"idle"}))')
    kept.append('fe.handle(k.GetAutoUpdatePreferences,()=>({autoDownloadAndInstallUpdates:!1}))')
    kept.append('fe.handle(k.SetAutoDownloadAndInstallUpdates,async()=>{})')
    kept.append('fe.handle(k.OpenUpdateStatusWindow,async()=>{})')
    kept.append('fe.handle(k.AcknowledgePostUpdateReleaseNotes,async()=>{})')
    kept.append('fe.handle(k.ReportTelemetryEvent,async()=>{})')
    kept.append('fe.handle(k.ReportArmsCustomEvent,async()=>{})')
    return text[:open_brace + 1] + ','.join(kept) + text[index:]


def _host(text):
    text = apply_service_boundary(text, CLOUD_SERVICE_STUBS, CLOUD_SERVICES)
    # The built-in provider catalog (resources/config/provider/zcode-builtin.json)
    # is refreshed from the account endpoint (https://zcode.z.ai) and the release
    # is written over the active cache copy. In the standalone build that owner is
    # gone: the fetch adds a network round trip to every provider-settings refresh
    # and a successful release would replace the patched catalog (Zhipu removed,
    # 9Router template added). Both the settings facade and the synchronizer
    # itself answer "skipped" so no caller can reach the removed endpoint.
    text = replace_once(text, BUILTIN_REFRESH_FACADE, 'refreshZCodeBuiltin(t){return Promise.resolve("skipped")}')
    return replace_once(text, BUILTIN_REFRESH_SYNC, 'refresh(t={}){return Promise.resolve("skipped");')


def _renderer(text):
    # Account-driven login gate off; provider setup stays reachable from settings.
    text = replace_once(text, 'enabled:Okn({isWebRemoteControlRoot:Ge})', 'enabled:!1')
    # Paid-plan plugins never reach the catalog (agent drops them), so the
    # "Coding Plan" badge has nothing to label.
    text = replace_once(text, 'function S6t({item:e}){let{intl:t}=q();if(!e.listing?.requiresPaidPlan)return null;',
                        'function S6t({item:e}){let{intl:t}=q();return null;')
    # Subscription surfaces are deleted, not just disabled: the upgrade buttons
    # in the composer quota rows and the plan/usage entries in the profile menu.
    text = drop_balanced(text, '(0,$.jsxs)(lN,{type:`button`,variant:`default`,size:`sm`,onClick:o,className:Z(d,`button-gradient gap-1.5')
    text = drop_balanced(text, '(0,$.jsxs)(lN,{type:`button`,size:`xs`,className:Z(`h-6 shrink-0 gap-1 px-2 text-ui-sm`')
    text = replace_once(text, 'function Qen({state:e,onUsageClick:t,onUpgradeClick:n}){let{intl:r}=q(),i=cN(),',
                        'function Qen({state:e,onUsageClick:t,onUpgradeClick:n}){return null;let{intl:r}=q(),i=cN(),')
    # The Usage stats section becomes the local-only Activity page: the page
    # component renders our panel and the app/coding-plan tab bar is dropped.
    text = replace_once(text, 'function Xwn({activeTab:e,providerSourcesLoading:t,workspaceIdentity:n,workspacePath:r,selectedCodingPlanSource:i}){return e===`app`?(0,$.jsx)(Ewn,{}):(0,$.jsx)(Iwn,{loadingSources:t,workspaceIdentity:n,workspacePath:r,selectedSource:i})}',
                        'function Xwn({activeTab:e,providerSourcesLoading:t,workspaceIdentity:n,workspacePath:r,selectedCodingPlanSource:i}){return $.jsx(ZCodeActivityPanel,{})}')
    text = replace_once(text, 'b===`usage`?(0,$.jsx)(YOn,{activeTab:he,codingPlanSources:ye,onTabChange:Ae}):null', 'null')
    # Web/Mobile remote control pairs through the account relay, so the titlebar
    # trigger and its dialog are deleted rather than answered.
    text = replace_once(text, 'function xin({workspacePath:e,workspaceIdentity:t,remoteSessionId:n,initialTaskId:r,compact:i=!1,className:a}){return C3()?(0,$.jsx)(Sin,{workspacePath:e,workspaceIdentity:t,remoteSessionId:n,initialTaskId:r,compact:i,className:a}):null}',
                        'function xin({workspacePath:e,workspaceIdentity:t,remoteSessionId:n,initialTaskId:r,compact:i=!1,className:a}){return null}')
    # The account provider families (Z.ai, BigModel) and their plan rows are
    # renderer constants; emptying them removes the connect/subscribe surfaces.
    text = replace_span(text, 'Q1e=[{id:W.zaiStartPlan,', 'new Map(Q1e.map(', 'Q1e=[];')
    text = replace_span(text, '$1e=[{id:W.zaiStartPlan,', 'function e0e(e){', '$1e=[];')
    # The provider picker groups Zhipu templates first; with those gone the empty
    # group header is dropped as well.
    text = replace_once(text, '{id:`zhipu`,templates:u.flatMap(t=>e.filter(e=>e.templateId===t))},', '')
    # Model settings still builds an account "Providers" navigation group whose
    # rows come from the OAuth preset providers. That group is never filtered out
    # when empty, so standalone keeps a header waiting on an account source forever
    # (and the detail pane falls back to its permanent common.loading card). Drop
    # the group so only local Custom providers and catalog templates remain.
    text = replace_span(text, 'y=(0,Q.useMemo)(()=>[{id:`preset`,',
                        '{id:`custom`,title:h.formatMessage({id:`settings.modelProvider.customTitle`})',
                        'y=(0,Q.useMemo)(()=>[')
    # Both Model-settings views take the account preset loading gate as a prop;
    # pin it off so neither the group header spinner nor the refresh state waits
    # for a preset source that has no owner locally.
    text = replace_once(text, 'loadingLabel:o.formatMessage({id:`common.loading`}),presetLoading:tt,customLoading:nt,',
                        'loadingLabel:o.formatMessage({id:`common.loading`}),presetLoading:!1,customLoading:nt,')
    text = replace_once(text, 'presetLoading:tt,codingPlanAuthError:ve,', 'presetLoading:!1,codingPlanAuthError:ve,')
    # With no provider configured there is no selectable navigation item, so the
    # detail pane falls back to its permanent common.loading card: the page reads
    # like a search that never finishes. Standalone renders its own empty state
    # instead (label `settings.modelProvider.empty` ships with the app) and leaves
    # the template picker path untouched for when providers do exist.
    text = replace_once(text, 'ie?(0,$.jsx)(OCn,{templates:m,creating:oe,',
                        '!ie&&(p?.length??0)===0?(0,$.jsx)(ZCodeProviderEmptyState,{}):ie?(0,$.jsx)(OCn,{templates:m,creating:oe,')
    text += PROVIDER_EMPTY_STATE
    # The status hook polls the removed channel once per second, so it is inert.
    text = replace_once(text, 'function o4({enabled:e=!0,intervalMs:t=1e3}={}){let n=Wo(),[r,i]=(0,Q.useState)({status:`idle`});return(0,Q.useEffect)(()=>{if(!e||!n){i({status:`idle`});return}',
                        'function o4({enabled:e=!0,intervalMs:t=1e3}={}){let n=Wo(),[r,i]=(0,Q.useState)({status:`idle`});return(0,Q.useEffect)(()=>{if(!0){i({status:`idle`});return}')
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
    # The telemetry core is gone, so the host telemetry port must not report to it.
    text = replace_once(text, 'onSessionCreateTelemetry:s(a=>{jo.reportEvent(a.event).catch(()=>{})},"onSessionCreateTelemetry")', 'onSessionCreateTelemetry:s(()=>{},"onSessionCreateTelemetry")')
    text = replace_once(text, 'VP(),fr(),us.focusWindow(mo(t))', 'fr(),us.focusWindow(mo(t))')
    text = replace_once(text, 'VP(),us.blurWindow(mo(t))', 'us.blurWindow(mo(t))')
    text = replace_span(text, 'GP=YC(', 'function jP(e)', 'GP=async()=>null,qP={shutdown:async()=>{}},Xu=void 0,ep=X||Z.getVersion();')
    text = replace_span(text, ',Gr=Hb(', 'var Qa=!1;', ';')
    text = replace_once(text, 'xb(w,{iconPath:qz});', '')
    text = _remote_ipc(text)
    # The remote control registrations left with their owner, so the function
    # that only registered them is unreachable; the window-close hook called the
    # removed manager directly and must stay guarded. The span keeps its end
    # anchor, so it must end after the registration marker.
    text = replace_span(text, 'function Rk(e){', 'function n1(e){', '')
    text = replace_once(text, 'e.webRemoteControlManager.disposeWindow(n),', '')
    text = replace_span(text, 'jo.flushPendingReports({timeoutMs:2e3}),', '(async()=>{try{await o?.dispose()}', '')
    text = replace_span(text, 'await Oy(Ve),SV(),Ly(', '(process.platform==="darwin"||process.platform==="win32")&&Z.clearRecentDocuments()', '')
    text = replace_span(text, 'Xu=jy({rollout:pV,', 'w.info("[startup] ',
                        'Ei.handle(k.GetRendererActionTraceConfig,()=>({enabled:!1})),'
                        'Ik({logger:w,isDockerDaemonAvailable:Gc,listAvailableWSLDistros:Kc,listAvailableDockerContainers:qc,listSSHConfigAliases:Zc}),')
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
    return guard_main(text)


def _intl(text):
    """Rename the account-era labels: local Activity page, no upgrade wording."""
    text = replace_once(text, '"chat.error.noAvailableModel":`No model available. Upgrade or set a custom model.`',
                        '"chat.error.noAvailableModel":`No model available. Set a custom model.`')
    text = replace_once(text, '"chat.error.noAvailableModel":`当前没有可用模型。请开通编程套餐或配置自定义模型。`',
                        '"chat.error.noAvailableModel":`当前没有可用模型。请配置自定义模型。`')
    text = replace_once(text, '"settings.usageTitle":`Usage stats`', '"settings.usageTitle":`Activity`')
    text = replace_once(text, '"settings.usageTitle":`使用统计`', '"settings.usageTitle":`活跃度`')
    text = replace_once(text, '"settings.usageDescription":`Review rough activity and model usage aggregated from local sessions.`',
                        '"settings.usageDescription":`Prompt activity and streaks from your local history.`')
    text = replace_once(text, '"settings.usageDescription":`查看会话活跃度与模型用量的粗略统计。`',
                        '"settings.usageDescription":`来自本地历史的 prompt 与连续天数统计。`')
    text = replace_once(text, '"settings.usage.sectionTitle":`Usage stats`', '"settings.usage.sectionTitle":`Activity`')
    text = replace_once(text, '"settings.usage.sectionTitle":`使用统计`', '"settings.usage.sectionTitle":`活跃度`')
    return text


def patch_archive(archive, replacements, renderer_asset):
    text = replacements.get(MAIN, archive.read(MAIN)).decode()
    replacements[MAIN] = _main(text).encode()
    text = replacements.get(HOST, archive.read(HOST)).decode()
    replacements[HOST] = _host(text).encode()
    text = replacements.get(renderer_asset, archive.read(renderer_asset)).decode()
    replacements[renderer_asset] = _renderer(text).encode()
    text = replacements.get(INTL, archive.read(INTL)).decode()
    replacements[INTL] = _intl(text).encode()


def patch_agent(text):
    # Marketplace entries that require a paid plan are dropped from the catalog
    # manifest, so neither the store nor the CLI can offer them.
    text = replace_once(text, '.filter(fu).map(a=>{let l=typeof a.name=="string"?a.name.trim():"";if(l.length===0)return null;',
                        '.filter(fu).map(a=>{let l=typeof a.name=="string"?a.name.trim():"";if(l.length===0||a.requiresPaidPlan===!0)return null;')
    # The account provider families (Z.ai, BigModel) are the rows Model settings
    # offers to connect; without them no account surface is reachable.
    text = replace_span(text, 'wXe=[{id:"zai",label:"Z.ai",', 'QZi=new Map(', 'wXe=[],')
    text = replace_span(text, 'let $=Vec(z),J=await N3e(', 'let ie=e.providerEndpointRoutingPort', 'let J=z,q;')
    text = replace_once(text, 'Ye.start(),I?.start(),L=DXo(Tt,Fe=>Ye.send(Fe),u),', 'Ye.start(),')
    text = replace_once(text, ',n("telemetry",()=>Iwt())', '')
    text = replace_once(text, 'zcodeBuiltinProviders:t.providers,', 'zcodeBuiltinProviders:uw.empty(),')
    return text
