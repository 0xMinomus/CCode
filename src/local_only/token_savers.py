"""Pinned renderer and agent patches for local Token savers."""

from . import replace_once, storage
PIGGY_BANK_IMPORT = 'import{default as CCodePiggyBank}from"./piggy-bank-BLUAYYsf.js";'


ROUTE = 'function TS(e){return e===`general`||e===`appearance`||e===`migration`||e===`browser`||e===`modelProvider`||e===`memory`||e===`plugin`||e===`mcp`||e===`skill`||e===`plugins`||e===`usage`||e===`subagents`||e===`commands`||e===`hooks`||e===`workspaceFileSearch`||e===`computerUse`||e===`automations`||e===`shortcuts`}'
ROUTE_WITH_TOKEN_SAVERS = replace_once(ROUTE, '||e===`memory`||e===`plugin`||', '||e===`memory`||e===`tokenSavers`||e===`plugin`||')
NAVIGATION = 'function VOn({isDesktop:e=!1,isMacDesktop:t=!1,isWindowsDesktop:n=!1}={}){let r=e||t||n,i=BOn.filter(e=>e.id===`computerUse`&&!r?!1:ES(e.id));return{settingsSectionGroups:zOn.map(e=>({...e,sections:i.filter(t=>t.groupId===e.id)})).filter(e=>e.sections.length>0),settingsSections:i}}'
NAVIGATION_WITH_TOKEN_SAVERS = 'function VOn({isDesktop:e=!1,isMacDesktop:t=!1,isWindowsDesktop:n=!1}={}){let r=e||t||n,i=BOn.filter(e=>e.id===`computerUse`&&!r?!1:ES(e.id)),s=i.findIndex(e=>e.id===`memory`),a=i.find(e=>e.id===`usage`);if(s<0||!a)throw Error("Token savers navigation anchor is unavailable");i.splice(s+1,0,{id:`tokenSavers`,icon:a.icon,titleId:`settings.tokenSavers`,groupId:`agentCapabilities`});return{settingsSectionGroups:zOn.map(e=>({...e,sections:i.filter(t=>t.groupId===e.id)})).filter(e=>e.sections.length>0),settingsSections:i}}'
MEMORY_BRANCH = 'b===`memory`?(0,$.jsx)(Eg,{services:qe,children:(0,$.jsx)(WDn,{memoryEnabled:Ze,memoryService:qe.memoryService,onMemoryEnabledChange:$t,projectMemoryViewerAvailable:!!e,workspaceDisplayNames:Xe})}):b===`plugin`?'
TOKEN_SAVERS_BRANCH = 'b===`memory`?(0,$.jsx)(Eg,{services:qe,children:(0,$.jsx)(WDn,{memoryEnabled:Ze,memoryService:qe.memoryService,onMemoryEnabledChange:$t,projectMemoryViewerAvailable:!!e,workspaceDisplayNames:Xe})}):b===`tokenSavers`?(0,$.jsx)(CCodeTokenSaversPanel,{}):b===`plugin`?'


def patch_renderer(text):
    text = replace_once(text, 'const __vite__mapDeps=',
                        PIGGY_BANK_IMPORT + 'const __vite__mapDeps=')
    text = replace_once(text, ROUTE, ROUTE_WITH_TOKEN_SAVERS)
    text = replace_once(text, NAVIGATION, NAVIGATION_WITH_TOKEN_SAVERS)
    text = replace_once(text, 'icon:a.icon,titleId:`settings.tokenSavers`',
                        'icon:CCodePiggyBank,titleId:`settings.tokenSavers`')
    return replace_once(text, MEMORY_BRANCH, TOKEN_SAVERS_BRANCH)


def patch_intl(text):
    text = replace_once(text, '"settings.memory":`记忆`,"settings.memory.workspaceMemory":',
                        '"settings.memory":`记忆`,"settings.tokenSavers":`Token 节省`,"settings.memory.workspaceMemory":')
    return replace_once(text, '"settings.memory":`Memory`,"settings.memory.workspaceMemory":',
                        '"settings.memory":`Memory`,"settings.tokenSavers":`Token savers`,"settings.memory.workspaceMemory":')


def patch_preload(text):
    return replace_once(text,
                        'save:(settings)=>ipcRenderer.invoke("ccode-token-savers:save",settings)',
                        'save:(settings)=>ipcRenderer.invoke("ccode-token-savers:save",settings),'
                        'installRtk:()=>ipcRenderer.invoke("ccode-token-savers:install-rtk")')


def patch_archive(archive, replacements, renderer_asset, intl_asset, preload_asset):
    renderer = replacements.get(renderer_asset, archive.read(renderer_asset)).decode()
    replacements[renderer_asset] = patch_renderer(renderer).encode()
    intl = replacements.get(intl_asset, archive.read(intl_asset)).decode()
    replacements[intl_asset] = patch_intl(intl).encode()
    preload = replacements.get(preload_asset, archive.read(preload_asset)).decode()
    replacements[preload_asset] = patch_preload(preload).encode()


def patch_agent(text):
    text = replace_once(text, storage.AGENT_BOOTSTRAP,
                        storage.AGENT_BOOTSTRAP +
                        'const ccodeTokenSavers=require("../token-savers/token-savers-runtime.cjs");\n')
    text = replace_once(text, 'userInstructions:l,projectContext:u,diagnostics:o',
                        'userInstructions:ccodeTokenSavers.applyPromptModes(l),projectContext:u,diagnostics:o')
    return replace_once(text, 'needsApproval:o.needsApproval',
                        'needsApproval:o.name==="Bash"?((input,context)=>ccodeTokenSavers.needsShellApproval(input,context,o.needsApproval)):o.needsApproval')
