function CCodeTokenSaversPanel(){
 const defaults={version:1,rtk:{enabled:false},caveman:{enabled:false,level:'full'},ponytail:{enabled:false,level:'full'}};
 const [state,setState]=Q.useState({status:'loading',settings:defaults,rtk:null,error:null,refreshing:false});
 const [saving,setSaving]=Q.useState(false);
 const [installing,setInstalling]=Q.useState(false);
 const [installError,setInstallError]=Q.useState(null);
 Q.useEffect(()=>{
  let live=true;
  (async()=>{
   const api=typeof window==='undefined'?null:window.ccodeTokenSavers;
   if(!api){if(live)setState(s=>({...s,status:'error',error:'Token savers bridge is unavailable.'}));return;}
   try{const data=await api.snapshot();if(live)setState({status:'ready',settings:data.settings??defaults,rtk:data.rtk??null,error:data.settingsError??null,refreshing:false});}
   catch(error){if(live)setState(s=>({...s,status:'error',error:String(error?.message??error)}));}
  })();
  return()=>{live=false};
 },[]);
 const refresh=async()=>{
  const api=typeof window==='undefined'?null:window.ccodeTokenSavers;
  if(!api)return;
  setState(s=>({...s,refreshing:true,error:null}));
  try{const data=await api.snapshot();setState(s=>({...s,status:'ready',settings:data.settings??s.settings,rtk:data.rtk??null,error:data.settingsError??null,refreshing:false}));}
  catch(error){setState(s=>({...s,error:String(error?.message??error),refreshing:false}));}
 };
 const save=async settings=>{
  const api=typeof window==='undefined'?null:window.ccodeTokenSavers;
  if(!api)return;
  setSaving(true);setState(s=>({...s,error:null}));
  try{const saved=await api.save(settings);setState(s=>({...s,settings:saved}));}
  catch(error){setState(s=>({...s,error:String(error?.message??error)}));}
  finally{setSaving(false);}
 };
 const installRtk=async()=>{
  const api=typeof window==='undefined'?null:window.ccodeTokenSavers;
  if(!api?.installRtk){setInstallError('RTK installation is unavailable. Restart CCode and try again.');return;}
  setInstalling(true);setInstallError(null);
  try{const data=await api.installRtk();setState(s=>({...s,status:'ready',settings:data.settings??s.settings,rtk:data.rtk??null,error:data.settingsError??null}));}
  catch(error){setInstallError(String(error?.message??error).replace(/^Error invoking remote method '[^']+': Error: /,''));}
  finally{setInstalling(false);}
 };
 if(state.status==='loading')return $.jsx('div',{className:'text-ui-base text-foreground-subtle',children:'Loading Token savers…'});
 if(state.status==='error')return $.jsx('div',{className:'text-ui-base text-foreground-subtle',children:state.error});
 const settings=state.settings??defaults,rtk=state.rtk??{available:false,daily:[],error:'RTK status is unavailable.'};
 const series=CCodeTokenSaversChartSeries(rtk.daily??[]),max=series.reduce((value,day)=>Math.max(value,day.savedTokens),0),last30=series.reduce((sum,day)=>sum+day.savedTokens,0);
 const updateFeature=(name,enabled)=>save({...settings,[name]:{...settings[name],enabled}});
 const updateLevel=(name,level)=>save({...settings,[name]:{...settings[name],level}});
 const ready=state.status==='ready';
 const rtkAvailable=rtk.available===true;
 const busy=saving||installing||state.refreshing;
 const installTarget=[rtk.installVersion,rtk.installEdition?'('+rtk.installEdition+')':null].filter(Boolean).join(' ');
 const installDescription=rtk.installSupported===false?'One-click installation supports Windows x64 and Linux x64 only.':'Install RTK'+(installTarget?' '+installTarget:'')+' for CCode, then enable it automatically.';
 const rtkControl=rtkAvailable?$.jsx(Xx,{'aria-label':'Enable RTK',checked:settings.rtk.enabled===true,disabled:!ready||busy,onCheckedChange:enabled=>updateFeature('rtk',enabled)}):$.jsx(X,{type:'button',variant:'outline',size:'sm','aria-label':installError?'Retry RTK installation':'Install RTK','data-testid':'ccode-token-savers-rtk-install',disabled:!ready||busy||rtk.installSupported===false,onClick:installRtk,children:installing?'Installing…':installError?'Retry':'Install'});
 return $.jsxs('div',{className:'space-y-4','data-testid':'ccode-token-savers-panel',children:[
  $.jsx('p',{className:'text-ui-sm text-foreground-subtle',children:'Choose which local token-saving tools shape shell commands and agent instructions.'}),
  $.jsxs(Q1,{children:[
   $.jsx(Z1,{label:'RTK',description:rtkAvailable?'RTK rewrites supported commands; no-match preserves CCode approval, while errors stop execution.':installDescription,control:rtkControl}),
   $.jsx(Z1,{label:'Caveman',description:'Apply a concise response style to agent instructions. Lite, Full, or Ultra compression.',control:CCodeTokenSaversFeatureControl('Caveman',settings.caveman,level=>updateLevel('caveman',level),enabled=>updateFeature('caveman',enabled),!ready||busy)}),
   $.jsx(Z1,{label:'Ponytail',description:'Avoid unnecessary work while preserving correctness and safety. Lite, Full, or Ultra pruning.',control:CCodeTokenSaversFeatureControl('Ponytail',settings.ponytail,level=>updateLevel('ponytail',level),enabled=>updateFeature('ponytail',enabled),!ready||busy)})
  ]}),
  installError?$.jsx('p',{role:'alert',className:'text-ui-sm text-destructive',style:{overflowWrap:'anywhere'},'data-testid':'ccode-token-savers-install-error',children:installError}):null,
  installing?$.jsx('p',{role:'status',className:'text-ui-sm text-foreground-subtle',children:'Downloading and verifying RTK…'}):null,
  state.error?$.jsx('p',{className:'text-ui-sm text-destructive','data-testid':'ccode-token-savers-error',children:state.error}):null,
  $.jsxs('div',{className:'rounded-xl bg-surface px-4 py-3','data-testid':'ccode-token-savers-chart',children:[
   $.jsxs('div',{className:'mb-3 flex items-start justify-between gap-3',children:[
    $.jsxs('div',{className:'min-w-0',children:[
     $.jsx('h3',{className:'text-ui-base font-medium text-foreground',children:'Estimated tokens saved'}),
     $.jsx('p',{className:'mt-1 text-ui-sm text-foreground-subtle',children:'RTK shell-output estimates across projects; not provider-billed model tokens.'})
    ]}),
    $.jsx('button',{type:'button','data-testid':'ccode-token-savers-refresh',disabled:busy,onClick:refresh,className:'h-7 flex-none rounded-lg px-2 text-ui-sm text-foreground-subtle transition-colors hover:bg-surface-hover hover:text-foreground disabled:opacity-50',children:state.refreshing?'Refreshing…':'Refresh'})
   ]}),
   rtk.error?$.jsx('p',{className:'py-6 text-center text-ui-sm text-foreground-subtle','data-testid':'ccode-token-savers-chart-empty',children:rtk.available?`RTK analytics unavailable: ${rtk.error}`:'Install RTK above to start tracking estimated tokens saved.'}):$.jsxs(Q.Fragment,{children:[
    $.jsxs('div',{className:'mb-3 text-ui-lg font-medium text-foreground','data-testid':'ccode-token-savers-last-30',children:[CCodeTokenSaversNumber(last30),' tokens · last 30 days']}),
    $.jsx('div',{className:'flex items-end gap-1',style:{height:'112px'},'role':'group','aria-label':'Estimated RTK tokens saved per day during the last 30 days','data-testid':'ccode-token-savers-bars',children:series.map(day=>{
     const height=max?Math.max(day.savedTokens?1:2,Math.round(day.savedTokens/max*100)):2;
     return $.jsx('div',{className:'flex min-w-0 flex-1 items-end',style:{height:'100%'},children:$.jsx(uA,{title:`${day.day}\n${CCodeTokenSaversNumber(day.savedTokens)} estimated tokens saved`,side:'top',children:$.jsx('div',{role:'img','aria-label':`${day.day}: ${day.savedTokens} estimated tokens saved`,'data-testid':`ccode-token-savers-bar-${day.day}`,className:'w-full rounded-[4px] border border-transparent transition-transform hover:scale-110 hover:border-border-hover',style:{height:`${height}%`,backgroundColor:day.savedTokens?'var(--color-usage-heatmap-3)':'var(--color-usage-heatmap-0)'}})})},day.day);
    })}),
    $.jsx('div',{className:'mt-2 flex justify-between text-ui-xs text-foreground-subtlest','aria-hidden':'true',children:[series[0]?.day,series[7]?.day,series[14]?.day,series[21]?.day,series[29]?.day].filter(Boolean).map(day=>$.jsx('span',{children:day.slice(5)},day))})
   ]})
  ]})
 ]});
}
function CCodeTokenSaversFeatureControl(name,feature,onLevel,onEnabled,busy){
 const enabled=feature.enabled===true;
 return $.jsxs('div',{className:'flex flex-none items-center gap-2',children:[
  CCodeTokenSaversModes(name,feature.level,onLevel,busy||!enabled,!enabled),
  $.jsx(Xx,{'aria-label':`Enable ${name}`,checked:enabled,disabled:busy,onCheckedChange:onEnabled})
 ]});
}
function CCodeTokenSaversModes(name,value,onChange,disabled,dimmed){
 return $.jsx('div',{role:'group','aria-label':`${name} level`,className:'flex flex-none items-center gap-0.5 rounded-full bg-surface p-0.5'+(dimmed?' opacity-50':''),children:['lite','full','ultra'].map(level=>{
  const active=value===level;
  return $.jsx('button',{type:'button','aria-pressed':active,disabled,onClick:()=>onChange(level),'data-testid':`ccode-token-savers-${name.toLowerCase()}-${level}`,className:'h-6 rounded-full px-2 text-ui-sm font-medium transition-colors '+(active?'bg-background text-foreground':'text-foreground-subtle hover:text-foreground'),children:level[0].toUpperCase()+level.slice(1)},level);
 })});
}
function CCodeTokenSaversChartSeries(rows,today=CCodeTokenSaversDayKey(new Date())){
 const counts=new Map();
 for(const row of rows??[]){
  if(typeof row?.day!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(row.day))continue;
  const value=Number(row.savedTokens);
  if(!Number.isFinite(value)||value<0)continue;
  counts.set(row.day,(counts.get(row.day)??0)+Math.floor(value));
 }
 const [year,month,day]=today.split('-').map(Number),cursor=new Date(year,month-1,day-29),series=[];
 for(let index=0;index<30;index++){
  const key=CCodeTokenSaversDayKey(cursor);
  series.push({day:key,savedTokens:counts.get(key)??0});
  cursor.setDate(cursor.getDate()+1);
 }
 return series;
}
function CCodeTokenSaversDayKey(date){
 const pad=value=>String(value).padStart(2,'0');
 return `${date.getFullYear()}-${pad(date.getMonth()+1)}-${pad(date.getDate())}`;
}
function CCodeTokenSaversNumber(value){
 const total=Number(value)||0;
 return new Intl.NumberFormat(undefined,{notation:total>=1000?'compact':'standard',maximumFractionDigits:total>=1000?1:0}).format(total);
}
if(typeof module!=='undefined'&&module.exports)module.exports={CCodeTokenSaversPanel,CCodeTokenSaversModes,CCodeTokenSaversChartSeries,CCodeTokenSaversDayKey,CCodeTokenSaversNumber};
