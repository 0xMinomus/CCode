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


class DataBackupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.folder = pathlib.Path(self.temporary.name)
        self.root = self.folder / 'standalone'
        self.db = self.root / 'data/.zcode/cli/db/db.sqlite'
        self.db.parent.mkdir(parents=True)
        self.task = self.root / 'data/.zcode/v2/workspace/task/messages.json'
        self.task.parent.mkdir(parents=True)
        self.task.write_text('{"messages":["local task"]}')
        self.profile = self.root / 'electron/Preferences'
        self.profile.parent.mkdir()
        self.profile.write_text('{"voice":"review"}')
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
        self.assertIn('data/.zcode/cli/db/db.sqlite-wal', manifest['omittedSqliteSidecars'])
        copied = self.snapshot / 'files/data/.zcode/cli/db/db.sqlite'
        with contextlib.closing(sqlite3.connect(copied)) as connection:
            self.assertEqual(connection.execute('SELECT message FROM tasks').fetchone(), ('committed in WAL',))
        self.assertFalse(copied.with_name('db.sqlite-wal').exists())
        self.assertEqual((self.snapshot / 'files/data/.zcode/v2/workspace/task/messages.json').read_bytes(), self.task.read_bytes())
        self.assertEqual((self.snapshot / 'files/electron/Preferences').read_bytes(), self.profile.read_bytes())
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
        self.assertEqual(self.profile.read_text(), '{"voice":"review"}')
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

    def test_symlink_source_target_and_snapshot_refused(self):
        self.create_database().close()
        link = self.root / 'data/outside'
        link.symlink_to(self.folder)
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            backup.backup(self.root, self.snapshot)
        link.unlink()
        alias = self.folder / 'namespace-alias'
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'Symlink'):
            backup.backup(alias, self.snapshot)
        backup.backup(self.root, self.snapshot)
        (self.snapshot / 'files/electron/escape').symlink_to(self.profile)
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            backup.restore(self.root, self.snapshot)
        with self.assertRaisesRegex(ValueError, 'Symlink'):
            backup.restore(alias, self.snapshot)

    def test_electron_singletons_are_not_restored(self):
        self.create_database().close()
        (self.root / 'electron/SingletonLock').symlink_to('host-1234')
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


if __name__ == '__main__':
    unittest.main()
