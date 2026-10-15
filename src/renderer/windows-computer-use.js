function windowsCuaLocal(p){return typeof navigator!=="undefined"&&/Windows/.test(navigator.userAgent)&&!p.remoteSessionId&&!p.remoteTarget&&!(p.workspaceIdentity?.trim()&&Xa(p.workspaceIdentity.trim()));}
const WINDOWS_CUA_TOOLS=["screen_screenshot","screen_read_text","screen_click(element or x,y)","screen_type","screen_key","screen_scroll","screen_wait_text","screen_verify","screen_sense","screen_focus"];
function useWindowsCua(p){
 const services=Dg();
 const server=Iv(s=>s.servers.find(x=>x.name==="windows-desktop"&&x.source==="ccodeagentmcp"));
 const [busy,setBusy]=Q.useState(false),[error,setError]=Q.useState(null);
 Q.useEffect(()=>{Iv.getState().ensureLoadedForWorkspace(p.workspacePath,services.mcpSyncService,p.workspaceIdentity).catch(e=>setError(String(e)));},[p.workspacePath,p.workspaceIdentity,services.mcpSyncService]);
 const toggle=async enabled=>{if(!server)return;setBusy(true);setError(null);try{await Iv.getState().toggleServer(server.id,enabled);}catch(e){setError(String(e));}finally{setBusy(false);}};
 return {server,busy,error,toggle};
}
function WindowsCuaSettings(p){
 const {server,busy,error,toggle}=useWindowsCua(p),enabled=!!server?.enabled;
 return $.jsxs("div",{className:"space-y-4",children:[
 $.jsxs(Q1,{children:[
 $.jsx(Z1,{label:"Computer Use — Windows",description:"Drives the Windows desktop through the windows-desktop MCP server: screenshots, UI Automation text and elements, SendInput, and the same pointer-takeover guard as Linux.",control:server?$.jsx(Xx,{"aria-label":"Enable Windows Computer Use",checked:enabled,disabled:busy,onCheckedChange:toggle}):$.jsx("span",{className:"text-ui-sm text-foreground-subtle",children:"No server entry in this installation"})})
 ]}),
 $.jsxs("div",{className:"rounded-lg border border-border p-4 space-y-2",children:[
 $.jsx("p",{className:"font-medium",children:!server?"Backend not found":enabled?"Computer Use is on":"Computer Use is off"}),
 $.jsx("p",{className:"text-ui-sm text-foreground-subtle",children:server?server.status==="connected"?"Backend connected · "+(server.toolCount??WINDOWS_CUA_TOOLS.length)+" tools":enabled?"windows-desktop is available to new chats. If you just enabled it, start a new chat.":"Turn it on to expose the desktop tools to new chats.":"This installation has no windows-desktop server, so there is nothing here to switch on. Reinstall CCode, or add the server yourself in the MCP server list, then reopen this page."}),
 $.jsx("p",{className:"text-ui-sm text-foreground-subtle",children:"Tools: "+WINDOWS_CUA_TOOLS.join(", ")}),
 $.jsx("p",{className:"text-ui-sm text-foreground-subtle",children:"Windows has no portal permission dialog. Screen capture runs directly, so there is no screen-picker or remote-control prompt to approve before the first action."}),
 $.jsx("p",{className:"text-ui-sm text-foreground-subtle",children:"Elevated windows are out of reach. The Windows integrity policy (UIPI) blocks input from this normal-privilege process, so Task Manager, an elevated console, and the UAC secure desktop cannot be driven. No force mode pierces that, and none is offered."}),
 $.jsx("p",{className:"text-ui-sm text-foreground-subtle",children:"Moving the mouse yourself cancels a pending action with STOPPED and the agent must yield to you. A pointer you parked elsewhere is not treated as takeover."}),
 $.jsx("p",{className:"text-ui-sm text-foreground-subtle",children:"Multi-monitor and mixed-DPI behaviour is not verified by the build: test on this machine before relying on it."}),
 $.jsx("p",{className:"text-ui-sm text-foreground-subtle",children:"Use a vision model. Example: use windows-desktop to read the screen as text, then click the element it reports."}),
 $.jsx("p",{className:"text-ui-xs text-foreground-subtlest",children:"Local Windows integration: this switch is the windows-desktop entry you also see in Settings → MCP Servers; same backend, one state, either switch works."}),
 error?$.jsx("p",{className:"text-destructive",children:error}):null
 ]})]});
}
