"""Integrity of the bundled default skills that ship inside the app resources."""
import pathlib
import json
import os
import shutil
import subprocess
import tempfile
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from local_only import skills_plugin

BUNDLE = ROOT / 'src/skills'
UI = ['design-taste-frontend', 'emil-design-eng', 'impeccable', 'prototype', 'full-output-enforcement']
GSAP = ['gsap-core', 'gsap-frameworks', 'gsap-performance', 'gsap-plugins', 'gsap-react',
        'gsap-scrolltrigger', 'gsap-timeline', 'gsap-utils']
ANTISLOP = ['antislop', 'antislop-code', 'antislop-copywriting', 'antislop-human']
WORKFLOW = ['code-review', 'diagnosing-bugs', 'investigate-first', 'lean-build', 'migration', 'safe-refactor',
            'surgical-patch', 'tdd', 'verify-and-stop', 'resolving-merge-conflicts', 'pr', 'research', 'wizard',
            'find-skills', 'handoff']
SELECTED = sorted(UI + GSAP + ANTISLOP + WORKFLOW)
# Keys the app's skill loader accepts in SKILL.md frontmatter; anything else is a
# `skill_invalid_frontmatter` warning at load time.
APP_FRONTMATTER_KEYS = {'name', 'description', 'when_to_use', 'license', 'metadata'}
JUNK = re.compile(r'^(\.DS_Store|Thumbs\.db|\.git|node_modules|__pycache__)$|\.pyc$')


def frontmatter(text):
    """Return the SKILL.md frontmatter block, or None when it is malformed."""
    if not text.startswith('---'):
        return None
    body = text.split('\n', 1)[1]
    end = body.find('\n---')
    return body[:end] if end >= 0 else None


class BundledSkillBundleTests(unittest.TestCase):
    def test_the_bundle_holds_exactly_the_selected_skills(self):
        names = sorted(path.name for path in BUNDLE.iterdir() if path.is_dir())
        self.assertEqual(names, SELECTED)
        self.assertEqual(len(names), 32)
        self.assertNotIn('antislop-ui', names, 'the ignored antislop skills stay out of the bundle')
        self.assertNotIn('antislop-layoutmobile', names)

    def test_every_skill_has_app_compatible_frontmatter(self):
        for name in SELECTED:
            with self.subTest(skill=name):
                text = (BUNDLE / name / 'SKILL.md').read_text()
                block = frontmatter(text)
                self.assertIsNotNone(block, 'missing frontmatter')
                self.assertRegex(block, rf'(?m)^name:\s*{re.escape(name)}\s*$',
                                 'the frontmatter name must match the directory name')
                self.assertRegex(block, r'(?m)^description:\s*(?:\S|[>|])')
                keys = {line.split(':', 1)[0].strip() for line in block.splitlines()
                        if line and not line[0].isspace() and ':' in line and not line.startswith('-')}
                self.assertLessEqual(keys, APP_FRONTMATTER_KEYS, f'unexpected frontmatter keys: {sorted(keys)}')

    @unittest.skipIf(os.name != 'posix', 'POSIX file modes are not meaningful on Windows')
    def test_scripts_that_the_skills_execute_keep_their_executable_bit(self):
        script = BUNDLE / 'impeccable/scripts/impeccable'
        self.assertTrue(script.is_file())
        self.assertTrue(script.stat().st_mode & 0o111, 'the bundled CLI must stay executable')

    def test_no_editor_or_build_junk_is_committed(self):
        junk = [str(path.relative_to(BUNDLE)) for path in BUNDLE.rglob('*') if JUNK.search(path.name)]
        self.assertEqual(junk, [])

    def test_large_payloads_stay_out_of_the_bundle(self):
        biggest = max((path.stat().st_size, str(path.relative_to(BUNDLE))) for path in BUNDLE.rglob('*') if path.is_file())
        self.assertLess(biggest[0], 2_000_000, f'unexpected large bundled file: {biggest}')


class NativeSkillVisibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(ROOT / 'scripts'))
        from asar import Archive
        baseline = ROOT / 'baselines/ccode-3.14.5-original.asar'
        agent = ROOT / 'baselines/ccode-3.14.5-original-agent.cjs'
        if not baseline.is_file() or not agent.is_file():
            raise unittest.SkipTest('pinned upstream artifacts are unavailable')
        cls.archive = Archive(baseline)
        cls.agent = skills_plugin.patch_agent(agent.read_text())
        cls.host = skills_plugin.patch_host(cls.archive.read('out/host/index.js').decode())
        cls.renderer = skills_plugin.patch_renderer(
            cls.archive.read('out/renderer/assets/styles-C4MhEMbW.js').decode())

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.home = self.root / 'home'
        self.home.mkdir()
        self.resources = self.root / 'resources'
        self.pack = self.resources / 'glm/packages/bundled-skills/skills'
        shutil.copytree(BUNDLE, self.pack)
        self.workspace = self.root / 'workspace'
        self.workspace.mkdir()

    def run_js(self, source, *, esm=False):
        node = shutil.which('node')
        if not node:
            self.skipTest('Node.js is unavailable')
        script = self.resources / 'app.asar/out/host' / ('check.mjs' if esm else 'check.cjs')
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text(source)
        result = subprocess.run(
            [node, str(script)], env={**os.environ, 'HOME': str(self.home)},
            text=True, capture_output=True, check=True, timeout=30)
        return json.loads(result.stdout)

    @staticmethod
    def function(text, name, next_name):
        start = text.index('function ' + name + '(')
        if text[start - 6:start] == 'async ':
            start -= 6
        return text[start:text.index('function ' + next_name + '(', start)]

    def write_skill(self, directory, name):
        directory.mkdir(parents=True, exist_ok=True)
        (directory / 'SKILL.md').write_text(
            f'---\nname: {name}\ndescription: fixture skill\n---\nKeep user content.\n')

    def host_listing(self):
        # Run the pinned filesystem scanner and Skills service, including YAML
        # parsing, against real temporary roots rather than fabricated rows.
        prefix = 'node_modules/yaml/'
        for name, _ in self.archive.entries():
            if name.startswith(prefix):
                target = self.resources / 'app.asar' / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(self.archive.read(name))
        start = self.host.index('import{access as kge,appendFile as Pge,')
        end = self.host.index('i(tR,"createSkillsService");', start) + len('i(tR,"createSkillsService");')
        module = self.host[start:end]
        bootstrap = ('const i=(value)=>value,y=()=>{},Hs="SKILL.md",ul=10,'
                     'pc=name=>!name.startsWith("."),uc=new Set();\n')
        return self.run_js(
            'import {fileURLToPath as j2e} from "node:url";\n' + bootstrap + module +
            '\nconsole.log(JSON.stringify(await tR({isDesktopRuntime:true}).list('
            + json.dumps({'workspacePath': str(self.workspace), 'provider': 'glm'}) + ')));', esm=True)

    def test_actual_skills_service_lists_native_defaults_and_keeps_user_skills(self):
        self.write_skill(self.home / '.ccode/skills/my-user-skill', 'my-user-skill')
        self.write_skill(self.workspace / '.ccode/skills/my-project-skill', 'my-project-skill')
        legacy = self.home / '.ccode/cli/plugins/cache/ccode-plugins-official/ccode-skills/1.0.0'
        self.write_skill(legacy / 'skills/antislop', 'antislop')
        (legacy / '.ccode-plugin').mkdir()
        manifest = legacy / '.ccode-plugin/plugin.json'
        manifest.write_text(json.dumps({'name': 'ccode-skills', 'skills': 'skills'}))
        custom = self.root / 'user-plugin'
        self.write_skill(custom / 'skills/custom-workflow', 'custom-workflow')
        (custom / '.ccode-plugin').mkdir()
        (custom / '.ccode-plugin/plugin.json').write_text(
            json.dumps({'name': 'ccode-skills', 'skills': 'skills'}))
        config = self.home / '.ccode/cli/config.json'
        config.write_text(json.dumps({'plugins': {
            'dirs': [str(custom)],
            'enabledPlugins': {'ccode-skills@ccode-plugins-official': True}}}))
        original_config, original_manifest = config.read_bytes(), manifest.read_bytes()
        result = self.host_listing()
        defaults = [skill for skill in result['skills'] if skill.get('source') == 'bundled']
        self.assertEqual(sorted(skill['name'] for skill in defaults), SELECTED)
        self.assertTrue(all(skill['readOnly'] and skill['scope'] == 'user' for skill in defaults))
        self.assertEqual(len(result['skills']), 35)
        self.assertEqual({skill['name'] for skill in result['skills']} - set(SELECTED),
                         {'my-user-skill', 'my-project-skill', 'custom-workflow'})
        self.assertEqual(next(skill for skill in result['skills'] if skill['name'] == 'custom-workflow')['pluginId'],
                         'ccode-skills@inline')
        self.assertFalse(any(skill.get('pluginId') == 'ccode-skills@ccode-plugins-official'
                             for skill in result['skills']))
        self.assertEqual(config.read_bytes(), original_config)
        self.assertEqual(manifest.read_bytes(), original_manifest)
        self.assertTrue((legacy / 'skills/antislop/SKILL.md').is_file())

    def test_renderer_routes_all_native_rows_to_default_not_installed_or_plugin(self):
        self.write_skill(self.home / '.ccode/skills/my-user-skill', 'my-user-skill')
        rows = self.host_listing()['skills']
        source = 'const X7=s=>s.trim().toLowerCase();\n'
        for name, following in [('fEn', 'pEn'), ('I0', 'R4t'), ('R4t', 'z4t')]:
            source += self.function(self.renderer, name, following) + '\n'
        source += ('const rows=' + json.dumps(rows) +
                   ';const visible=fEn(rows,[],"user");'
                   'console.log(JSON.stringify({groups:R4t(visible,""),'
                   'search:R4t(visible,"GSAP"),workspace:fEn(rows,[],"workspace")}));')
        result = self.run_js(source)
        self.assertEqual(sorted(skill['name'] for skill in result['groups']['builtIn']), SELECTED)
        self.assertEqual([skill['name'] for skill in result['groups']['local']], ['my-user-skill'])
        self.assertEqual(result['groups']['plugin'], [])
        self.assertTrue(result['search']['builtIn'])
        self.assertEqual(result['workspace'], [])

    def test_agent_reference_catalog_includes_native_system_skills(self):
        catalog = {'skills': [
            {'name': name, 'path': '/resources/glm/packages/bundled-skills/skills/' + name + '/SKILL.md',
             'description': 'bundled default', 'scope': 'system', 'source': 'bundled'}
            for name in SELECTED] + [
            {'name': 'my-user-skill', 'path': '/home/user/.ccode/skills/my-user-skill/SKILL.md',
             'description': 'user skill', 'scope': 'user', 'source': 'ccode'}]}
        source = self.function(self.agent, 'LZo', 'YXa')
        start = self.agent.index('function YXa(')
        source += self.agent[start:self.agent.index('var jZo=', start)]
        source += '\nconsole.log(JSON.stringify(LZo("workspace",' + json.dumps(catalog) + ')));'
        result = self.run_js(source)
        self.assertEqual(len(result['skills']), 33)
        self.assertEqual(sorted(skill['name'] for skill in result['skills'] if skill['name'] in SELECTED),
                         SELECTED)
        self.assertTrue(all(skill['scope'] == 'user' for skill in result['skills']))
        self.assertTrue(all(set(skill) == {'id', 'name', 'description', 'path', 'scope', 'enabled'}
                            for skill in result['skills']))

    def test_agent_discovers_native_pack_without_loading_legacy_plugin(self):
        electron = ROOT / 'app/ccode'
        if not electron.is_file():
            self.skipTest('packaged Electron runtime is unavailable')
        agent = self.resources / 'glm/ccode.cjs'
        agent.write_text(self.agent)
        self.write_skill(self.pack / 'dynamic-workflows', 'dynamic-workflows')
        for name in ('patterns.md', 'examples.md'):
            (self.pack / 'dynamic-workflows' / name).write_text('Vendor workflow seed.\n')
        self.write_skill(self.home / '.ccode/skills/my-user-skill', 'my-user-skill')
        legacy = self.home / '.ccode/cli/plugins/cache/ccode-plugins-official/ccode-skills/1.0.0'
        self.write_skill(legacy / 'skills/antislop', 'antislop')
        (legacy / '.ccode-plugin').mkdir()
        (legacy / '.ccode-plugin/plugin.json').write_text(json.dumps(
            {'name': 'ccode-skills', 'version': '1.0.0', 'skills': 'skills'}))
        config = self.home / '.ccode/cli/config.json'
        config.write_text(json.dumps({'plugins': {
            'enabledPlugins': {'ccode-skills@ccode-plugins-official': True}}}))
        before = config.read_bytes()
        env = {**os.environ, 'HOME': str(self.home), 'ELECTRON_RUN_AS_NODE': '1',
               'CCODE_STORAGE_DIR': str(self.home / '.ccode'),
               'STORAGE_DIR': str(self.home / '.ccode')}
        result = subprocess.run(
            [str(electron), str(agent), 'skills', 'list', '--json'],
            cwd=self.workspace, env=env, capture_output=True, text=True, check=True, timeout=30)
        catalog = json.loads(result.stdout)
        self.assertEqual(sorted(skill['name'] for skill in catalog['skills']
                                if skill['name'] in SELECTED), SELECTED)
        self.assertTrue(all(skill['source'] == 'bundled' and skill['scope'] == 'system'
                            for skill in catalog['skills'] if skill['name'] in SELECTED))
        self.assertFalse(any(skill.get('pluginName') == 'ccode-skills' for skill in catalog['skills']))
        self.assertIn('my-user-skill', {skill['name'] for skill in catalog['skills']})
        plugins = subprocess.run(
            [str(electron), str(agent), 'plugins', 'list'],
            cwd=self.workspace, env=env, capture_output=True, text=True, check=True, timeout=30)
        self.assertNotIn('ccode-skills@ccode-plugins-official', plugins.stdout)
        self.assertEqual(config.read_bytes(), before)
        self.assertTrue((legacy / 'skills/antislop/SKILL.md').is_file())

    def test_patch_rejects_drifted_or_repeated_pinned_anchors(self):
        for patch, text, anchor in [
            (skills_plugin.patch_agent, self.agent, skills_plugin.AGENT_DISCOVERY_ANCHOR),
            (skills_plugin.patch_host, self.host, skills_plugin.HOST_ROOTS_ANCHOR),
            (skills_plugin.patch_renderer, self.renderer, skills_plugin.RENDERER_GROUP_ANCHOR),
        ]:
            with self.subTest(patch=patch.__name__), self.assertRaises(ValueError):
                patch(text)
            with self.subTest(patch=patch.__name__, repeated=True), self.assertRaises(ValueError):
                patch(anchor + anchor)


if __name__ == '__main__':
    unittest.main()
