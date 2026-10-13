import copy,importlib.util,json,os,pathlib,tempfile,time,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('sync',ROOT/'services/model-sync/sync.py');sync=importlib.util.module_from_spec(spec);spec.loader.exec_module(sync)
CAT={'opencode':{'models':{'space-bunny-free':{'reasoning':True,'reasoning_options':[{'type':'effort','values':['low','medium','high','xhigh','max']}],'limit':{'context':1048576},'modalities':{'input':['text','image']}}}}}
def config():return {'config':{'providerConfigRules':{'providerRules':[{'providerId':'vansrouter','config':{'api':{'type':'openai-chat-completions'},'personalModelIds':['oc/space-bunny-free']}}]},'modelConfigRules':{'manualProviderModelRules':[]}}}
class SyncTests(unittest.TestCase):
 def test_new_model_and_idempotence(self):
  d,s,c=sync.enrich(config(),CAT,{});r=d['config']['modelConfigRules']['manualProviderModelRules'][0]
  self.assertTrue(r['config']['properties']['inputFormat']['supportsImage']);self.assertIn('max',r['config']['optionSpecs']['reasoningLevel']['values'])
  d2,_,c2=sync.enrich(d,CAT,s);self.assertEqual(d,d2);self.assertEqual(c2,[])
 def test_manual_override_survives(self):
  d,s,_=sync.enrich(config(),CAT,{});d['config']['modelConfigRules']['manualProviderModelRules'][0]['config']['optionSpecs']['reasoningLevel']={'values':['high'],'map':'{"reasoning_effort":"high"}'}
  out,_,changes=sync.enrich(d,CAT,s);self.assertEqual(d,out);self.assertEqual(changes,[])
 def test_unknown_and_combo_not_invented(self):
  d=config();d['config']['providerConfigRules']['providerRules'][0]['config']['personalModelIds']=['oc/unknown','combo/new']
  out,_,changes=sync.enrich(d,CAT,{});self.assertEqual(d,out);self.assertEqual(changes,[])
 def test_metadata_refresh(self):
  d,s,_=sync.enrich(config(),CAT,{});cat=copy.deepcopy(CAT);cat['opencode']['models']['space-bunny-free']['reasoning_options'][0]['values']=['low','high']
  out,_,c=sync.enrich(d,cat,s);self.assertEqual(c,['oc/space-bunny-free']);self.assertEqual(out['config']['modelConfigRules']['manualProviderModelRules'][0]['config']['optionSpecs']['reasoningLevel']['values'],['low','high'])

def gateway_entry(model_id,context=1000000,output=384000,**caps):
  capabilities={'vision':False,'pdf':False,'tools':True,'search':False,'reasoning':False,'thinkingEffortSupported':False,'thinkingCanDisable':False,'contextWindow':context,'maxOutput':output}
  capabilities.update(caps)
  return {'id':model_id,'object':'model','owned_by':model_id.split('/',1)[0],'context_length':context,'max_completion_tokens':output,'capabilities':capabilities}

def gateway_fixture():
  models=[gateway_entry('combo/coding-harian',reasoning=True,thinkingEffortSupported=True,thinkingCanDisable=True,vision=True)]
  models+= [gateway_entry(f'cmc/model-{index:02d}',reasoning=True,thinkingEffortSupported=True,thinkingCanDisable=False) for index in range(12)]
  models+= [gateway_entry(f'oc/free-{index}') for index in range(3)]
  models+= [gateway_entry('groq/llama')]
  return models

def family_config():return {'config':{'providerConfigRules':{'providerRules':[]},'modelConfigRules':{'manualProviderModelRules':[]}}}

