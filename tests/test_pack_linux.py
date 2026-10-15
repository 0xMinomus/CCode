import os
import pathlib
import stat
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'src'))
import pack_linux


class LauncherContractTests(unittest.TestCase):
    def exports(self, text):
        names = set()
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith('export '):
                names.add(stripped[len('export '):].split('=', 1)[0])
        return names

    def test_packaged_launcher_exports_what_run_sh_exports(self):
        project = self.exports((ROOT / 'scripts/run.sh').read_text())
        packaged = self.exports(pack_linux.LAUNCHER)
        self.assertEqual(project, packaged)
        self.assertIn('CCODE_STANDALONE_ROOT', packaged)
        self.assertIn('CCODE_SESSION_DB_PATH', packaged)

    def test_packaged_launcher_uses_the_shared_operations_lock(self):
        # run.sh derives this lock from the namespace root, and a backup or apply takes it
        # exclusively; a different path would let both run against a live app.
        self.assertIn('"$(dirname "$root")/.$(basename "$root").operations.lock"', pack_linux.LAUNCHER)
        self.assertIn('flock --shared "$lock"', pack_linux.LAUNCHER)


class StageHygieneTests(unittest.TestCase):
    def make_venv(self, root):
        venv = root / 'services/desktop/.venv'
        (venv / 'bin').mkdir(parents=True)
        (venv / 'lib/__pycache__').mkdir(parents=True)
        (venv / 'lib/__pycache__/module.cpython-314.pyc').write_bytes(b'cache')
        (venv / 'bin/python3').write_text('link placeholder\n')
        (venv / 'bin/pip').write_text(f'#!{pathlib.Path.home()}/repo/services/desktop/.venv/bin/python\n')
        (venv / 'pyvenv.cfg').write_text(
            'home = /usr/bin\ninclude-system-site-packages = false\nversion = 3.14.8\n'
            f'command = /usr/bin/python3 -m venv {pathlib.Path.home()}/repo/services/desktop/.venv\n')
        return venv

    def test_release_refuses_retired_deployed_resources(self):
        self.assertEqual(pack_linux.ALL_COMPONENTS, ('model-sync', 'desktop'))
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            app = root / 'app'
            (app / 'resources/voice').mkdir(parents=True)
            with mock.patch.object(pack_linux, 'APPLIED', app):
                with self.assertRaisesRegex(SystemExit, 'Retired Voice resource'):
                    pack_linux.stage_tree(root / 'release', (), '1.0.0')

    def test_sanitize_drops_caches_console_scripts_and_build_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            venv = self.make_venv(root)
            pack_linux.sanitize(root)
            self.assertTrue((venv / 'bin/python3').exists())
            self.assertFalse((venv / 'bin/pip').exists())
            self.assertFalse(list(root.rglob('__pycache__')))
            self.assertFalse(list(root.rglob('*.pyc')))
            config = (venv / 'pyvenv.cfg').read_text()
            self.assertNotIn('command =', config)
            self.assertIn('home = /usr/bin', config)

    def test_path_gate_refuses_the_build_machine_home_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            (root / 'notice.md').write_text('clean\n')
            pack_linux.assert_no_personal_paths(root)
            (root / 'leak.txt').write_text(f'built in {pathlib.Path.home()}/somewhere\n')
            with self.assertRaises(SystemExit):
                pack_linux.assert_no_personal_paths(root)

    def test_normalize_modes_makes_the_tree_readable_for_installed_users(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            private_dir = root / 'app/resources'
            private_dir.mkdir(parents=True)
            os.chmod(private_dir, 0o700)
            bundle = private_dir / 'app.asar'
            bundle.write_bytes(b'payload')
            os.chmod(bundle, 0o600)
            runner = root / 'ccode'
            runner.write_text('#!/usr/bin/env bash\n')
            os.chmod(runner, 0o700)
            pack_linux.normalize_modes(root)
            self.assertEqual(stat.S_IMODE(private_dir.stat().st_mode), 0o755)
            self.assertEqual(stat.S_IMODE(bundle.stat().st_mode), 0o644)
            self.assertEqual(stat.S_IMODE(runner.stat().st_mode), 0o755)

    def test_local_state_is_dropped_and_provider_configs_refuse_the_build(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            state = root / 'services/model-sync'
            (state / 'backups').mkdir(parents=True)
            (state / 'backups/provider_config-20260101-000000-000000.json').write_text('{}')
            (state / 'state.json').write_text('{}')
            (state / 'catalog.json').write_text('{}')
            (state / 'sync.lock').write_text('')
            pack_linux.strip_local_state(root)
            self.assertFalse((state / 'backups').exists())
            self.assertFalse((state / 'state.json').exists())
            self.assertFalse((state / 'catalog.json').exists())
            self.assertFalse((state / 'sync.lock').exists())
            (root / 'provider_config.json').write_text('{"key":"secret"}')
            with self.assertRaises(SystemExit):
                pack_linux.strip_local_state(root)


if __name__ == '__main__':
    unittest.main()
