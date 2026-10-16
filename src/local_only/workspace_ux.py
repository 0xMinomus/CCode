"""Workspace UX patches: per-task folders and file context actions.

Two user-facing behaviours, both anchored on the pinned upstream renderer:

1. A new task that would start in the shared conversation workspace
   (`<data>/.ccode/workspace/default`) instead gets a fresh folder
   (`~/CCodeProject/task-<stamp>-<rand>`) created through the upstream
   scratch-workspace RPC. Restored conversations keep their stored paths, so
   nothing moves; only new drafts are redirected.
2. The change-summary rows of a turn get a context menu with
   Reveal in File Manager / Copy path / Copy relative path, reusing the
   upstream Radix ContextMenu primitives (`JA`/`YA`/`XA`/`ZA`/`QA`) and the
   file-action hook (`Nj`).

Every replacement goes through ``replace_once``: a missing or duplicated
anchor fails ``make build`` instead of silently skipping the patch.
"""

from . import replace_once

HELPER_ANCHOR = 'function Dyn({services:e,baseFeedbackService:t,'
DYN_BODY_ANCHOR = '){let L=yv(`toggleSidebar`),R=yv(`newTask`)'
CONV_TASK_ANCHOR = (
    'handleCreateConversationTask:(0,Q.useCallback)(async()=>{try{let e=await i();r(e),'
    'B$.getState().deactivateActiveGroup(),_$.getState().resetToPrimaryPane(),lo.getState().startDraft(e)}catch{}},[i,r])'
)
SIDEBAR_ANCHOR = (
    '$n=(0,Q.useCallback)((e,t,n,r)=>{let i=lo.getState(),a=t??Kt.filter(S_).find(t=>t.workspacePath===e)?.workspaceIdentity;'
    'if(C_({tabs:Kt},e,a))return;'
)
ROOT_THUNK_ANCHOR = 'let[y,b]=(0,Q.useState)(null),x=Q$(),'
ROOT_TASK_ANCHOR = 'D=(0,Q.useCallback)((t,n)=>{let a=r.getState(),'
ROOT_GUARD_ANCHOR = 'if(C_(a,d.workspacePath,d.workspaceIdentity??void 0))return;'
ROOT_DRAFT_ANCHOR = (
    'let E=(0,Q.useCallback)((e,t)=>{v===`desktop-continuous`&&(B$.getState().deactivateActiveGroup(),'
    '_$.getState().resetToPrimaryPane()),lo.getState().startDraft(e,void 0,t)},[v])'
)
CHANGE_HOOK_ANCHOR = 'function CRt({header:e,context:t}){let{intl:n}=q(),r=e.fileChanges,'
CHANGE_OPEN_ANCHOR = (
    'return(0,$.jsx)(`div`,{className:`w-full bg-background/50 overflow-hidden`,children:(0,$.jsxs)(`div`,{"aria-disabled":!i,'
)
CHANGE_CLOSE_ANCHOR = (
    '(0,$.jsx)(dZ,{target:{type:`file`,path:e.path,title:r,label:r,previewSource:a},'
    'onOpenCodeViewer:t.onOpenCodeViewer,hideOpenWithMenu:t.compactForRemoteControl===!0,stopPropagation:!0})]})]})},e.path)'
)

# The fresh-folder helper. It receives a thunk so a shadowed or unavailable
# services binding degrades to a caught warning and the caller falls back to the
# conversation workspace instead of breaking task creation. A short reuse window
# collapses re-entrant calls (bootstrap effects, teardown events, rapid clicks)
# into one folder instead of one per call.
NEW_TASK_FOLDER = '''let __ccodeTaskFolder=null,__ccodeTaskFolderAt=0;
async function __ccodeNewTaskFolder(fsThunk){try{let now=Date.now();if(__ccodeTaskFolder&&now-__ccodeTaskFolderAt<5000)return __ccodeTaskFolder;let d=new Date(),p=n=>String(n).padStart(2,`0`),fs=fsThunk();if(!fs||typeof fs.createScratchWorkspace!==`function`)return null;let name=`task-`+d.getFullYear()+p(d.getMonth()+1)+p(d.getDate())+`-`+p(d.getHours())+p(d.getMinutes())+p(d.getSeconds())+`-`+Math.random().toString(36).slice(2,6);let res=await fs.createScratchWorkspace({name:name});if(res&&res.path){__ccodeTaskFolder=res.path;__ccodeTaskFolderAt=Date.now();return res.path}}catch(err){try{console.warn(`[CCode] fresh task folder unavailable; using the conversation workspace`,err)}catch{}}return null}
'''

