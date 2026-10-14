#!/usr/bin/python3
"""Build the patch from a pinned upstream archive; output is staged, never live."""
import hashlib,json,pathlib,shutil,subprocess,sys
from asar import Archive
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from local_only import replace_once,rebrand
from local_only import storage,cloud,catalog,branding,skills_plugin,mcp_catalog,n8n_plugin,plugins,runtime_tuning,token_savers,marketplace
SKILL_MARKER='.ccode-skills.json'
VENDOR_SKILL_SEEDS=('skills/dynamic-workflows/SKILL.md','skills/dynamic-workflows/examples.md','skills/dynamic-workflows/patterns.md')
AGENT_RESOURCE='glm/ccode.cjs'
CATALOG_RESOURCE='config/provider/ccode-builtin.json'
BUNDLE_META='glm/.node-bundle-meta.json'
class Rebranded:
 """Archive view: every text read already carries the CCode identity."""
 def __init__(self,archive,replacements):
  self.archive=archive;self.replacements=replacements
 def read(self,name):
  data=self.replacements.get(name)
  if data is None:
   data=rebrand.asset(name,self.archive.read(name))
   self.replacements[name]=data
  return data
 def write(self,destination,replacements,renames):
  self.archive.write(destination,replacements,renames=renames,transform=rebrand.asset)
def renamed_entries(archive):
 """Archive entries whose file name still carries the upstream product token."""
 renames={}
 for name,_ in archive.entries():
  if rebrand.leftover(name):
   renames[name]=rebrand.apply(name)
 return renames
def stage_skill_pack(skill_source,installed,output):
 skills=sorted(path.name for path in skill_source.iterdir() if (path/'SKILL.md').is_file())
 if not skills:raise ValueError('No bundled skills to stage in '+str(skill_source))
 for name in VENDOR_SKILL_SEEDS:
  if not (installed/name).is_file():raise ValueError('Installed bundled skill seed is missing: '+str(installed/name))
 marker=installed/SKILL_MARKER
 previous=json.loads(marker.read_text()).get('skills',[]) if marker.exists() else []
 if not isinstance(previous,list) or any(not isinstance(name,str) or not name or name in ('.','..') or '/' in name or '\\' in name for name in previous):
  raise ValueError('Invalid bundled skill ownership marker: '+str(marker))
 pack=output/'glm/packages'/skills_plugin.PACK_DIR
 if pack.exists():shutil.rmtree(pack)
 shutil.copytree(installed,pack)
 for name in set(previous)-set(skills):
  if name=='dynamic-workflows':continue
  shutil.rmtree(pack/'skills'/name,ignore_errors=True)
 for name in skills:
  destination=pack/'skills'/name
  if destination.exists():shutil.rmtree(destination)
  shutil.copytree(skill_source/name,destination)
 (pack/SKILL_MARKER).write_text(json.dumps({'skills':skills},indent=2)+'\n')
 shutil.rmtree(output/'glm/packages/ccode-skills-plugin',ignore_errors=True)
 rebrand.rewrite_tree(pack)
 files=sorted(str(path.relative_to(output)) for path in pack.rglob('*') if path.is_file())
 return skills,files
def installed_catalog():
 """Installed provider catalog; the deployed copy keeps its name across applies."""
 directory=ROOT/'app/resources/config/provider'
 for name in ('ccode-builtin.json',rebrand.previous('ccode-builtin.json')):
  if (directory/name).exists():return directory/name
 raise ValueError('Installed provider catalog is missing: '+str(directory))
