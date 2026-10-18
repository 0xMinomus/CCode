"""Workspace UX patch: file actions on the change-summary rows.

The change-summary rows of a turn reuse the upstream Radix ContextMenu
primitives (`JA`/`YA`/`XA`/`ZA`/`QA`) and the existing file-action hook (`Nj`)
so a generated file can be found without leaving CCode: Reveal in File Manager,
Copy path, Copy relative path.

Folder creation is *not* done here: a task started outside a project keeps the
upstream conversation workspace until it actually produces a file, and the
per-task archive is owned by `task-archive.cjs` (see `task_archive.py`). Every
replacement goes through ``replace_once``: a missing or duplicated anchor fails
``make build`` instead of silently skipping the patch.
"""

from . import replace_once

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

MARKERS = ('__ccodeRail',)


def patch_renderer(text):
    """Add the change-summary context menu to the renderer bundle."""
    text = replace_once(text, CHANGE_HOOK_ANCHOR, CHANGE_HOOK_PATCHED)
    text = replace_once(text, CHANGE_OPEN_ANCHOR, CHANGE_OPEN_PATCHED)
    text = replace_once(text, CHANGE_CLOSE_ANCHOR, CHANGE_CLOSE_PATCHED)
    for marker in MARKERS:
        if marker not in text:
            raise ValueError('Workspace UX patch marker is missing: ' + marker)
    return text
