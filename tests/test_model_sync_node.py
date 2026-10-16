import contextlib
import http.server
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import threading
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CLI = ROOT / 'src/main/model-sync.cjs'
NODE = shutil.which('node')

# Shared node prelude: the port under test plus the gateway fixture the Python
# suite (tests/test_model_sync.py) uses, so both suites cover the same shapes.
PRELUDE = '''
const m=require(__MODULE__);
const assert=require('node:assert/strict');
function entry(id,caps){
  const extra=caps||{};
  const context=extra.contextWindow===undefined?1000000:extra.contextWindow;
  const output=extra.maxOutput===undefined?384000:extra.maxOutput;
  const capabilities={vision:false,pdf:false,tools:true,search:false,reasoning:false,
    thinkingEffortSupported:false,thinkingCanDisable:false,contextWindow:context,maxOutput:output};
  Object.assign(capabilities,extra);
  return {id,object:'model',owned_by:id.slice(0,id.indexOf('/')),context_length:context,
    max_completion_tokens:output,capabilities};
}
function fixture(){
  const models=[entry('combo/coding-harian',{reasoning:true,thinkingEffortSupported:true,thinkingCanDisable:true,vision:true})];
  for(let index=0;index<12;index+=1)models.push(entry(`cmc/model-${String(index).padStart(2,'0')}`,{reasoning:true,thinkingEffortSupported:true,thinkingCanDisable:false}));
  for(let index=0;index<3;index+=1)models.push(entry(`oc/free-${index}`));
  models.push(entry('groq/llama'));
  return models;
}
function family(){
  return {config:{providerConfigRules:{providerRules:[]},modelConfigRules:{manualProviderModelRules:[]}}};
}
'''


def script(body):
    return PRELUDE.replace('__MODULE__', json.dumps(str(CLI))) + body


def run_node(body, extra_env=None, timeout=120):
    if NODE is None:
        raise unittest.SkipTest('node is unavailable')
    env = dict(os.environ)
    env.update(extra_env or {})
    env.pop('CCODE_MODEL_SYNC_CONFIG', None)
    env.pop('CCODE_MODEL_SYNC_STATE', None)
    env.pop('CCODE_MODEL_SYNC_GATEWAY', None)
    result = subprocess.run([NODE, '-e', body], capture_output=True, text=True, env=env, timeout=timeout)
    if result.returncode != 0:
        raise AssertionError(f'node failed: {result.stderr.strip()}')
    # The port logs progress on stdout like the Python script; the test payload is
    # always the final line.
    lines = [line for line in result.stdout.strip().splitlines() if line.strip()]
    return json.loads(lines[-1])


def run_cli(args, env, timeout=120):
    if NODE is None:
        raise unittest.SkipTest('node is unavailable')
    return subprocess.run([NODE, str(CLI), *args], capture_output=True, text=True,
                          env={**os.environ, **env}, timeout=timeout)


def gateway_entry(model_id, context=1000000, output=384000, **caps):
    capabilities = {'vision': False, 'pdf': False, 'tools': True, 'search': False, 'reasoning': False,
                    'thinkingEffortSupported': False, 'thinkingCanDisable': False,
                    'contextWindow': context, 'maxOutput': output}
    capabilities.update(caps)
    return {'id': model_id, 'object': 'model', 'owned_by': model_id.split('/', 1)[0],
            'context_length': context, 'max_completion_tokens': output, 'capabilities': capabilities}


def gateway_fixture():
    models = [gateway_entry('combo/coding-harian', reasoning=True, thinkingEffortSupported=True,
                            thinkingCanDisable=True, vision=True)]
    models += [gateway_entry(f'cmc/model-{index:02d}', reasoning=True,
                             thinkingEffortSupported=True, thinkingCanDisable=False) for index in range(12)]
    models += [gateway_entry(f'oc/free-{index}') for index in range(3)]
    models += [gateway_entry('groq/llama')]
    return models


def family_config():
    return {'config': {'providerConfigRules': {'providerRules': []},
                       'modelConfigRules': {'manualProviderModelRules': []}}}


def family_provider(api_key='local-gateway', base_url=None, models=None):
    return {'providerId': '9router', 'providerName': '9Router', 'enabled': True,
            'config': {'group': 'standard-personal', 'access': {'type': 'api-key', 'apiKey': api_key},
                       'api': {'type': 'openai-chat-completions', 'baseUrl': base_url or 'http://127.0.0.1:20128/v1'},
                       'personalModelIds': list(models or []), 'modelOrder': list(models or [])}}


class GatewayServer(http.server.ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, models):
        self.models = models
        super().__init__(('127.0.0.1', 0), GatewayHandler)


class GatewayHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.split('?', 1)[0] != '/v1/models':
            self.send_error(404)
            return
        body = json.dumps({'data': self.server.models}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@contextlib.contextmanager
def gateway_stub(models):
    server = GatewayServer(models)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_address[1]}/v1'
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@contextlib.contextmanager
def standalone_root():
    with tempfile.TemporaryDirectory() as folder:
        root = pathlib.Path(folder)
        state = root / 'model-sync'
        state.mkdir(parents=True)
        config = root / 'data/.ccode/v2/provider_config.json'
        config.parent.mkdir(parents=True)
        # A fresh snapshot skips the catalog download, so no run touches the network.
        (state / 'catalog.json').write_text('{"opencode":{"models":{}}}')
        yield root, config, state


def sync_env(root, config, state, gateway):
    return {'CCODE_STANDALONE_ROOT': str(root), 'CCODE_MODEL_SYNC_CONFIG': str(config),
            'CCODE_MODEL_SYNC_STATE': str(state), 'CCODE_MODEL_SYNC_GATEWAY': gateway}


