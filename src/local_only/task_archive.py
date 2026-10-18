"""Per-task archive for tasks that run outside a project.

No folder is created when the app opens or a draft starts: the task keeps using
the upstream conversation workspace, exactly like the stock build. The moment a
task actually produced changed files, the renderer hands their paths to
``task-archive.cjs`` (main process), which copies them into a hidden
``~/CCodeProject/task-<date>-<time>-<id>`` folder keyed by session id. The
workspace and the UI stay untouched, so the sidebar keeps its single "Tasks"
section and no folder name is shown; the folder is still there when the user
looks for it (Reveal in File Manager / Copy path on the change rows).

The copy happens in main so a large or failed copy can never block the change
summary: the renderer call is fire-and-forget.
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

MARKER = 'window.ccodeTaskArchive?.archive'


def patch_renderer(text):
    """Forward produced file paths to the main-process archive."""
    text = replace_once(text, FILE_CHANGES_ANCHOR, FILE_CHANGES_PATCHED)
    if MARKER not in text:
        raise ValueError('Task archive hook is missing from the renderer bundle')
    return text
