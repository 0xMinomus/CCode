function linuxCuaLocal(p){return typeof navigator!=="undefined"&&/Linux/.test(navigator.userAgent)&&!p.remoteSessionId&&!p.remoteTarget&&!(p.workspaceIdentity?.trim()&&Xa(p.workspaceIdentity.trim()));}
function useLinuxCua(p){
 const services=Dg();
 // `fedora-desktop` is the pre-rename name; installs that predate the rename keep working.
 const server=Iv(s=>s.servers.find(x=>(x.name==="linux-desktop"||x.name==="fedora-desktop")&&x.source==="ccodeagentmcp"));
 const [busy,setBusy]=Q.useState(false),[error,setError]=Q.useState(null);
 Q.useEffect(()=>{Iv.getState().ensureLoadedForWorkspace(p.workspacePath,services.mcpSyncService,p.workspaceIdentity).catch(e=>setError(String(e)));},[p.workspacePath,p.workspaceIdentity,services.mcpSyncService]);
 const toggle=async enabled=>{if(!server)return;setBusy(true);setError(null);try{await Iv.getState().toggleServer(server.id,enabled);}catch(e){setError(String(e));}finally{setBusy(false);}};
 return {server,busy,error,toggle};
}
function LinuxCuaSettings(p){
 const {server,busy,error,toggle}=useLinuxCua(p),{settings,update}=gv();
 const enabled=!!server?.enabled;
 return $.jsxs("div",{className:"space-y-4",children:[
 $.jsxs(Q1,{children:[
 $.jsx(Z1,{label:"Enable Computer Use",description:"Turning this on makes desktop tools available to new chats.",control:server?$.jsx(Xx,{"aria-label":"Enable Linux Computer Use",checked:enabled,disabled:busy,onCheckedChange:toggle}):$.jsx("span",{className:"text-ui-sm text-foreground-subtle",children:"Backend not found"})}),
 $.jsx(Z1,{label:"Show Computer Use button in the composer",description:"When off, the composer button is hidden.",control:$.jsx(Xx,{"aria-label":"Show Linux Computer Use shortcut",checked:settings?.computerUseComposerEntryHidden===false,disabled:!enabled,onCheckedChange:v=>update({computerUseComposerEntryHidden:!v})})})
 ]}),
 error?$.jsx("p",{className:"text-destructive",children:error}):null
 ]});
}
function LinuxCuaShortcut(p){
 const {server}=useLinuxCua(p),{settings}=gv(),open=A_(s=>s.openSettingsTab);
 if(settings?.computerUseComposerEntryHidden!==false||p.isWebRemoteControl)return null;
 return $.jsx(uA,{title:"Computer Use Linux · "+(server?.enabled?"on":"off"),children:$.jsxs(X,{type:"button",variant:"ghost",size:"default","data-testid":"linux-computer-use-shortcut",className:"h-7 rounded-lg px-1.5 gap-1",onClick:()=>{MS("computerUse");open();},children:[$.jsx($ae,{className:"size-4","aria-hidden":true}),$.jsx("span",{children:"Computer Use"})]})});
}
