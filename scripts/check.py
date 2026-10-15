#!/usr/bin/python3
import ast,json,pathlib,subprocess,sys
ROOT=pathlib.Path(__file__).resolve().parents[1]
for p in list((ROOT/'scripts').glob('*.py'))+list((ROOT/'src/local_only').glob('*.py'))+list((ROOT/'services/voice').glob('*.py'))+[ROOT/'services/desktop/ccode_fast_profile.py',ROOT/'services/model-sync/sync.py']:
 ast.parse(p.read_text(),filename=str(p))
for p in list((ROOT/'src/renderer').glob('*.js'))+list((ROOT/'src/main').glob('*.cjs'))+list((ROOT/'services/mcp').glob('*.cjs')):
 subprocess.run(['node','--check',str(p)],check=True)
subprocess.run(['node',str(ROOT/'services/mcp/test-n8n.cjs')],check=True,cwd=ROOT)
subprocess.run([sys.executable,'-m','unittest','discover','-s',str(ROOT/'tests'),'-v'],check=True,cwd=ROOT)
staged=ROOT/'runtime/build/resources/app.asar'
if staged.exists():
 from asar import Archive
 m=json.loads((ROOT/'project.json').read_text());a=Archive(staged)
 folder=ROOT/'runtime/check';folder.mkdir(parents=True,exist_ok=True)
 proof=json.loads((staged.parent/'build-manifest.json').read_text())
 for name in proof['patched_assets']:
  if not name.endswith(('.js','.cjs')):continue
  p=folder/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(a.read(name));subprocess.run(['node','--check',str(p)],check=True)
 subprocess.run(['node','--check',str(ROOT/'runtime/build/resources/glm/ccode.cjs')],check=True)
 subprocess.run(['node','--check',str(ROOT/'runtime/build/resources/voice/main.cjs')],check=True)
 subprocess.run(['node','--check',str(ROOT/'runtime/build/resources/activity/main.cjs')],check=True)
 subprocess.run(['node','--check',str(ROOT/'runtime/build/resources/token-savers/main.cjs')],check=True)
 subprocess.run(['node','--check',str(ROOT/'runtime/build/resources/token-savers/token-savers-runtime.cjs')],check=True)
 subprocess.run(['node','--check',str(ROOT/'runtime/build/resources/commands/main.cjs')],check=True)
 subprocess.run(['node','--check',str(ROOT/'runtime/build/resources/marketplace/marketplace-compat.cjs')],check=True)
 subprocess.run(['node','--check',str(staged.parent/'mcp/main.cjs')],check=True)
 for p in (staged.parent/'mcp').glob('*.cjs'):
  if p.name!='main.cjs':subprocess.run(['node','--check',str(p)],check=True)
 catalog=json.loads((ROOT/'runtime/build/resources/config/provider/ccode-builtin.json').read_text())
 rules=catalog['config']['providerConfigRules']
 assert not [t for t in rules['templateRules'] if (t.get('config') or {}).get('access',{}).get('type')=='zhipu-coding-plan-api-key'],'Zhipu template survived'
 assert not [p for p in rules['providerRules'] if (p.get('config') or {}).get('access',{}).get('type')=='zhipu-account'],'Zhipu account provider survived'
 assert len([t for t in rules['templateRules'] if t.get('templateId')=='9router'])==1,'9Router template missing'
 print('Staged provider catalog drops Zhipu and keeps the 9Router template')
 print('Staged ASAR scripts pass syntax checks')
print('Checks passed')