def main():
 manifest=json.loads((ROOT/'project.json').read_text());base=ROOT/manifest['baseline']
 if hashlib.sha256(base.read_bytes()).hexdigest()!=manifest['baseline_sha256']:raise ValueError('Baseline hash mismatch; review upstream version before changing project.json')
 plugins.verify_baseline(manifest['plugins_baseline_sha256'])
 archive=Archive(base);replacements={};view=Rebranded(archive,replacements)
 renderer=manifest['renderer_asset'];s=view.read(renderer).decode()
 s=replace_once(s,'function iOn({isDesktop:','function originalCuaSettings({isDesktop:')
 s=replace_once(s,'function mit(e){let t=Wo()','function mit(e){if(fedoraCuaLocal(e))return $.jsx(FedoraCuaShortcut,e);let t=Wo()')
 anchor='(0,$.jsx)(git,{workspacePath:v,workspaceIdentity:y,remoteSessionId:b,isWebRemoteControl:_,currentSessionBusy:$t})'
 s=replace_once(s,anchor,anchor+',(0,$.jsx)(CCodeVoiceInput,{disabled:h||_})')
 s+='\n'+(ROOT/'src/renderer/linux-computer-use.js').read_text()+'\nfunction iOn(p){return fedoraCuaLocal(p)?$.jsx(FedoraCuaSettings,p):$.jsx(originalCuaSettings,p);}\n'
 s+='\n'+(ROOT/'src/renderer/voice-input.js').read_text()+'\n'
 s+='\n'+(ROOT/'src/renderer/activity-panel.js').read_text()+'\n'
 s+='\n'+(ROOT/'src/renderer/token-savers-panel.js').read_text()+'\n'
 s=skills_plugin.patch_renderer(s)
 s+='\n'+(ROOT/'src/renderer/mcp-catalog.js').read_text()+'\n'
 s=mcp_catalog.patch_renderer(s)
 main=view.read(manifest['main_asset']).decode()+'''\nimport {app as ccodeVoiceApp,ipcMain as ccodeVoiceIpcMain} from "electron";
import {createRequire as ccodeVoiceCreateRequire} from "node:module";
const ccodeVoiceRequire=ccodeVoiceCreateRequire(import.meta.url);
if(process.platform==="linux"){ccodeVoiceRequire(process.resourcesPath+"/voice/main.cjs").register({app:ccodeVoiceApp,ipcMain:ccodeVoiceIpcMain});}
ccodeVoiceRequire(process.resourcesPath+"/activity/main.cjs").register({app:ccodeVoiceApp,ipcMain:ccodeVoiceIpcMain});
ccodeVoiceRequire(process.resourcesPath+"/mcp/main.cjs").register({app:ccodeVoiceApp,ipcMain:ccodeVoiceIpcMain});
ccodeVoiceRequire(process.resourcesPath+"/token-savers/main.cjs").register({ipcMain:ccodeVoiceIpcMain});
'''
 preload=view.read(manifest['preload_asset']).decode()+'''\n(()=>{const {contextBridge,ipcRenderer}=require("electron");contextBridge.exposeInMainWorld("ccodeVoice",{start:(options)=>ipcRenderer.invoke("ccode-voice:start",options),stop:()=>ipcRenderer.invoke("ccode-voice:stop"),cancel:()=>ipcRenderer.invoke("ccode-voice:cancel")});contextBridge.exposeInMainWorld("ccodeActivity",{summary:(options)=>ipcRenderer.invoke("ccode-activity:summary",options)});contextBridge.exposeInMainWorld("ccodeTokenSavers",{snapshot:()=>ipcRenderer.invoke("ccode-token-savers:snapshot"),save:(settings)=>ipcRenderer.invoke("ccode-token-savers:save",settings)});contextBridge.exposeInMainWorld("ccodeDetect",{run:()=>ipcRenderer.invoke("ccode-detect:run")});contextBridge.exposeInMainWorld("ccodeMcpCatalog",{list:()=>ipcRenderer.invoke("ccode-mcp-catalog:list"),install:(options)=>ipcRenderer.invoke("ccode-mcp-catalog:install",options)});})();\n'''
 replacements[renderer]=s.encode();replacements[manifest['main_asset']]=main.encode();replacements[manifest['preload_asset']]=preload.encode()
 storage.patch_archive(view,replacements,renderer)
 early_main='out/main/chunk-HH7N2YVI.js'
 replacements[early_main]=replace_once(view.read(early_main).decode(),storage.ESM_BOOTSTRAP,storage.ESM_BOOTSTRAP+
  'import {createRequire as ccodeMcpBootstrapRequire} from "node:module";\nccodeMcpBootstrapRequire(import.meta.url)(process.resourcesPath+"/mcp/main.cjs").bootstrap();\n').encode()
 cloud.patch_archive(view,replacements,renderer)
 token_savers.patch_archive(view,replacements,renderer,manifest['renderer_intl_asset'])
 replacements[cloud.HOST]=skills_plugin.patch_host(view.read(cloud.HOST).decode()).encode()
 runtime_tuning.patch_archive(view,replacements,cloud.HOST,renderer)
 branding.patch_archive(view,replacements,{'renderer':renderer,'intl':manifest['renderer_intl_asset'],'icon':manifest['renderer_icon_asset']})
 identity=json.loads(view.read('package.json'))
 identity.update({'name':manifest['application_name'],'productName':branding.PRODUCT,'description':branding.PRODUCT+' desktop application'})
 replacements['package.json']=(json.dumps(identity,indent=2)+'\n').encode()
 agent_base=ROOT/manifest['agent_baseline']
 if hashlib.sha256(agent_base.read_bytes()).hexdigest()!=manifest['agent_baseline_sha256']:raise ValueError('Agent baseline hash mismatch; review upstream version before changing project.json')
 agent=runtime_tuning.patch_agent(n8n_plugin.patch_agent(skills_plugin.patch_agent(token_savers.patch_agent(marketplace.patch_agent(cloud.patch_agent(storage.patch_agent(rebrand.apply(agent_base.read_text()))))))))
 rebrand.assert_clean(agent,AGENT_RESOURCE)
 output=ROOT/'runtime/build/resources';view.write(output/'app.asar',replacements,renamed_entries(archive))
 (output/'glm').mkdir(parents=True,exist_ok=True);(output/AGENT_RESOURCE).write_text(agent)
 (output/BUNDLE_META).write_text(rebrand.apply((ROOT/'app/resources'/BUNDLE_META).read_text()))
 (output/'app-update.yml').write_text(rebrand.apply((ROOT/'app/resources/app-update.yml').read_text()))
 (output/'voice').mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/'src/main/voice.cjs',output/'voice/main.cjs')
 (output/'activity').mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/'src/main/activity.cjs',output/'activity/main.cjs')
 (output/'token-savers').mkdir(parents=True,exist_ok=True)
 shutil.copy2(ROOT/'src/main/token-savers.cjs',output/'token-savers/main.cjs')
 shutil.copy2(ROOT/'src/main/token-savers-runtime.cjs',output/'token-savers/token-savers-runtime.cjs')
 rebrand.rewrite_tree(output/'voice');rebrand.rewrite_tree(output/'activity');rebrand.rewrite_tree(output/'token-savers')
 (output/marketplace.RESOURCE_DIR).mkdir(parents=True,exist_ok=True)
 (output/marketplace.RESOURCE_FILE).write_text(marketplace.render_runtime())
 (output/'config/provider').mkdir(parents=True,exist_ok=True)
 (output/CATALOG_RESOURCE).write_text(rebrand.apply(catalog.patch_catalog(installed_catalog().read_text())))
 for name,source in branding.PACKAGED_ICONS.items():shutil.copy2(branding.ICON_DIR/source,output/name)
 payload=plugins.stage(output)
 skills,pack_files=stage_skill_pack(ROOT/'src/skills',ROOT/'app/resources/glm/packages'/skills_plugin.PACK_DIR,output)
 subprocess.run(['node',str(ROOT/'services/mcp/stage.cjs'),str(output/'mcp')],check=True,cwd=ROOT)
 rebrand.rewrite_tree(output/'mcp')
 mcp_files=sorted(str(path.relative_to(output)) for path in (output/'mcp').rglob('*') if path.is_file())
 files=['app.asar',AGENT_RESOURCE,BUNDLE_META,'app-update.yml','voice/main.cjs','activity/main.cjs','token-savers/main.cjs','token-savers/token-savers-runtime.cjs',marketplace.RESOURCE_FILE,CATALOG_RESOURCE,*branding.PACKAGED_ICONS,*pack_files,*mcp_files,*payload['files']]
 proof={'application_name':manifest['application_name'],'patched_assets':sorted(replacements),
        'bundled_skill_pack':skills_plugin.PACK_DIR,'bundled_skills':skills,'plugin_payload':payload,
        'sha256':{name:hashlib.sha256((output/name).read_bytes()).hexdigest() for name in files}}
 (output/'build-manifest.json').write_text(json.dumps(proof,indent=2)+'\n')
 print('Build staged:',output/'app.asar')
if __name__=='__main__':main()