class DiscoveryTests(unittest.TestCase):
 def test_grouping_splits_wide_namespaces_and_merges_narrow(self):
  groups=dict((key,len(value)) for key,value in sync.discovery_groups(gateway_fixture(),10))
  self.assertEqual(groups,{'combo':1,'cmc':12,'lainnya':4})
  self.assertEqual([key for key,_ in sync.discovery_groups(gateway_fixture(),10)],['combo','cmc','lainnya'])
  self.assertEqual(sync.discovery_provider('cmc'),('9router-cmc','9Router · cmc'))
  self.assertEqual(sync.discovery_provider('combo'),('9router','9Router'))

 def test_model_config_uses_gateway_metadata_only_when_verified(self):
  entry=gateway_entry('cmc/model-00',reasoning=True,thinkingEffortSupported=True,thinkingCanDisable=True,vision=True,search=True)
  config=sync.discovery_model_config(entry)
  self.assertEqual(config['properties']['contextWindow'],1000000)
  self.assertEqual(config['properties']['inputFormat'],{'supportsImage':True,'supportsVideo':False,'supportsPdf':False})
  self.assertTrue(config['properties']['supportsNativeWebSearch'])
  self.assertEqual(config['optionSpecs']['maxOutputTokens'],{'max':384000})
  self.assertEqual(config['optionSpecs']['reasoningLevel']['values'],['off','low','medium','high','xhigh','max'])
  self.assertEqual(config['optionSpecs']['reasoningLevel']['map'],'{"reasoning_effort": reasoningLevel}')
  plain=sync.discovery_model_config(gateway_entry('oc/free-0',reasoning=True,thinkingEffortSupported=False))
  self.assertEqual(plain['optionSpecs']['reasoningLevel'],{'values':['disabled'],'map':'{}'},'unverified effort gets the inert placeholder the schema requires')
  self.assertIsNone(sync.discovery_model_config(gateway_entry('mmf/nometa',context=0,output=0)),'models without limits are skipped, not invented')

 def test_merge_bootstraps_family_and_is_idempotent(self):
  out,state,changes,status=sync.discovery_merge(family_config(),gateway_fixture(),{},bootstrap=True)
  self.assertEqual(status,'ok')
  providers={item['providerId']:item for item in out['config']['providerConfigRules']['providerRules']}
  self.assertEqual(sorted(providers),['9router','9router-cmc','9router-lainnya'])
  self.assertEqual(providers['9router']['providerName'],'9Router')
  self.assertEqual(providers['9router-cmc']['config']['api']['baseUrl'],sync.GATEWAY_BASE_URL)
  self.assertEqual(providers['9router-cmc']['config']['access']['type'],'api-key')
  self.assertEqual(len(providers['9router-cmc']['config']['personalModelIds']),12)
  self.assertEqual(out['config']['providerOrder'],['9router','9router-cmc','9router-lainnya'])
  self.assertEqual(len(out['config']['modelConfigRules']['manualProviderModelRules']),17)
  for rule in out['config']['modelConfigRules']['manualProviderModelRules']:
   self.assertIsInstance(rule['config']['optionSpecs'].get('reasoningLevel'),dict,'every manual rule needs reasoningLevel (host schema)')
  again,_,changes2,status2=sync.discovery_merge(out,gateway_fixture(),state,bootstrap=True)
  self.assertEqual(changes2,[]);self.assertEqual(status2,'ok');self.assertEqual(again,out)

 def test_merge_respects_disabled_deleted_and_hand_edited_models(self):
  out,state,_,_=sync.discovery_merge(family_config(),gateway_fixture(),{},bootstrap=True)
  providers=out['config']['providerConfigRules']['providerRules']
  cmc=next(item for item in providers if item['providerId']=='9router-cmc')
  rules=out['config']['modelConfigRules']['manualProviderModelRules']
  rule=next(item for item in rules if item['modelId']=='cmc/model-00')
  # user disables one model, deletes another, and hand-edits a third
  cmc['config']['personalModelIds'].remove('cmc/model-01')
  cmc['config']['personalModelIds'].remove('cmc/model-02')
  cmc['config']['modelOrder'].remove('cmc/model-02')
  rule['config']['properties']['contextWindow']=123456
  merged,newstate,changes,_=sync.discovery_merge(out,gateway_fixture(),state,bootstrap=True)
  merged_cmc=next(item for item in merged['config']['providerConfigRules']['providerRules'] if item['providerId']=='9router-cmc')
  self.assertIn('cmc/model-01',merged_cmc['config']['personalModelIds'],'an unlisted model is listed again')
  self.assertNotIn('cmc/model-02',merged_cmc['config']['modelOrder'],'deleted model is not resurrected')
  self.assertEqual(newstate['discovery']['removed'],['cmc/model-02'])
  self.assertEqual(next(item for item in merged['config']['modelConfigRules']['manualProviderModelRules'] if item['modelId']=='cmc/model-00')['config']['properties']['contextWindow'],123456,'hand-edited rule is never overwritten')
  self.assertEqual(changes,['listed:cmc/model-01'],'only the unlisted model is surfaced; the hand-edited rule is untouched')

 def test_merge_never_touches_other_providers(self):
  data=family_config()
  data['config']['providerConfigRules']['providerRules'].append({'providerId':'vansrouter','providerName':'Vansrouter','enabled':True,
    'config':{'group':'standard-personal','access':{'type':'api-key','apiKey':'user-key'},'api':{'type':'openai-chat-completions','baseUrl':'http://127.0.0.1:20128/v1'}}})
  out,_,_,_=sync.discovery_merge(data,gateway_fixture(),{},bootstrap=True)
  vansrouter=next(item for item in out['config']['providerConfigRules']['providerRules'] if item['providerId']=='vansrouter')
  self.assertNotIn('personalModelIds',vansrouter['config'],'a user provider outside the family is left as-is')
  self.assertEqual(out['config']['providerOrder'],['9router','9router-cmc','9router-lainnya'])

 def test_snapshot_catalog_fills_gateway_gaps_without_unsupported_levels(self):
  # The gateway lists the free OpenCode tier without limits; the models.dev snapshot
  # the repo already syncs knows them. Levels the gateway would reject stay out.
  catalog={'opencode':{'models':{'space-bunny-free':{'limit':{'context':1048576,'output':524288},
      'modalities':{'input':['text','image','video']},'structured_output':True,
      'reasoning_options':[{'type':'effort','values':['minimal','low','medium','high','xhigh']}]}}}}
  bare={'id':'oc/space-bunny-free','object':'model','owned_by':'oc'}   # the gateway sends no capabilities for this tier
  config=sync.discovery_model_config(bare,catalog)
  self.assertEqual(config['properties']['contextWindow'],1048576)
  self.assertEqual(config['optionSpecs']['maxOutputTokens'],{'max':524288})
  self.assertEqual(config['properties']['inputFormat'],{'supportsImage':True,'supportsVideo':True,'supportsPdf':False})
  self.assertTrue(config['properties']['supportsJsonSchemaOutput'])
  self.assertEqual(config['optionSpecs']['reasoningLevel']['values'],['low','medium','high','xhigh'],'only gateway-accepted levels are offered')
  explicit=sync.discovery_model_config(gateway_entry('oc/space-bunny-free',vision=False),catalog)
  self.assertFalse(explicit['properties']['inputFormat']['supportsImage'],'live gateway flags win over the snapshot')
  self.assertIsNone(sync.discovery_model_config(gateway_entry('dv/unknown',context=0,output=0),catalog),'unknown models stay skipped')

 def test_catalog_rules_never_clash_with_manual_rules(self):
  # The host schema rejects a model that has both a smart (catalog) and a manual
  # rule, so a manual rule we wrote for a catalog model must be dropped.
  out,state,_,_=sync.discovery_merge(family_config(),gateway_fixture(),{},bootstrap=True)
  out['config']['modelConfigRules']['providerModelRules']=[{'providerId':'9router','modelId':'combo/coding-harian'}]
  merged,newstate,changes,_=sync.discovery_merge(out,gateway_fixture(),state,bootstrap=True)
  manual=[rule['modelId'] for rule in merged['config']['modelConfigRules']['manualProviderModelRules'] if rule.get('providerId')=='9router']
  self.assertNotIn('combo/coding-harian',manual,'no manual rule beside a catalog rule')
  self.assertIn('combo/coding-harian',merged['config']['providerConfigRules']['providerRules'][0]['config']['modelOrder'],'the catalog model stays selectable')
  self.assertNotIn('9router/combo/coding-harian',newstate['discovery']['rules'])

 def test_model_switch_state_survives_metadata_refresh(self):
  # The host keeps the per-model on/off switch as config.enabled on the rule.
  out,state,_,_=sync.discovery_merge(family_config(),gateway_fixture(),{},bootstrap=True)
  rules=out['config']['modelConfigRules']['manualProviderModelRules']
  rule=next(item for item in rules if item['modelId']=='cmc/model-00')
  rule['config']['enabled']=False                      # user switched this model off
  rule['config']['properties']['contextWindow']=999    # user hand-edited a value
  merged,newstate,_,_=sync.discovery_merge(out,gateway_fixture(),state,bootstrap=True)
  updated=next(item for item in merged['config']['modelConfigRules']['manualProviderModelRules'] if item['modelId']=='cmc/model-00')
  self.assertFalse(updated['config']['enabled'],'the off switch survives')
  self.assertEqual(updated['config']['properties']['contextWindow'],999,'hand edits are still never overwritten')
  # a rule we own but the user only toggled keeps refreshing its metadata
  second=next(rule for rule in merged['config']['modelConfigRules']['manualProviderModelRules'] if rule['modelId']=='cmc/model-03')
  second['config']['enabled']=False
  refreshed,_,changes,_=sync.discovery_merge(merged,gateway_fixture(),newstate,bootstrap=True)
  kept=next(rule for rule in refreshed['config']['modelConfigRules']['manualProviderModelRules'] if rule['modelId']=='cmc/model-03')
  self.assertFalse(kept['config']['enabled'])

 def test_known_but_unlisted_model_is_listed_again(self):
  # A model the host still knows but which is missing from the provider lists is
  # re-listed; the row shows up again with whatever switch its rule carries.
  out,state,_,_=sync.discovery_merge(family_config(),gateway_fixture(),{},bootstrap=True)
  cmc=next(item for item in out['config']['providerConfigRules']['providerRules'] if item['providerId']=='9router-cmc')
  cmc['config']['personalModelIds'].remove('cmc/model-04')
  merged,_,_,_=sync.discovery_merge(out,gateway_fixture(),state,bootstrap=True)
  merged_cmc=next(item for item in merged['config']['providerConfigRules']['providerRules'] if item['providerId']=='9router-cmc')
  self.assertIn('cmc/model-04',merged_cmc['config']['personalModelIds'],'the row is listed again')
  rule=next(item for item in merged['config']['modelConfigRules']['manualProviderModelRules'] if item['modelId']=='cmc/model-04')
  self.assertNotEqual(rule['config'].get('enabled'),False,'no switch was set, so it stays on')

 def test_stale_catalog_rule_is_replaced_by_a_manual_rule(self):
  # A stored smart rule for a model the catalog no longer defines is inert (the host
  # cannot render it) and blocks a manual rule, so discovery must replace it.
  out,state,_,_=sync.discovery_merge(family_config(),gateway_fixture(),{},bootstrap=True)
  out['config']['modelConfigRules']['providerModelRules']=[{'providerId':'9router','modelId':'combo/coding-harian'}]
  merged,_,changes,_=sync.discovery_merge(out,gateway_fixture(),state,bootstrap=True,catalog_matches=set())
  self.assertEqual(merged['config']['modelConfigRules'].get('providerModelRules') or [],[])
  manual=[rule['modelId'] for rule in merged['config']['modelConfigRules']['manualProviderModelRules'] if rule.get('providerId')=='9router']
  self.assertIn('combo/coding-harian',manual)
  self.assertIn('stale-smart:combo/coding-harian',changes)

 def test_user_key_on_one_group_spreads_to_the_family(self):
  out,state,_,_=sync.discovery_merge(family_config(),gateway_fixture(),{},bootstrap=True)
  providers=out['config']['providerConfigRules']['providerRules']
  next(item for item in providers if item['providerId']=='9router-cmc')['config']['access']['apiKey']='user-real-key'
  merged,_,_,_=sync.discovery_merge(out,gateway_fixture(),state,bootstrap=True)
  keys={item['providerId']:item['config']['access'].get('apiKey') for item in merged['config']['providerConfigRules']['providerRules']}
  self.assertEqual(set(keys.values()),{'user-real-key'},'one pasted key covers every group')

 def test_empty_provider_is_filled_before_the_ttl_elapses(self):
  # A provider just added from the UI has an empty model list; the 60s timer must
  # fill it immediately instead of waiting out the 12h discovery TTL.
  with tempfile.TemporaryDirectory() as folder:
    root=pathlib.Path(folder);state_root=root/'model-sync';state_root.mkdir(parents=True)
    config_path=root/'data/.zcode/v2/provider_config.json';config_path.parent.mkdir(parents=True)
    (state_root/'catalog.json').write_text('{"opencode":{"models":{}}}')
    data=family_config()
    data['config']['providerConfigRules']['providerRules'].append({'providerId':'9router','providerName':'9Router','enabled':True,
      'config':{'group':'standard-personal','access':{'type':'api-key','apiKey':'local-gateway'},
                'api':{'type':'openai-chat-completions','baseUrl':sync.GATEWAY_BASE_URL},'personalModelIds':[],'modelOrder':[]}})
    config_path.write_text(json.dumps(data))
    (state_root/'state.json').write_text(json.dumps({'managed':{},'discovery':{'fetchedAt':time.time()-60,'groups':{}}}))
    saved=(os.environ.get('ZCODE_MODEL_SYNC_CONFIG'),os.environ.get('ZCODE_MODEL_SYNC_STATE'),os.environ.get('ZCODE_STANDALONE_ROOT'))
    os.environ.update({'ZCODE_MODEL_SYNC_CONFIG':str(config_path),'ZCODE_MODEL_SYNC_STATE':str(state_root),'ZCODE_STANDALONE_ROOT':str(root)})
    real=sync.gateway_models
    sync.gateway_models=lambda *a,**k:gateway_fixture()
    try:sync.main([])
    finally:
      sync.gateway_models=real
      for key,value in zip(('ZCODE_MODEL_SYNC_CONFIG','ZCODE_MODEL_SYNC_STATE','ZCODE_STANDALONE_ROOT'),saved):
        if value is None:os.environ.pop(key,None)
        else:os.environ[key]=value
    written=json.loads(config_path.read_text())
    providers={item['providerId']:item for item in written['config']['providerConfigRules']['providerRules']}
    self.assertEqual(sorted(providers),['9router'],'the 60s timer fills the existing group only')
    self.assertEqual(len(providers['9router']['config']['personalModelIds']),1,'the combo group is filled')

 def test_empty_provider_is_filled_before_the_ttl_elapses(self):
  # A provider just added from the UI has an empty model list; the 60s timer must
  # fill it immediately instead of waiting out the 12h discovery TTL.
  with tempfile.TemporaryDirectory() as folder:
    root=pathlib.Path(folder);state_root=root/'model-sync';state_root.mkdir(parents=True)
    config_path=root/'data/.zcode/v2/provider_config.json';config_path.parent.mkdir(parents=True)
    (state_root/'catalog.json').write_text('{"opencode":{"models":{}}}')
    data=family_config()
    data['config']['providerConfigRules']['providerRules'].append({'providerId':'9router','providerName':'9Router','enabled':True,
      'config':{'group':'standard-personal','access':{'type':'api-key','apiKey':'local-gateway'},
                'api':{'type':'openai-chat-completions','baseUrl':sync.GATEWAY_BASE_URL},'personalModelIds':[],'modelOrder':[]}})
    config_path.write_text(json.dumps(data))
    (state_root/'state.json').write_text(json.dumps({'managed':{},'discovery':{'fetchedAt':time.time()-60,'groups':{}}}))
    saved=(os.environ.get('ZCODE_MODEL_SYNC_CONFIG'),os.environ.get('ZCODE_MODEL_SYNC_STATE'),os.environ.get('ZCODE_STANDALONE_ROOT'))
    os.environ.update({'ZCODE_MODEL_SYNC_CONFIG':str(config_path),'ZCODE_MODEL_SYNC_STATE':str(state_root),'ZCODE_STANDALONE_ROOT':str(root)})
    real=sync.gateway_models
    sync.gateway_models=lambda *a,**k:gateway_fixture()
    try:sync.main([])
    finally:
      sync.gateway_models=real
      for key,value in zip(('ZCODE_MODEL_SYNC_CONFIG','ZCODE_MODEL_SYNC_STATE','ZCODE_STANDALONE_ROOT'),saved):
        if value is None:os.environ.pop(key,None)
        else:os.environ[key]=value
    written=json.loads(config_path.read_text())
    providers={item['providerId']:item for item in written['config']['providerConfigRules']['providerRules']}
    self.assertEqual(sorted(providers),['9router'],'an automatic run fills existing groups, never creates them')
    self.assertEqual(len(providers['9router']['config']['personalModelIds']),1,'the combo group is filled')

 def test_auto_run_fills_only_the_groups_that_exist(self):
  # A rewritten file (or a user cleanup) leaves one group: automatic runs fill that
  # group and never resurrect the others; the explicit path does rebuild them.
  out,state,_,_=sync.discovery_merge(family_config(),gateway_fixture(),{},bootstrap=True)
  single=copy.deepcopy(out)
  single['config']['providerConfigRules']['providerRules']=[item for item in single['config']['providerConfigRules']['providerRules'] if item['providerId']=='9router']
  single['config']['modelConfigRules']['manualProviderModelRules']=[rule for rule in single['config']['modelConfigRules']['manualProviderModelRules'] if rule['providerId']=='9router']
  merged,_,_,_=sync.discovery_merge(single,gateway_fixture(),state,bootstrap=False)
  ids=[item['providerId'] for item in merged['config']['providerConfigRules']['providerRules']]
  self.assertEqual(ids,['9router'],'auto fills existing groups only')
  combo=merged['config']['providerConfigRules']['providerRules'][0]
  self.assertEqual(combo['config']['personalModelIds'],['combo/coding-harian'],'the existing group is still filled')

 def test_auto_runs_never_create_groups_and_bootstrap_does(self):
  out,state,_,_=sync.discovery_merge(family_config(),gateway_fixture(),{},bootstrap=True)
  kept=[item for item in out['config']['providerConfigRules']['providerRules'] if item['providerId']!='9router-cmc']
  out['config']['providerConfigRules']['providerRules']=kept   # user deletes that group in the UI
  merged,_,_,_=sync.discovery_merge(out,gateway_fixture(),state,bootstrap=False)
  ids=[item['providerId'] for item in merged['config']['providerConfigRules']['providerRules']]
  self.assertNotIn('9router-cmc',ids,'an automatic run leaves the deleted group alone')
  back,_,_,_=sync.discovery_merge(merged,gateway_fixture(),state,bootstrap=True)
  self.assertIn('9router-cmc',[item['providerId'] for item in back['config']['providerConfigRules']['providerRules']],
                'the Auto Detect path (bootstrap) rebuilds the family')

 def test_emptied_provider_is_refilled_not_blacklisted(self):
  # One provider losing every model is a rewrite of that list, not five user
  # deletions: blacklisting them would hide real models forever.
  out,state,_,_=sync.discovery_merge(family_config(),gateway_fixture(),{},bootstrap=True)
  cmc=next(item for item in out['config']['providerConfigRules']['providerRules'] if item['providerId']=='9router-cmc')
  cmc['config']['personalModelIds']=[]; cmc['config']['modelOrder']=[]
  merged,newstate,_,_=sync.discovery_merge(out,gateway_fixture(),state,bootstrap=False)
  merged_cmc=next(item for item in merged['config']['providerConfigRules']['providerRules'] if item['providerId']=='9router-cmc')
  self.assertEqual(len(merged_cmc['config']['personalModelIds']),12)
  self.assertEqual(newstate['discovery'].get('removed') or [],[])

 def test_mass_disappearance_refills_instead_of_blacklisting(self):
  # A whole provider losing its models is an external rewrite, not 12 individual
  # deletions: discovery must refill and must not blacklist the gateway.
  out,state,_,_=sync.discovery_merge(family_config(),gateway_fixture(),{},bootstrap=True)
  wiped=copy.deepcopy(out); wiped_state=copy.deepcopy(state)
  for provider in wiped['config']['providerConfigRules']['providerRules']:
   provider['config']['personalModelIds']=[]; provider['config']['modelOrder']=[]
  wiped['config']['modelConfigRules']['manualProviderModelRules']=[]
  merged,newstate,changes,_=sync.discovery_merge(wiped,gateway_fixture(),wiped_state,bootstrap=True)
  cmc=next(item for item in merged['config']['providerConfigRules']['providerRules'] if item['providerId']=='9router-cmc')
  self.assertEqual(len(cmc['config']['personalModelIds']),12,'a wiped provider is refilled')
  self.assertEqual(newstate['discovery'].get('removed') or [],[],'a wipe is not remembered as user deletions')

 def test_single_user_deletion_is_still_remembered(self):
  out,state,_,_=sync.discovery_merge(family_config(),gateway_fixture(),{},bootstrap=True)
  cmc=next(item for item in out['config']['providerConfigRules']['providerRules'] if item['providerId']=='9router-cmc')
  cmc['config']['personalModelIds'].remove('cmc/model-05'); cmc['config']['modelOrder'].remove('cmc/model-05')
  out['config']['modelConfigRules']['manualProviderModelRules']=[rule for rule in out['config']['modelConfigRules']['manualProviderModelRules'] if rule.get('modelId')!='cmc/model-05']
  merged,newstate,_,_=sync.discovery_merge(out,gateway_fixture(),state,bootstrap=True)
  merged_cmc=next(item for item in merged['config']['providerConfigRules']['providerRules'] if item['providerId']=='9router-cmc')
  self.assertNotIn('cmc/model-05',merged_cmc['config']['personalModelIds'])
  self.assertEqual(newstate['discovery']['removed'],['cmc/model-05'])

 def test_commit_refuses_a_config_that_loses_most_models(self):
  with tempfile.TemporaryDirectory() as folder:
   root=pathlib.Path(folder);state_root=root/'model-sync';state_root.mkdir(parents=True)
   target=root/'provider_config.json'
   full,_,_,_=sync.discovery_merge(family_config(),gateway_fixture(),{},bootstrap=True)
   target.write_text(json.dumps(full))
   gutted=copy.deepcopy(full)
   for provider in gutted['config']['providerConfigRules']['providerRules']:
    provider['config']['personalModelIds']=[]; provider['config']['modelOrder']=[]
   written=sync.commit(target,target.read_bytes(),gutted,state_root,None,['x'])
   self.assertEqual(written,'refused','a destructive write is refused')
   self.assertEqual(json.loads(target.read_text()),full,'the file is left untouched')
   self.assertFalse(list(state_root.glob('backups/*')) if (state_root/'backups').exists() else [],'no backup for a refused write')

 def test_gateway_unreachable_keeps_config_and_sets_backoff(self):
  with tempfile.TemporaryDirectory() as folder:
    root=pathlib.Path(folder);state_root=root/'model-sync';state_root.mkdir(parents=True)
    config_path=root/'data/.zcode/v2/provider_config.json';config_path.parent.mkdir(parents=True)
    (state_root/'catalog.json').write_text('{"opencode":{"models":{}}}')
    original=family_config();original['config']['providerConfigRules']['providerRules'].append({'providerId':'9router','providerName':'9Router','enabled':True,
      'config':{'group':'standard-personal','access':{'type':'api-key','apiKey':'local'},'api':{'type':'openai-chat-completions','baseUrl':sync.GATEWAY_BASE_URL},'personalModelIds':[],'modelOrder':[]}})
    config_path.write_text(json.dumps(original))
    saved=(os.environ.get('ZCODE_MODEL_SYNC_CONFIG'),os.environ.get('ZCODE_MODEL_SYNC_STATE'),os.environ.get('ZCODE_STANDALONE_ROOT'))
    os.environ.update({'ZCODE_MODEL_SYNC_CONFIG':str(config_path),'ZCODE_MODEL_SYNC_STATE':str(state_root),'ZCODE_STANDALONE_ROOT':str(root)})
    real=sync.gateway_models
    sync.gateway_models=lambda *a,**k:(_ for _ in ()).throw(OSError('gateway down'))
    try:sync.main(['--discover'])
    finally:
      sync.gateway_models=real
      for key,value in zip(('ZCODE_MODEL_SYNC_CONFIG','ZCODE_MODEL_SYNC_STATE','ZCODE_STANDALONE_ROOT'),saved):
        if value is None:os.environ.pop(key,None)
        else:os.environ[key]=value
    self.assertEqual(json.loads(config_path.read_text()),original,'gateway down must not touch the config')
    self.assertIn('failedAt',json.loads((state_root/'state.json').read_text()).get('discovery',{}))

 def test_main_discovers_through_fixture_gateway(self):
  with tempfile.TemporaryDirectory() as folder:
    root=pathlib.Path(folder);state_root=root/'model-sync';state_root.mkdir(parents=True)
    config_path=root/'data/.zcode/v2/provider_config.json';config_path.parent.mkdir(parents=True)
    (state_root/'catalog.json').write_text('{"opencode":{"models":{}}}')
    config_path.write_text(json.dumps(family_config()))
    saved=(os.environ.get('ZCODE_MODEL_SYNC_CONFIG'),os.environ.get('ZCODE_MODEL_SYNC_STATE'),os.environ.get('ZCODE_STANDALONE_ROOT'))
    os.environ.update({'ZCODE_MODEL_SYNC_CONFIG':str(config_path),'ZCODE_MODEL_SYNC_STATE':str(state_root),'ZCODE_STANDALONE_ROOT':str(root)})
    real=sync.gateway_models
    sync.gateway_models=lambda *a,**k:gateway_fixture()
    try:sync.main(['--discover','--bootstrap'])
    finally:
      sync.gateway_models=real
      for key,value in zip(('ZCODE_MODEL_SYNC_CONFIG','ZCODE_MODEL_SYNC_STATE','ZCODE_STANDALONE_ROOT'),saved):
        if value is None:os.environ.pop(key,None)
        else:os.environ[key]=value
    written=json.loads(config_path.read_text())
    providers={item['providerId']:item for item in written['config']['providerConfigRules']['providerRules']}
    self.assertEqual(sorted(providers),['9router','9router-cmc','9router-lainnya'])
    self.assertEqual(len(providers['9router-cmc']['config']['personalModelIds']),12)
    state_written=json.loads((state_root/'state.json').read_text())
    self.assertIn('fetchedAt',state_written['discovery'])
    backups=sorted((state_root/'backups').glob('provider_config-*.json'))
    self.assertEqual(len(backups),1,'the previous config is backed up before the write')
