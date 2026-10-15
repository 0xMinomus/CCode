import contextlib
import importlib.util
import json
import os
import pathlib
import sqlite3
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('data_backup', ROOT / 'scripts/data_backup.py')
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)


def symlink_or_skip(test, target, destination, target_is_directory=False):
    try:
        destination.symlink_to(target, target_is_directory)
    except OSError:
        test.skipTest('POSIX symlink privilege is unavailable on this host')


class DataBackupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.folder = pathlib.Path(self.temporary.name)
        self.root = self.folder / 'standalone'
        self.db = self.root / 'data/.ccode/cli/db/db.sqlite'
        self.db.parent.mkdir(parents=True)
        self.task = self.root / 'data/.ccode/v2/workspace/task/messages.json'
        self.task.parent.mkdir(parents=True)
        self.task.write_text('{"messages":["local task"]}')
        self.profile = self.root / 'electron/Preferences'
        self.profile.parent.mkdir()
        self.profile.write_text('{"theme":"dark"}')
        self.snapshot = self.folder / 'snapshot'

    def create_database(self):
        connection = sqlite3.connect(self.db)
        self.addCleanup(connection.close)
        connection.execute('PRAGMA journal_mode=WAL')
        connection.execute('PRAGMA wal_autocheckpoint=0')
        connection.execute('CREATE TABLE tasks (id INTEGER PRIMARY KEY, message TEXT)')
        connection.execute('INSERT INTO tasks VALUES (1, "committed in WAL")')
        connection.commit()
        return connection

    def test_quiescent_wal_snapshot_and_private_permissions(self):
        self.create_database()
        self.assertTrue(self.db.with_name('db.sqlite-wal').exists())
        backup.backup(self.root, self.snapshot)
        manifest = backup.validate_snapshot(self.snapshot)
        self.assertIn('data/.ccode/cli/db/db.sqlite-wal', manifest['omittedSqliteSidecars'])
        copied = self.snapshot / 'files/data/.ccode/cli/db/db.sqlite'
        with contextlib.closing(sqlite3.connect(copied)) as connection:
            self.assertEqual(connection.execute('SELECT message FROM tasks').fetchone(), ('committed in WAL',))
        self.assertFalse(copied.with_name('db.sqlite-wal').exists())
        self.assertEqual((self.snapshot / 'files/data/.ccode/v2/workspace/task/messages.json').read_bytes(), self.task.read_bytes())
        self.assertEqual((self.snapshot / 'files/electron/Preferences').read_bytes(), self.profile.read_bytes())

    @unittest.skipIf(os.name != 'posix', 'POSIX file modes are not meaningful on Windows')
    def test_snapshot_permissions_are_private(self):
        self.create_database()
        backup.backup(self.root, self.snapshot)
        for path in (self.snapshot, *self.snapshot.rglob('*')):
            self.assertEqual(path.stat().st_mode & 0o077, 0, str(path))

    def test_restore_keeps_original_and_recovers_task_profile_database(self):
        connection = self.create_database()
        backup.backup(self.root, self.snapshot)
        connection.close()
        self.task.write_text('changed task')
        self.profile.write_text('changed preference')
        with contextlib.closing(sqlite3.connect(self.db)) as changed:
            changed.execute('UPDATE tasks SET message="changed database"')
            changed.commit()
        original = backup.restore(self.root, self.snapshot)
        self.assertEqual((original / self.task.relative_to(self.root)).read_text(), 'changed task')
        self.assertEqual(self.task.read_text(), '{"messages":["local task"]}')
        self.assertEqual(self.profile.read_text(), '{"theme":"dark"}')
        with contextlib.closing(sqlite3.connect(self.db)) as restored:
            self.assertEqual(restored.execute('SELECT message FROM tasks').fetchone(), ('committed in WAL',))

    def test_corruption_refuses_restore_without_touching_original(self):
        self.create_database().close()
        backup.backup(self.root, self.snapshot)
        (self.snapshot / 'files/electron/Preferences').write_text('tampered')
        before = self.task.read_bytes()
        with self.assertRaisesRegex(ValueError, 'checksum'):
            backup.restore(self.root, self.snapshot)
        self.assertEqual(self.task.read_bytes(), before)
        self.assertEqual(list(self.folder.glob('standalone-pre-restore-*')), [])

    def test_manifest_traversal_and_unlisted_file_refused(self):
        self.create_database().close()
        backup.backup(self.root, self.snapshot)
        path = self.snapshot / 'manifest.json'
        manifest = json.loads(path.read_text())
        manifest['entries'][0]['path'] = '../escape'
        path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            backup.validate_snapshot(self.snapshot)
        manifest['entries'][0]['path'] = 'data'
        path.write_text(json.dumps(manifest))
        (self.snapshot / 'files/extra').write_text('unlisted')
        with self.assertRaisesRegex(ValueError, 'inventory'):
            backup.validate_snapshot(self.snapshot)

    def test_symlink_policy_keeps_inside_links_and_refuses_escape(self):
        self.create_database().close()
        link = self.root / 'data/outside'
        symlink_or_skip(self, self.folder, link)
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            backup.backup(self.root, self.snapshot)
        link.unlink()
        alias = self.folder / 'namespace-alias'
        symlink_or_skip(self, self.root, alias, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'Symlink'):
            backup.backup(alias, self.snapshot)
        backup.backup(self.root, self.snapshot)
        symlink_or_skip(self, self.profile, self.snapshot / 'files/electron/escape')
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            backup.restore(self.root, self.snapshot)
        with self.assertRaisesRegex(ValueError, 'Symlink'):
            backup.restore(alias, self.snapshot)

    def test_workspace_links_are_snapshotted_and_restored(self):
        self.create_database().close()
        link = self.root / 'data/.ccode/workspace/node_modules/.bin/tool'
        link.parent.mkdir(parents=True, exist_ok=True)
        symlink_or_skip(self, '../../cli/tool.js', link)
        backup.backup(self.root, self.snapshot)
        manifest = backup.validate_snapshot(self.snapshot)
        self.assertEqual([entry['path'] for entry in manifest['links']],
                         ['data/.ccode/workspace/node_modules/.bin/tool'])
        self.assertNotIn('data/.ccode/workspace/node_modules/.bin/tool',
                         [entry['path'] for entry in manifest['entries']])
        link.unlink()
        backup.restore(self.root, self.snapshot)
        self.assertTrue(link.is_symlink())
        self.assertEqual(os.readlink(link), '../../cli/tool.js')

    def test_escaping_link_target_in_a_snapshot_is_refused(self):
        self.create_database().close()
        link = self.root / 'data/.ccode/workspace/tool'
        link.parent.mkdir(parents=True, exist_ok=True)
        symlink_or_skip(self, '../../cli/tool.js', link)
        backup.backup(self.root, self.snapshot)
        manifest_path = self.snapshot / 'manifest.json'
        manifest = json.loads(manifest_path.read_text())
        manifest['links'][0]['target'] = '../../../../outside/tool.js'
        manifest_path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, 'escapes'):
            backup.validate_snapshot(self.snapshot)

    def test_electron_singletons_are_not_restored(self):
        self.create_database().close()
        (self.root / 'electron/SingletonLock').parent.mkdir(parents=True, exist_ok=True)
        symlink_or_skip(self, 'host-1234', self.root / 'electron/SingletonLock')
        backup.backup(self.root, self.snapshot)
        backup.restore(self.root, self.snapshot)
        self.assertFalse((self.root / 'electron/SingletonLock').is_symlink())

    def test_launch_lock_refuses_offline_restore(self):
        self.create_database().close()
        backup.backup(self.root, self.snapshot)
        with backup.namespace_lock(self.root, exclusive=False):
            with self.assertRaisesRegex(ValueError, 'active'):
                backup.restore(self.root, self.snapshot)
        self.assertTrue(self.task.exists())

    def test_launch_lock_refuses_backup(self):
        self.create_database().close()
        with backup.namespace_lock(self.root, exclusive=False):
            with self.assertRaisesRegex(ValueError, 'active'):
                backup.backup(self.root, self.snapshot)
        self.assertFalse(self.snapshot.exists())

    def test_promotion_failure_restores_original(self):
        self.create_database().close()
        backup.backup(self.root, self.snapshot)
        self.task.write_text('original must survive')
        rename = os.rename

        def fail_promotion(source, target):
            if pathlib.Path(source).name.startswith('.standalone-restore-') and pathlib.Path(target) == self.root:
                raise OSError('injected promotion failure')
            return rename(source, target)

        with mock.patch.object(backup.os, 'rename', side_effect=fail_promotion):
            with self.assertRaisesRegex(OSError, 'promotion failure'):
                backup.restore(self.root, self.snapshot)
        self.assertEqual(self.task.read_text(), 'original must survive')
        self.assertEqual(list(self.folder.glob('.standalone-restore-*')), [])