class EnrichTests(unittest.TestCase):
    def test_new_model_idempotence_and_manual_override(self):
        result = run_node(script('''
const catalog={opencode:{models:{'space-bunny-free':{reasoning:true,
  reasoning_options:[{type:'effort',values:['low','medium','high','xhigh','max']}],
  limit:{context:1048576},modalities:{input:['text','image']}}}}};
const base={config:{providerConfigRules:{providerRules:[{providerId:'vansrouter',
  config:{api:{type:'openai-chat-completions'},personalModelIds:['oc/space-bunny-free']}}]},
  modelConfigRules:{manualProviderModelRules:[]}}};
const [filled,state,changes]=m.enrich(base,catalog,{});
const rule=filled.config.modelConfigRules.manualProviderModelRules[0];
assert.equal(rule.config.properties.inputFormat.supportsImage,true);
assert.equal(rule.config.properties.contextWindow,1048576);
assert.equal(rule.config.properties.supportsMidConversationSystem,true);
assert.equal(rule.config.properties.supportsJsonSchemaOutput,false);
assert.deepStrictEqual(changes,['oc/space-bunny-free']);
assert.deepStrictEqual(rule.config.optionSpecs.reasoningLevel.values,['low','medium','high','xhigh','max']);
assert.equal(rule.config.optionSpecs.reasoningLevel.map,'{"reasoning_effort": reasoningLevel}');
const [again,nextState,changes2]=m.enrich(filled,catalog,state);
assert.deepStrictEqual(again,filled);
assert.deepStrictEqual(changes2,[]);
assert.deepStrictEqual(state.managed,nextState.managed);
const edited=JSON.parse(JSON.stringify(filled));
edited.config.modelConfigRules.manualProviderModelRules[0].config.optionSpecs.reasoningLevel=
  {values:['high'],map:'{"reasoning_effort":"high"}'};
const [kept,,changes3]=m.enrich(edited,catalog,state);
assert.deepStrictEqual(kept,edited);
assert.deepStrictEqual(changes3,[]);
const refreshedCatalog=JSON.parse(JSON.stringify(catalog));
refreshedCatalog.opencode.models['space-bunny-free'].reasoning_options[0].values=['low','high'];
const [refreshed,,changes4]=m.enrich(filled,refreshedCatalog,state);
assert.deepStrictEqual(changes4,['oc/space-bunny-free']);
assert.deepStrictEqual(refreshed.config.modelConfigRules.manualProviderModelRules[0]
  .config.optionSpecs.reasoningLevel.values,['low','high']);
const unknown=JSON.parse(JSON.stringify(base));
unknown.config.providerConfigRules.providerRules[0].config.personalModelIds=['oc/unknown','combo/new'];
const [untouched,,changes5]=m.enrich(unknown,catalog,{});
assert.deepStrictEqual(untouched,unknown);
assert.deepStrictEqual(changes5,[]);
console.log(JSON.stringify({values:rule.config.optionSpecs.reasoningLevel.values,refresh:changes4}));
'''))
        self.assertEqual(result['values'], ['low', 'medium', 'high', 'xhigh', 'max'])
        self.assertEqual(result['refresh'], ['oc/space-bunny-free'])

    def test_reasoning_spec_mapping_table(self):
        result = run_node(script('''
const effort=m.reasoningSpec({reasoning_options:[{type:'effort',values:['low','low','max']}]},'oc/x');
assert.deepStrictEqual(effort.values,['low','max']);
assert.equal(effort.map,'{"reasoning_effort": reasoningLevel}');
assert.equal(m.reasoningSpec({reasoning_options:[{type:'effort',values:['low','']}]},'oc/x'),null);
assert.equal(m.reasoningSpec({reasoning_options:[{type:'effort',values:[]}]},'oc/x'),null);
assert.equal(m.reasoningSpec({reasoning_options:[{type:'toggle'}]},'oc/mystery'),null);
const glm=m.reasoningSpec({reasoning_options:[{type:'toggle'}],family:'glm'},'oc/model');
assert.deepStrictEqual(glm.values,['disabled','enabled']);
assert.equal(glm.map,'{"thinking": {"type": reasoningLevel == "disabled" ? "disabled" : "enabled"}}');
assert.equal(m.reasoningSpec({reasoning_options:[{type:'toggle'}]},'oc/qwen3').map,'{"enable_thinking": reasoningLevel == "enabled"}');
assert.equal(m.reasoningSpec({reasoning_options:[{type:'toggle'}]},'oc/ling-2').map,'{"reasoning": {"enabled": reasoningLevel == "enabled"}}');
assert.deepStrictEqual(m.reasoningSpec({reasoning:true,reasoning_options:[]},'oc/x'),{values:['enabled'],map:'{}'});
assert.deepStrictEqual(m.reasoningSpec({reasoning:false,reasoning_options:[]},'oc/x'),{values:['disabled'],map:'{}'});
assert.equal(m.reasoningSpec({},'oc/x'),null);
assert.equal(m.placeholder(undefined),true);
assert.equal(m.placeholder({values:['disabled','enabled'],map:'{}'}),true);
assert.equal(m.placeholder({values:['disabled','enabled'],map:' {"thinking":1} '}),false);
console.log(JSON.stringify({glm:glm.map,effort:effort.values}));
'''))
        self.assertEqual(result['effort'], ['low', 'max'])
        self.assertIn('"thinking"', result['glm'])

    def test_metadata_skips_combos_and_fixed_suffixes(self):
        result = run_node(script('''
const catalog={opencode:{models:{'space-bunny-free':{family:'x'}}}};
assert.equal(m.metadata('combo/coding-harian',catalog),null);
assert.equal(m.metadata('oc/space-bunny-free',catalog).family,'x');
assert.equal(m.metadata('oc/space-bunny-free (high)',catalog),null);
assert.equal(m.metadata('unknown-model',catalog),null);
assert.equal(m.metadata('gq/llama',catalog),null);
console.log(JSON.stringify({family:catalog.opencode.models['space-bunny-free'].family}));
'''))
        self.assertEqual(result['family'], 'x')


