import contextlib
import hashlib
import os
import importlib.util
import io
import json
import pathlib
import struct
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
spec = importlib.util.spec_from_file_location('apply_build', ROOT / 'scripts/apply_build.py')
apply_build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(apply_build)
sys.path.insert(0, str(ROOT / 'src'))
from local_only import branding

SKILL_PACK_PART = apply_build.SKILL_PACK + '.part'


def identity_archive():
    payload = json.dumps({'name': 'ccode'}).encode()
    header = json.dumps({'files': {'package.json': {'offset': '0', 'size': len(payload)}}}).encode()
    padding = (-len(header)) % 4
    size = 4 + len(header) + padding
    return struct.pack('<IIII', 4, 4 + size, size, len(header)) + header + b'\0' * padding + payload


class PromotionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.staged = self.root / 'runtime/build/resources'
        self.target = self.root / 'app/resources'
        self.names = ['app.asar', 'glm/zcode.cjs', 'voice/main.cjs', 'activity/main.cjs',
                      'config/provider/zcode-builtin.json', 'icon.png', 'icon_512x512.png', 'icon_windows.png']
        self.previous = {}
        for name in self.names:
            old = ('previous:' + name).encode()
            self.previous[name] = old
            for base in [self.staged, self.target]:
                (base / name).parent.mkdir(parents=True, exist_ok=True)
            (self.target / name).write_bytes(old)
            (self.staged / name).write_bytes(identity_archive() if name == 'app.asar' else ('new:' + name).encode())
        (self.root / 'project.json').write_text(json.dumps({'application_name': 'ccode'}))
        self.app_dir = self.root / 'app'
        (self.app_dir / 'usr/share/icons/hicolor/16x16/apps').mkdir(parents=True)
        (self.app_dir / 'zcode.desktop').write_text('[Desktop Entry]\nName=ZCode\nExec=AppRun --no-sandbox %U\n'
                                                    'Icon=zcode\nStartupWMClass=ZCode\nComment=ZCode Desktop App\n')
        (self.app_dir / 'AppRun').write_text('#!/bin/bash\nBIN="$APPDIR/zcode"\nexec "$BIN"\n')
        (self.app_dir / 'zcode').write_bytes(b'electron-binary')
        (self.app_dir / 'zcode.png').symlink_to('usr/share/icons/hicolor/1024x1024/apps/zcode.png')
        self.namespace = self.root / 'namespace'
        self.cache = self.namespace / 'data/.zcode/v2/runtime/provider/linux-x86_64/3.14.5/endpoint-test/zcode-builtin.json'
        self.cache.parent.mkdir(parents=True, exist_ok=True)
        cache_document = {"schemaVersion": 1, "revision": 30, "config": {"providerConfigRules": {"templateRules": [
            {"templateId": "zai-api", "config": {"access": {"type": "zhipu-coding-plan-api-key"},
                                                  "api": {"type": "anthropic-messages", "baseUrl": "https://api.z.ai/api/anthropic"},
                                                  "builtinModelIds": ["GLM-5.3"]}}],
            "providerRules": []}, "modelConfigRules": {"modelRules": []}}}
        self.cache.write_text(json.dumps(cache_document))
        self.cache_before = self.cache.read_text()
        env = mock.patch.dict(os.environ, {'ZCODE_STANDALONE_ROOT': str(self.namespace)})
        env.start()
        self.addCleanup(env.stop)
        self.pack_staged = self.staged / 'glm/packages/bundled-skills'
        self.pack_target = self.target / 'glm/packages/bundled-skills'
        staged_pack_files = {
            'skills/alpha/SKILL.md': b'new alpha body\n',
            'skills/beta/SKILL.md': b'new beta body\n',
            'skills/dynamic-workflows/SKILL.md': b'vendor body\n',
            '.ccode-skills.json': b'{"skills": ["alpha", "beta"]}\n',
        }
        self.pack_previous = {
            'skills/alpha/SKILL.md': b'old alpha body\n',
            'skills/stale/SKILL.md': b'old stale body\n',
            'skills/dynamic-workflows/SKILL.md': b'vendor body\n',
            '.ccode-skills.json': b'{"skills": ["alpha", "stale"]}\n',
        }
        for rel, data in staged_pack_files.items():
            (self.pack_staged / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.pack_staged / rel).write_bytes(data)
        for rel, data in self.pack_previous.items():
            (self.pack_target / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.pack_target / rel).write_bytes(data)
        staged_names = [*self.names, *(str(path.relative_to(self.staged)) for path in sorted(self.pack_staged.rglob('*'))
                                 if path.is_file())]
        proof = {'application_name': 'ccode', 'bundled_skills': ['alpha', 'beta'], 'sha256': {
            name: hashlib.sha256((self.staged / name).read_bytes()).hexdigest() for name in staged_names}}
        (self.staged / 'build-manifest.json').write_text(json.dumps(proof))
        patch = mock.patch.object(apply_build, 'ROOT', self.root)
        patch.start()
        self.addCleanup(patch.stop)

    def test_modified_staged_resource_cannot_replace_current_app(self):
        (self.staged / 'glm/zcode.cjs').write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
            apply_build.main()
        for name in self.names:
            self.assertEqual((self.target / name).read_bytes(), self.previous[name])

    def test_app_dir_identity_is_renamed_to_ccode(self):
        apply_build.main()
        self.assertFalse((self.app_dir / 'zcode').exists())
        self.assertEqual((self.app_dir / 'ccode').read_bytes(), b'electron-binary')
        launcher = (self.app_dir / 'ccode.desktop').read_text()
        for expected in ('Name=CCode', 'Icon=ccode', 'StartupWMClass=ccode', 'Comment=CCode Desktop App'):
            self.assertIn(expected, launcher)
        self.assertFalse((self.app_dir / 'zcode.desktop').exists())
        self.assertEqual((self.app_dir / 'AppRun').read_text().count('BIN="$APPDIR/ccode"'), 1)
        self.assertFalse((self.app_dir / 'zcode.png').is_symlink())
        self.assertEqual(os.readlink(self.app_dir / '.DirIcon'), 'usr/share/icons/hicolor/1024x1024/apps/ccode.png')
        installed = self.app_dir / 'usr/share/icons/hicolor/16x16/apps/ccode.png'
        self.assertEqual(installed.read_bytes(), (branding.ICON_DIR / 'ccode-16.png').read_bytes())
        previous = sorted((self.root / 'runtime/backups').glob('*/appdir/zcode.desktop'))
        self.assertEqual(len(previous), 1)

    def test_derived_catalog_cache_is_refreshed(self):
        apply_build.main()
        patched = json.loads(self.cache.read_text())
        templates = [rule.get('templateId') for rule in patched['config']['providerConfigRules']['templateRules']]
        self.assertEqual(templates, ['9router'])
        backups = list((self.root / 'runtime/backups').glob('*/derived/**/zcode-builtin.json'))
        self.assertEqual(len(backups), 1, 'previous cache is kept for rollback')
        self.assertEqual(backups[0].read_text(), self.cache_before)

    def test_failed_promotion_leaves_cache_untouched(self):
        with mock.patch.object(apply_build, 'refresh_derived_catalogs', side_effect=OSError('simulated cache failure')):
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaisesRegex(OSError, 'simulated cache failure'):
                apply_build.main()
        self.assertEqual(self.cache.read_text(), self.cache_before)

    def test_partial_promotion_restores_all_previous_resources(self):
        real_replace = apply_build.os.replace

        def fail_second_resource(source, destination):
            if pathlib.Path(destination) == self.target / 'glm/zcode.cjs':
                raise OSError('simulated filesystem failure')
            return real_replace(source, destination)

        with mock.patch.object(apply_build.os, 'replace', side_effect=fail_second_resource):
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaisesRegex(OSError, 'filesystem failure'):
                apply_build.main()
        for name in self.names:
            self.assertEqual((self.target / name).read_bytes(), self.previous[name])
            self.assertFalse((self.target / name).with_name(pathlib.Path(name).name + '.new').exists())

    def test_bundled_skills_are_promoted_and_stale_ones_pruned(self):
        apply_build.main()
        self.assertEqual((self.pack_target / 'skills/alpha/SKILL.md').read_bytes(), b'new alpha body\n')
        self.assertEqual((self.pack_target / 'skills/beta/SKILL.md').read_bytes(), b'new beta body\n')
        self.assertFalse((self.pack_target / 'skills/stale').exists(), 'skills we removed are pruned')
        self.assertEqual((self.pack_target / '.ccode-skills.json').read_bytes(), b'{"skills": ["alpha", "beta"]}\n')
        self.assertEqual((self.pack_target / 'skills/dynamic-workflows/SKILL.md').read_bytes(), b'vendor body\n',
                         'vendor bundled skills are never touched')

    def test_corrupt_staged_skill_cannot_replace_the_pack(self):
        (self.pack_staged / 'skills/beta/SKILL.md').write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError, 'Staged skill checksum mismatch'):
            apply_build.main()
        for rel, data in self.pack_previous.items():
            self.assertEqual((self.pack_target / rel).read_bytes(), data, rel)
        for name in self.names:
            self.assertEqual((self.target / name).read_bytes(), self.previous[name])

    def test_failed_skill_copy_restores_the_previous_pack(self):
        real_copytree = apply_build.shutil.copytree

        def flaky(source, destination, *args, **kwargs):
            if str(destination).endswith('/skills/beta'):
                raise OSError('simulated copy failure')
            return real_copytree(source, destination, *args, **kwargs)

        with mock.patch.object(apply_build.shutil, 'copytree', side_effect=flaky):
            with self.assertRaises(OSError):
                apply_build.main()
        for rel, data in self.pack_previous.items():
            self.assertEqual((self.pack_target / rel).read_bytes(), data, rel)
        self.assertFalse((self.pack_target / 'skills/beta').exists(), 'half-copied skills are rolled back')
        for name in self.names:
            self.assertEqual((self.target / name).read_bytes(), self.previous[name])

    def test_failed_pack_snapshot_leaves_the_pack_untouched(self):
        real_copytree = apply_build.shutil.copytree

        def flaky(source, destination, *args, **kwargs):
            if str(destination).endswith(SKILL_PACK_PART):
                raise OSError('simulated snapshot failure')
            return real_copytree(source, destination, *args, **kwargs)

        with mock.patch.object(apply_build.shutil, 'copytree', side_effect=flaky):
            with self.assertRaises(OSError):
                apply_build.main()
        for rel, data in self.pack_previous.items():
            self.assertEqual((self.pack_target / rel).read_bytes(), data, rel)
        self.assertTrue((self.pack_target / 'skills/stale').exists(), 'an intact pack is never replaced by a partial snapshot')
        for name in self.names:
            self.assertEqual((self.target / name).read_bytes(), self.previous[name])

    def test_apply_prunes_old_backups_and_removes_stale_markers(self):
        backups = self.root / 'runtime/backups'
        old = ['20200101-000000-000000', '20200102-000000-000000', '20200103-000000-000000']
        for stamp in old:
            (backups / stamp).mkdir(parents=True)
        marker = self.cache.with_name('zcode-builtin-refresh.json')
        marker.write_text('{}')
        apply_build.main()
        remaining = sorted(p.name for p in backups.iterdir())
        self.assertEqual(len(remaining), 2, remaining)
        self.assertEqual(len([p for p in backups.iterdir() if (p / 'applied-build.json').exists()]), 1)
        self.assertEqual(remaining[0], old[-1])
        self.assertFalse(marker.exists())
        self.assertTrue(self.cache.exists())


class MaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)

    def test_backup_retention_keeps_two_newest(self):
        backups = self.root / 'backups'
        stamps = ['20200101-000000-000000', '20200102-000000-000000',
                  '20200103-000000-000000', '20200104-000000-000000']
        for stamp in stamps:
            (backups / stamp).mkdir(parents=True)
        (backups / 'not-a-backup').mkdir()
        (backups / 'link').symlink_to(backups / 'not-a-backup', target_is_directory=True)
        removed = apply_build.prune_backups(backups, backups / stamps[-1])
        self.assertEqual(sorted(p.name for p in removed), stamps[:2])
        self.assertEqual(sorted(p.name for p in backups.iterdir()),
                         sorted(stamps[2:] + ['link', 'not-a-backup']))

    def test_backup_retention_tolerates_missing_or_empty_directory(self):
        missing = self.root / 'missing'
        self.assertEqual(apply_build.prune_backups(missing, missing / 'run'), [])
        empty = self.root / 'empty'
        empty.mkdir()
        self.assertEqual(apply_build.prune_backups(empty, empty / 'run'), [])

    def endpoint_under(self, namespace):
        endpoint = namespace / 'data/.zcode/v2/runtime/provider/linux-x86_64/3.14.5/endpoint-test'
        endpoint.mkdir(parents=True)
        return endpoint

    def test_stale_catalog_markers_removed_catalog_kept(self):
        namespace = self.root / 'namespace'
        endpoint = self.endpoint_under(namespace)
        (endpoint / 'zcode-builtin.json').write_text('{}')
        marker = endpoint / 'zcode-builtin-refresh.json'
        marker.write_text('{}')
        env = mock.patch.dict(os.environ, {'ZCODE_STANDALONE_ROOT': str(namespace)})
        env.start()
        self.addCleanup(env.stop)
        removed = apply_build.remove_stale_catalog_markers()
        self.assertEqual([p.name for p in removed], ['zcode-builtin-refresh.json'])
        self.assertFalse(marker.exists())
        self.assertTrue((endpoint / 'zcode-builtin.json').exists())

    def test_stale_catalog_markers_tolerate_missing_namespace(self):
        env = mock.patch.dict(os.environ, {'ZCODE_STANDALONE_ROOT': str(self.root / 'absent')})
        env.start()
        self.addCleanup(env.stop)
        self.assertEqual(apply_build.remove_stale_catalog_markers(), [])


if __name__ == '__main__':
    unittest.main()
