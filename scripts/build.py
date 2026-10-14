#!/usr/bin/python3
"""Build the patch from a pinned upstream archive; output is staged, never live."""
import hashlib,json,pathlib,shutil,subprocess,sys
from asar import Archive
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from local_only import replace_once
from local_only import storage,cloud,catalog,branding,skills_plugin,mcp_catalog
SKILL_MARKER='.ccode-skills.json'
VENDOR_SKILL_SEEDS=('skills/dynamic-workflows/SKILL.md','skills/dynamic-workflows/examples.md','skills/dynamic-workflows/patterns.md')
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
 files=sorted(str(path.relative_to(output)) for path in pack.rglob('*') if path.is_file())
 return skills,files
def main():
 manifest=json.loads((ROOT/'project.json').read_text());base=ROOT/manifest['baseline']
 if hashlib.sha256(base.read_bytes()).hexdigest()!=manifest['baseline_sha256']:raise ValueError('Baseline hash mismatch; review upstream version before changing project.json')
 archive=Archive(base);renderer=manifest['renderer_asset'];s=archive.read(renderer).decode()
 s=replace_once(s,'function iOn({isDesktop:','function originalCuaSettings({isDesktop:')
 s=replace_once(s,'function mit(e){let t=Wo()','function mit(e){if(fedoraCuaLocal(e))return $.jsx(FedoraCuaShortcut,e);let t=Wo()')
 anchor='(0,$.jsx)(git,{workspacePath:v,workspaceIdentity:y,remoteSessionId:b,isWebRemoteControl:_,currentSessionBusy:$t})'
 s=replace_once(s,anchor,anchor+',(0,$.jsx)(ZCodeVoiceInput,{disabled:h||_})')
 s+='\n'+(ROOT/'src/renderer/linux-computer-use.js').read_text()+'\nfunction iOn(p){return fedoraCuaLocal(p)?$.jsx(FedoraCuaSettings,p):$.jsx(originalCuaSettings,p);}\n'
 s+='\n'+(ROOT/'src/renderer/voice-input.js').read_text()+'\n'
 s+='\n'+(ROOT/'src/renderer/activity-panel.js').read_text()+'\n'
 s=skills_plugin.patch_renderer(s)
 s+='\n'+(ROOT/'src/renderer/mcp-catalog.js').read_text()+'\n'
 s=mcp_catalog.patch_renderer(s)
 main=archive.read(manifest['main_asset']).decode()+'''\nimport {app as zcodeVoiceApp,ipcMain as zcodeVoiceIpcMain} from "electron";
import {createRequire as zcodeVoiceCreateRequire} from "node:module";
const zcodeVoiceRequire=zcodeVoiceCreateRequire(import.meta.url);
if(process.platform==="linux"){zcodeVoiceRequire(process.resourcesPath+"/voice/main.cjs").register({app:zcodeVoiceApp,ipcMain:zcodeVoiceIpcMain});}
zcodeVoiceRequire(process.resourcesPath+"/activity/main.cjs").register({app:zcodeVoiceApp,ipcMain:zcodeVoiceIpcMain});
zcodeVoiceRequire(process.resourcesPath+"/mcp/main.cjs").register({app:zcodeVoiceApp,ipcMain:zcodeVoiceIpcMain});
'''
 preload=archive.read(manifest['preload_asset']).decode()+'''\n(()=>{const {contextBridge,ipcRenderer}=require("electron");contextBridge.exposeInMainWorld("zcodeVoice",{start:(options)=>ipcRenderer.invoke("zcode-voice:start",options),stop:()=>ipcRenderer.invoke("zcode-voice:stop"),cancel:()=>ipcRenderer.invoke("zcode-voice:cancel")});contextBridge.exposeInMainWorld("zcodeActivity",{summary:(options)=>ipcRenderer.invoke("zcode-activity:summary",options)});contextBridge.exposeInMainWorld("zcodeDetect",{run:()=>ipcRenderer.invoke("zcode-detect:run")});contextBridge.exposeInMainWorld("ccodeMcpCatalog",{list:()=>ipcRenderer.invoke("zcode-mcp-catalog:list"),install:(options)=>ipcRenderer.invoke("zcode-mcp-catalog:install",options),test:(options)=>ipcRenderer.invoke("zcode-mcp-catalog:test",options)});})();\n'''
 replacements={renderer:s.encode(),manifest['main_asset']:main.encode(),manifest['preload_asset']:preload.encode()}
 storage.patch_archive(archive,replacements,renderer)
 early_main='out/main/chunk-HH7N2YVI.js'
 replacements[early_main]=replace_once(replacements[early_main].decode(),storage.ESM_BOOTSTRAP,storage.ESM_BOOTSTRAP+
  'import {createRequire as zcodeMcpBootstrapRequire} from "node:module";\nzcodeMcpBootstrapRequire(import.meta.url)(process.resourcesPath+"/mcp/main.cjs").bootstrap();\n').encode()
 cloud.patch_archive(archive,replacements,renderer)
 replacements[cloud.HOST]=skills_plugin.patch_host(replacements[cloud.HOST].decode()).encode()
 branding.patch_archive(archive,replacements,{'renderer':renderer,'intl':manifest['renderer_intl_asset'],'icon':manifest['renderer_icon_asset']})
 identity=json.loads(archive.read('package.json'))
 identity.update({'name':manifest['application_name'],'productName':branding.PRODUCT,'description':branding.PRODUCT+' desktop application'})
 replacements['package.json']=(json.dumps(identity,indent=2)+'\n').encode()
 agent_base=ROOT/manifest['agent_baseline']
 if hashlib.sha256(agent_base.read_bytes()).hexdigest()!=manifest['agent_baseline_sha256']:raise ValueError('Agent baseline hash mismatch; review upstream version before changing project.json')
 agent=skills_plugin.patch_agent(cloud.patch_agent(storage.patch_agent(agent_base.read_text())))
 output=ROOT/'runtime/build/resources';archive.write(output/'app.asar',replacements)
 (output/'glm').mkdir(parents=True,exist_ok=True);(output/'glm/zcode.cjs').write_text(agent)
 (output/'voice').mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/'src/main/voice.cjs',output/'voice/main.cjs')
 (output/'activity').mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/'src/main/activity.cjs',output/'activity/main.cjs')
 catalog_source=ROOT/'app/resources/config/provider/zcode-builtin.json'
 if not catalog_source.exists():raise ValueError('Installed provider catalog is missing: '+str(catalog_source))
 (output/'config/provider').mkdir(parents=True,exist_ok=True)
 (output/'config/provider/zcode-builtin.json').write_text(catalog.patch_catalog(catalog_source.read_text()))
 for name,source in branding.PACKAGED_ICONS.items():shutil.copy2(branding.ICON_DIR/source,output/name)
 skills,pack_files=stage_skill_pack(ROOT/'src/skills',ROOT/'app/resources/glm/packages'/skills_plugin.PACK_DIR,output)
 subprocess.run(['node',str(ROOT/'services/mcp/stage.cjs'),str(output/'mcp')],check=True,cwd=ROOT)
 mcp_files=sorted(str(path.relative_to(output)) for path in (output/'mcp').rglob('*') if path.is_file())
 files=['app.asar','glm/zcode.cjs','voice/main.cjs','activity/main.cjs','config/provider/zcode-builtin.json',*branding.PACKAGED_ICONS,*pack_files,*mcp_files]
 proof={'application_name':manifest['application_name'],'patched_assets':sorted(replacements),
        'bundled_skill_pack':skills_plugin.PACK_DIR,'bundled_skills':skills,
        'sha256':{name:hashlib.sha256((output/name).read_bytes()).hexdigest() for name in files}}
 (output/'build-manifest.json').write_text(json.dumps(proof,indent=2)+'\n')
 print('Build staged:',output/'app.asar')
if __name__=='__main__':main()
