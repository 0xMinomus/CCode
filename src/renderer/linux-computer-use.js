function fedoraCuaLocal(p){return typeof navigator!=="undefined"&&/Linux/.test(navigator.userAgent)&&!p.remoteSessionId&&!p.remoteTarget&&!(p.workspaceIdentity?.trim()&&Xa(p.workspaceIdentity.trim()));}
function useFedoraCua(p){
 const services=Dg();
 const server=Iv(s=>s.servers.find(x=>x.name==="fedora-desktop"&&x.source==="zcodeagentmcp"));
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
 $.jsx(Z1,{label:"Computer Use — Linux",description:"Kontrol seluruh desktop melalui screen-mcp dan izin berbagi layar Fedora.",control:$.jsx(Xx,{"aria-label":"Enable Linux Computer Use",checked:enabled,disabled:busy||!server,onCheckedChange:toggle})}),
 $.jsx(Z1,{label:"Tampilkan pintasan di kotak chat",description:"Buka panel Computer Use dari kotak chat.",control:$.jsx(Xx,{"aria-label":"Show Linux Computer Use shortcut",checked:settings?.computerUseComposerEntryHidden===false,disabled:!enabled,onCheckedChange:v=>update({computerUseComposerEntryHidden:!v})})})
 ]}),
 $.jsxs("div",{className:"rounded-lg border border-border p-4 space-y-2",children:[
 $.jsx("p",{className:"font-medium",children:!server?"Backend belum ditemukan":enabled?"Computer Use aktif":"Computer Use nonaktif"}),
 $.jsx("p",{className:"text-ui-sm text-foreground-subtle",children:server?.status==="connected"?"Backend terhubung · "+(server.toolCount??22)+" tools":enabled?"fedora-desktop tersedia untuk chat baru. Jika baru diaktifkan, mulai chat baru.":"Aktifkan untuk menyediakan tools desktop di chat baru."}),
 $.jsx("p",{className:"text-ui-sm text-foreground-subtle",children:"Saat pertama digunakan, pilih layar dan izinkan mouse/keyboard di dialog Fedora. Gerakan mouse kamu dapat menghentikan kontrol agent."}),
 $.jsx("p",{className:"text-ui-sm text-foreground-subtle",children:"Gunakan model Vision. Contoh: Gunakan fedora-desktop untuk mengambil screenshot lalu buka Files."}),
 $.jsx("p",{className:"text-ui-xs text-foreground-subtlest",children:"Integrasi Linux lokal: panel ini mengendalikan MCP fedora-desktop; backend helper macOS/Windows tidak digunakan."}),
 error?$.jsx("p",{className:"text-destructive",children:error}):null
 ]})
 ]});
}
function FedoraCuaShortcut(p){
 const {server}=useFedoraCua(p),{settings}=gv(),open=A_(s=>s.openSettingsTab);
 if(settings?.computerUseComposerEntryHidden!==false||p.isWebRemoteControl)return null;
 return $.jsx(uA,{title:"Computer Use Linux · "+(server?.enabled?"aktif":"nonaktif"),children:$.jsxs(X,{type:"button",variant:"ghost",size:"default","data-testid":"fedora-computer-use-shortcut",className:"h-7 rounded-lg px-1.5 gap-1",onClick:()=>{MS("computerUse");open();},children:[$.jsx($ae,{className:"size-4","aria-hidden":true}),$.jsx("span",{children:"Computer Use"})]})});
}