class DiscoveryTests(unittest.TestCase):
    def test_grouping_splits_wide_namespaces_and_merges_narrow(self):
        result = run_node(script('''
const groups=m.discoveryGroups(fixture(),10);
const sizes=Object.fromEntries(groups.map(([key,value])=>[key,value.length]));
assert.deepStrictEqual(sizes,{combo:1,cmc:12,lainnya:4});
assert.deepStrictEqual(groups.map(([key])=>key),['combo','cmc','lainnya']);
assert.deepStrictEqual(m.discoveryProvider('cmc'),['9router-cmc','9Router \\u00b7 cmc']);
assert.deepStrictEqual(m.discoveryProvider('combo'),['9router','9Router']);
assert.deepStrictEqual(m.discoveryProvider('lainnya'),['9router-lainnya','9Router \\u00b7 lainnya']);
assert.deepStrictEqual(m.discoveryGroups(fixture(),0).map(([key])=>key),['combo','cmc','oc','groq']);
console.log(JSON.stringify({sizes,keys:groups.map(([key])=>key)}));
'''))
        self.assertEqual(result['sizes'], {'combo': 1, 'cmc': 12, 'lainnya': 4})
        self.assertEqual(result['keys'], ['combo', 'cmc', 'lainnya'])

    def test_model_config_uses_gateway_metadata_only_when_verified(self):
        result = run_node(script('''
const verified=m.discoveryModelConfig(entry('cmc/model-00',
  {reasoning:true,thinkingEffortSupported:true,thinkingCanDisable:true,vision:true,search:true}));
assert.equal(verified.properties.contextWindow,1000000);
assert.deepStrictEqual(verified.properties.inputFormat,{supportsImage:true,supportsVideo:false,supportsPdf:false});
assert.equal(verified.properties.supportsNativeWebSearch,true);
assert.deepStrictEqual(verified.optionSpecs.maxOutputTokens,{max:384000});
assert.deepStrictEqual(verified.optionSpecs.reasoningLevel.values,['off','low','medium','high','xhigh','max']);
assert.equal(verified.optionSpecs.reasoningLevel.map,'{"reasoning_effort": reasoningLevel}');
const plain=m.discoveryModelConfig(entry('oc/free-0',{reasoning:true,thinkingEffortSupported:false}));
assert.deepStrictEqual(plain.optionSpecs.reasoningLevel,{values:['disabled'],map:'{}'});
assert.equal(m.discoveryModelConfig(entry('mmf/nometa',{contextWindow:0,maxOutput:0})),null);
assert.equal(m.firstLimit(0,undefined,null,-3),null);
assert.equal(m.firstLimit(undefined,null,7,9),7);
console.log(JSON.stringify({values:verified.optionSpecs.reasoningLevel.values,plain:plain.optionSpecs.reasoningLevel}));
'''))
        self.assertEqual(result['values'], ['off', 'low', 'medium', 'high', 'xhigh', 'max'])
        self.assertEqual(result['plain'], {'values': ['disabled'], 'map': '{}'})

    def test_merge_bootstraps_family_and_is_idempotent(self):
        result = run_node(script('''
const [out,state,changes,status]=m.discoveryMerge(family(),fixture(),{},null,m.GATEWAY_BASE_URL,true);
assert.equal(status,'ok');
const providers=Object.fromEntries(out.config.providerConfigRules.providerRules.map(item=>[item.providerId,item]));
assert.deepStrictEqual(Object.keys(providers).sort(),['9router','9router-cmc','9router-lainnya']);
assert.equal(providers['9router'].providerName,'9Router');
assert.equal(providers['9router-cmc'].config.api.baseUrl,m.GATEWAY_BASE_URL);
assert.equal(providers['9router-cmc'].config.access.type,'api-key');
assert.equal(providers['9router-cmc'].config.access.apiKey,m.DISCOVERY_API_KEY_PLACEHOLDER);
assert.equal(providers['9router-cmc'].config.personalModelIds.length,12);
assert.deepStrictEqual(out.config.providerOrder,['9router','9router-cmc','9router-lainnya']);
const rules=out.config.modelConfigRules.manualProviderModelRules;
assert.equal(rules.length,17);
for(const rule of rules)assert.equal(typeof rule.config.optionSpecs.reasoningLevel,'object',
  'every manual rule needs reasoningLevel (host schema)');
assert.deepStrictEqual(state.discovery.groups,{'9router':1,'9router-cmc':12,'9router-lainnya':4});
const [again,nextState,changes2,status2]=m.discoveryMerge(out,fixture(),state,null,m.GATEWAY_BASE_URL,true);
assert.deepStrictEqual(changes2,[]);
assert.equal(status2,'ok');
assert.deepStrictEqual(again,out);
assert.deepStrictEqual(nextState,state);
console.log(JSON.stringify({providers:Object.keys(providers).sort(),rules:rules.length,order:out.config.providerOrder}));
'''))
        self.assertEqual(result['providers'], ['9router', '9router-cmc', '9router-lainnya'])
        self.assertEqual(result['rules'], 17)

    def test_merge_respects_disabled_deleted_and_hand_edited_models(self):
        result = run_node(script('''
const [out,state]=m.discoveryMerge(family(),fixture(),{},null,m.GATEWAY_BASE_URL,true);
const cmc=out.config.providerConfigRules.providerRules.find(item=>item.providerId==='9router-cmc');
const rule=out.config.modelConfigRules.manualProviderModelRules.find(item=>item.modelId==='cmc/model-00');
cmc.config.personalModelIds=cmc.config.personalModelIds.filter(id=>id!=='cmc/model-01'&&id!=='cmc/model-02');
cmc.config.modelOrder=cmc.config.modelOrder.filter(id=>id!=='cmc/model-02');
rule.config.properties.contextWindow=123456;
const [merged,newstate,changes]=m.discoveryMerge(out,fixture(),state,null,m.GATEWAY_BASE_URL,true);
const mergedCmc=merged.config.providerConfigRules.providerRules.find(item=>item.providerId==='9router-cmc');
assert.ok(mergedCmc.config.personalModelIds.includes('cmc/model-01'),'an unlisted model is listed again');
assert.ok(!mergedCmc.config.modelOrder.includes('cmc/model-02'),'deleted model is not resurrected');
assert.deepStrictEqual(newstate.discovery.removed,['cmc/model-02']);
assert.equal(merged.config.modelConfigRules.manualProviderModelRules.find(item=>item.modelId==='cmc/model-00')
  .config.properties.contextWindow,123456,'hand-edited rule is never overwritten');
assert.deepStrictEqual(changes,['listed:cmc/model-01']);
console.log(JSON.stringify({changes,removed:newstate.discovery.removed}));
'''))
        self.assertEqual(result['changes'], ['listed:cmc/model-01'])
        self.assertEqual(result['removed'], ['cmc/model-02'])

    def test_merge_never_touches_other_providers(self):
        result = run_node(script('''
const data=family();
data.config.providerConfigRules.providerRules.push({providerId:'vansrouter',providerName:'Vansrouter',enabled:true,
  config:{group:'standard-personal',access:{type:'api-key',apiKey:'user-key'},
    api:{type:'openai-chat-completions',baseUrl:'http://127.0.0.1:20128/v1'}}});
const [out,,,status]=m.discoveryMerge(data,fixture(),{},null,m.GATEWAY_BASE_URL,true);
assert.equal(status,'ok');
const vans=out.config.providerConfigRules.providerRules.find(item=>item.providerId==='vansrouter');
assert.ok(!('personalModelIds' in vans.config),'a user provider outside the family is left as-is');
assert.deepStrictEqual(vans.config.access,{type:'api-key',apiKey:'user-key'});
assert.deepStrictEqual(out.config.providerOrder,['9router','9router-cmc','9router-lainnya']);
console.log(JSON.stringify({order:out.config.providerOrder}));
'''))
        self.assertEqual(result['order'], ['9router', '9router-cmc', '9router-lainnya'])

    def test_snapshot_catalog_fills_gateway_gaps_without_unsupported_levels(self):
        result = run_node(script('''
const catalog={opencode:{models:{'space-bunny-free':{limit:{context:1048576,output:524288},
  modalities:{input:['text','image','video']},structured_output:true,
  reasoning_options:[{type:'effort',values:['minimal','low','medium','high','xhigh']}]}}}};
const bare={id:'oc/space-bunny-free',object:'model',owned_by:'oc'};
const config=m.discoveryModelConfig(bare,catalog);
assert.equal(config.properties.contextWindow,1048576);
assert.deepStrictEqual(config.optionSpecs.maxOutputTokens,{max:524288});
assert.deepStrictEqual(config.properties.inputFormat,{supportsImage:true,supportsVideo:true,supportsPdf:false});
assert.equal(config.properties.supportsJsonSchemaOutput,true);
assert.deepStrictEqual(config.optionSpecs.reasoningLevel.values,['low','medium','high','xhigh']);
const explicit=m.discoveryModelConfig(entry('oc/space-bunny-free',{vision:false}),catalog);
assert.equal(explicit.properties.inputFormat.supportsImage,false,'live gateway flags win over the snapshot');
assert.equal(m.discoveryModelConfig(entry('dv/unknown',{contextWindow:0,maxOutput:0}),catalog),null);
console.log(JSON.stringify({levels:config.optionSpecs.reasoningLevel.values,explicit:explicit.properties.inputFormat}));
'''))
        self.assertEqual(result['levels'], ['low', 'medium', 'high', 'xhigh'])
        self.assertFalse(result['explicit']['supportsImage'])

    def test_catalog_rules_never_clash_with_manual_rules(self):
        result = run_node(script('''
const [out,state]=m.discoveryMerge(family(),fixture(),{},null,m.GATEWAY_BASE_URL,true);
out.config.modelConfigRules.providerModelRules=[{providerId:'9router',modelId:'combo/coding-harian'}];
const [merged,newstate,changes]=m.discoveryMerge(out,fixture(),state,null,m.GATEWAY_BASE_URL,true);
const manual=merged.config.modelConfigRules.manualProviderModelRules
  .filter(rule=>rule.providerId==='9router').map(rule=>rule.modelId);
assert.ok(!manual.includes('combo/coding-harian'),'no manual rule beside a catalog rule');
assert.ok(merged.config.providerConfigRules.providerRules[0].config.modelOrder.includes('combo/coding-harian'),
  'the catalog model stays selectable');
assert.ok(!Object.prototype.hasOwnProperty.call(newstate.discovery.rules,'9router/combo/coding-harian'));
assert.ok(changes.includes('smart:combo/coding-harian'));
console.log(JSON.stringify({manual,changes}));
'''))
        self.assertNotIn('combo/coding-harian', result['manual'])
        self.assertIn('smart:combo/coding-harian', result['changes'])

    def test_model_switch_state_survives_metadata_refresh(self):
        result = run_node(script('''
const [out,state]=m.discoveryMerge(family(),fixture(),{},null,m.GATEWAY_BASE_URL,true);
const rules=out.config.modelConfigRules.manualProviderModelRules;
const first=rules.find(rule=>rule.modelId==='cmc/model-00');
first.config.enabled=false;
first.config.properties.contextWindow=999;
const [merged,newstate]=m.discoveryMerge(out,fixture(),state,null,m.GATEWAY_BASE_URL,true);
const updated=merged.config.modelConfigRules.manualProviderModelRules.find(rule=>rule.modelId==='cmc/model-00');
assert.equal(updated.config.enabled,false,'the off switch survives');
assert.equal(updated.config.properties.contextWindow,999,'hand edits are still never overwritten');
const second=merged.config.modelConfigRules.manualProviderModelRules.find(rule=>rule.modelId==='cmc/model-03');
second.config.enabled=false;
const [refreshed,,changes]=m.discoveryMerge(merged,fixture(),newstate,null,m.GATEWAY_BASE_URL,true);
const kept=refreshed.config.modelConfigRules.manualProviderModelRules.find(rule=>rule.modelId==='cmc/model-03');
assert.equal(kept.config.enabled,false);
assert.deepStrictEqual(changes,[]);
console.log(JSON.stringify({enabled:kept.config.enabled,changes}));
'''))
        self.assertFalse(result['enabled'])
        self.assertEqual(result['changes'], [])

    def test_known_but_unlisted_model_is_listed_again(self):
        result = run_node(script('''
const [out,state]=m.discoveryMerge(family(),fixture(),{},null,m.GATEWAY_BASE_URL,true);
const cmc=out.config.providerConfigRules.providerRules.find(item=>item.providerId==='9router-cmc');
cmc.config.personalModelIds=cmc.config.personalModelIds.filter(id=>id!=='cmc/model-04');
const [merged,,changes]=m.discoveryMerge(out,fixture(),state,null,m.GATEWAY_BASE_URL,true);
const mergedCmc=merged.config.providerConfigRules.providerRules.find(item=>item.providerId==='9router-cmc');
assert.ok(mergedCmc.config.personalModelIds.includes('cmc/model-04'),'the row is listed again');
const rule=merged.config.modelConfigRules.manualProviderModelRules.find(item=>item.modelId==='cmc/model-04');
assert.notEqual(rule.config.enabled,false,'no switch was set, so it stays on');
assert.deepStrictEqual(changes,['listed:cmc/model-04']);
console.log(JSON.stringify({changes}));
'''))
        self.assertEqual(result['changes'], ['listed:cmc/model-04'])

    def test_stale_catalog_rule_is_replaced_by_a_manual_rule(self):
        result = run_node(script('''
const [out,state]=m.discoveryMerge(family(),fixture(),{},null,m.GATEWAY_BASE_URL,true);
out.config.modelConfigRules.providerModelRules=[{providerId:'9router',modelId:'combo/coding-harian'}];
const [merged,,changes]=m.discoveryMerge(out,fixture(),state,null,m.GATEWAY_BASE_URL,true,
  m.DISCOVERY_GROUP_MIN,new Set());
assert.deepStrictEqual(merged.config.modelConfigRules.providerModelRules,[]);
const manual=merged.config.modelConfigRules.manualProviderModelRules
  .filter(rule=>rule.providerId==='9router').map(rule=>rule.modelId);
assert.ok(manual.includes('combo/coding-harian'));
assert.ok(changes.includes('stale-smart:combo/coding-harian'));
console.log(JSON.stringify({changes,manual}));
'''))
        self.assertIn('stale-smart:combo/coding-harian', result['changes'])
        self.assertIn('combo/coding-harian', result['manual'])

    def test_user_key_on_one_group_spreads_to_the_family(self):
        result = run_node(script('''
const [out,state]=m.discoveryMerge(family(),fixture(),{},null,m.GATEWAY_BASE_URL,true);
const cmc=out.config.providerConfigRules.providerRules.find(item=>item.providerId==='9router-cmc');
cmc.config.access.apiKey='user-real-key';
const [merged]=m.discoveryMerge(out,fixture(),state,null,m.GATEWAY_BASE_URL,true);
const keys=merged.config.providerConfigRules.providerRules.map(item=>item.config.access.apiKey);
assert.deepStrictEqual([...new Set(keys)],['user-real-key'],'one pasted key covers every group');
console.log(JSON.stringify({keys}));
'''))
        self.assertEqual(set(result['keys']), {'user-real-key'})

    def test_auto_runs_fill_only_existing_groups_and_bootstrap_rebuilds(self):
        result = run_node(script('''
const [out,state]=m.discoveryMerge(family(),fixture(),{},null,m.GATEWAY_BASE_URL,true);
const single=JSON.parse(JSON.stringify(out));
single.config.providerConfigRules.providerRules=single.config.providerConfigRules.providerRules
  .filter(item=>item.providerId==='9router');
single.config.modelConfigRules.manualProviderModelRules=single.config.modelConfigRules.manualProviderModelRules
  .filter(rule=>rule.providerId==='9router');
const [merged]=m.discoveryMerge(single,fixture(),state,null,m.GATEWAY_BASE_URL,false);
assert.deepStrictEqual(merged.config.providerConfigRules.providerRules.map(item=>item.providerId),['9router']);
assert.deepStrictEqual(merged.config.providerConfigRules.providerRules[0].config.personalModelIds,['combo/coding-harian']);
const kept=JSON.parse(JSON.stringify(out));
kept.config.providerConfigRules.providerRules=kept.config.providerConfigRules.providerRules
  .filter(item=>item.providerId!=='9router-cmc');
const [auto]=m.discoveryMerge(kept,fixture(),state,null,m.GATEWAY_BASE_URL,false);
assert.ok(!auto.config.providerConfigRules.providerRules.some(item=>item.providerId==='9router-cmc'),
  'an automatic run leaves the deleted group alone');
const [back]=m.discoveryMerge(auto,fixture(),state,null,m.GATEWAY_BASE_URL,true);
assert.ok(back.config.providerConfigRules.providerRules.some(item=>item.providerId==='9router-cmc'),
  'the Auto Detect path (bootstrap) rebuilds the family');
console.log(JSON.stringify({auto:auto.config.providerConfigRules.providerRules.map(item=>item.providerId),
  rebuilt:back.config.providerConfigRules.providerRules.map(item=>item.providerId)}));
'''))
        self.assertNotIn('9router-cmc', result['auto'], 'an automatic run leaves the deleted group alone')
        self.assertEqual(result['auto'], ['9router', '9router-lainnya'])
        self.assertIn('9router-cmc', result['rebuilt'], 'the Auto Detect path (bootstrap) rebuilds the family')

    def test_emptied_provider_and_whole_family_wipe_are_refilled(self):
        result = run_node(script('''
const [out,state]=m.discoveryMerge(family(),fixture(),{},null,m.GATEWAY_BASE_URL,true);
const cmc=out.config.providerConfigRules.providerRules.find(item=>item.providerId==='9router-cmc');
cmc.config.personalModelIds=[];
cmc.config.modelOrder=[];
const [merged,newstate]=m.discoveryMerge(out,fixture(),state,null,m.GATEWAY_BASE_URL,false);
const mergedCmc=merged.config.providerConfigRules.providerRules.find(item=>item.providerId==='9router-cmc');
assert.equal(mergedCmc.config.personalModelIds.length,12);
assert.deepStrictEqual(newstate.discovery.removed??[],[]);
const wiped=JSON.parse(JSON.stringify(out));
for(const provider of wiped.config.providerConfigRules.providerRules){
  provider.config.personalModelIds=[];
  provider.config.modelOrder=[];
}
wiped.config.modelConfigRules.manualProviderModelRules=[];
const [filled,wipedState]=m.discoveryMerge(wiped,fixture(),JSON.parse(JSON.stringify(state)),null,
  m.GATEWAY_BASE_URL,true);
const filledCmc=filled.config.providerConfigRules.providerRules.find(item=>item.providerId==='9router-cmc');
assert.equal(filledCmc.config.personalModelIds.length,12,'a wiped provider is refilled');
assert.deepStrictEqual(wipedState.discovery.removed??[],[],'a wipe is not remembered as user deletions');
console.log(JSON.stringify({refilled:mergedCmc.config.personalModelIds.length,removed:newstate.discovery.removed??[]}));
'''))
        self.assertEqual(result['refilled'], 12)
        self.assertEqual(result['removed'], [])

    def test_single_user_deletion_is_a_tombstone_and_readd_hands_it_back(self):
        result = run_node(script('''
const [out,state]=m.discoveryMerge(family(),fixture(),{},null,m.GATEWAY_BASE_URL,true);
const cmc=out.config.providerConfigRules.providerRules.find(item=>item.providerId==='9router-cmc');
cmc.config.personalModelIds=cmc.config.personalModelIds.filter(id=>id!=='cmc/model-05');
cmc.config.modelOrder=cmc.config.modelOrder.filter(id=>id!=='cmc/model-05');
out.config.modelConfigRules.manualProviderModelRules=out.config.modelConfigRules.manualProviderModelRules
  .filter(rule=>rule.modelId!=='cmc/model-05');
const [merged,newstate]=m.discoveryMerge(out,fixture(),state,null,m.GATEWAY_BASE_URL,true);
const mergedCmc=merged.config.providerConfigRules.providerRules.find(item=>item.providerId==='9router-cmc');
assert.ok(!mergedCmc.config.personalModelIds.includes('cmc/model-05'));
assert.deepStrictEqual(newstate.discovery.removed,['cmc/model-05']);
const readd=JSON.parse(JSON.stringify(merged));
readd.config.providerConfigRules.providerRules.find(item=>item.providerId==='9router-cmc')
  .config.personalModelIds.push('cmc/model-05');
const [,readdState]=m.discoveryMerge(readd,fixture(),newstate,null,m.GATEWAY_BASE_URL,true);
assert.deepStrictEqual(readdState.discovery.removed??[],[]);
console.log(JSON.stringify({removed:newstate.discovery.removed,afterReadd:readdState.discovery.removed??[]}));
'''))
        self.assertEqual(result['removed'], ['cmc/model-05'])
        self.assertEqual(result['afterReadd'], [])

    def test_commit_refuses_a_config_that_loses_most_models(self):
        with tempfile.TemporaryDirectory() as folder:
            state = pathlib.Path(folder) / 'model-sync'
            state.mkdir()
            target = pathlib.Path(folder) / 'provider_config.json'
            body = script('''
const fs=require('node:fs');
const [full]=m.discoveryMerge(family(),fixture(),{},null,m.GATEWAY_BASE_URL,true);
fs.writeFileSync(__TARGET__,JSON.stringify(full));
const gutted=JSON.parse(JSON.stringify(full));
for(const provider of gutted.config.providerConfigRules.providerRules){
  provider.config.personalModelIds=[];
  provider.config.modelOrder=[];
}
const written=m.commit(__TARGET__,fs.readFileSync(__TARGET__),gutted,__STATE__,null,['x']);
assert.equal(written,'refused','a destructive write is refused');
assert.deepStrictEqual(JSON.parse(fs.readFileSync(__TARGET__,'utf8')),full,'the file is left untouched');
console.log(JSON.stringify({written}));
''').replace('__TARGET__', json.dumps(str(target))).replace('__STATE__', json.dumps(str(state)))
            result = run_node(body)
            self.assertEqual(result['written'], 'refused')
            self.assertFalse(list(state.glob('backups/*')), 'no backup for a refused write')

    def test_commit_writes_a_backup_and_an_atomic_config(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            state = root / 'model-sync'
            state.mkdir()
            config = root / 'data/.ccode/v2/provider_config.json'
            config.parent.mkdir(parents=True)
            body = script('''
const fs=require('node:fs');
const [full,,changes,status]=m.discoveryMerge(family(),fixture(),{},null,m.GATEWAY_BASE_URL,true);
assert.equal(status,'ok');
fs.writeFileSync(__CONFIG__,JSON.stringify(family()));
const raw=fs.readFileSync(__CONFIG__);
const written=m.commit(__CONFIG__,raw,full,__STATE__,null,changes);
assert.equal(written,true);
assert.deepStrictEqual(JSON.parse(fs.readFileSync(__CONFIG__,'utf8')),full);
console.log(JSON.stringify({written,changes:changes.length,text:fs.readFileSync(__CONFIG__,'utf8').slice(0,2)}));
''').replace('__CONFIG__', json.dumps(str(config))).replace('__STATE__', json.dumps(str(state)))
            result = run_node(body)
            self.assertTrue(result['written'])
            self.assertEqual(result['text'], '{\n', 'json.dump(indent=2) shape with a trailing newline')
            self.assertTrue(config.read_text().endswith('}\n'))
            backups = list((state / 'backups').glob('provider_config-*.json'))
            self.assertEqual(len(backups), 1, 'the previous config is backed up before the write')

    def test_gateway_unreachable_keeps_config_and_sets_backoff(self):
        with standalone_root() as (root, config, state):
            original = family_config()
            original['config']['providerConfigRules']['providerRules'].append(family_provider(api_key='local'))
            config.write_text(json.dumps(original))
            result = run_cli(['--discover'], sync_env(root, config, state, 'http://127.0.0.1:1/v1'))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('Model discovery unavailable; keeping current config:', result.stdout)
            self.assertNotIn('Gateway models:', result.stdout)
            self.assertEqual(json.loads(config.read_text()), original, 'gateway down must not touch the config')
            written = json.loads((state / 'state.json').read_text())
            self.assertIn('failedAt', written.get('discovery', {}))
            self.assertFalse((state / 'backups').exists())

    def test_ttl_hold_skips_the_gateway_entirely(self):
        with standalone_root() as (root, config, state):
            original = family_config()
            original['config']['providerConfigRules']['providerRules'].append(family_provider(models=['combo/coding-harian']))
            original['config']['providerOrder'] = ['9router']
            config.write_text(json.dumps(original))
            (state / 'state.json').write_text(json.dumps(
                {'managed': {}, 'discovery': {'fetchedAt': time.time(), 'groups': {'9router': 1}}}))
            result = run_cli([], sync_env(root, config, state, 'http://127.0.0.1:1/v1'))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn('Gateway models:', result.stdout)
            self.assertEqual(json.loads(config.read_text()), original)
            self.assertNotIn('failedAt', json.loads((state / 'state.json').read_text()).get('discovery', {}))

    def test_failure_backoff_is_respected_without_an_explicit_discover(self):
        with standalone_root() as (root, config, state):
            original = family_config()
            original['config']['providerConfigRules']['providerRules'].append(family_provider())
            config.write_text(json.dumps(original))
            failed_at = time.time()
            (state / 'state.json').write_text(json.dumps(
                {'managed': {}, 'discovery': {'fetchedAt': failed_at - 60, 'failedAt': failed_at}}))
            result = run_cli([], sync_env(root, config, state, 'http://127.0.0.1:1/v1'))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn('Gateway models:', result.stdout)
            discovery = json.loads((state / 'state.json').read_text())['discovery']
            self.assertEqual(discovery['failedAt'], failed_at, 'backoff keeps the original timestamp')

    def test_concurrent_run_exits_quietly(self):
        with standalone_root() as (root, config, state):
            original = family_config()
            original['config']['providerConfigRules']['providerRules'].append(family_provider())
            config.write_text(json.dumps(original))
            (state / 'sync.lock').write_text(f'{os.getpid()}\n')
            result = run_cli(['--discover'], sync_env(root, config, state, 'http://127.0.0.1:1/v1'))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), '', 'a concurrent run stays quiet')
            self.assertEqual(json.loads(config.read_text()), original)
            self.assertFalse((state / 'state.json').exists())

    def test_stale_lock_without_a_pid_is_reclaimed(self):
        with standalone_root() as (root, config, state):
            original = family_config()
            original['config']['providerConfigRules']['providerRules'].append(family_provider())
            config.write_text(json.dumps(original))
            lock = state / 'sync.lock'
            lock.write_text('')  # a lock without a pid, like a POSIX flock holder
            old = time.time() - 3600
            os.utime(lock, (old, old))
            result = run_cli(['--discover'], sync_env(root, config, state, 'http://127.0.0.1:1/v1'))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('Model discovery unavailable; keeping current config:', result.stdout)
            self.assertIn('failedAt', json.loads((state / 'state.json').read_text())['discovery'])
            self.assertFalse(lock.exists(), 'a stale lock is released after the run')

    def test_fresh_pidless_lock_still_blocks_the_run(self):
        with standalone_root() as (root, config, state):
            original = family_config()
            original['config']['providerConfigRules']['providerRules'].append(family_provider())
            config.write_text(json.dumps(original))
            (state / 'sync.lock').write_text('')
            result = run_cli(['--discover'], sync_env(root, config, state, 'http://127.0.0.1:1/v1'))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), '')
            self.assertFalse((state / 'state.json').exists())

    def test_empty_provider_is_filled_before_the_ttl_elapses(self):
        with gateway_stub(gateway_fixture()) as base_url:
            with standalone_root() as (root, config, state):
                data = family_config()
                data['config']['providerConfigRules']['providerRules'].append(family_provider(base_url=base_url))
                config.write_text(json.dumps(data))
                (state / 'state.json').write_text(json.dumps(
                    {'managed': {}, 'discovery': {'fetchedAt': time.time() - 60, 'groups': {}}}))
                result = run_cli([], sync_env(root, config, state, base_url))
                self.assertEqual(result.returncode, 0, result.stderr)
                written = json.loads(config.read_text())
                providers = {item['providerId']: item for item in written['config']['providerConfigRules']['providerRules']}
                self.assertEqual(sorted(providers), ['9router'], 'an automatic run fills existing groups only')
                self.assertEqual(providers['9router']['config']['personalModelIds'], ['combo/coding-harian'])

    def test_cli_discovers_through_a_live_gateway_stub(self):
        with gateway_stub(gateway_fixture()) as base_url:
            with standalone_root() as (root, config, state):
                config.write_text(json.dumps(family_config()))
                result = run_cli(['--discover', '--bootstrap'], sync_env(root, config, state, base_url))
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('Gateway models: 17', result.stdout)
                written = json.loads(config.read_text())
                providers = {item['providerId']: item for item in written['config']['providerConfigRules']['providerRules']}
                self.assertEqual(sorted(providers), ['9router', '9router-cmc', '9router-lainnya'])
                self.assertEqual(providers['9router']['providerName'], '9Router')
                self.assertEqual(providers['9router-cmc']['providerName'], '9Router · cmc')
                self.assertEqual(providers['9router-cmc']['config']['api']['baseUrl'], base_url,
                                 'CCODE_MODEL_SYNC_GATEWAY drives the written family')
                self.assertEqual(providers['9router-cmc']['config']['access'],
                                 {'type': 'api-key', 'apiKey': 'local-gateway'})
                self.assertEqual(len(providers['9router-cmc']['config']['personalModelIds']), 12)
                self.assertEqual(providers['9router-lainnya']['config']['personalModelIds'],
                                 ['oc/free-0', 'oc/free-1', 'oc/free-2', 'groq/llama'])
                self.assertEqual(written['config']['providerOrder'], ['9router', '9router-cmc', '9router-lainnya'])
                rules = written['config']['modelConfigRules']['manualProviderModelRules']
                self.assertEqual(len(rules), 17)
                for rule in rules:
                    self.assertIsInstance(rule['config']['optionSpecs'].get('reasoningLevel'), dict)
                combo = next(rule for rule in rules if rule['modelId'] == 'combo/coding-harian')
                self.assertEqual(combo['config']['optionSpecs']['reasoningLevel']['values'],
                                 ['off', 'low', 'medium', 'high', 'xhigh', 'max'])
                combo_provider = providers['9router']
                self.assertEqual(combo_provider['config']['personalModelIds'], ['combo/coding-harian'])
                self.assertEqual(combo_provider['config']['modelOrder'], ['combo/coding-harian'])
                discovery = json.loads((state / 'state.json').read_text())['discovery']
                self.assertIn('fetchedAt', discovery)
                self.assertEqual(discovery['groups'], {'9router': 1, '9router-cmc': 12, '9router-lainnya': 4})
                self.assertEqual(discovery['skipped'], [])
                backups = list((state / 'backups').glob('provider_config-*.json'))
                self.assertEqual(len(backups), 1, 'the previous config is backed up before the write')
                self.assertEqual(json.loads(backups[0].read_text()), family_config())
                self.assertFalse((state / 'sync.lock').exists(), 'the run releases its guard')

    def test_second_run_is_idempotent_over_the_stub(self):
        with gateway_stub(gateway_fixture()) as base_url:
            with standalone_root() as (root, config, state):
                config.write_text(json.dumps(family_config()))
                env = sync_env(root, config, state, base_url)
                first = run_cli(['--discover', '--bootstrap'], env)
                self.assertEqual(first.returncode, 0, first.stderr)
                after_first = config.read_text()
                second = run_cli(['--discover', '--bootstrap'], env)
                self.assertEqual(second.returncode, 0, second.stderr)
                self.assertIn('Gateway models: 17', second.stdout)
                self.assertEqual(config.read_text(), after_first, 'a re-run writes nothing new')
                self.assertNotIn('Updated provider config:', second.stdout)
                self.assertEqual(len(list((state / 'backups').glob('provider_config-*.json'))), 1)


