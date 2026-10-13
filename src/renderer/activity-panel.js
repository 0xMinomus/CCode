// Local "Activity" page: prompt counts per day, streaks and a contribution-style
// heatmap, all computed by the main process from the local session database.
// No cloud, no account, no plan data.
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
 if(state.status==='loading')return $.jsx('div',{className:'text-ui-base text-foreground-subtle',children:'Menghitung aktivitas lokal…'});
 if(state.status==='error')return $.jsx('div',{className:'text-ui-base text-foreground-subtle',children:state.error});
 if(data.available===false)return $.jsx('div',{className:'text-ui-base text-foreground-subtle',children:data.error||'Aktivitas lokal belum tersedia.'});
 const card=(label,value)=>$.jsxs('div',{className:'flex flex-col gap-1 rounded-xl border border-border p-4',children:[
  $.jsx('span',{className:'text-ui-xs text-foreground-subtle',children:label}),
  $.jsx('span',{className:'text-2xl font-semibold tracking-tight text-foreground',children:value})]},label);
 const rangeLabel=range==='12m'?'12 bulan terakhir':`tahun ${range}`;
 const intensity=ZCodeActivityIntensity;
 return $.jsxs('div',{className:'flex flex-col gap-6','data-testid':'zcode-activity-panel',children:[
  $.jsxs('div',{className:'flex flex-col gap-1',children:[
   $.jsx('h2',{className:'text-2xl font-semibold tracking-tight text-foreground',children:'Activity'}),
   $.jsx('p',{className:'text-ui-base text-foreground-subtle',children:'Prompt yang Anda kirim ke agent, dihitung dari riwayat lokal aplikasi ini.'})]}),
  $.jsxs('div',{className:'grid grid-cols-2 gap-3 lg:grid-cols-4',children:[
   card('Prompt hari ini',data.today??0),
   card('Streak saat ini',`${data.currentStreak??0} hari`),
   card('Streak terpanjang',`${data.longestStreak??0} hari`),
   card('Total prompt',data.total??0)]}),
  $.jsxs('section',{className:'flex flex-col gap-3 rounded-xl border border-border bg-surface p-4','data-testid':'zcode-activity-heatmap',children:[
   $.jsxs('div',{className:'flex flex-wrap items-center justify-between gap-2',children:[
    $.jsxs('span',{className:'text-ui-base text-foreground',children:[
     $.jsx('span',{className:'font-semibold',children:rangeTotal.toLocaleString()}),' prompt · ',rangeLabel]}),
    $.jsxs('div',{className:'flex flex-wrap items-center gap-1',children:[
     ZCodeActivityPill('12m','12 bulan',range,setRange),
     ...(data.years??[]).map(row=>ZCodeActivityPill(row.year,row.year,range,setRange))]})]}),
   $.jsx('div',{className:'overflow-x-auto',children:$.jsxs('div',{className:'flex gap-2',children:[
    $.jsxs('div',{className:'flex flex-col pt-[18px] text-ui-xs text-foreground-subtle',style:{gap:'2px'},children:ZCodeActivityDayLabels.map((label,index)=>$.jsx('span',{className:'h-[11px] leading-[11px]',children:label},index))}),
    $.jsxs('div',{className:'flex flex-col',style:{gap:'2px'},children:[
     $.jsx('div',{className:'flex text-ui-xs text-foreground-subtle',style:{gap:'2px',height:'16px'},children:grid.months.map((label,index)=>$.jsx('span',{className:'shrink-0 overflow-visible whitespace-nowrap',style:{width:'11px'},children:label},index))}),
     $.jsx('div',{className:'flex',style:{gap:'2px'},children:grid.weeks.map((week,index)=>$.jsx('div',{className:'flex flex-col',style:{gap:'2px'},children:week.map((cell,row)=>cell
      ?$.jsx('div',{title:`${cell.day}: ${cell.prompts} prompt`,className:'h-[11px] w-[11px] rounded-[2px] '+intensity(cell.prompts)},cell.day)
      :$.jsx('div',{className:'h-[11px] w-[11px] rounded-[2px] bg-transparent'},`${index}-${row}`))},index))})]})]})}),
   $.jsxs('div',{className:'flex items-center justify-end gap-1 text-ui-xs text-foreground-subtle',children:[
    'Less',
    ...[0,1,3,6,10].map(level=>$.jsx('div',{className:'h-[11px] w-[11px] rounded-[2px] '+intensity(level)},level)),
    'More']})]})]});
}
function ZCodeActivityPill(id,label,range,setRange){
 const active=range===id;
 return $.jsx('button',{type:'button',onClick:()=>setRange(id),'data-testid':`zcode-activity-range-${id}`,
  className:'rounded-full border px-2.5 py-0.5 text-ui-xs transition-colors '+(active?'border-primary bg-primary text-primary-foreground':'border-border text-foreground-subtle hover:bg-surface-hover'),children:label},id);
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
const ZCodeActivityMonthNames=['Jan','Feb','Mar','Apr','Mei','Jun','Jul','Agu','Sep','Okt','Nov','Des'];
const ZCodeActivityDayLabels=['','Mon','','Wed','','Fri',''];
function ZCodeActivityIntensity(prompts){
 if(!prompts)return 'bg-foreground/5';
 if(prompts<3)return 'bg-primary/25';
 if(prompts<6)return 'bg-primary/45';
 if(prompts<10)return 'bg-primary/70';
 return 'bg-primary';
}
if(typeof module!=='undefined'&&module.exports)module.exports={ZCodeActivityPanel,ZCodeActivityGrid,ZCodeActivityDayKey,ZCodeActivityIntensity,ZCodeActivityDayLabels,ZCodeActivityMonthNames};
