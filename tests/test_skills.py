"""Integrity of the bundled default skills that ship inside the app resources."""
import pathlib
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


class BundledPluginTests(unittest.TestCase):
    """The default skills reach the UI as a bundled plugin, not as a bare skill pack."""

    def test_the_agent_anchor_is_still_unique(self):
        baseline = ROOT / 'baselines/zcode-3.14.5-original-agent.cjs'
        text = baseline.read_text(errors='replace')
        self.assertEqual(text.count(skills_plugin.ANCHOR), 1,
                         'the bundled-plugin list anchor moved; re-pin it before changing skills_plugin.py')

    def test_the_patch_prepends_one_definition(self):
        baseline = ROOT / 'baselines/zcode-3.14.5-original-agent.cjs'
        patched = skills_plugin.patch_agent(baseline.read_text(errors='replace'))
        self.assertEqual(patched.count(f'name:"{skills_plugin.PLUGIN_NAME}"'), 1)
        self.assertIn(f'packages/{skills_plugin.PLUGIN_DIR}', patched)
        self.assertIn('skills/antislop/SKILL.md', patched)

    def test_the_manifest_points_at_the_skill_payload(self):
        manifest = skills_plugin.plugin_manifest()
        self.assertEqual(manifest['name'], skills_plugin.PLUGIN_NAME)
        self.assertEqual(manifest['skills'], 'skills')
        self.assertTrue(manifest['description'])
        for name in skills_plugin.SEED_SKILLS:
            self.assertTrue((BUNDLE / name / 'SKILL.md').is_file(), name)


if __name__ == '__main__':
    unittest.main()
