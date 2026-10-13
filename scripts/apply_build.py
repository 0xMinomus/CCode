#!/usr/bin/python3
"""Promote an already-staged build after the app has been closed."""
import hashlib,json,pathlib,shutil,os,datetime,sys
from asar import Archive
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from local_only import catalog,branding
def namespace_root():
 return pathlib.Path(os.environ.get('ZCODE_STANDALONE_ROOT','').strip() or pathlib.Path.home()/'.local/share/ccode')
def derived_catalogs():
 """Provider catalogs the agent cached per endpoint; they win over the bundled copy."""
 return sorted(namespace_root().glob('data/.zcode/v2/runtime/provider/*/*/endpoint-*/zcode-builtin.json'))
BACKUP_RETENTION=2
APP_DIR_ICON_DIR='usr/share/icons/hicolor'
APP_RUN_BIN='BIN="$APPDIR/zcode"'
FILES=['app.asar','glm/zcode.cjs','voice/main.cjs','activity/main.cjs','config/provider/zcode-builtin.json']
def timestamped_backup(name):
 """True when name is a backup timestamp this script created."""
 try:datetime.datetime.strptime(name,'%Y%m%d-%H%M%S-%f')
 except ValueError:return False
 return True
def prune_backups(backups_root,current,keep=BACKUP_RETENTION):
 """Keep only the newest keep script-made backups, never the one from this run."""
 removed=[]
 try:entries=list(backups_root.iterdir())
 except OSError:return removed
 backups=[]
 for path in entries:
  if path.is_symlink() or not path.is_dir() or not timestamped_backup(path.name):continue
  backups.append(path)
 backups.sort(key=lambda path:path.name,reverse=True)
 for path in backups[keep:]:
  if path.name==current.name:continue
  try:shutil.rmtree(path)
  except OSError:continue
  removed.append(path)
 return removed
def stale_catalog_markers():
 """Refresh markers the removed cloud owner kept rescheduling for cached catalogs."""
 return sorted(namespace_root().glob('data/.zcode/v2/runtime/provider/*/*/endpoint-*/zcode-builtin-refresh.json'))
def remove_stale_catalog_markers():
 removed=[]
 for path in stale_catalog_markers():
  try:path.unlink()
  except OSError:continue
  removed.append(path)
 return removed
def refresh_derived_catalogs(backup):
 """Rewrite the cached catalogs with the standalone boundary, keeping backups for rollback."""
 refreshed=[]
 try:
  for path in derived_catalogs():
   text=path.read_text()
   patched=catalog.patch_catalog(text)
   if patched==text:continue
   previous=backup/'derived'/path.relative_to(namespace_root());previous.parent.mkdir(parents=True,exist_ok=True)
   shutil.copy2(path,previous)
   path.write_text(patched)
   refreshed.append(path)
 except BaseException:
  for path in refreshed:
   shutil.copy2(backup/'derived'/path.relative_to(namespace_root()),path)
  raise
 return refreshed
def appdir_identity(app_dir,backup):
 """Rename the deployed AppDir identity to CCode: binary, launcher entry, icons, AppRun."""
 if not app_dir.is_dir():raise ValueError('Missing app directory: '+str(app_dir))
 notes=[]
 binary=app_dir/'zcode';renamed=app_dir/'ccode'
 if binary.exists():
  if renamed.exists():raise ValueError('Both app/zcode and app/ccode exist; resolve the rename first')
  os.rename(binary,renamed);notes.append('binary: zcode -> ccode')
 archived=backup/'appdir';archived.mkdir(parents=True,exist_ok=True)
 launcher=app_dir/'zcode.desktop'
 if launcher.exists():
  text=launcher.read_text()
  for old,new in (('Name=ZCode','Name=CCode'),('Comment=ZCode Desktop App','Comment=CCode Desktop App'),
                  ('Icon=zcode','Icon=ccode'),('StartupWMClass=ZCode','StartupWMClass=ccode')):
   if old in text:text=text.replace(old,new)
  shutil.copy2(launcher,archived/launcher.name);launcher.unlink()
  (app_dir/'ccode.desktop').write_text(text);notes.append('launcher: zcode.desktop -> ccode.desktop')
 target=APP_DIR_ICON_DIR+'/1024x1024/apps/ccode.png'
 for name in ('.DirIcon','ccode.png'):
  link=app_dir/name
  if link.exists() or link.is_symlink():link.unlink()
  link.symlink_to(target)
 old_link=app_dir/'zcode.png'
 if old_link.exists() or old_link.is_symlink():old_link.unlink();notes.append('icon link: zcode.png -> ccode.png')
 icons=0
 for size in branding.LOCAL_ICON_SIZES:
  directory=app_dir/APP_DIR_ICON_DIR/f'{size}x{size}/apps'
  if not directory.is_dir():continue
  shutil.copy2(branding.ICON_DIR/f'ccode-{size}.png',directory/'ccode.png')
  legacy=directory/'zcode.png'
  if legacy.exists():legacy.unlink()
  icons+=1
 if icons:notes.append(f'icons: {icons} theme sizes now paint the CCode mark')
 run=app_dir/'AppRun'
 if run.exists():
  text=run.read_text()
  if APP_RUN_BIN in text:
   shutil.copy2(run,archived/run.name);run.write_text(text.replace(APP_RUN_BIN,'BIN="$APPDIR/ccode"'))
   notes.append('AppRun: launches app/ccode')
 return notes
def main():
 executables={(ROOT/'app/ccode').resolve(),(ROOT/'app/zcode').resolve()}
 for proc in pathlib.Path('/proc').iterdir():
  if not proc.name.isdigit():continue
  try:
   if (proc/'exe').resolve() in executables:raise SystemExit('Close CCode before applying the build. Current app PID: '+proc.name)
  except (OSError,PermissionError):pass
 staged=ROOT/'runtime/build/resources';target=ROOT/'app/resources'
 manifest=json.loads((ROOT/'project.json').read_text())
 proof=json.loads((staged/'build-manifest.json').read_text())
 files=[*FILES,*branding.PACKAGED_ICONS]
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
 identity_notes=appdir_identity(ROOT/'app',backup)
 refreshed=refresh_derived_catalogs(backup)
 removed_markers=remove_stale_catalog_markers()
 pruned=prune_backups(ROOT/'runtime/backups',backup)
 print('Build applied. Previous resources:',backup)
 if identity_notes:print('AppDir identity:',*identity_notes,sep='\n  ')
 if refreshed:print('Refreshed cached provider catalog:',*[str(p) for p in refreshed],sep='\n  ')
 if removed_markers:print('Removed stale catalog markers:',*[str(p) for p in removed_markers],sep='\n  ')
 if pruned:print('Pruned old backups:',*[str(p) for p in pruned],sep='\n  ')
if __name__=='__main__':main()
