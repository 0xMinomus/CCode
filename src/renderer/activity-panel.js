// Local "Activity" page: prompt counts per day, streaks and a contribution-style
// heatmap, all computed by the main process from the local session database.
// The layout mirrors the original upstream usage page (metrics strip with dividers,
// heatmap card with a year segment control) and reuses its theme tokens
// `--color-usage-heatmap-0..4` plus the bundled tooltip component for cell hover.
// The grid is always one calendar year (Jan-Dec, 365 or 366 cells). No cloud, no
// account, no plan data.
function CCodeActivityPanel(){
 const [state,setState]=Q.useState({status:'loading'});
 const [picked,setPicked]=Q.useState(null);
 Q.useEffect(()=>{
  let live=true;
  (async()=>{
   const api=typeof window==='undefined'?null:window.ccodeActivity;
   if(!api){if(live)setState({status:'error',error:'Activity bridge is unavailable.'});return;}
   try{const data=await api.summary();if(live)setState({status:'ready',data});}
   catch(error){if(live)setState({status:'error',error:String(error?.message??error)});}
  })();
  return()=>{live=false};
 },[]);
 const data=state.data??{};
 const days=data.days??[];
 const counts=Q.useMemo(()=>{const map=new Map();for(const row of days)map.set(row.day,row.prompts);return map;},[days]);
 const years=CCodeActivityYears(data.years,new Date().getFullYear());
 const range=years.includes(picked)?picked:years[years.length-1];
 const grid=Q.useMemo(()=>CCodeActivityGrid(counts,range),[counts,range]);
 const rangeTotal=grid.weeks.flat().reduce((sum,cell)=>sum+(cell?.prompts??0),0);
 if(state.status==='loading')return $.jsx('div',{className:'text-ui-base text-foreground-subtle',children:'Loading local activity…'});
 if(state.status==='error')return $.jsx('div',{className:'text-ui-base text-foreground-subtle',children:state.error});
 if(data.available===false)return $.jsx('div',{className:'text-ui-base text-foreground-subtle',children:data.error||'Local activity is not available yet.'});
 const heatmapStyle={gridTemplateColumns:`repeat(${grid.weeks.length}, minmax(0, 1fr))`};
 return $.jsxs('div',{className:'space-y-4','data-testid':'ccode-activity-panel',children:[
  $.jsxs('div',{className:'flex flex-col overflow-hidden rounded-xl bg-surface sm:flex-row sm:items-center','data-testid':'ccode-activity-metrics',children:CCodeActivityStats(data).map((stat,index)=>$.jsxs(Q.Fragment,{children:[
   index>0?$.jsx('div',{'aria-hidden':'true',className:'hidden h-7 w-px bg-border sm:block'},`divider-${stat.label}`):null,
   $.jsxs('div',{className:'min-w-0 flex-1 px-4 py-3 text-center',children:[
    $.jsx('div',{className:'truncate text-ui-lg font-medium text-foreground',children:stat.value}),
    $.jsxs('div',{className:'mt-1 flex min-w-0 items-center justify-center gap-1 text-ui-base text-foreground-subtle',children:[
     $.jsx('span',{className:'min-w-0 truncate',children:stat.label})]})]},stat.label)]},stat.label))}),
  $.jsxs('div',{className:'rounded-xl bg-surface px-3 py-3','data-testid':'ccode-activity-heatmap',children:[
   $.jsxs('div',{className:'mb-3 flex items-center justify-between gap-3',children:[
    $.jsxs('div',{className:'flex min-w-0 flex-col',children:[
     $.jsx('h3',{className:'min-w-0 truncate text-ui-base font-medium text-foreground',children:'Prompt activity'}),
     $.jsxs('div',{className:'min-w-0 truncate text-ui-sm text-foreground-subtle',children:[
      $.jsx('span',{className:'font-medium',children:CCodeActivityNumber(rangeTotal)}),
      ` prompt${rangeTotal===1?'':'s'} · `,range]})]}),
    $.jsx('div',{className:'flex flex-wrap items-center gap-0.5 rounded-full bg-surface p-0.5','data-testid':'ccode-activity-ranges',children:years.map(year=>CCodeActivitySegment(year,range,setPicked))})]}),
   $.jsxs('div',{children:[
    $.jsx('div',{className:'grid w-full gap-x-0.5',style:heatmapStyle,children:grid.weeks.map((week,index)=>$.jsx('div',{className:'flex min-w-0 flex-col gap-1',children:week.map((cell,row)=>cell
     ?$.jsx(CCodeActivityCell,{cell},cell.day)
     :$.jsx('div',{className:'aspect-square w-full min-w-0'},`${index}-${row}`))},index))}),
    $.jsx('div',{className:'mt-3 grid w-full gap-x-0.5',style:heatmapStyle,children:CCodeActivityMonthSpans(grid.months).map(group=>$.jsx('div',{'data-usage-heatmap-month-label':'true',className:'min-w-0 truncate text-ui-sm text-foreground-subtle',style:{gridColumn:`span ${group.span}`},children:group.label},group.key))})]})]})]});
}
function CCodeActivityCell({cell}){
 const prompts=cell.prompts??0;
 return $.jsx(uA,{title:`${cell.day}\n${prompts} prompt${prompts===1?'':'s'}`,children:
  $.jsx('div',{className:'aspect-square w-full min-w-0 rounded-[4px] border transition-transform hover:scale-110 hover:border-border-hover '+(prompts?'border-border':'border-transparent'),
   style:{backgroundColor:CCodeActivityHeatColor(prompts)}})});
}
function CCodeActivitySegment(year,range,setRange){
 const active=range===year;
 return $.jsx('button',{type:'button',onClick:()=>setRange(year),'data-testid':`ccode-activity-range-${year}`,
  className:'h-6 flex-none justify-center rounded-full px-2.5 py-0 text-ui-sm font-medium transition-colors '+(active?'bg-background text-foreground':'text-foreground-subtle hover:text-foreground'),children:year},year);
}
function CCodeActivityStats(data){
 const day=value=>`${CCodeActivityNumber(value??0)} d`;
 return [
  {label:'Prompts today',value:CCodeActivityNumber(data.today??0)},
  {label:'Current streak',value:day(data.currentStreak)},
  {label:'Longest streak',value:day(data.longestStreak)},
  {label:'Active days',value:CCodeActivityNumber(data.activeDays??0)},
  {label:'Total prompts',value:CCodeActivityNumber(data.total??0)}];
}
function CCodeActivityNumber(value,locale){
 const total=Number(value)||0;
 return new Intl.NumberFormat(locale,{notation:total>=1000?'compact':'standard',maximumFractionDigits:total>=1000?1:0}).format(total);
}
function CCodeActivityYears(rows,currentYear){
 const years=new Set();
 for(const row of rows??[])years.add(String(row?.year??row));
 years.add(String(currentYear));
 return [...years].filter(year=>/^\d{4}$/.test(year)).sort();
}
function CCodeActivityDayKey(date){
 const pad=n=>String(n).padStart(2,'0');
 return `${date.getFullYear()}-${pad(date.getMonth()+1)}-${pad(date.getDate())}`;
}
function CCodeActivityGrid(counts,year){
 const weeks=[],months=[],parse=key=>{const[y,m,d]=key.split('-').map(Number);return new Date(y,m-1,d);};
 const number=Number(year);
 const rangeStart=new Date(number,0,1),rangeEnd=new Date(number,11,31);
 const start=new Date(rangeStart);
 start.setDate(start.getDate()-start.getDay());
 let cursor=new Date(start),lastMonth=-1,index=0;
 while(cursor<=rangeEnd){
  const week=[];
  for(let day=0;day<7;day++){
   const cellKey=CCodeActivityDayKey(cursor);
   const inside=cursor>=rangeStart&&cursor<=rangeEnd;
   week.push(inside?{day:cellKey,prompts:counts.get(cellKey)??0}:null);
   cursor.setDate(cursor.getDate()+1);
  }
  const firstDay=week.find(Boolean);
  const monthLabel=firstDay?parse(firstDay.day).getMonth():lastMonth;
  months.push(monthLabel!==lastMonth?CCodeActivityMonthNames[monthLabel]:'');
  lastMonth=monthLabel;
  weeks.push(week);
  index+=1;
  if(index>55)break;
 }
 return {weeks,months};
}
function CCodeActivityMonthSpans(months){
 const groups=[];
 for(const label of months){
  if(label||groups.length===0)groups.push({key:`${groups.length}-${label}`,label,span:1});
  else groups[groups.length-1].span+=1;
 }
 return groups;
}
const CCodeActivityMonthNames=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
function CCodeActivityHeatColor(prompts){
 const level=!prompts?0:prompts<3?1:prompts<6?2:prompts<10?3:4;
 return `var(--color-usage-heatmap-${level})`;
}
if(typeof module!=='undefined'&&module.exports)module.exports={CCodeActivityPanel,CCodeActivityCell,CCodeActivityGrid,CCodeActivityDayKey,CCodeActivityHeatColor,CCodeActivityMonthSpans,CCodeActivityMonthNames,CCodeActivityNumber,CCodeActivitySegment,CCodeActivityStats,CCodeActivityYears};