class DetectionWiringTests(unittest.TestCase):
    def test_detection_command_shape_and_linux_branch(self):
        # The deployed shape: activity.cjs lives at <install>/app/resources/activity,
        # so projectRoot() is three levels up and the Python script sits in
        # <install>/services/model-sync.
        with tempfile.TemporaryDirectory() as folder:
            install = pathlib.Path(folder) / 'install'
            resources = install / 'app/resources'
            (resources / 'activity').mkdir(parents=True)
            (resources / 'model-sync').mkdir()
            shutil.copy2(ROOT / 'src/main/activity.cjs', resources / 'activity' / 'main.cjs')
            (resources / 'model-sync/main.cjs').write_text('// staged port placeholder')
            (install / 'services/model-sync').mkdir(parents=True)
            sync_py = install / 'services/model-sync/sync.py'
            sync_py.write_text('# staged python placeholder')
            body = '''
const assert=require('node:assert/strict');
const path=require('node:path');
process.resourcesPath=__RESOURCES__;
// Pin the win32 decision branch: the command shape must not depend on the test host.
Object.defineProperty(process,'platform',{value:'win32',configurable:true});
const a=require(__ACTIVITY__);
const windows=a.detectionCommand();
assert.deepStrictEqual(windows.env,{ELECTRON_RUN_AS_NODE:'1'});
assert.equal(windows.command,process.execPath);
assert.equal(windows.script,path.join(__RESOURCES__,'model-sync','main.cjs'));
assert.equal(windows.error,undefined);
Object.defineProperty(process,'platform',{value:'linux',configurable:true});
const linux=a.detectionCommand();
assert.equal(linux.command,'/usr/bin/python3');
assert.equal(linux.script,__SYNC_PY__);
assert.deepStrictEqual(linux.env,{});
console.log(JSON.stringify({windows,linux}));
'''.replace('__RESOURCES__', json.dumps(str(resources))) \
   .replace('__ACTIVITY__', json.dumps(str(resources / 'activity' / 'main.cjs'))) \
   .replace('__SYNC_PY__', json.dumps(str(sync_py)))
            result = run_node(body)
            self.assertEqual(result['windows']['env'], {'ELECTRON_RUN_AS_NODE': '1'})
            self.assertEqual(result['windows']['script'], str(resources / 'model-sync' / 'main.cjs'))
            self.assertEqual(result['linux']['env'], {})
            self.assertEqual(result['linux']['command'], '/usr/bin/python3')
            self.assertEqual(result['linux']['script'], str(sync_py),
                             'the staged layout resolves the Python script inside the install root')

    def test_detection_command_reports_a_missing_script(self):
        with tempfile.TemporaryDirectory() as folder:
            body = f'''
process.resourcesPath={json.dumps(str(pathlib.Path(folder)))};
const a=require({json.dumps(str(ROOT / 'src/main/activity.cjs'))});
console.log(JSON.stringify(a.detectionCommand()));
'''
            result = run_node(body)
            self.assertIn('Model sync script is missing:', result['error'])
            self.assertNotIn('command', result)

    def test_run_detection_spawns_the_node_port_with_the_electron_flag(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            resources = root / 'app/resources'
            (resources / 'model-sync').mkdir(parents=True)
            probe = resources / 'model-sync/main.cjs'
            probe.write_text("console.error('PROBE '+JSON.stringify({argv:process.argv.slice(2),"
                             "runAsNode:process.env.ELECTRON_RUN_AS_NODE,"
                             "config:process.env.CCODE_MODEL_SYNC_CONFIG,"
                             "state:process.env.CCODE_MODEL_SYNC_STATE,"
                             "root:process.env.CCODE_STANDALONE_ROOT}));\n"
                             "console.log('Gateway models: 1');\n")
            (root / 'data/.ccode/v2').mkdir(parents=True)
            (root / 'model-sync').mkdir()
            config = root / 'data/.ccode/v2/provider_config.json'
            config.write_text(json.dumps(family_config()))
            body = f'''
process.resourcesPath={json.dumps(str(resources))};
process.env.CCODE_STANDALONE_ROOT={json.dumps(str(root))};
// Pin the win32 decision branch: the node port is what this test exercises.
Object.defineProperty(process,'platform',{{value:'win32',configurable:true}});
const a=require({json.dumps(str(ROOT / 'src/main/activity.cjs'))});
(async()=>{{ console.log(JSON.stringify(await a.runDetection())); }})().catch(error=>{{console.error(error);process.exitCode=1}});
'''
            result = run_node(body)
            self.assertTrue(result['ok'], result.get('error'))
            self.assertIn('Gateway models: 1', result['log'])
            self.assertIn('PROBE ', result['log'])
            captured = json.loads(result['log'][result['log'].index('PROBE ') + len('PROBE '):].splitlines()[0])
            self.assertEqual(captured['argv'], ['--discover', '--bootstrap'])
            self.assertEqual(captured['runAsNode'], '1')
            self.assertEqual(captured['config'], str(config))
            self.assertEqual(captured['state'], str(root / 'model-sync'))
            self.assertEqual(captured['root'], str(root))

    def test_run_detection_end_to_end_through_the_real_port(self):
        with gateway_stub(gateway_fixture()) as base_url:
            with tempfile.TemporaryDirectory() as folder:
                root = pathlib.Path(folder)
                resources = root / 'app/resources'
                (resources / 'model-sync').mkdir(parents=True)
                shutil.copy2(CLI, resources / 'model-sync/main.cjs')
                state = root / 'model-sync'
                state.mkdir()
                (state / 'catalog.json').write_text('{"opencode":{"models":{}}}')
                (root / 'data/.ccode/v2').mkdir(parents=True)
                config = root / 'data/.ccode/v2/provider_config.json'
                config.write_text(json.dumps(family_config()))
                body = f'''
process.resourcesPath={json.dumps(str(resources))};
process.env.CCODE_STANDALONE_ROOT={json.dumps(str(root))};
process.env.CCODE_MODEL_SYNC_GATEWAY={json.dumps(base_url)};
// Pin the win32 decision branch: the node port is what this test exercises.
Object.defineProperty(process,'platform',{{value:'win32',configurable:true}});
const a=require({json.dumps(str(ROOT / 'src/main/activity.cjs'))});
(async()=>{{ console.log(JSON.stringify(await a.runDetection())); }})().catch(error=>{{console.error(error);process.exitCode=1}});
'''
                result = run_node(body)
                self.assertTrue(result['ok'], result.get('error'))
                self.assertEqual(result['providers'], 3)
                self.assertEqual(result['models'], 17)
                self.assertEqual(result['rules'], 17)
                self.assertEqual(result['names'], ['9Router', '9Router · cmc', '9Router · lainnya'])
                self.assertIn('Gateway models: 17', result['log'])
                written = json.loads(config.read_text())
                self.assertEqual(sorted(item['providerId'] for item in written['config']['providerConfigRules']['providerRules']),
                                 ['9router', '9router-cmc', '9router-lainnya'])


if __name__ == '__main__':
    unittest.main()
