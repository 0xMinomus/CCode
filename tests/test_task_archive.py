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


def run_node(script, *arguments):
    result = subprocess.run(['node', '-e', script, str(MODULE), *map(str, arguments)],
                            check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


class RendererHookTests(unittest.TestCase):
    def test_every_anchor_is_replaced_and_markers_stay(self):
        source = '\n'.join((
            task_archive.FILE_CHANGES_ANCHOR,
            task_archive.ATTACHMENT_ANCHOR,
            task_archive.CRT_PREFIX + 'r=e.fileChanges,',
            task_archive.MENU_ANCHOR,
        ))
        patched = task_archive.patch_renderer(source)
        for anchor in (task_archive.FILE_CHANGES_ANCHOR, task_archive.ATTACHMENT_ANCHOR,
                       task_archive.MENU_ANCHOR):
            self.assertNotIn(anchor, patched)
        for marker in task_archive.MARKERS:
            self.assertIn(marker, patched)
        # Produced files, composer attachments, and the task menu all forward.
        for fragment in ('window.ccodeTaskArchive.archive({workspacePath:n?.workspacePath',
                         'window.ccodeTaskArchive.upload({workspacePath:n?.workspacePath',
                         'onOpenTaskPathInFileManager:()=>{__ccodeTaskFolder(f,u,n,Ee)}',
                         'onCopyWorkspacePath:()=>{__ccodeTaskCopyPath(f,u,n,Te,F.formatMessage({id:`appHeader.copyPath`}))}',
                         'let __cu=await zRe(e,n,t,r);'):
            self.assertIn(fragment, patched)

    def test_missing_anchor_fails_loudly(self):
        with self.assertRaises(ValueError):
            task_archive.patch_renderer('async fileChanges(t){return 1}')

    def test_attachment_cap_matches_the_main_process_limit(self):
        self.assertEqual(task_archive.ATTACHMENT_MAX_BASE64, 94371840)
        self.assertIn(f'length<={task_archive.ATTACHMENT_MAX_BASE64}', task_archive.ATTACHMENT_PATCHED)


ARCHIVE_SCRIPT = (
    'const mod=require(process.argv[1]);const path=require("path"),fs=require("fs");'
    'const [root,base,other]=process.argv.slice(2);'
    'const out=path.join(base,"outputs","DESIGN.md");'
    'const outside=path.join(path.dirname(base),"outside.txt");'
    'const r1=mod.archive({workspacePath:base,sessionId:"session-1",paths:[out,outside]},{root,base});'
    'const r2=mod.archive({workspacePath:base,sessionId:"session-1",paths:[out]},{root,base});'
    'const r3=mod.archive({workspacePath:other,sessionId:"other",paths:[out]},{root,base});'
    'const r4=mod.archive({workspacePath:base,sessionId:"empty",paths:[]},{root,base});'
    'const u1=mod.upload({workspacePath:base,sessionId:"session-1",fileName:"../laporan.pdf",'
    'dataBase64:Buffer.from("pdf").toString("base64")},{root,base});'
    'const u2=mod.upload({workspacePath:base,sessionId:"session-1",fileName:"kosong.txt",dataBase64:""},{root,base});'
    'const res1=mod.resolve({workspacePath:base,relPath:"outputs/DESIGN.md"},{root,base});'
    'const res2=mod.resolve({workspacePath:base,relPath:"belum.md"},{root,base});'
    'const f1=mod.folder({sessionId:"session-1"},{root,base});'
    'const f2=mod.folder({taskId:"session-1"},{root,base});'
    'const f3=mod.folder({sessionId:"tidak-ada",workspacePath:base},{root,base});'
    'const f4=mod.folder({sessionId:"tidak-ada",workspacePath:path.join(path.dirname(base),"project")},{root,base});'
    'process.stdout.write(JSON.stringify({r1,r2,r3,r4,u1,u2,res1,res2,f1,f2,f3,f4}));'
)


class ArchiveModuleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        workspace = pathlib.Path(self.temporary.name) / 'workspace'
        (workspace / 'default' / 'outputs').mkdir(parents=True)
        self.base = workspace / 'default'
        (self.base / 'outside.txt').write_text('secret\n')
        (self.base / 'outputs' / 'DESIGN.md').write_text('design\n')
        (self.base / 'belum.md').write_text('live\n')
        self.other = workspace / 'project'
        self.other.mkdir()
        self.root = pathlib.Path(self.temporary.name) / 'CCodeProject'

    def archive(self):
        return run_node(ARCHIVE_SCRIPT, self.root, self.base, self.other)

    def test_archive_upload_and_lookup_share_one_folder(self):
        result = self.archive()

        self.assertTrue(result['r1']['ok'])
        self.assertEqual(result['r1']['copied'], ['outputs/DESIGN.md'])
        folder = pathlib.Path(result['r1']['folder'])
        self.assertEqual(folder.parent, self.root)
        self.assertTrue(folder.name.startswith('task-'))
        self.assertTrue((folder / 'outputs' / 'DESIGN.md').is_file())
        # The same session reuses its folder; project workspaces never archive.
        self.assertEqual(result['r2']['folder'], result['r1']['folder'])
        self.assertEqual(result['r3']['skipped'], 'not-conversation')
        # Nothing produced means no folder.
        self.assertEqual(result['r4']['skipped'], 'no-files')
        self.assertEqual([path.name for path in self.root.iterdir() if path.name.startswith('task-')],
                         [folder.name])

        # A file the user attached lands in the same folder, name sanitized.
        self.assertTrue(result['u1']['ok'])
        self.assertEqual(result['u1']['file'], 'laporan.pdf')
        self.assertEqual(result['u1']['folder'], result['r1']['folder'])
        self.assertEqual((folder / 'laporan.pdf').read_text(), 'pdf')
        self.assertEqual(result['u2']['skipped'], 'missing-input')

        # Rows resolve to the archived copy, then to the live workspace file.
        self.assertEqual(result['res1'],
                         {'ok': True, 'path': str(folder / 'outputs' / 'DESIGN.md'), 'archived': True})
        self.assertEqual(result['res2'],
                         {'ok': True, 'path': str(self.base / 'belum.md'), 'archived': False})
        self.assertEqual(result['f1']['folder'], result['r1']['folder'])
        self.assertEqual(result['f2']['folder'], result['r1']['folder'])
        self.assertEqual(result['f3']['folder'], result['r1']['folder'])
        self.assertEqual(result['f4']['skipped'], 'none')

        index = json.loads((self.root / '.task-folders.json').read_text())
        self.assertEqual(index['sessions']['session-1'], result['r1']['folder'])
        self.assertEqual(index['latest'][str(self.base)], result['r1']['folder'])
        self.assertEqual(index['files'][str(self.base)]['outputs/DESIGN.md'], result['r1']['folder'])
        self.assertEqual(index['files'][str(self.base)]['laporan.pdf'], result['r1']['folder'])

    def test_files_outside_the_conversation_workspace_are_refused(self):
        result = self.archive()
        folder = pathlib.Path(result['r1']['folder'])
        self.assertEqual(sorted(path.name for path in folder.iterdir()), ['laporan.pdf', 'outputs'])
        self.assertFalse((folder / 'outside.txt').exists())
        self.assertFalse((folder / 'workspace').exists())

    def test_legacy_flat_index_is_absorbed(self):
        legacy = self.root / 'task-legacy'
        legacy.mkdir(parents=True)
        (self.root / '.task-folders.json').write_text(json.dumps({'session-legacy': str(legacy)}))
        script = (
            'const mod=require(process.argv[1]);const [root,base]=process.argv.slice(2);'
            'const f=mod.folder({sessionId:"session-legacy"},{root,base});'
            'process.stdout.write(JSON.stringify({f}));'
        )
        result = run_node(script, self.root, self.base)
        self.assertEqual(result['f'], {'ok': True, 'folder': str(legacy)})


class OpenFolderTests(unittest.TestCase):
    SCRIPT = (
        'const mod=require(process.argv[1]);const [target,mode]=process.argv.slice(2);'
        'let revealed=null;'
        'const shell={openPath:()=>new Promise(()=>{}),showItemInFolder:p=>{revealed=p}};'
        '(async()=>{'
        'const opened=await Promise.race([mod.openFolder({path:mode==="file"?target+"/prd.md":target},{shell}),'
        'new Promise(r=>setTimeout(()=>r({ok:false,skipped:"hung"}),1500))]);'
        'const missing=await mod.openFolder({path:target+"/tidak-ada"},{shell});'
        'process.stdout.write(JSON.stringify({opened,missing,revealed}))})()'
    )

    def test_directory_open_never_waits_for_the_launcher(self):
        # `shell.openPath` can stall until the file manager activates; the IPC
        # reply must not depend on it.
        with tempfile.TemporaryDirectory() as temporary:
            result = run_node(self.SCRIPT, temporary, 'directory')
            self.assertEqual(result['opened'], {'ok': True, 'path': temporary})
            self.assertEqual(result['missing'], {'ok': False, 'skipped': 'missing'})
            self.assertIsNone(result['revealed'])

    def test_file_target_is_revealed_in_the_file_manager(self):
        with tempfile.TemporaryDirectory() as temporary:
            (pathlib.Path(temporary) / 'prd.md').write_text('x\n')
            result = run_node(self.SCRIPT, temporary, 'file')
            self.assertEqual(result['opened'], {'ok': True, 'path': str(pathlib.Path(temporary) / 'prd.md')})
            self.assertEqual(result['revealed'], str(pathlib.Path(temporary) / 'prd.md'))


if __name__ == '__main__':
    unittest.main()
