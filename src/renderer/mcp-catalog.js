// Optional MCP servers are rendered as rows of the native "Installed servers"
// list: the same grid, icon tile, and trailing control slot as a native row.
// A catalog row shows Install; once the server is written to the workspace MCP
// config the native row (with its on/off switch) takes over and this row drops out.
const CCodeMcpCatalog={
 useEntries(){
  const api=typeof window==='undefined'?null:window.ccodeMcpCatalog;
  const [state,setState]=Q.useState({status:'loading',items:[]});
  const request=Q.useRef(0),live=Q.useRef(false);
  const reload=Q.useCallback(async()=>{
   const version=++request.current;
   try{
    if(!api)throw Error('MCP catalog bridge is unavailable.');
    const entries=await api.list();
    if(!Array.isArray(entries))throw Error('MCP catalog returned an invalid server list.');
    if(live.current&&version===request.current)setState({status:'ready',items:entries});
   }catch(error){
    if(live.current&&version===request.current)setState({status:'error',items:[],error:CCodeMcpCatalogMessage(error)});
   }
  },[api]);
  Q.useEffect(()=>{live.current=true;void reload();return()=>{live.current=false;request.current+=1};},[reload]);
  return state.status==='ready'?{status:'ready',items:state.items,reload}:{status:state.status,error:state.error,reload};
 }
};
function CCodeMcpCatalogRow({entry,onInstalled}){
 const [busy,setBusy]=Q.useState(false),[error,setError]=Q.useState(null);
 async function install(){
  if(busy)return;
  setBusy(true);setError(null);
  try{
   const api=typeof window==='undefined'?null:window.ccodeMcpCatalog;
   if(!api)throw Error('MCP catalog bridge is unavailable.');
   const result=await api.install({id:entry.id});
   if(!result?.ok)throw Error(result?.error||'Installation failed.');
   await onInstalled();
   // The installed server belongs to the native list; run its own Refresh so the
   // row with the on/off switch appears right away.
   document.querySelector('[data-mcp-plugin-installed-actions="true"] button[data-slot="tooltip-trigger"]')?.click();
  }catch(failure){setError(CCodeMcpCatalogMessage(failure));}
  finally{setBusy(false);}
 }
 return $.jsxs('div',{className:'grid cursor-default grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3 px-4 py-3 transition-colors hover:bg-hover','data-testid':`mcp-catalog-${entry.id}`,children:[
  $.jsx('div',{className:'flex size-9 shrink-0 items-center justify-center rounded-lg bg-background text-foreground-subtle','aria-hidden':true,children:$.jsx(Ps,{className:'size-4'})}),
  $.jsxs('div',{className:'min-w-0',children:[
   $.jsxs('div',{className:'flex flex-wrap items-center gap-2',children:[
    $.jsx('span',{className:'truncate text-ui-base font-medium text-foreground',children:entry.name}),
    entry.default?$.jsx('span',{className:'inline-flex rounded-md bg-surface px-1.5 py-0.5 text-ui-sm text-foreground-subtle ring-1 ring-border',children:'Default'}):null]}),
   $.jsx('div',{className:'mt-1 truncate text-ui-sm text-foreground-subtle',children:entry.description}),
   error?$.jsx('div',{role:'alert',className:'mt-1 text-ui-sm text-destructive',style:{overflowWrap:'anywhere'},children:error}):null]}),
  $.jsx('div',{className:'flex shrink-0 items-center gap-2',children:$.jsx(X,{type:'button',variant:'outline',size:'sm',disabled:busy,'aria-label':`Install ${entry.name}`,onClick:()=>void install(),children:busy?'Installing…':'Install'})})]});
}
function CCodeMcpCatalogMessage(value){
 return String(value?.message??value);
}
if(typeof module!=='undefined'&&module.exports)module.exports={CCodeMcpCatalog,CCodeMcpCatalogRow,CCodeMcpCatalogMessage};
