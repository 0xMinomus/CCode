function fedoraCuaLocal(p){return typeof navigator!=="undefined"&&/Linux/.test(navigator.userAgent)&&!p.remoteSessionId&&!p.remoteTarget&&!(p.workspaceIdentity?.trim()&&Xa(p.workspaceIdentity.trim()));}
function useFedoraCua(p){
 const services=Dg();
 const server=Iv(s=>s.servers.find(x=>x.name==="fedora-desktop"&&x.source==="ccodeagentmcp"));
 const [busy,setBusy]=Q.useState(false),[error,setError]=Q.useState(null);
 Q.useEffect(()=>{Iv.getState().ensureLoadedForWorkspace(p.workspacePath,services.mcpSyncService,p.workspaceIdentity).catch(e=>setError(String(e)));},[p.workspacePath,p.workspaceIdentity,services.mcpSyncService]);
 const toggle=async enabled=>{if(!server)return;setBusy(true);setError(null);try{await Iv.getState().toggleServer(server.id,enabled);}catch(e){setError(String(e));}finally{setBusy(false);}};
 return {server,busy,error,toggle};
}
function FedoraCuaSettings(p){
 const {server,busy,error,toggle}=useFedoraCua(p),{settings,update}=gv();
 const enabled=!!server?.enabled;
 return $.jsxs("div",{className:"space-y-4",children:[
 $.jsxs(Q1,{children:[
 $.jsx(Z1,{label:"Computer Use — Linux",description:"Drives the whole desktop through screen-mcp and Fedora's screen-sharing permission.",control:$.jsx(Xx,{"aria-label":"Enable Linux Computer Use",checked:enabled,disabled:busy||!server,onCheckedChange:toggle})}),
 $.jsx(Z1,{label:"Show the shortcut in the chat box",description:"Opens the Computer Use panel from the chat box.",control:$.jsx(Xx,{"aria-label":"Show Linux Computer Use shortcut",checked:settings?.computerUseComposerEntryHidden===false,disabled:!enabled,onCheckedChange:v=>update({computerUseComposerEntryHidden:!v})})})
 ]}),
 $.jsxs("div",{className:"rounded-lg border border-border p-4 space-y-2",children:[
 $.jsx("p",{className:"font-medium",children:!server?"Backend not found":enabled?"Computer Use is on":"Computer Use is off"}),
 $.jsx("p",{className:"text-ui-sm text-foreground-subtle",children:server?.status==="connected"?"Backend connected · "+(server.toolCount??22)+" tools":enabled?"fedora-desktop is available to new chats. If you just enabled it, start a new chat.":"Turn it on to expose the desktop tools to new chats."}),
 $.jsx("p",{className:"text-ui-sm text-foreground-subtle",children:"On first use, pick a screen and allow mouse/keyboard in the Fedora dialog. Moving the mouse yourself stops the agent's control."}),
 $.jsx("p",{className:"text-ui-sm text-foreground-subtle",children:"Use a vision model. Example: use fedora-desktop to take a screenshot, then open Files."}),
 $.jsx("p",{className:"text-ui-xs text-foreground-subtlest",children:"Local Linux integration: this panel drives the fedora-desktop MCP; the macOS/Windows helper backends are not used."}),
 error?$.jsx("p",{className:"text-destructive",children:error}):null
 ]})
 ]});
}
function FedoraCuaShortcut(p){
 const {server}=useFedoraCua(p),{settings}=gv(),open=A_(s=>s.openSettingsTab);
 if(settings?.computerUseComposerEntryHidden!==false||p.isWebRemoteControl)return null;
 return $.jsx(uA,{title:"Computer Use Linux · "+(server?.enabled?"on":"off"),children:$.jsxs(X,{type:"button",variant:"ghost",size:"default","data-testid":"fedora-computer-use-shortcut",className:"h-7 rounded-lg px-1.5 gap-1",onClick:()=>{MS("computerUse");open();},children:[$.jsx($ae,{className:"size-4","aria-hidden":true}),$.jsx("span",{children:"Computer Use"})]})});
}
