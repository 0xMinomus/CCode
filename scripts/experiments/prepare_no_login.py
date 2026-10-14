#!/usr/bin/python3
import pathlib,sys,shutil,json
ROOT=pathlib.Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'scripts'))
from asar import Archive
TEST=ROOT/'runtime/no-login';app=TEST/'app';home=TEST/'home'
if not app.exists():shutil.copytree(ROOT/'app',app,symlinks=True,ignore=lambda d,n:[x for x in n if x.startswith('app.asar.')])
# Replace UI account endpoint only; do not create an account or forge authenticated state.
a=Archive(ROOT/'app/resources/app.asar');manifest=json.loads((ROOT/'project.json').read_text());replacements={}
for name,_ in a.entries():
 if name.startswith('out/renderer/') and name.endswith(('.js','.cjs')):
  data=a.read(name)
  if b'https://ccode.z.ai' in data:replacements[name]=data.replace(b'https://ccode.z.ai',b'http://127.0.0.1:28081')
a.write(app/'resources/app.asar',replacements)
profile=home/'.ccode/v2';profile.mkdir(parents=True,exist_ok=True)
actual=json.loads((pathlib.Path.home()/'.ccode/v2/provider_config.json').read_text());cfg=actual['config']
provider=next(p for p in cfg['providerConfigRules']['providerRules'] if p['providerId']=='vansrouter')
provider['config']['personalModelIds']=['oc/space-bunny-free'];provider['config']['modelOrder']=['oc/space-bunny-free']
model=next(r for r in cfg['modelConfigRules']['manualProviderModelRules'] if r['providerId']=='vansrouter' and r['modelId']=='oc/space-bunny-free')
d={'schemaVersion':1,'config':{'providerOrder':['vansrouter'],'providerConfigRules':{'providerRules':[provider]},'modelConfigRules':{'providerModelRules':[],'manualProviderModelRules':[model]}}}
p=profile/'provider_config.json';p.write_text(json.dumps(d,indent=2)+'\n');p.chmod(0o600)
(profile/'setting.json').write_text(json.dumps({'locale':'en-US','memoryEnabled':False,'proactiveSuggestionsEnabled':False,'autoDownloadAndInstallUpdates':False,'computerUseComposerEntryHidden':True,'onboardingOccupation':'developer'})+'\n')
(home/'.ccode/cli').mkdir(parents=True,exist_ok=True);(home/'.ccode/cli/config.json').write_text(json.dumps({'mcp':{'servers':{}},'ui':{'locale':'en-US'}})+'\n')
assert not (profile/'credentials.json').exists(),'Test profile unexpectedly contains credentials'
print('Clean account-less profile prepared. API key is confined to ignored runtime config; account credentials are absent.')
print('Renderer account endpoint replacements:',len(replacements))
