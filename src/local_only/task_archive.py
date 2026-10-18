"""Per-task archive for tasks that run outside a project.

No folder is created when the app opens or a draft starts: the task keeps using
the upstream conversation workspace, exactly like the stock build, so the
sidebar stays a single "Tasks" section and the UI never shows a folder name.
The moment a task (or the user) hands over a file, the renderer forwards it to
``task-archive.cjs`` (main process), which copies it into
``~/CCodeProject/task-<date>-<time>-<id>`` keyed by session id, so a later task
that regenerates the same name never overwrites the earlier result.

Three renderer hooks keep the archive reachable without exposing the hidden
workspace:

* ``fileChanges`` — produced/changed files of a turn (fire-and-forget).
* ``attachmentPut`` — a file the user attached in the composer, stored next to
  the produced files.
* the workspace header's task menu — "Open in File Manager" opens the task
  folder when it exists, and the change-summary row actions resolve to the
  archived copy first (``workspace_ux.py`` owns that menu).
"""

from . import replace_once

FILE_CHANGES_ANCHOR = (
    'async fileChanges(t){return await a(),e.conversationFileChangesV4({...n,sessionId:t.sessionId,'
    'target:t.target,baseRevision:t.baseRevision,baseLogEpoch:t.baseLogEpoch})}'
)
FILE_CHANGES_PATCHED = (
    'async fileChanges(t){await a();'
    'let __cc=await e.conversationFileChangesV4({...n,sessionId:t.sessionId,target:t.target,'
    'baseRevision:t.baseRevision,baseLogEpoch:t.baseLogEpoch});'
    'try{if(__cc&&__cc.state!==`reverted`&&Array.isArray(__cc.items)&&typeof window<`u`&&window.ccodeTaskArchive?.archive){'
    'window.ccodeTaskArchive.archive({workspacePath:n?.workspacePath,sessionId:t.sessionId,'
    'paths:__cc.items.map(x=>x.path).filter(Boolean)}).catch(()=>{})}}catch{}return __cc}'
)

ATTACHMENT_ANCHOR = 'async attachmentPut(t,r){return await a(),zRe(e,n,t,r)},'
# 94371840 base64 chars decode to ~67 MiB; the main process enforces the real
# 64 MiB cap, this only keeps a pathological payload out of the IPC channel.
ATTACHMENT_MAX_BASE64 = 94371840
ATTACHMENT_PATCHED = (
    'async attachmentPut(t,r){await a();'
    'let __cu=await zRe(e,n,t,r);'
    f'try{{const __cb=t?.dataBase64,__cf=t?.fileName,__cs=t?.sessionId;'
    f'if(typeof __cb==`string`&&__cb.length<={ATTACHMENT_MAX_BASE64}&&typeof __cf==`string`&&__cf&&__cs'
    '&&typeof window<`u`&&window.ccodeTaskArchive?.upload){'
    'window.ccodeTaskArchive.upload({workspacePath:n?.workspacePath,sessionId:__cs,'
    'fileName:__cf,dataBase64:__cb}).catch(()=>{})}}catch{}return __cu},'
)

# The workspace header menu; `f` is the active session id, `u` the active task
# id and `n` the workspace path in that scope.
MENU_ANCHOR = (
    'onOpenTaskPathInFileManager:()=>{Ee()},'
    'onCopyWorkspacePath:()=>{Te(F.formatMessage({id:`appHeader.copyPath`}),n)},'
)
MENU_PATCHED = (
    'onOpenTaskPathInFileManager:()=>{__ccodeTaskFolder(f,u,n,Ee)},'
    'onCopyWorkspacePath:()=>{__ccodeTaskCopyPath(f,u,n,Te,F.formatMessage({id:`appHeader.copyPath`}))},'
)

CRT_PREFIX = 'function CRt({header:e,context:t}){let{intl:n}=q(),'
HELPERS = (
    'async function __ccodeTaskFolder(e,t,n,r){'
    'try{let o=await window.ccodeTaskArchive?.folder?.({sessionId:e,taskId:t,workspacePath:n});'
    'if(o&&o.ok&&o.folder){let s=await window.ccodeTaskArchive.open?.({path:o.folder});if(s&&s.ok)return}}catch{}'
    'return r()}\n'
    'async function __ccodeTaskCopyPath(e,t,n,r,o){'
    'try{let s=await window.ccodeTaskArchive?.folder?.({sessionId:e,taskId:t,workspacePath:n});'
    'if(s&&s.ok&&s.folder)return r(o,s.folder)}catch{}return r(o,n)}\n'
)

MARKERS = ('window.ccodeTaskArchive?.archive', 'window.ccodeTaskArchive?.upload',
           '__ccodeTaskFolder(', '__ccodeTaskCopyPath(')


def patch_renderer(text):
    """Hook produced files, composer attachments, and the task menu."""
    text = replace_once(text, FILE_CHANGES_ANCHOR, FILE_CHANGES_PATCHED)
    text = replace_once(text, ATTACHMENT_ANCHOR, ATTACHMENT_PATCHED)
    text = replace_once(text, CRT_PREFIX, HELPERS + CRT_PREFIX)
    text = replace_once(text, MENU_ANCHOR, MENU_PATCHED)
    for marker in MARKERS:
        if marker not in text:
            raise ValueError('Task archive hook is missing from the renderer bundle: ' + marker)
    return text
