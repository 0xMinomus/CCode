import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from local_only import workspace_ux

SOURCE = '\n'.join((
    workspace_ux.CHANGE_HOOK_ANCHOR,
    workspace_ux.CHANGE_OPEN_ANCHOR,
    workspace_ux.CHANGE_CLOSE_ANCHOR + ',e.path)',
))


class ChangeMenuTests(unittest.TestCase):
    def test_every_anchor_is_replaced_and_markers_stay(self):
        patched = workspace_ux.patch_renderer(SOURCE)
        self.assertNotIn(workspace_ux.CHANGE_HOOK_ANCHOR, patched)
        self.assertNotIn(workspace_ux.CHANGE_OPEN_ANCHOR, patched)
        # The close anchor keeps its body; the wrapper closes right after it.
        self.assertIn(workspace_ux.CHANGE_CLOSE_ANCHOR[:-len('},e.path)')] + '},e.path)})', patched)
        self.assertIn('__ccodeRail', patched)

    def test_missing_anchor_fails_loudly(self):
        with self.assertRaises(ValueError):
            workspace_ux.patch_renderer(SOURCE.replace(workspace_ux.CHANGE_OPEN_ANCHOR, ''))

    def test_context_menu_wraps_the_row_and_keeps_the_key(self):
        patched = workspace_ux.patch_renderer(SOURCE)
        self.assertIn('(0,$.jsxs)(JA,{children:[(0,$.jsx)(YA,{asChild:!0,children:', patched)
        self.assertIn('revealInFileManager', patched)
        self.assertIn('copyAbsolutePath', patched)
        self.assertIn('copyRelativePath', patched)
        self.assertIn(']},e.path)', patched)

    def test_menu_uses_the_file_action_hook_and_existing_labels(self):
        for fragment in ('git.changeContext.revealInFileManager',
                         'fileActions.copyAbsolutePath',
                         'fileActions.copyRelativePath',
                         '__ccodeRail.canRevealInFileManager',
                         'workspaceRemoteSessionId'):
            self.assertIn(fragment, workspace_ux.CHANGE_MENU + workspace_ux.CHANGE_HOOK_PATCHED)

    def test_row_actions_resolve_the_archived_copy_first(self):
        patched = workspace_ux.patch_renderer(SOURCE)
        self.assertIn('__ccodeTaskRowReveal', patched)
        for fragment in ('window.ccodeTaskArchive?.resolve?.({workspacePath:t,relPath:n})',
                         'await e.revealInFileManager({path:r,kind:`file`})',
                         'await e.copyAbsolutePath({path:r})',
                         '__ccodeTaskRowReveal(t.workspacePath,e.path,__ccodeRail)',
                         '__ccodeTaskRowCopyPath(t.workspacePath,e.path,__ccodeRail)',
                         'copyRelativePath({path:e.path})'):
            self.assertIn(fragment, patched)
        # The old relative-path mix-up is gone: Copy relative path no longer
        # receives the absolute path the row already computed.
        self.assertNotIn('copyRelativePath({path:e.path,relativePath:r})', patched)


if __name__ == '__main__':
    unittest.main()
