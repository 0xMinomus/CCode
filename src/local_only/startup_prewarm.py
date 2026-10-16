"""Preload the pinned workspace window at login, retaining its native single-instance path."""
from pathlib import Path
from . import replace_once

RESOURCE = 'startup-prewarm/main.cjs'
MAIN = 'out/main/index.js'
PRELOAD = 'out/preload/index.cjs'
SINGLE_INSTANCE = 'var AV=Z.requestSingleInstanceLock(gb(process.argv));AV||Z.quit();'
SECOND_INSTANCE = 'Z.on("second-instance",(e,t,r,o)=>{if(OC('
WINDOW_OPTIONS = 'autoHideMenuBar:kN(),...PN(),webPreferences:{preload:e.preloadPath,'
MAXIMIZE = 'Wr(n,t),o.maximized&&n.maximize(),n.on("enter-full-screen",'
DOM_READY = 'process.platform==="win32"&&!t.isDestroyed()&&(t.show(),t.focus());'
READY = 'Z.whenReady().then(async()=>{cy(),'
COORDINATOR = 'async function n(i){if(e.canCreateWindow&&!e.canCreateWindow(i))'
SECOND_FOCUS = 'let n=Re()[0];n&&(n.isMinimized()&&n.restore(),n.isVisible()||n.show(),n.focus())});Z.whenReady()'
GENERAL_ROW = 'b?(0,$.jsx)(Z1,{label:me.formatMessage({id:`settings.keepAwakeWhileRunning`})'


def patch_main(text):
    text = replace_once(text, SINGLE_INSTANCE,
                        'import {createRequire as ccodePrewarmRequire} from "node:module";'
                        'import {ipcMain as ccodePrewarmIpc} from "electron";'
                        'const ccodeStartup=ccodePrewarmRequire(import.meta.url)(process.resourcesPath+"/' + RESOURCE + '").create({app:Z});'
                        + SINGLE_INSTANCE + 'AV&&ccodeStartup.register(ccodePrewarmIpc,{deferredReconcile:!0});')
    text = replace_once(text, WINDOW_OPTIONS,
                        'autoHideMenuBar:kN(),...PN(),show:!ccodeStartup.hidden,skipTaskbar:ccodeStartup.hidden,'
                        'webPreferences:{backgroundThrottling:!ccodeStartup.hidden,preload:e.preloadPath,')
    text = replace_once(text, MAXIMIZE,
                        'Wr(n,t),ccodeStartup.track(n,o.maximized),o.maximized&&!ccodeStartup.hidden&&n.maximize(),n.on("enter-full-screen",')
    text = replace_once(text, DOM_READY,
                        'process.platform==="win32"&&!ccodeStartup.hidden&&!t.isDestroyed()&&(t.show(),t.focus());')
    text = replace_once(text, SECOND_INSTANCE,
                        'Z.on("second-instance",(e,t,r,o)=>{if(t.includes("--hidden"))return;ccodeStartup.reveal();if(OC(')
    text = replace_once(text, SECOND_FOCUS,
                        'if(Z.isReady()&&Re().length)Zo.ensurePrimaryWindow("second-instance")});Z.whenReady()')
    text = replace_once(text, COORDINATOR,
                        'async function n(i){if(i!=="app-ready")ccodeStartup.reveal();if(e.canCreateWindow&&!e.canCreateWindow(i))')
    text = replace_once(text, 'Z.on("open-url",(e,t)=>{e.preventDefault();',
                        'Z.on("open-url",(e,t)=>{e.preventDefault();ccodeStartup.reveal();')
    text = replace_once(text, 'i&&Zk(i.webContents,w),cC({locale:se,logger:w,parentWindow:Re()[0]??',
                        'i&&Zk(i.webContents,w),!ccodeStartup.hidden&&cC({locale:se,logger:w,parentWindow:Re()[0]??')
    return replace_once(text, READY,
                        'Z.whenReady().then(async()=>{if(!AV)return;if(!ccodeStartup.shouldStart()){Z.quit();return}cy(),')


def patch_renderer(text):
    text = replace_once(text, GENERAL_ROW,
                        'b?(0,$.jsx)(CCodeStartupPrewarm,{}):null,' + GENERAL_ROW)
    return text + '\n' + (Path(__file__).resolve().parents[1] / 'renderer/startup-prewarm.js').read_text() + '\n'


def patch_archive(archive, replacements, renderer_asset):
    for name, patch in ((MAIN, patch_main), (renderer_asset, patch_renderer)):
        source = replacements[name] if name in replacements else archive.read(name)
        replacements[name] = patch(source.decode()).encode()
    source = replacements[PRELOAD] if PRELOAD in replacements else archive.read(PRELOAD)
    replacements[PRELOAD] = (source.decode() + '''
(()=>{const {contextBridge,ipcRenderer}=require("electron");contextBridge.exposeInMainWorld("ccodeStartupPrewarm",{get:()=>ipcRenderer.invoke("ccode-startup-prewarm:get"),set:enabled=>ipcRenderer.invoke("ccode-startup-prewarm:set",enabled)});})();
''').encode()
