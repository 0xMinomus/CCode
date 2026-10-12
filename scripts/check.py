#!/usr/bin/python3
import ast,json,pathlib,subprocess,sys
ROOT=pathlib.Path(__file__).resolve().parents[1]
for p in list((ROOT/'scripts').glob('*.py'))+list((ROOT/'src/local_only').glob('*.py'))+list((ROOT/'services/voice').glob('*.py'))+[ROOT/'services/desktop/zcode_fast_profile.py',ROOT/'services/model-sync/sync.py']:
 ast.parse(p.read_text(),filename=str(p))
for p in list((ROOT/'src/renderer').glob('*.js'))+[ROOT/'src/main/voice.cjs']:
 subprocess.run(['node','--check',str(p)],check=True)
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
 subprocess.run(['node','--check',str(ROOT/'runtime/build/resources/glm/zcode.cjs')],check=True)
 subprocess.run(['node','--check',str(ROOT/'runtime/build/resources/voice/main.cjs')],check=True)
 print('Staged ASAR scripts pass syntax checks')
print('Checks passed')
