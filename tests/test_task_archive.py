import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from local_only import task_archive

MODULE = ROOT / 'src/main/task-archive.cjs'


class RendererHookTests(unittest.TestCase):
    def test_file_changes_call_forwards_paths_to_the_archive(self):
        source = task_archive.FILE_CHANGES_ANCHOR + ';'
        patched = task_archive.patch_renderer(source)
        self.assertNotIn(task_archive.FILE_CHANGES_ANCHOR + ';', patched)
        for fragment in (task_archive.MARKER, 'workspacePath:n?.workspacePath',
                         'sessionId:t.sessionId', "state!==`reverted`"):
            self.assertIn(fragment, patched)

    def test_missing_anchor_fails_loudly(self):
        with self.assertRaises(ValueError):
            task_archive.patch_renderer('async fileChanges(t){return 1}')


class ArchiveModuleTests(unittest.TestCase):
    def run_node(self, base, root, session, file, other):
        script = (
            'const mod=require(process.argv[1]);'
            'const [root,base,session,file,other]=process.argv.slice(2);'
            'const r1=mod.archive({workspacePath:base,sessionId:session,paths:[file]},{root,base});'
            'const r2=mod.archive({workspacePath:base,sessionId:session,paths:[file]},{root,base});'
            'const r3=mod.archive({workspacePath:other,sessionId:`other`,paths:[file]},{root,base});'
            'const r4=mod.archive({workspacePath:base,sessionId:`outside`,paths:[process.argv[7]]},{root,base});'
            'const f=mod.folder({sessionId:session},{root,base});'
            'process.stdout.write(JSON.stringify({r1,r2,r3,r4,f}));'
        )
        result = subprocess.run(['node', '-e', script, str(MODULE), str(root), str(base), session,
                                 str(file), str(other), str(base.parent / 'outside.txt')],
                                check=True, capture_output=True, text=True)
        return json.loads(result.stdout)

    def test_archive_copies_inside_conversation_workspace_and_reuses_folder(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = pathlib.Path(temporary) / 'workspace'
            (workspace / 'outputs').mkdir(parents=True)
            base = workspace / 'default'
            (base / 'outputs').mkdir(parents=True)
            produced = base / 'outputs' / 'DESIGN.md'
            produced.write_text('design\n')
            root = pathlib.Path(temporary) / 'CCodeProject'
            other = workspace / 'project'
            other.mkdir()
            outside = pathlib.Path(temporary) / 'outside.txt'
            outside.write_text('secret\n')

            result = self.run_node(base, root, 'session-1', produced, other)

            self.assertTrue(result['r1']['ok'])
            self.assertEqual(result['r1']['copied'], ['outputs/DESIGN.md'])
            folder = pathlib.Path(result['r1']['folder'])
            self.assertTrue((folder / 'outputs' / 'DESIGN.md').is_file())
            self.assertEqual(folder.parent, root)
            self.assertTrue(folder.name.startswith('task-'))
            # Same session reuses its folder; project workspaces never archive.
            self.assertEqual(result['r2']['folder'], result['r1']['folder'])
            self.assertEqual(result['r3']['skipped'], 'not-conversation')
            # Files outside the conversation workspace are refused.
            self.assertFalse((folder / 'outside.txt').exists())
            self.assertEqual(result['f']['folder'], result['r1']['folder'])
            index = json.loads((root / '.task-folders.json').read_text())
            self.assertEqual(index['session-1'], result['r1']['folder'])


if __name__ == '__main__':
    unittest.main()
