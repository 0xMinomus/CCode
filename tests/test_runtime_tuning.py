import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from local_only import runtime_tuning

SOURCE = '\n'.join((runtime_tuning.CHIP_LABEL[0], runtime_tuning.CHIP_FIXED[0]))


class FakeArchive:
    def __init__(self, entries):
        self.entries = entries

    def read(self, name):
        return self.entries[name]


class ReasoningChipTests(unittest.TestCase):
    def test_fixed_level_renders_icon_only_and_dimmed(self):
        patched = runtime_tuning.patch_renderer(SOURCE)
        # The label span is now guarded, and only under the upstream "single
        # fixed option" flag; the clickable branches keep their label.
        self.assertIn('M?null:' + runtime_tuning.CHIP_LABEL[0], patched)
        self.assertNotIn(runtime_tuning.CHIP_FIXED[0], patched)
        self.assertIn('children:(0,$.jsx)(VH,{label:N})})', patched)
        # Dimmed colour on the non-clickable chip; tooltip and aria stay.
        self.assertIn('text-foreground-subtle`,v,f),"aria-label":N,"data-thought-level-fixed":`true`', patched)
        self.assertNotIn('text-foreground`,v,f),"aria-label":N,"data-thought-level-fixed"', patched)

    def test_missing_anchor_fails_loudly(self):
        with self.assertRaises(ValueError):
            runtime_tuning.patch_renderer(SOURCE.replace(runtime_tuning.CHIP_FIXED[0], ''))
        with self.assertRaises(ValueError):
            runtime_tuning.patch_renderer(SOURCE.replace(runtime_tuning.CHIP_LABEL[0], ''))

    def test_archive_patch_applies_selection_and_chip_together(self):
        renderer = runtime_tuning.RENDERER_SELECTION[0] + '\n' + SOURCE
        archive = FakeArchive({'renderer': renderer.encode(), 'host': runtime_tuning.HOST_SELECTION[0].encode()})
        replacements = {}
        runtime_tuning.patch_archive(archive, replacements, 'host', 'renderer')
        patched_host = replacements['host'].decode()
        patched_renderer = replacements['renderer'].decode()
        self.assertIn('ccodePreferredReasoningLevel(', patched_host)
        self.assertIn('ccodePreferredReasoningLevel((e.providers.find', patched_renderer)
        self.assertIn('M?null:(0,$.jsx)(`span`,{ref:y,', patched_renderer)
        self.assertIn('text-foreground-subtle`,v,f)', patched_renderer)
        # The helper is appended exactly once per asset.
        self.assertEqual(patched_host.count('function ccodePreferredReasoningLevel('), 1)
        self.assertEqual(patched_renderer.count('function ccodePreferredReasoningLevel('), 1)

    def test_agent_patch_keeps_the_stop_rule(self):
        agent = runtime_tuning.AGENT_EFFORT[0] + '\n' + runtime_tuning.HARNESS_HEAD
        patched = runtime_tuning.patch_agent(agent)
        self.assertIn('defaultLevel:s.values.includes("low")?"low":s.values.at(-1)}', patched)
        self.assertIn('Answer what was asked, then stop.', patched)


if __name__ == '__main__':
    unittest.main()
