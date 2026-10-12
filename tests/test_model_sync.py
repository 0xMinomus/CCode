import copy,importlib.util,pathlib,unittest
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
