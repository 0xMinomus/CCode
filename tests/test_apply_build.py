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
build_spec = importlib.util.spec_from_file_location('build', ROOT / 'scripts/build.py')
build = importlib.util.module_from_spec(build_spec)
build_spec.loader.exec_module(build)
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
        self.pack_staged = self.staged / apply_build.SKILL_PACK
        self.pack_target = self.target / apply_build.SKILL_PACK
        vendor = {'README.md': b'vendor pack\n',
                  'skills/dynamic-workflows/SKILL.md': b'vendor workflow\n',
                  'skills/dynamic-workflows/examples.md': b'vendor examples\n',
                  'skills/dynamic-workflows/patterns.md': b'vendor patterns\n',
                  'skills/other-vendor/SKILL.md': b'unowned vendor skill\n'}
        staged_pack_files = {
            **vendor, '.ccode-skills.json': b'{"skills": ["alpha", "beta"]}\n',
            'skills/alpha/SKILL.md': b'new alpha body\n',
            'skills/beta/SKILL.md': b'new beta body\n',
        }
        self.pack_previous = {
            **vendor, '.ccode-skills.json': b'{"skills": ["alpha", "stale"]}\n',
            'skills/alpha/SKILL.md': b'old alpha body\n',
            'skills/stale/SKILL.md': b'old stale body\n',
        }
        self.legacy = self.target / apply_build.LEGACY_SKILL_PLUGIN
        self.legacy_previous = {'.zcode-plugin/plugin.json': b'{"name": "ccode-skills", "skills": "skills"}\n',
                                'skills/alpha/SKILL.md': b'legacy alpha body\n'}
        for rel, data in self.legacy_previous.items():
            (self.legacy / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.legacy / rel).write_bytes(data)
        self.user_skills = self.namespace / 'data/.zcode/skills'
        self.user_previous = {'alpha/SKILL.md': b'user alpha\n', 'personal/SKILL.md': b'user personal\n'}
        for rel, data in self.user_previous.items():
            (self.user_skills / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.user_skills / rel).write_bytes(data)
        for rel, data in staged_pack_files.items():
            (self.pack_staged / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.pack_staged / rel).write_bytes(data)
        for rel, data in self.pack_previous.items():
            (self.pack_target / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.pack_target / rel).write_bytes(data)
        self.mcp_staged = self.staged / apply_build.MCP_RESOURCE
        self.mcp_target = self.target / apply_build.MCP_RESOURCE
        self.mcp_previous = {'main.cjs': b'old MCP main\n', 'obsolete.cjs': b'old MCP dependency\n'}
        mcp_files = {'main.cjs': b'new MCP main\n', 'launch.cjs': b'new MCP launcher\n', 'catalog.json': b'[]\n',
                     'runtime/package.json': b'{"private":true}\n', 'runtime/package-lock.json': b'{}\n',
                     'runtime/node_modules/server/index.js': b'new bundled server\n'}
        for base, files in ((self.mcp_staged, mcp_files), (self.mcp_target, self.mcp_previous)):
            for rel, data in files.items():
                (base / rel).parent.mkdir(parents=True, exist_ok=True)
                (base / rel).write_bytes(data)
        self.unowned = self.target / 'other-resource/personal.txt'
        self.unowned.parent.mkdir()
        self.unowned.write_bytes(b'preserved resource\n')
        staged_names = [*self.names, *(str(path.relative_to(self.staged)) for tree in (self.pack_staged, self.mcp_staged)
                                     for path in sorted(tree.rglob('*')) if path.is_file())]
        proof = {'application_name': 'ccode', 'bundled_skill_pack': apply_build.skills_plugin.PACK_DIR,
                 'bundled_skills': ['alpha', 'beta'], 'sha256': {
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
        self.assert_previous_resources()

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

    def test_fresh_install_promotes_native_pack_without_a_plugin(self):
        apply_build.shutil.rmtree(self.pack_target)
        apply_build.shutil.rmtree(self.legacy)
        apply_build.main()
        self.assertEqual((self.pack_target / 'skills/alpha/SKILL.md').read_bytes(), b'new alpha body\n')
        self.assertEqual((self.pack_target / 'skills/dynamic-workflows/examples.md').read_bytes(), b'vendor examples\n')
        self.assertFalse(self.legacy.exists())
        self.assertFalse((self.pack_target / '.zcode-plugin').exists())
        self.assertEqual((self.mcp_target / 'runtime/node_modules/server/index.js').read_bytes(), b'new bundled server\n')
        self.assertFalse((self.mcp_target / 'obsolete.cjs').exists())
        self.assertEqual(self.unowned.read_bytes(), b'preserved resource\n')
        for rel, data in self.user_previous.items():
            self.assertEqual((self.user_skills / rel).read_bytes(), data)

    def test_plugin_only_install_transitions_and_can_restore_original_resources(self):
        apply_build.shutil.rmtree(self.pack_target)
        backup = self.root / 'transition-backup'
        backup.mkdir()
        proof = json.loads((self.staged / 'build-manifest.json').read_text())
        apply_build.promote_skill_pack(self.staged, self.target, proof, backup)
        self.assertTrue((self.pack_target / 'skills/alpha/SKILL.md').exists())
        self.assertFalse(self.legacy.exists())
        apply_build.restore_skill_pack(self.target, backup)
        self.assertFalse(self.pack_target.exists())
        for rel, data in self.legacy_previous.items():
            self.assertEqual((self.legacy / rel).read_bytes(), data)
        for rel, data in self.user_previous.items():
            self.assertEqual((self.user_skills / rel).read_bytes(), data)

    def assert_previous_resources(self):
        for rel, data in self.mcp_previous.items():
            self.assertEqual((self.mcp_target / rel).read_bytes(), data, rel)
        self.assertEqual(self.unowned.read_bytes(), b'preserved resource\n')
        for base, files in ((self.pack_target, self.pack_previous), (self.legacy, self.legacy_previous),
                            (self.user_skills, self.user_previous)):
            for rel, data in files.items():
                self.assertEqual((base / rel).read_bytes(), data, rel)
        for name in self.names:
            self.assertEqual((self.target / name).read_bytes(), self.previous[name])

    def test_native_pack_replaces_owned_skills_preserves_vendor_and_user_skills(self):
        apply_build.main()
        self.assertEqual((self.pack_target / 'skills/alpha/SKILL.md').read_bytes(), b'new alpha body\n')
        self.assertEqual((self.pack_target / 'skills/beta/SKILL.md').read_bytes(), b'new beta body\n')
        self.assertFalse((self.pack_target / 'skills/stale').exists())
        for rel, data in self.pack_previous.items():
            if rel == 'README.md' or rel.startswith(('skills/dynamic-workflows/', 'skills/other-vendor/')):
                self.assertEqual((self.pack_target / rel).read_bytes(), data, rel)
        for rel, data in self.user_previous.items():
            self.assertEqual((self.user_skills / rel).read_bytes(), data)
        self.assertFalse((self.pack_target / '.zcode-plugin').exists())
        self.assertFalse(self.legacy.exists())
        backups = list((self.root / 'runtime/backups').glob('*/' + apply_build.LEGACY_SKILL_PLUGIN))
        self.assertEqual(len(backups), 1)
        for rel, data in self.legacy_previous.items():
            self.assertEqual((backups[0] / rel).read_bytes(), data)

    def test_corrupt_staged_skill_cannot_replace_deployed_resources(self):
        (self.pack_staged / 'skills/beta/SKILL.md').write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError, 'Staged skill pack checksum mismatch'):
            apply_build.main()
        self.assert_previous_resources()

    def test_corrupt_vendor_seed_cannot_replace_deployed_resources(self):
        (self.pack_staged / 'skills/dynamic-workflows/examples.md').write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError, 'Staged skill pack checksum mismatch'):
            apply_build.main()
        self.assert_previous_resources()

    def test_unhashed_staged_file_cannot_be_promoted(self):
        (self.pack_staged / 'skills/beta/extra.md').write_bytes(b'unhashed')
        with self.assertRaisesRegex(ValueError, 'inventory mismatch'):
            apply_build.main()
        self.assert_previous_resources()

    def test_missing_staged_file_cannot_be_promoted(self):
        (self.pack_staged / 'skills/beta/SKILL.md').unlink()
        with self.assertRaisesRegex(ValueError, 'inventory mismatch'):
            apply_build.main()
        self.assert_previous_resources()

    def test_old_plugin_manifest_is_rejected(self):
        proof_path = self.staged / 'build-manifest.json'
        proof = json.loads(proof_path.read_text())
        del proof['bundled_skill_pack']
        proof['bundled_plugin'] = 'ccode-skills-plugin'
        proof_path.write_text(json.dumps(proof))
        with self.assertRaisesRegex(ValueError, 'wrong bundled skill pack'):
            apply_build.main()
        self.assert_previous_resources()

    def test_corrupt_mcp_tree_is_rejected_before_promoting_any_resource(self):
        dependency = self.mcp_staged / 'runtime/node_modules/server/index.js'
        original = dependency.read_bytes()
        for mutation in ('checksum', 'unhashed', 'missing'):
            with self.subTest(mutation=mutation):
                dependency.write_bytes(original)
                extra = self.mcp_staged / 'runtime/unhashed.js'
                if extra.exists():
                    extra.unlink()
                if mutation == 'checksum':
                    dependency.write_bytes(b'corrupt dependency')
                elif mutation == 'unhashed':
                    extra.write_bytes(b'unhashed dependency')
                else:
                    dependency.unlink()
                with self.assertRaisesRegex(ValueError, 'Staged MCP resource (checksum|file inventory) mismatch'):
                    apply_build.main()
                self.assert_previous_resources()

    def test_partial_mcp_copy_restores_existing_and_fresh_resources(self):
        real_copytree = apply_build.shutil.copytree
        for fresh in (False, True):
            with self.subTest(fresh=fresh):
                if fresh:
                    apply_build.shutil.rmtree(self.mcp_target)
                copies = {'count': 0}

                def flaky(source, destination, *args, **kwargs):
                    if pathlib.Path(destination) == self.mcp_target:
                        copies['count'] += 1
                        if copies['count'] == 1:
                            pathlib.Path(destination).mkdir(parents=True)
                            (pathlib.Path(destination) / 'partial').write_bytes(b'partial MCP tree')
                            raise OSError('simulated MCP copy failure')
                    return real_copytree(source, destination, *args, **kwargs)

                with mock.patch.object(apply_build.shutil, 'copytree', side_effect=flaky):
                    with self.assertRaisesRegex(OSError, 'MCP copy failure'):
                        apply_build.main()
                if fresh:
                    self.assertFalse(self.mcp_target.exists())
                    for name in self.names:
                        self.assertEqual((self.target / name).read_bytes(), self.previous[name])
                    for rel, data in self.pack_previous.items():
                        self.assertEqual((self.pack_target / rel).read_bytes(), data)
                    for rel, data in self.legacy_previous.items():
                        self.assertEqual((self.legacy / rel).read_bytes(), data)
                    self.assertEqual(self.unowned.read_bytes(), b'preserved resource\n')
                else:
                    self.assert_previous_resources()
                self.assertEqual(self.cache.read_text(), self.cache_before)


    def test_failed_native_pack_copy_restores_previous_resources(self):
        real_copytree = apply_build.shutil.copytree
        copies = {'count': 0}

        def flaky(source, destination, *args, **kwargs):
            if pathlib.Path(destination) == self.pack_target:
                copies['count'] += 1
                if copies['count'] == 1:
                    pathlib.Path(destination).mkdir(parents=True)
                    (pathlib.Path(destination) / 'partial').write_bytes(b'partial pack')
                    raise OSError('simulated copy failure')
            return real_copytree(source, destination, *args, **kwargs)

        with mock.patch.object(apply_build.shutil, 'copytree', side_effect=flaky):
            with self.assertRaisesRegex(OSError, 'copy failure'):
                apply_build.main()
        self.assertEqual(copies['count'], 2)
        self.assertFalse((self.pack_target / 'partial').exists())
        self.assert_previous_resources()

    def test_first_install_copy_failure_removes_partial_native_pack(self):
        apply_build.shutil.rmtree(self.pack_target)
        apply_build.shutil.rmtree(self.legacy)
        real_copytree = apply_build.shutil.copytree

        def flaky(source, destination, *args, **kwargs):
            if pathlib.Path(destination) == self.pack_target:
                pathlib.Path(destination).mkdir(parents=True)
                (pathlib.Path(destination) / 'partial').write_bytes(b'partial pack')
                raise OSError('simulated first install failure')
            return real_copytree(source, destination, *args, **kwargs)

        with mock.patch.object(apply_build.shutil, 'copytree', side_effect=flaky):
            with self.assertRaisesRegex(OSError, 'first install failure'):
                apply_build.main()
        self.assertFalse(self.pack_target.exists())
        self.assertFalse(self.legacy.exists())
        for name in self.names:
            self.assertEqual((self.target / name).read_bytes(), self.previous[name])

    def test_failed_pack_snapshot_leaves_previous_resources_untouched(self):
        real_copytree = apply_build.shutil.copytree

        def flaky(source, destination, *args, **kwargs):
            if str(destination).endswith(SKILL_PACK_PART):
                pathlib.Path(destination).mkdir(parents=True)
                (pathlib.Path(destination) / 'partial').write_bytes(b'partial snapshot')
                raise OSError('simulated snapshot failure')
            return real_copytree(source, destination, *args, **kwargs)

        with mock.patch.object(apply_build.shutil, 'copytree', side_effect=flaky):
            with self.assertRaisesRegex(OSError, 'snapshot failure'):
                apply_build.main()
        self.assert_previous_resources()

    def test_failed_legacy_snapshot_leaves_previous_resources_untouched(self):
        real_copytree = apply_build.shutil.copytree

        def flaky(source, destination, *args, **kwargs):
            if str(destination).endswith(apply_build.LEGACY_SKILL_PLUGIN + '.part'):
                raise OSError('simulated legacy snapshot failure')
            return real_copytree(source, destination, *args, **kwargs)

        with mock.patch.object(apply_build.shutil, 'copytree', side_effect=flaky):
            with self.assertRaisesRegex(OSError, 'legacy snapshot failure'):
                apply_build.main()
        self.assert_previous_resources()

    def test_failed_legacy_retirement_restores_native_pack_and_legacy_plugin(self):
        real_rmtree = apply_build.shutil.rmtree
        failures = {'count': 0}

        def flaky(path, *args, **kwargs):
            if pathlib.Path(path) == self.legacy and not failures['count']:
                failures['count'] += 1
                real_rmtree(path, *args, **kwargs)
                raise OSError('simulated legacy retirement failure')
            return real_rmtree(path, *args, **kwargs)

        with mock.patch.object(apply_build.shutil, 'rmtree', side_effect=flaky):
            with self.assertRaisesRegex(OSError, 'legacy retirement failure'):
                apply_build.main()
        self.assert_previous_resources()

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


class SkillPackStagingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.source = self.root / 'src/skills'
        self.installed = self.root / 'installed/bundled-skills'
        self.output = self.root / 'staged'
        self.pack = self.output / apply_build.SKILL_PACK
        self.vendor = {'README.md': b'vendor README\n',
                       'skills/dynamic-workflows/SKILL.md': b'vendor workflow\n',
                       'skills/dynamic-workflows/examples.md': b'vendor examples\n',
                       'skills/dynamic-workflows/patterns.md': b'vendor patterns\n',
                       'skills/other-vendor/SKILL.md': b'unowned skill\n'}
        installed = {**self.vendor,
                     '.ccode-skills.json': b'{"skills": ["alpha", "removed", "dynamic-workflows"]}\n',
                     'skills/alpha/SKILL.md': b'old alpha\n',
                     'skills/alpha/obsolete.md': b'obsolete reference\n',
                     'skills/removed/SKILL.md': b'old owned skill\n'}
        for rel, data in installed.items():
            (self.installed / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.installed / rel).write_bytes(data)
        for rel, data in {'alpha/SKILL.md': b'canonical alpha\n', 'alpha/references.md': b'canonical reference\n',
                          'beta/SKILL.md': b'canonical beta\n'}.items():
            (self.source / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.source / rel).write_bytes(data)

    def test_stages_native_pack_and_prunes_only_previously_owned_skills(self):
        stale_plugin = self.output / apply_build.LEGACY_SKILL_PLUGIN
        stale_plugin.mkdir(parents=True)
        (stale_plugin / 'old-plugin').write_bytes(b'old staging')
        skills, files = build.stage_skill_pack(self.source, self.installed, self.output)
        self.assertEqual(skills, ['alpha', 'beta'])
        self.assertEqual(json.loads((self.pack / '.ccode-skills.json').read_text()), {'skills': skills})
        self.assertEqual((self.pack / 'skills/alpha/SKILL.md').read_bytes(), b'canonical alpha\n')
        self.assertEqual((self.pack / 'skills/alpha/references.md').read_bytes(), b'canonical reference\n')
        self.assertFalse((self.pack / 'skills/alpha/obsolete.md').exists())
        self.assertFalse((self.pack / 'skills/removed').exists())
        self.assertTrue((self.installed / 'skills/removed/SKILL.md').exists(), 'build never modifies installed resources')
        for rel, data in self.vendor.items():
            self.assertEqual((self.pack / rel).read_bytes(), data)
        self.assertFalse(stale_plugin.exists())
        self.assertFalse((self.pack / '.zcode-plugin').exists())
        self.assertEqual(files, sorted(str(path.relative_to(self.output)) for path in self.pack.rglob('*') if path.is_file()))

    def test_missing_ownership_marker_preserves_all_noncanonical_skills(self):
        (self.installed / '.ccode-skills.json').unlink()
        build.stage_skill_pack(self.source, self.installed, self.output)
        self.assertEqual((self.pack / 'skills/removed/SKILL.md').read_bytes(), b'old owned skill\n')

    def test_missing_vendor_seed_refuses_staging(self):
        for seed in build.VENDOR_SKILL_SEEDS:
            with self.subTest(seed=seed):
                previous = (self.installed / seed).read_bytes()
                (self.installed / seed).unlink()
                with self.assertRaisesRegex(ValueError, 'seed is missing'):
                    build.stage_skill_pack(self.source, self.installed, self.output)
                self.assertFalse(self.pack.exists())
                (self.installed / seed).write_bytes(previous)

    def test_invalid_ownership_marker_cannot_prune_outside_pack(self):
        (self.installed / '.ccode-skills.json').write_text('{"skills": ["../../outside"]}')
        with self.assertRaisesRegex(ValueError, 'Invalid bundled skill ownership marker'):
            build.stage_skill_pack(self.source, self.installed, self.output)
        self.assertFalse(self.pack.exists())

    def test_canonical_pack_contains_all_32_skills_and_reference_payloads(self):
        source = ROOT / 'src/skills'
        skills, files = build.stage_skill_pack(source, self.installed, self.output)
        expected = sorted(path.name for path in source.iterdir() if (path / 'SKILL.md').is_file())
        self.assertEqual(len(skills), 32)
        self.assertEqual(skills, expected)
        for name in skills:
            for path in (source / name).rglob('*'):
                if path.is_file():
                    relative = path.relative_to(source)
                    self.assertEqual((self.pack / 'skills' / relative).read_bytes(), path.read_bytes())
                    self.assertIn(str((self.pack / 'skills' / relative).relative_to(self.output)), files)
        for rel, data in self.vendor.items():
            self.assertEqual((self.pack / rel).read_bytes(), data)


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
