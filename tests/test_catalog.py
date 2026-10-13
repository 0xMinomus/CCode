import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from local_only import catalog  # noqa: E402

CATALOG = ROOT / 'app/resources/config/provider/zcode-builtin.json'


def fixture():
    return json.dumps({
        "schemaVersion": 1,
        "revision": 30,
        "config": {
            "providerConfigRules": {
                "templateRules": [
                    {"templateId": "zai-api", "templateNameMap": {"en-US": "Z.ai Coding Plan"},
                     "config": {"access": {"type": "zhipu-coding-plan-api-key"}, "api": {"type": "anthropic-messages", "baseUrl": "https://api.z.ai/api/anthropic"}, "builtinModelIds": ["GLM-5.3"]}},
                    {"templateId": "bigmodel-standard-api", "templateNameMap": {"en-US": "BigModel API"},
                     "config": {"access": {"type": "api-key"}, "api": {"type": "openai-chat-completions", "baseUrl": "https://open.bigmodel.cn/api/paas/v4"}, "builtinModelIds": ["GLM-5.3"]}},
                    {"templateId": "deepseek", "templateNameMap": {"en-US": "DeepSeek"},
                     "config": {"access": {"type": "api-key"}, "api": {"type": "anthropic-messages", "baseUrl": "https://api.deepseek.com/anthropic"}, "builtinModelIds": ["deepseek-v4-pro"]}},
                ],
                "providerRules": [
                    {"providerId": "account:zai-individual-coding-plan", "providerName": "Z.AI Individual Coding Plan",
                     "config": {"group": "zai-family", "access": {"type": "zhipu-account"}, "api": {"type": "anthropic-messages", "baseUrl": "https://api.z.ai/api/anthropic"}}},
                    {"providerId": "account:bigmodel-start-plan", "providerName": "Start Plan",
                     "config": {"group": "bigmodel-family", "access": {"type": "zhipu-account"}}},
                ],
            },
            "modelConfigRules": {
                "modelRules": [
                    {"modelMatch": ".*", "config": {"enabled": True}},
                    {"modelMatch": "glm-5.3", "config": {"properties": {"contextWindow": 200000}}},
                ],
                "providerSiteRules": [
                    {"providerId": "zai", "config": {"loginUrl": "https://z.ai/login"}},
                    {"providerId": "deepseek", "config": {"loginUrl": "https://platform.deepseek.com"}},
                ],
            },
        },
    }, ensure_ascii=False)


class CatalogPatchTests(unittest.TestCase):
    def test_zhipu_rules_disappear_and_ninerouter_is_added(self):
        patched = json.loads(catalog.patch_catalog(fixture()))
        rules = patched['config']['providerConfigRules']
        self.assertEqual([t['templateId'] for t in rules['templateRules']], ['deepseek', '9router'])
        self.assertEqual(rules['providerRules'], [])
        templates = {t['templateId']: t for t in rules['templateRules']}
        ninerouter = templates['9router']['config']
        self.assertEqual(ninerouter['api']['baseUrl'], 'http://127.0.0.1:20128/v1')
        self.assertEqual(ninerouter['builtinModelIds'], [], 'a fresh provider must start with an empty model list')
        self.assertEqual(ninerouter['access'], {'type': 'api-key'})

    def test_model_rules_for_zhipu_hosts_are_removed(self):
        patched = json.loads(catalog.patch_catalog(fixture()))
        model_rules = patched['config']['modelConfigRules']
        sites = [entry.get('providerId') for entry in model_rules['providerSiteRules']]
        self.assertEqual(sites, ['deepseek'])
        matches = [entry.get('modelMatch') for entry in model_rules['modelRules']]
        self.assertIn('.*', matches)
        self.assertNotIn('combo/coding-harian', matches, 'the template must not seed a model')

    def test_seeded_combo_rule_is_stripped_on_repatch(self):
        seeded = json.loads(catalog.patch_catalog(fixture()))
        seeded['config']['modelConfigRules']['modelRules'].append(
            {'modelMatch': catalog.NINEROUTER_SEEDED_MODEL, 'config': {'enabled': True}})
        cleaned = json.loads(catalog.patch_catalog(json.dumps(seeded)))
        matches = [entry.get('modelMatch') for entry in cleaned['config']['modelConfigRules']['modelRules']]
        self.assertNotIn(catalog.NINEROUTER_SEEDED_MODEL, matches)

    def test_orphan_template_model_rules_are_removed(self):
        patched = json.loads(catalog.patch_catalog(fixture()))
        # fixture has no templateModelRules; the installed catalog has 244, none may
        # stay for a removed Zhipu template.
        self.assertTrue(all(rule.get('templateId') not in catalog.ZHIPU_TEMPLATES
                            for rule in patched['config']['modelConfigRules'].get('templateModelRules', [])))

    def test_patch_is_idempotent(self):
        once = catalog.patch_catalog(fixture())
        twice = catalog.patch_catalog(once)
        self.assertEqual(once, twice)

    def test_unexpected_shape_fails_loudly(self):
        with self.assertRaises(ValueError):
            catalog.patch_catalog(json.dumps({"config": {"providerConfigRules": {}}}))


@unittest.skipUnless(CATALOG.exists(), 'installed provider catalog is not present')
class InstalledCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = json.loads(CATALOG.read_text())
        cls.after = json.loads(catalog.patch_catalog(CATALOG.read_text()))

    def test_installed_catalog_patch_is_idempotent(self):
        once = catalog.patch_catalog(CATALOG.read_text())
        self.assertEqual(catalog.patch_catalog(once), once)

    def test_patched_installed_catalog_has_no_zhipu_and_one_ninerouter(self):
        rules = self.after['config']['providerConfigRules']
        text = json.dumps(rules, ensure_ascii=False)
        for marker in ('zhipu-account', 'zhipu-coding-plan-api-key', 'account:zai', 'account:bigmodel', 'api.z.ai', 'open.bigmodel.cn'):
            self.assertNotIn(marker, text, marker)
        self.assertEqual(len([t for t in rules['templateRules'] if t['templateId'] == '9router']), 1)
        self.assertTrue([t for t in rules['templateRules'] if t['templateId'] == 'deepseek'], 'other providers stay')
        hosts = json.dumps(self.after['config']['modelConfigRules'], ensure_ascii=False)
        self.assertNotIn('api.z.ai', hosts)
        self.assertNotIn('zcode.z.ai', hosts)


if __name__ == '__main__':
    unittest.main()
