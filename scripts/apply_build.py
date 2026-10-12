#!/usr/bin/python3
"""Promote an already-staged build after the app has been closed."""
import hashlib,json,pathlib,shutil,os,datetime
from asar import Archive
ROOT=pathlib.Path(__file__).resolve().parents[1]
def main():
 executable=(ROOT/'app/zcode').resolve()
 for proc in pathlib.Path('/proc').iterdir():
  if not proc.name.isdigit():continue
  try:
   if (proc/'exe').resolve()==executable:raise SystemExit('Close ZCode before applying the build. Current app PID: '+proc.name)
  except (OSError,PermissionError):pass
 staged=ROOT/'runtime/build/resources';target=ROOT/'app/resources'
 manifest=json.loads((ROOT/'project.json').read_text())
 proof=json.loads((staged/'build-manifest.json').read_text())
 files=['app.asar','glm/zcode.cjs','voice/main.cjs']
 if proof['application_name']!=manifest['application_name']:raise ValueError('Wrong staged application identity')
 for name in files:
  if hashlib.sha256((staged/name).read_bytes()).hexdigest()!=proof['sha256'][name]:raise ValueError('Staged build checksum mismatch: '+name)
 identity=json.loads(Archive(staged/'app.asar').read('package.json'))
 if identity['name']!=manifest['application_name']:raise ValueError('Missing standalone application identity')
 backup=ROOT/'runtime/backups'/datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f');backup.mkdir(parents=True,mode=0o700)
 promoted=[]
 try:
  for name in files:
   previous=backup/name;previous.parent.mkdir(parents=True,exist_ok=True)
   if (target/name).exists():shutil.copy2(target/name,previous)
   dst=target/name;dst.parent.mkdir(parents=True,exist_ok=True)
   shutil.copy2(staged/name,dst.with_name(dst.name+'.new'))
  for name in files:
   dst=target/name;os.replace(dst.with_name(dst.name+'.new'),dst);promoted.append(name)
 except BaseException:
  for name in reversed(promoted):
   if (backup/name).exists():shutil.copy2(backup/name,target/name)
   else:(target/name).unlink()
  raise
 finally:
  for name in files:
   temp=(target/name).with_name(pathlib.Path(name).name+'.new')
   if temp.exists():temp.unlink()
 shutil.copy2(staged/'build-manifest.json',backup/'applied-build.json')
 print('Build applied. Previous resources:',backup)
if __name__=='__main__':main()