class WindowsNamespaceMatcherTests(unittest.TestCase):
    def test_matches_only_the_running_namespace(self):
        root = pathlib.PureWindowsPath('C:/Users/x/AppData/Local/CCode')
        quoted = '"C:\\app\\CCode.exe" --type=gpu-process --user-data-dir="C:\\Users\\x\\AppData\\Local\\CCode\\electron"'
        unquoted = '"C:\\app\\CCode.exe" --user-data-dir=C:\\Users\\x\\AppData\\Local\\CCode\\electron'
        self.assertTrue(backup.windows_namespace_in_use(root, [quoted]))
        self.assertTrue(backup.windows_namespace_in_use(root, [unquoted]))
        self.assertTrue(backup.windows_namespace_in_use(root, [quoted.upper()]), 'the match is case-insensitive')
        self.assertTrue(backup.windows_namespace_in_use(root, [quoted.replace('\\', '/')]), 'forward slashes are accepted')

    def test_ignores_other_roots_and_unrelated_clients(self):
        root = pathlib.PureWindowsPath('C:/Users/x/AppData/Local/CCode')
        other = '"C:\\app\\CCode.exe" --user-data-dir="D:\\isolated\\root\\electron"'
        sibling = '"C:\\app\\CCode.exe" --user-data-dir="C:\\Users\\x\\AppData\\Local\\CCode-other\\electron"'
        bare = '"C:\\app\\CCode.exe" '
        self.assertFalse(backup.windows_namespace_in_use(root, [other]))
        self.assertFalse(backup.windows_namespace_in_use(root, [sibling]), 'a shared prefix is not this namespace')
        self.assertFalse(backup.windows_namespace_in_use(root, [bare]))
        self.assertFalse(backup.windows_namespace_in_use(root, []))
        self.assertFalse(backup.windows_namespace_in_use(root, None))
        self.assertFalse(backup.windows_namespace_in_use(root, [None, 3]))

    def test_default_root_and_isolated_root_do_not_collide(self):
        running = pathlib.PureWindowsPath('C:/Users/x/AppData/Local/CCode')
        lines = ['"C:\\app\\CCode.exe" --user-data-dir="C:\\Users\\x\\AppData\\Local\\CCode\\electron"']
        self.assertTrue(backup.windows_namespace_in_use(running, lines))
        self.assertFalse(backup.windows_namespace_in_use(pathlib.PureWindowsPath('C:/tmp/isolated'), lines))


if __name__ == '__main__':
    unittest.main()
