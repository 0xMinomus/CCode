"""Workspace UX patch: file actions on the change-summary rows.

The change-summary rows of a turn reuse the upstream Radix ContextMenu
primitives (`JA`/`YA`/`XA`/`ZA`/`QA`) and the existing file-action hook (`Nj`)
so a generated file can be found without leaving CCode: Reveal in File Manager,
Copy path, Copy relative path. Every action resolves through `task-archive.cjs`
first, so it points at the per-task copy when the file was archived and at the
live workspace file otherwise — the hidden conversation workspace is never what
the user is sent to.

Folder creation is *not* done here: a task started outside a project keeps the
upstream conversation workspace until it actually hands over a file, and the
per-task archive is owned by `task-archive.cjs` (see `task_archive.py`). Every
replacement goes through ``replace_once``: a missing or duplicated anchor fails
``make build`` instead of silently skipping the patch.
"""

from . import replace_once

CRT_PREFIX = 'function CRt({header:e,context:t}){let{intl:n}=q(),'
CHANGE_HOOK_ANCHOR = 'function CRt({header:e,context:t}){let{intl:n}=q(),r=e.fileChanges,'
CHANGE_OPEN_ANCHOR = (
    'return(0,$.jsx)(`div`,{className:`w-full bg-background/50 overflow-hidden`,children:(0,$.jsxs)(`div`,{"aria-disabled":!i,'
)
CHANGE_CLOSE_ANCHOR = (
    '(0,$.jsx)(dZ,{target:{type:`file`,path:e.path,title:r,label:r,previewSource:a},'
    'onOpenCodeViewer:t.onOpenCodeViewer,hideOpenWithMenu:t.compactForRemoteControl===!0,stopPropagation:!0})]})]})},e.path)'
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
    'onSelect:()=>{void __ccodeTaskRowReveal(t.workspacePath,e.path,__ccodeRail)},'
    'children:[(0,$.jsx)(sc,{className:`size-4`}),n.formatMessage({id:`git.changeContext.revealInFileManager`})]}),'
    '(0,$.jsx)(QA,{}),'
    '(0,$.jsxs)(ZA,{onSelect:()=>{void __ccodeTaskRowCopyPath(t.workspacePath,e.path,__ccodeRail)},'
    'children:[(0,$.jsx)(Qs,{className:`size-4`}),n.formatMessage({id:`fileActions.copyAbsolutePath`})]}),'
    '(0,$.jsxs)(ZA,{onSelect:()=>{void __ccodeRail.copyRelativePath({path:e.path})},'
    'children:[(0,$.jsx)(Qs,{className:`size-4`}),n.formatMessage({id:`fileActions.copyRelativePath`})]})]})'
)
CHANGE_OPEN_PATCHED = (
    'return(0,$.jsxs)(JA,{children:[(0,$.jsx)(YA,{asChild:!0,children:'
    '(0,$.jsx)(`div`,{className:`w-full bg-background/50 overflow-hidden`,children:(0,$.jsxs)(`div`,{"aria-disabled":!i,'
)
CHANGE_CLOSE_PATCHED = CHANGE_CLOSE_ANCHOR[:-len('},e.path)')] + '},e.path)})' + ',' + CHANGE_MENU + ']},e.path)'

# The rows know the workspace and the relative path, not the session id, so the
# main process resolves: archived copy first, live workspace file otherwise.
ROW_HELPERS = (
    'async function __ccodeTaskRowTarget(t,n){'
    'try{let e=await window.ccodeTaskArchive?.resolve?.({workspacePath:t,relPath:n});'
    'if(e&&e.ok&&e.path)return e.path}catch{}return n}\n'
    'async function __ccodeTaskRowReveal(t,n,e){let r=await __ccodeTaskRowTarget(t,n);'
    'await e.revealInFileManager({path:r,kind:`file`})}\n'
    'async function __ccodeTaskRowCopyPath(t,n,e){let r=await __ccodeTaskRowTarget(t,n);'
    'await e.copyAbsolutePath({path:r})}\n'
)

MARKERS = ('__ccodeRail', '__ccodeTaskRowReveal(')


def patch_renderer(text):
    """Add the change-summary context menu to the renderer bundle."""
    text = replace_once(text, CRT_PREFIX, ROW_HELPERS + CRT_PREFIX)
    text = replace_once(text, CHANGE_HOOK_ANCHOR, CHANGE_HOOK_PATCHED)
    text = replace_once(text, CHANGE_OPEN_ANCHOR, CHANGE_OPEN_PATCHED)
    text = replace_once(text, CHANGE_CLOSE_ANCHOR, CHANGE_CLOSE_PATCHED)
    for marker in MARKERS:
        if marker not in text:
            raise ValueError('Workspace UX patch marker is missing: ' + marker)
    return text
