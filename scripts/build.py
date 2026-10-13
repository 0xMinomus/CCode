#!/usr/bin/python3
"""Build the patch from a pinned upstream archive; output is staged, never live."""
import hashlib,json,pathlib,shutil,sys
from asar import Archive
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from local_only import replace_once
from local_only import storage,cloud,catalog
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
 main=archive.read(manifest['main_asset']).decode()+'''\nimport {app as zcodeVoiceApp,ipcMain as zcodeVoiceIpcMain} from "electron";
import {createRequire as zcodeVoiceCreateRequire} from "node:module";
const zcodeVoiceRequire=zcodeVoiceCreateRequire(import.meta.url);
if(process.platform==="linux"){zcodeVoiceRequire(process.resourcesPath+"/voice/main.cjs").register({app:zcodeVoiceApp,ipcMain:zcodeVoiceIpcMain});}
zcodeVoiceRequire(process.resourcesPath+"/activity/main.cjs").register({app:zcodeVoiceApp,ipcMain:zcodeVoiceIpcMain});
'''
 preload=archive.read(manifest['preload_asset']).decode()+'''\n(()=>{const {contextBridge,ipcRenderer}=require("electron");contextBridge.exposeInMainWorld("zcodeVoice",{start:(options)=>ipcRenderer.invoke("zcode-voice:start",options),stop:()=>ipcRenderer.invoke("zcode-voice:stop"),cancel:()=>ipcRenderer.invoke("zcode-voice:cancel")});contextBridge.exposeInMainWorld("zcodeActivity",{summary:(options)=>ipcRenderer.invoke("zcode-activity:summary",options)});contextBridge.exposeInMainWorld("zcodeDetect",{run:()=>ipcRenderer.invoke("zcode-detect:run")});})();\n'''
 replacements={renderer:s.encode(),manifest['main_asset']:main.encode(),manifest['preload_asset']:preload.encode()}
 storage.patch_archive(archive,replacements,renderer)
 cloud.patch_archive(archive,replacements,renderer)
 identity=json.loads(archive.read('package.json'))
 identity.update({'name':manifest['application_name'],'productName':'ZCode on Steroids'})
 replacements['package.json']=(json.dumps(identity,indent=2)+'\n').encode()
 agent_base=ROOT/manifest['agent_baseline']
 if hashlib.sha256(agent_base.read_bytes()).hexdigest()!=manifest['agent_baseline_sha256']:raise ValueError('Agent baseline hash mismatch; review upstream version before changing project.json')
 agent=cloud.patch_agent(storage.patch_agent(agent_base.read_text()))
 output=ROOT/'runtime/build/resources';archive.write(output/'app.asar',replacements)
 (output/'glm').mkdir(parents=True,exist_ok=True);(output/'glm/zcode.cjs').write_text(agent)
 (output/'voice').mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/'src/main/voice.cjs',output/'voice/main.cjs')
 (output/'activity').mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/'src/main/activity.cjs',output/'activity/main.cjs')
 catalog_source=ROOT/'app/resources/config/provider/zcode-builtin.json'
 if not catalog_source.exists():raise ValueError('Installed provider catalog is missing: '+str(catalog_source))
 (output/'config/provider').mkdir(parents=True,exist_ok=True)
 (output/'config/provider/zcode-builtin.json').write_text(catalog.patch_catalog(catalog_source.read_text()))
 files=['app.asar','glm/zcode.cjs','voice/main.cjs','activity/main.cjs','config/provider/zcode-builtin.json']
 proof={'application_name':manifest['application_name'],'patched_assets':sorted(replacements),'sha256':{name:hashlib.sha256((output/name).read_bytes()).hexdigest() for name in files}}
 (output/'build-manifest.json').write_text(json.dumps(proof,indent=2)+'\n')
 print('Build staged:',output/'app.asar')
if __name__=='__main__':main()
