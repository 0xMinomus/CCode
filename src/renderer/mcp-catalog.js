function CCodeMcpCatalog({local,scope,searchQuery='',onInstalled}){
 const nativeServers=Iv(state=>state.nativeServers);
 const enabledStates=Iv(state=>state.enabledStates);
 const [catalog,setCatalog]=Q.useState({status:'loading',entries:[]});
 const [pending,setPending]=Q.useState(null);
 const [results,setResults]=Q.useState({});
 const live=Q.useRef(false),request=Q.useRef(0),inFlight=Q.useRef(false);
 const visible=local&&scope==='user';
 const api=typeof window==='undefined'?null:window.ccodeMcpCatalog;
 const refresh=Q.useCallback(async()=>{
  const version=++request.current;
  if(live.current)setCatalog(previous=>({...previous,status:previous.entries.length?'refreshing':'loading',error:undefined}));
  try{
   if(!api)throw Error('MCP catalog bridge is unavailable.');
   const entries=await api.list();
   if(!Array.isArray(entries))throw Error('MCP catalog returned an invalid server list.');
   if(live.current&&version===request.current)setCatalog({status:'ready',entries});
  }catch(error){
   if(live.current&&version===request.current)setCatalog(previous=>({...previous,status:'error',error:CCodeMcpCatalogMessage(error)}));
  }
 },[api]);
 Q.useEffect(()=>{live.current=true;return()=>{live.current=false;request.current+=1};},[]);
 Q.useEffect(()=>{if(visible)void refresh();},[visible,nativeServers,enabledStates,refresh]);
 async function run(entry,action,config={}){
  if(inFlight.current)return;
  inFlight.current=true;
  setPending({id:entry.id,action});
  setResults(previous=>({...previous,[entry.id]:null}));
  const secrets=(entry.configFields??[]).filter(field=>field.type==='password').map(field=>config[field.key]).filter(Boolean);
  try{
   if(!api)throw Error('MCP catalog bridge is unavailable.');
   const result=await api[action](action==='install'?{id:entry.id,config}:{id:entry.id});
   if(!result?.ok)throw Error(result?.error||result?.message||`${action==='install'?'Installation':'Tool test'} failed.`);
   let message=action==='install'?'Installed. Use Test to run a tool.':result.message||'Tool test completed.';
   if(action==='install'&&live.current){
    try{await onInstalled();}
    catch(error){message+=' '+CCodeMcpCatalogMessage(error,secrets);}
   }
   if(live.current)setResults(previous=>({...previous,[entry.id]:{ok:true,message:CCodeMcpCatalogMessage(message,secrets)}}));
  }catch(error){
   if(live.current)setResults(previous=>({...previous,[entry.id]:{ok:false,message:CCodeMcpCatalogMessage(error,secrets)}}));
  }finally{
   inFlight.current=false;
   if(live.current){await refresh();if(live.current)setPending(null);}
  }
 }
 if(!visible)return null;
 const query=searchQuery.trim().toLowerCase();
 const entries=catalog.entries.filter(entry=>!query||`${entry.name} ${entry.description}`.toLowerCase().includes(query));
 return $.jsxs('section',{'data-testid':'ccode-mcp-catalog',className:'space-y-4',children:[
  $.jsx(H7,{title:'Server catalog',count:entries.length,actions:$.jsx(X,{type:'button',variant:'outline',size:'sm',disabled:!!pending||catalog.status==='loading'||catalog.status==='refreshing',onClick:()=>void refresh(),children:catalog.status==='loading'||catalog.status==='refreshing'?'Refreshing…':'Refresh'})}),
  $.jsx('p',{className:'text-ui-base text-foreground',children:'Default servers are bundled with CCode. Install optional servers here; manage enabled servers in the native list below.'}),
  catalog.status==='loading'?$.jsx('p',{role:'status',className:'text-ui-base text-foreground',children:'Loading server catalog…'}):null,
  catalog.status==='error'?$.jsx('p',{role:'alert',className:'text-ui-base text-foreground',style:{overflowWrap:'anywhere'},children:catalog.error}):null,
  catalog.status==='ready'&&entries.length===0?$.jsx('p',{role:'status',className:'text-ui-base text-foreground',children:query?'No catalog servers match your search.':'No catalog servers are available.'}):null,
  entries.length?$.jsx('div',{className:'overflow-hidden rounded-xl border border-border bg-card',children:entries.map(entry=>$.jsx(CCodeMcpCatalogRow,{entry,pending,result:results[entry.id],run},entry.id))}):null]});
}
function CCodeMcpCatalogRow({entry,pending,result,run}){
 const [editing,setEditing]=Q.useState(false);
 const [config,setConfig]=Q.useState({});
 const trigger=Q.useRef(null);
 const fields=entry.configFields??[];
 const busy=!!pending;
 const active=pending?.id===entry.id;
 function close(){setEditing(false);setConfig({});trigger.current?.focus();}
 function install(){
  const values=config;
  setConfig({});setEditing(false);
  void run(entry,'install',values);
 }
 Q.useEffect(()=>{if(entry.installed){setEditing(false);setConfig({});}},[entry.installed]);
 const status=(entry.default?'Default':'Optional')+' · '+(entry.installed?'Installed':'Not installed')+(entry.status==='disabled'?' · Disabled':'');
 const progress=pending?.action==='install'?'Installing…':'Testing…';
 return $.jsxs('div',{'data-testid':`ccode-mcp-${entry.id}`,className:'border-b border-border px-4 py-3',children:[
  $.jsxs('div',{className:'flex flex-wrap items-center justify-between gap-3',children:[
   $.jsxs('div',{className:'min-w-0 flex-1',children:[
    $.jsx('h4',{className:'text-ui-base font-medium text-foreground',children:entry.name}),
    $.jsx('p',{className:'text-ui-sm text-foreground',style:{overflowWrap:'anywhere'},children:entry.description}),
    $.jsx('p',{className:'mt-1 text-ui-sm text-foreground',children:status})]}),
   entry.installed?$.jsx(X,{type:'button',variant:'outline',size:'sm',disabled:busy,onClick:()=>void run(entry,'test'),'aria-label':`Test ${entry.name}`,children:active?progress:'Test'}):$.jsx(X,{ref:trigger,type:'button',variant:'outline',size:'sm',disabled:busy,'aria-label':`Install ${entry.name}`,'aria-expanded':editing,'aria-controls':`ccode-mcp-config-${entry.id}`,onClick:()=>{if(editing)close();else if(fields.length)setEditing(true);else void run(entry,'install');},children:active?progress:'Install'})]}),
  editing?$.jsxs('form',{id:`ccode-mcp-config-${entry.id}`,className:'mt-3 space-y-3',onSubmit:event=>{event.preventDefault();if(!busy)install();},onKeyDown:event=>{if(event.key==='Escape'&&!busy){event.preventDefault();event.stopPropagation();close();}},children:[
   ...fields.map((field,index)=>$.jsxs('div',{className:'space-y-1.5',children:[
    $.jsx(B7,{htmlFor:`ccode-mcp-${entry.id}-${field.key}`,children:field.label+(field.required?'':' (optional)')}),
    $.jsx(Yo,{id:`ccode-mcp-${entry.id}-${field.key}`,name:field.key,size:'lg',type:field.type==='password'?'password':'text',required:field.required,autoFocus:index===0,autoComplete:'off',spellCheck:false,disabled:busy,placeholder:field.placeholder??'',value:config[field.key]??'',onChange:event=>{const value=event.target.value;setConfig(previous=>({...previous,[field.key]:value}));}})]},field.key)),
   $.jsxs('div',{className:'flex flex-wrap items-center gap-2',children:[
    $.jsx(X,{type:'submit',size:'sm',disabled:busy,children:'Install'}),
    $.jsx(X,{type:'button',variant:'ghost',size:'sm',disabled:busy,onClick:close,children:'Cancel'})]})]}):null,
  active?$.jsx('p',{role:'status',className:'mt-1 text-ui-sm text-foreground',children:pending.action==='install'?'Installing server…':'Running a server tool…'}):null,
  result?$.jsx('p',{role:result.ok?'status':'alert',className:'mt-1 text-ui-sm text-foreground',style:{overflowWrap:'anywhere'},children:(result.ok?'':'Failed: ')+result.message}):entry.error?$.jsx('p',{role:'alert',className:'mt-1 text-ui-sm text-foreground',style:{overflowWrap:'anywhere'},children:entry.error}):null]});
}
function CCodeMcpCatalogMessage(value,secrets=[]){
 let message=String(value?.message??value);
 for(const secret of secrets)message=message.split(String(secret)).join('[redacted]');
 return message;
}
if(typeof module!=='undefined'&&module.exports)module.exports={CCodeMcpCatalog,CCodeMcpCatalogRow,CCodeMcpCatalogMessage};
