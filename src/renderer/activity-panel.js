// Local "Activity" page: prompt counts per day, streaks and a contribution-style
// heatmap, all computed by the main process from the local session database.
// The layout mirrors the original upstream usage page (metrics strip with dividers,
// heatmap card with a segmented range control) and reuses its theme tokens
// `--color-usage-heatmap-0..4`. No cloud, no account, no plan data.
function ZCodeActivityPanel(){
 const [state,setState]=Q.useState({status:'loading'});
 const [range,setRange]=Q.useState('12m');
 Q.useEffect(()=>{
  let live=true;
  (async()=>{
   const api=typeof window==='undefined'?null:window.zcodeActivity;
   if(!api){if(live)setState({status:'error',error:'Activity bridge is unavailable.'});return;}
   try{const data=await api.summary();if(live)setState({status:'ready',data});}
   catch(error){if(live)setState({status:'error',error:String(error?.message??error)});}
  })();
  return()=>{live=false};
 },[]);
 const data=state.data??{};
 const days=data.days??[];
 const counts=Q.useMemo(()=>{const map=new Map();for(const row of days)map.set(row.day,row.prompts);return map;},[days]);
 const todayKey=ZCodeActivityDayKey(new Date());
 const grid=Q.useMemo(()=>ZCodeActivityGrid(counts,range,todayKey),[counts,range,todayKey]);
 const rangeTotal=grid.weeks.flat().reduce((sum,cell)=>sum+(cell?.prompts??0),0);
 if(state.status==='loading')return $.jsx('div',{className:'text-ui-base text-foreground-subtle',children:'Loading local activity…'});
 if(state.status==='error')return $.jsx('div',{className:'text-ui-base text-foreground-subtle',children:state.error});
 if(data.available===false)return $.jsx('div',{className:'text-ui-base text-foreground-subtle',children:data.error||'Local activity is not available yet.'});
 const heatmapStyle={gridTemplateColumns:`repeat(${grid.weeks.length}, minmax(0, 1fr))`};
 return $.jsxs('div',{className:'space-y-4','data-testid':'zcode-activity-panel',children:[
  $.jsxs('div',{className:'flex flex-col overflow-hidden rounded-xl bg-surface sm:flex-row sm:items-center','data-testid':'zcode-activity-metrics',children:ZCodeActivityStats(data).map((stat,index)=>$.jsxs(Q.Fragment,{children:[
   index>0?$.jsx('div',{'aria-hidden':'true',className:'hidden h-7 w-px bg-border sm:block'},`divider-${stat.label}`):null,
   $.jsxs('div',{className:'min-w-0 flex-1 px-4 py-3 text-center',children:[
    $.jsx('div',{className:'truncate text-ui-lg font-medium text-foreground',children:stat.value}),
    $.jsxs('div',{className:'mt-1 flex min-w-0 items-center justify-center gap-1 text-ui-base text-foreground-subtle',children:[
     $.jsx('span',{className:'min-w-0 truncate',children:stat.label})]})]},stat.label)]},stat.label))}),
  $.jsxs('div',{className:'rounded-xl bg-surface px-3 py-3','data-testid':'zcode-activity-heatmap',children:[
   $.jsxs('div',{className:'mb-3 flex items-center justify-between gap-3',children:[
    $.jsxs('div',{className:'flex min-w-0 flex-col',children:[
     $.jsx('h3',{className:'min-w-0 truncate text-ui-base font-medium text-foreground',children:'Prompt activity'}),
     $.jsxs('div',{className:'min-w-0 truncate text-ui-sm text-foreground-subtle',children:[
      $.jsx('span',{className:'font-medium',children:ZCodeActivityNumber(rangeTotal)}),
      ` prompt${rangeTotal===1?'':'s'} · `,ZCodeActivityRangeLabel(range)]})]}),
    $.jsx('div',{className:'flex flex-wrap items-center gap-0.5 rounded-full bg-surface p-0.5','data-testid':'zcode-activity-ranges',children:[
     ZCodeActivitySegment('12m','12 months',range,setRange),
     ...(data.years??[]).map(row=>ZCodeActivitySegment(row.year,row.year,range,setRange))]})]}),
   $.jsxs('div',{children:[
    $.jsx('div',{className:'grid w-full gap-x-0.5',style:heatmapStyle,children:grid.weeks.map((week,index)=>$.jsx('div',{className:'flex min-w-0 flex-col gap-1',children:week.map((cell,row)=>cell
     ?$.jsx(ZCodeActivityCell,{cell},cell.day)
     :$.jsx('div',{className:'aspect-square w-full min-w-0'},`${index}-${row}`))},index))}),
    $.jsx('div',{className:'mt-3 grid w-full gap-x-0.5',style:heatmapStyle,children:ZCodeActivityMonthSpans(grid.months).map(group=>$.jsx('div',{'data-usage-heatmap-month-label':'true',className:'min-w-0 truncate text-ui-sm text-foreground-subtle',style:{gridColumn:`span ${group.span}`},children:group.label},group.key))})]})]})]});
}
function ZCodeActivityCell({cell}){
 const prompts=cell.prompts??0;
 return $.jsx('div',{title:`${cell.day}: ${prompts} prompt${prompts===1?'':'s'}`,
  className:'aspect-square w-full min-w-0 rounded-[4px] border transition-transform hover:scale-110 hover:border-border-hover '+(prompts?'border-border':'border-transparent'),
  style:{backgroundColor:ZCodeActivityHeatColor(prompts)}});
}
function ZCodeActivitySegment(id,label,range,setRange){
 const active=range===id;
 return $.jsx('button',{type:'button',onClick:()=>setRange(id),'data-testid':`zcode-activity-range-${id}`,
  className:'h-6 flex-none justify-center rounded-full px-2.5 py-0 text-ui-sm font-medium transition-colors '+(active?'bg-background text-foreground':'text-foreground-subtle hover:text-foreground'),children:label},id);
}
function ZCodeActivityStats(data){
 const day=value=>`${ZCodeActivityNumber(value??0)} d`;
 return [
  {label:'Prompts today',value:ZCodeActivityNumber(data.today??0)},
  {label:'Current streak',value:day(data.currentStreak)},
  {label:'Longest streak',value:day(data.longestStreak)},
  {label:'Active days',value:ZCodeActivityNumber(data.activeDays??0)},
  {label:'Total prompts',value:ZCodeActivityNumber(data.total??0)}];
}
function ZCodeActivityNumber(value,locale){
 const total=Number(value)||0;
 return new Intl.NumberFormat(locale,{notation:total>=1000?'compact':'standard',maximumFractionDigits:total>=1000?1:0}).format(total);
}
function ZCodeActivityRangeLabel(range){
 return range==='12m'?'Last 12 months':String(range);
}
function ZCodeActivityDayKey(date){
 const pad=n=>String(n).padStart(2,'0');
 return `${date.getFullYear()}-${pad(date.getMonth()+1)}-${pad(date.getDate())}`;
}
function ZCodeActivityGrid(counts,range,todayKey){
 const weeks=[],months=[],parse=key=>{const[y,m,d]=key.split('-').map(Number);return new Date(y,m-1,d);};
 let rangeStart,rangeEnd;
 if(range==='12m'){rangeEnd=parse(todayKey);rangeStart=new Date(rangeEnd);rangeStart.setDate(rangeStart.getDate()-364);}
 else{rangeStart=new Date(Number(range),0,1);rangeEnd=new Date(Number(range),11,31);}
 const start=new Date(rangeStart);
 start.setDate(start.getDate()-start.getDay());
 const key=ZCodeActivityDayKey(new Date());
 let cursor=new Date(start),lastMonth=-1,index=0;
 while(cursor<=rangeEnd){
  const week=[],firstKey=ZCodeActivityDayKey(cursor);
  for(let day=0;day<7;day++){
   const cellKey=ZCodeActivityDayKey(cursor);
   const inside=cursor>=rangeStart&&cursor<=rangeEnd&&cellKey<=key;
   week.push(inside?{day:cellKey,prompts:counts.get(cellKey)??0}:null);
   cursor.setDate(cursor.getDate()+1);
  }
  const monthLabel=parse(firstKey).getMonth();
  months.push(monthLabel!==lastMonth?ZCodeActivityMonthNames[monthLabel]:'');
  lastMonth=monthLabel;
  weeks.push(week);
  index+=1;
  if(index>60)break;
 }
 return {weeks,months};
}
function ZCodeActivityMonthSpans(months){
 const groups=[];
 for(const label of months){
  if(label||groups.length===0)groups.push({key:`${groups.length}-${label}`,label,span:1});
  else groups[groups.length-1].span+=1;
 }
 return groups;
}
const ZCodeActivityMonthNames=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
function ZCodeActivityHeatColor(prompts){
 const level=!prompts?0:prompts<3?1:prompts<6?2:prompts<10?3:4;
 return `var(--color-usage-heatmap-${level})`;
}
if(typeof module!=='undefined'&&module.exports)module.exports={ZCodeActivityPanel,ZCodeActivityCell,ZCodeActivityGrid,ZCodeActivityDayKey,ZCodeActivityHeatColor,ZCodeActivityMonthSpans,ZCodeActivityMonthNames,ZCodeActivityNumber,ZCodeActivityRangeLabel,ZCodeActivitySegment,ZCodeActivityStats};