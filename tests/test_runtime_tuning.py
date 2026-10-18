import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from local_only import runtime_tuning

SOURCE = runtime_tuning.CHIP_HIDDEN[0] + ":r===`select`?null"


class FakeArchive:
    def __init__(self, entries):
        self.entries = entries

    def read(self, name):
        return self.entries[name]


class ReasoningChipTests(unittest.TestCase):
    def test_fixed_level_hides_the_chip(self):
        patched = runtime_tuning.patch_renderer(SOURCE)
        self.assertNotIn(runtime_tuning.CHIP_HIDDEN[0], patched)
        # The non-clickable branch collapses to null; the clickable ones follow
        # right after it in the same ternary.
        self.assertIn('return M?null:r===`select`?', patched)
        self.assertNotIn('data-thought-level-fixed', patched)

    def test_missing_anchor_fails_loudly(self):
        with self.assertRaises(ValueError):
            runtime_tuning.patch_renderer(SOURCE.replace(runtime_tuning.CHIP_HIDDEN[0], ''))
        with self.assertRaises(ValueError):
            runtime_tuning.patch_renderer('function nope(){}')

    def test_archive_patch_applies_selection_and_chip_together(self):
        renderer = runtime_tuning.RENDERER_SELECTION[0] + '\n' + SOURCE
        archive = FakeArchive({'renderer': renderer.encode(), 'host': runtime_tuning.HOST_SELECTION[0].encode()})
        replacements = {}
        runtime_tuning.patch_archive(archive, replacements, 'host', 'renderer')
        patched_host = replacements['host'].decode()
        patched_renderer = replacements['renderer'].decode()
        self.assertIn('ccodePreferredReasoningLevel(', patched_host)
        self.assertIn('ccodePreferredReasoningLevel((e.providers.find', patched_renderer)
        self.assertIn('return M?null:r===`select`?', patched_renderer)
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
