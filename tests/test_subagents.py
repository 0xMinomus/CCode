import json
import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'scripts'))

from asar import Archive
from local_only import rebrand, subagents


BASELINE = ROOT / 'baselines' / 'upstream-3.14.5-original.asar'
AGENT_BASELINE = ROOT / 'baselines' / 'upstream-3.14.5-original-agent.cjs'
RENDERER_ASSET = 'out/renderer/assets/styles-C4MhEMbW.js'
HOST_ASSET = 'out/host/index.js'


def _region(text, start, end):
    start_at = text.find(start)
    end_at = text.find(end, start_at + len(start))
    if start_at < 0 or end_at < 0:
        raise AssertionError(f'Missing test extraction boundary: {start} → {end}')
    return text[start_at:end_at]


def _run_node(script):
    result = subprocess.run(['node', '-e', script], cwd=ROOT, capture_output=True, text=True)
    if result.returncode:
        raise AssertionError(result.stderr or result.stdout)


class BuiltInSubagentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not BASELINE.is_file() or not AGENT_BASELINE.is_file():
            raise unittest.SkipTest('pinned subagent baselines are not present')
        archive = Archive(BASELINE)
        cls.host = subagents.patch_host(rebrand.apply(archive.read(HOST_ASSET).decode()))
        cls.renderer = subagents.patch_renderer(rebrand.apply(archive.read(RENDERER_ASSET).decode()))
        cls.agent = subagents.patch_agent(rebrand.apply(AGENT_BASELINE.read_text()))

    def test_catalog_defaults_inherit_and_disable_individual_profiles(self):
        host_catalog = _region(self.host, 'function tve(e={}){', 'i(tve,"createBuiltInAgents")')
        enabled_state = _region(self.host, 'function mq(e,t){', 'i(mq,"attachEnabledState")')
        expected = json.dumps(list(subagents.NAMES))
        script = f"""
const assert = require('node:assert/strict');
const cl = ({{name, scope, source}}) => `${{source}}:${{scope}}:${{name.trim().toLowerCase()}}`;
{host_catalog}
{enabled_state}
const expected = {expected};
const profiles = tve();
assert.deepEqual(profiles.map(profile => profile.name), expected);
assert.equal(new Set(profiles.map(profile => profile.id)).size, expected.length);
assert.ok(profiles.every(profile => profile.enabled === true && profile.readOnly === true));
assert.ok(profiles.every(profile => profile.modelSelection === undefined));
assert.ok(profiles.every(profile => profile.modelSelectionOverride === undefined));
assert.ok(profiles.every(profile => ['red', 'orange', 'yellow', 'green', 'cyan', 'blue', 'purple', 'pink'].includes(profile.color)));
assert.ok(profiles.slice(2).every(profile => profile.systemPrompt.length > 0));
const selection = {{providerId: 'local', modelId: 'test-model'}};
assert.equal(tve({{'Backend Developer': selection}}).find(profile => profile.name === 'Backend Developer').modelSelection, selection);
const disabled = mq(profiles, {{disabledAgentIds: [profiles[3].id]}});
assert.equal(disabled.find(profile => profile.name === 'Backend Developer').enabled, false);
assert.ok(disabled.filter(profile => profile.name !== 'Backend Developer').every(profile => profile.enabled === true));
const mixed = mq([
  {{id: 'user-id', scope: 'user', source: 'user'}},
  {{id: 'plugin-id', scope: 'user', source: 'plugin'}},
  {{id: 'workspace-id', scope: 'workspace', source: 'user'}}
], {{disabledAgentIds: ['user-id', 'plugin-id', 'workspace-id']}});
assert.equal(mixed[0].enabled, false);
assert.equal(mixed[1].enabled, false);
assert.equal(mixed[2].enabled, true);
"""
        _run_node(script)

    def test_settings_rows_offer_toggles_for_builtins_and_user_plugin_agents(self):
        helpers = _region(self.renderer, 'function O7(e){', 'function cTn(e)')
        names = json.dumps(list(subagents.NAMES))
        script = f"""
const assert = require('node:assert/strict');
{helpers}
const names = {names};
for (const name of names) {{
  const agent = {{name, scope: 'built-in', source: 'built-in'}};
  assert.equal(iTn(agent), true, `${{name}} needs an enabled-state toggle`);
  assert.equal(sTn(agent), name, `${{name}} needs the built-in model-inherit control`);
}}
assert.equal(iTn({{name: 'custom', scope: 'user', source: 'user'}}), true);
const visualJudge = {{name: 'documents:visual-judge', pluginName: 'documents', scope: 'user', source: 'plugin', readOnly: true}};
assert.equal(iTn(visualJudge), true);
assert.equal(iTn({{...visualJudge, name: 'pdf:visual-judge', pluginName: 'pdf'}}), true);
assert.equal(iTn({{name: 'plugin:reviewer', scope: 'user', source: 'plugin'}}), true);
assert.equal(iTn({{...visualJudge, scope: 'workspace'}}), false);
assert.equal(iTn({{name: 'workspace', scope: 'workspace', source: 'user'}}), false);
"""
        _run_node(script)

    def test_plugin_agent_toggle_disables_unique_bare_name_alias(self):
        plugin_discovery = _region(self.host, 'async function sve(e){', 'i(sve,"discoverPluginAgents")')
        enabled_state = _region(self.host, 'function mq(e,t){', 'i(mq,"attachEnabledState")')
        script = f"""(async () => {{
const assert = require('node:assert/strict');
const To = (...parts) => parts.join('/');
const UR = () => 'desktop';
const Lw = async () => '/home/test';
const ave = async () => ({{}});
let plugins = [];
const cve = async () => plugins;
const uve = async installPath => [installPath + '/agents/visual-judge.md'];
const _d = async path => path;
const Ow = ({{content, path, scope}}) => ({{agent: {{name: 'visual-judge', scope, path, tools: ['Read', 'Bash'], systemPrompt: 'visual review'}}}});
const fve = profile => profile;
const DS = (id, name) => id + ':' + name;
const Sq = new Set();
{plugin_discovery}
{enabled_state}
const makePlugin = name => ({{id: name + '@ccode-plugins-official', name, installPath: '/plugins/' + name, scope: 'user'}});
const load = () => sve({{storageOptions: {{}}, diagnostics: [], reservedNames: [], state: {{}}}});
plugins = ['documents', 'pdf', 'presentations', 'spreadsheets'].map(makePlugin);
const four = await load();
assert.deepEqual(four.profiles.map(profile => profile.name), [
  'documents:visual-judge',
  'pdf:visual-judge',
  'presentations:visual-judge',
  'spreadsheets:visual-judge'
]);
const pdf = four.profiles.find(profile => profile.pluginName === 'pdf');
const fourEnabled = mq(four.runtimeAgents, {{disabledAgentIds: [pdf.id]}});
assert.equal(fourEnabled.find(profile => profile.id === pdf.id).enabled, false);
assert.equal(fourEnabled.filter(profile => profile.id !== pdf.id).every(profile => profile.enabled), true);
plugins = [makePlugin('documents')];
const single = await load();
const canonical = single.profiles[0];
const alias = single.runtimeAgents.find(profile => profile.name === 'visual-judge');
assert.ok(alias);
assert.equal(alias.canonicalAgentId, canonical.id);
assert.equal(mq(single.runtimeAgents, {{disabledAgentIds: [canonical.id]}}).find(profile => profile.name === 'visual-judge').enabled, false);
}})().catch(error => {{ console.error(error); process.exitCode = 1; }});
"""
        _run_node(script)


    def test_disabled_profiles_are_hidden_and_cannot_dispatch(self):
        profile_block = _region(self.agent, 'function fpa(e={})', 'function bho(e,t={})')
        prompt_builder = _region(self.agent, 'function bho(e,t={})', 'function qvn(e){')
        resolver = (
            _region(self.agent, 'function gwn(e,t){', 'function zya(e,t){') +
            _region(self.agent, 'function zya(e,t){', 'function gSo(e){') +
            _region(self.agent, 'function gSo(e){', 'function $ya(e){')
        )
        name = 'Backend Developer'
        disabled_id = f'built-in:built-in:{name.lower()}'
        script = f"""
const assert = require('node:assert/strict');
const jht = 'Engineering Generalist';
const R$ = 'Codebase Explorer';
function Lvn() {{ return 'engineering prompt'; }}
const fr = {{ToolExecutionFailed: 'ToolExecutionFailed'}};
const Hz = {{UNKNOWN_AGENT_TYPE: 'UNKNOWN_AGENT_TYPE'}};
function Gr(_kind, message, options) {{ const error = new Error(message); error.context = options?.context; return error; }}
function iho() {{ return 'Bash, Read'; }}
function Soe(tools) {{ return tools.join(', '); }}
{profile_block}
{prompt_builder}
{resolver}
const disabledAgentIds = [{json.dumps(disabled_id)}];
const profiles = $vn([], {{disabledAgentIds}});
assert.equal(profiles.length, 11);
assert.equal(profiles.some(profile => profile.name === {json.dumps(name)}), false);
assert.equal(profiles.find(profile => profile.name === 'Engineering Generalist').systemPrompt, 'engineering prompt');
assert.equal(profiles.find(profile => profile.name === 'Codebase Explorer').systemPrompt, '');
assert.equal(vFe(profiles.find(profile => profile.name === 'Codebase Explorer')), true);
assert.equal(profiles.every(profile => profile.modelSelection === undefined), true);
const prompt = bho([], {{disabledAgentIds}});
assert.equal(prompt.includes({json.dumps(name)}), false);
assert.equal(prompt.includes('Frontend Developer'), true);
assert.throws(() => gwn(profiles, {{agentType: {json.dumps(name)}}}), /not found/);
assert.equal(gwn(profiles, {{agentType: 'Frontend Developer'}}).profile.name, 'Frontend Developer');
const override = {{providerId: 'local', modelId: 'explicit'}};
assert.equal($vn([], {{builtInModelSelectionOverrides: {{'Backend Developer': override}}}}).find(profile => profile.name === 'Backend Developer').modelSelection, override);
const visualJudgeId = 'plugin:documents:visual-judge';
const disabledVisualJudge = {{id: visualJudgeId, name: 'documents:visual-judge', source: 'plugin', scope: 'user', enabled: false, systemPrompt: 'visual review', tools: ['Read', 'Bash']}};
const hiddenPluginProfiles = $vn([disabledVisualJudge], {{}});
assert.equal(hiddenPluginProfiles.some(profile => profile.id === visualJudgeId), false);
assert.equal(bho([disabledVisualJudge], {{}}).includes('documents:visual-judge'), false);
assert.throws(() => gwn(hiddenPluginProfiles, {{agentType: 'documents:visual-judge'}}), /not found/);
const enabledVisualJudge = {{...disabledVisualJudge, enabled: true}};
const visiblePluginProfiles = $vn([enabledVisualJudge], {{}});
assert.equal(visiblePluginProfiles.some(profile => profile.id === visualJudgeId), true);
assert.equal(gwn(visiblePluginProfiles, {{agentType: 'documents:visual-judge'}}).profile.id, visualJudgeId);
"""
        _run_node(script)

    def test_legacy_model_overrides_follow_renamed_builtin_roles(self):
        host_normalizer = _region(self.host, 'function mve(e){', 'i(mve,"normalizeBuiltInSelectionOverrides")')
        agent_normalizer = _region(self.agent, 'function bHa(e){', 'function SHa(e,t){')
        script = f"""
const assert = require('node:assert/strict');
const wr = {{safeParse: value => ({{data: value}})}};
const Pu = {{safeParse: value => ({{success: value !== undefined, data: value}})}};
const Id = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const _Ha = Id;
{host_normalizer}
{agent_normalizer}
const oldGeneral = {{providerId: 'local', modelId: 'general'}};
const oldExplore = {{providerId: 'local', modelId: 'explore'}};
const migratedHost = mve({{'general-purpose': oldGeneral, Explore: oldExplore}});
assert.deepEqual(migratedHost, {{'Engineering Generalist': oldGeneral, 'Codebase Explorer': oldExplore}});
const migratedAgent = bHa({{'general-purpose': oldGeneral, Explore: oldExplore}});
assert.deepEqual(migratedAgent, {{'Engineering Generalist': oldGeneral, 'Codebase Explorer': oldExplore}});
"""
        _run_node(script)


if __name__ == '__main__':
    unittest.main()
