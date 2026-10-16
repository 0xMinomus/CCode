import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from local_only import workspace_ux

# Every anchor is embedded verbatim; `patch_renderer` uses `replace_once`, so a
# drift in any of them fails the suite the same way it would fail the build.
SOURCE = '\n'.join((
    workspace_ux.HELPER_ANCHOR + '{return null}',
    workspace_ux.DYN_BODY_ANCHOR,
    workspace_ux.CONV_TASK_ANCHOR,
    workspace_ux.SIDEBAR_ANCHOR + 'return null;',
    workspace_ux.ROOT_THUNK_ANCHOR,
    workspace_ux.ROOT_TASK_ANCHOR,
    workspace_ux.ROOT_GUARD_ANCHOR,
    workspace_ux.ROOT_DRAFT_ANCHOR,
    workspace_ux.CHANGE_HOOK_ANCHOR,
    workspace_ux.CHANGE_OPEN_ANCHOR,
    workspace_ux.CHANGE_CLOSE_ANCHOR,
))


class TaskFolderTests(unittest.TestCase):
    def test_every_anchor_is_replaced_and_markers_stay(self):
        patched = workspace_ux.patch_renderer(SOURCE)
        # Prefix anchors (helper, close) keep their leading text and are checked
        # separately below; every other anchor must disappear entirely.
        for anchor in (workspace_ux.DYN_BODY_ANCHOR,
                       workspace_ux.CONV_TASK_ANCHOR, workspace_ux.SIDEBAR_ANCHOR,
                       workspace_ux.ROOT_THUNK_ANCHOR, workspace_ux.ROOT_TASK_ANCHOR,
                       workspace_ux.ROOT_DRAFT_ANCHOR, workspace_ux.CHANGE_HOOK_ANCHOR,
                       workspace_ux.CHANGE_OPEN_ANCHOR):
            self.assertNotIn(anchor, patched)
        # The helper is inserted *before* the preserved `function Dyn(` prefix.
        self.assertEqual(patched.count(workspace_ux.HELPER_ANCHOR), 1)
        self.assertLess(patched.index('async function __ccodeNewTaskFolder'),
                        patched.index(workspace_ux.HELPER_ANCHOR))
        # The close anchor keeps its body; the wrapper closes right after it.
        self.assertEqual(patched.count(workspace_ux.CHANGE_CLOSE_ANCHOR), 1)
        self.assertIn(workspace_ux.CHANGE_CLOSE_ANCHOR[:-len('},e.path)')] + '},e.path)})', patched)
        for marker in workspace_ux.MARKERS:
            self.assertIn(marker, patched)
        self.assertIn('__ccodeNewTaskFolder(()=>e.fileService)', patched)
        self.assertIn('__ccodeNewTaskFolder(__ccodeDynFs)', patched)
        self.assertIn('__ccodeNewTaskFolder(__ccodeRootFs)', patched)
        self.assertIn('createScratchWorkspace({name:name})', patched)

    def test_missing_anchor_fails_loudly(self):
        with self.assertRaises(ValueError):
            workspace_ux.patch_renderer(SOURCE.replace(workspace_ux.ROOT_GUARD_ANCHOR, ''))

    def test_fresh_task_folder_helper_is_valid_javascript(self):
        script = workspace_ux.NEW_TASK_FOLDER + '__ccodeNewTaskFolder(()=>null).then(()=>{});\n'
        with tempfile.TemporaryDirectory() as temporary:
            path = pathlib.Path(temporary) / 'helper.js'
            path.write_text(script)
            subprocess.run(['node', '--check', str(path)], check=True, cwd=ROOT)


class ChangeMenuTests(unittest.TestCase):
    def test_context_menu_wraps_the_row_and_keeps_the_key(self):
        patched = workspace_ux.patch_renderer(SOURCE)
        row = patched[patched.index(workspace_ux.CHANGE_OPEN_PATCHED):]
        self.assertIn('(0,$.jsxs)(JA,{children:[(0,$.jsx)(YA,{asChild:!0,children:', row)
        self.assertIn('revealInFileManager', row)
        self.assertIn('copyAbsolutePath', row)
        self.assertIn('copyRelativePath', row)
        self.assertIn(']},e.path)', row)

    def test_menu_uses_the_file_action_hook_and_existing_labels(self):
        for fragment in ('git.changeContext.revealInFileManager',
                         'fileActions.copyAbsolutePath',
                         'fileActions.copyRelativePath',
                         '__ccodeRail.canRevealInFileManager',
                         'workspaceRemoteSessionId'):
            self.assertIn(fragment, workspace_ux.CHANGE_MENU + workspace_ux.CHANGE_HOOK_PATCHED)


if __name__ == '__main__':
    unittest.main()