CONV_TASK_PATCHED = (
    'handleCreateConversationTask:(0,Q.useCallback)(async()=>{try{let __cc=await __ccodeNewTaskFolder(()=>e.fileService),'
    '__ws=__cc??await i();r(__ws),B$.getState().deactivateActiveGroup(),_$.getState().resetToPrimaryPane(),'
    'lo.getState().startDraft(__ws)}catch{}},[i,r])'
)
# Only a new draft for the conversation workspace forks a folder: a request
# keyed by path+identity that is not `conversation` keeps the upstream path.
SIDEBAR_PATCHED = (
    '$n=(0,Q.useCallback)(async(e,t,n,r)=>{let i=lo.getState(),'
    'a=t??Kt.filter(S_).find(t=>t.workspacePath===e)?.workspaceIdentity;'
    'if(n===`conversation`){let __cc=await __ccodeNewTaskFolder(__ccodeDynFs);if(__cc){e=__cc;a=void 0;n=void 0;t=void 0}}'
    'if(C_({tabs:Kt},e,a))return;'
)
ROOT_GUARD_PATCHED = (
    'if(C_(a,d.workspacePath,d.workspaceIdentity??void 0))return;'
    'try{let __tab=(a.tabs??[]).find(t=>(t.workspacePath??``)===d.workspacePath&&(t.workspaceIdentity??``)===(d.workspaceIdentity??``));'
    'if(__tab&&__tab.workspacePurpose===`conversation`){let __cc=await __ccodeNewTaskFolder(__ccodeRootFs);'
    'if(__cc)d={workspacePath:__cc,workspaceIdentity:void 0}}}catch{}'
)
# `startDraftInWorkspace` is also the bootstrap/focus path, so it only forks a
# folder when the conversation workspace has no draft yet, and it activates the
# new folder (the other call sites select it themselves).
ROOT_DRAFT_PATCHED = (
    'let E=(0,Q.useCallback)(async(e,t)=>{if(v===`desktop-continuous`){B$.getState().deactivateActiveGroup(),'
    '_$.getState().resetToPrimaryPane()}'
    'try{let __st=r.getState(),__tab=(__st.tabs??[]).find(x=>(x.workspacePath??``)===e);'
    'if(__tab&&__tab.workspacePurpose===`conversation`&&!(lo.getState().getWorkspaceState(e,void 0)?.draftSessionId)){'
    'let __cc=await __ccodeNewTaskFolder(__ccodeRootFs);'
    'if(__cc){try{i(__cc)}catch{}e=__cc}}}catch{}'
    'lo.getState().startDraft(e,void 0,t)},[v])'
)
CHANGE_HOOK_PATCHED = (
    'function CRt({header:e,context:t}){let{intl:n}=q(),'
    '__ccodeRail=Nj({canOpenLocalFileManager:!0,'
    'isRemoteWorkspace:!!(t.workspaceRemoteSessionId||t.workspaceIdentity?.trim()),'
    'remoteTarget:void 0,workspaceIdentity:t.workspaceIdentity}),r=e.fileChanges,'
)
CHANGE_MENU = (
    '(0,$.jsxs)(XA,{className:`w-56`,children:['
    '(0,$.jsxs)(ZA,{disabled:!__ccodeRail.canRevealInFileManager({path:e.path,kind:`file`}),'
    'onSelect:()=>{void __ccodeRail.revealInFileManager({path:e.path,kind:`file`})},'
    'children:[(0,$.jsx)(sc,{className:`size-4`}),n.formatMessage({id:`git.changeContext.revealInFileManager`})]}),'
    '(0,$.jsx)(QA,{}),'
    '(0,$.jsxs)(ZA,{onSelect:()=>{void __ccodeRail.copyAbsolutePath({path:e.path})},'
    'children:[(0,$.jsx)(Qs,{className:`size-4`}),n.formatMessage({id:`fileActions.copyAbsolutePath`})]}),'
    '(0,$.jsxs)(ZA,{onSelect:()=>{void __ccodeRail.copyRelativePath({path:e.path,relativePath:r})},'
    'children:[(0,$.jsx)(Qs,{className:`size-4`}),n.formatMessage({id:`fileActions.copyRelativePath`})]})]})'
)
CHANGE_OPEN_PATCHED = (
    'return(0,$.jsxs)(JA,{children:[(0,$.jsx)(YA,{asChild:!0,children:'
    '(0,$.jsx)(`div`,{className:`w-full bg-background/50 overflow-hidden`,children:(0,$.jsxs)(`div`,{"aria-disabled":!i,'
)
CHANGE_CLOSE_PATCHED = CHANGE_CLOSE_ANCHOR[:-len('},e.path)')] + '},e.path)})' + ',' + CHANGE_MENU + ']},e.path)'

MARKERS = ('__ccodeNewTaskFolder', '__ccodeDynFs', '__ccodeRootFs', '__ccodeRail')


def patch_renderer(text):
    """Apply both workspace-UX behaviours to the renderer bundle."""
    text = replace_once(text, HELPER_ANCHOR, NEW_TASK_FOLDER + HELPER_ANCHOR)
    text = replace_once(text, DYN_BODY_ANCHOR, '){let __ccodeDynFs=()=>e.fileService;let L=yv(`toggleSidebar`),R=yv(`newTask`)')
    text = replace_once(text, CONV_TASK_ANCHOR, CONV_TASK_PATCHED)
    text = replace_once(text, SIDEBAR_ANCHOR, SIDEBAR_PATCHED)
    text = replace_once(text, ROOT_THUNK_ANCHOR, 'let[y,b]=(0,Q.useState)(null),__ccodeRootFs=()=>n.fileService,x=Q$(),')
    text = replace_once(text, ROOT_TASK_ANCHOR, 'D=(0,Q.useCallback)(async(t,n)=>{let a=r.getState(),')
    text = replace_once(text, ROOT_GUARD_ANCHOR, ROOT_GUARD_PATCHED)
    text = replace_once(text, ROOT_DRAFT_ANCHOR, ROOT_DRAFT_PATCHED)
    text = replace_once(text, CHANGE_HOOK_ANCHOR, CHANGE_HOOK_PATCHED)
    text = replace_once(text, CHANGE_OPEN_ANCHOR, CHANGE_OPEN_PATCHED)
    text = replace_once(text, CHANGE_CLOSE_ANCHOR, CHANGE_CLOSE_PATCHED)
    for marker in MARKERS:
        if marker not in text:
            raise ValueError('Workspace UX patch marker is missing: ' + marker)
    return text
