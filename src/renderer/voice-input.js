function ZCodeVoiceInput({disabled=false}){
 const [status,setStatus]=Q.useState('idle'),[error,setError]=Q.useState(''),[auto,setAuto]=Q.useState(()=>localStorage.getItem('zcode-voice-send-mode')==='auto');
 const [language,setLanguage]=Q.useState(()=>localStorage.getItem('zcode-voice-language')||'id');
 const live=Q.useRef(true),target=Q.useRef(null),timer=Q.useRef(null),inFlight=Q.useRef(false);
 const api=typeof window==='undefined'?null:window.zcodeVoice;
 Q.useEffect(()=>{live.current=true;return()=>{live.current=false;clearTimeout(timer.current);api?.cancel().catch(()=>{});};},[]);
 async function toggle(event){
  if(inFlight.current)return;setError('');inFlight.current=true;
  try{
   if(status==='idle'){
    const region=event.currentTarget.closest('.chat-composer-region');target.current=region?.querySelector('[contenteditable="true"]');
    if(!target.current)throw Error('Buka kotak chat terlebih dahulu.');
    await api.start({language});if(!live.current){await api.cancel();return;}
    setStatus('recording');timer.current=setTimeout(()=>{api.cancel().catch(()=>{});if(live.current){setStatus('idle');setError('Batas rekaman 60 detik. Coba perintah lebih singkat.');}},59000);
   }else if(status==='recording'){
    clearTimeout(timer.current);setStatus('transcribing');const result=await api.stop();if(!live.current)return;
    const text=(result.text||'').trim();if(!text){setError('Ucapan belum terbaca. Coba lagi dan cek mikrofon Fedora.');return;}
    const editor=target.current;if(!editor?.isConnected)throw Error('Kotak chat berubah. Rekam lagi pada chat yang ingin dipakai.');
    editor.focus();const range=document.createRange();range.selectNodeContents(editor);range.collapse(false);const selection=window.getSelection();selection.removeAllRanges();selection.addRange(range);
    const value=(editor.textContent.trim()?' ':'')+text;
    if(!document.execCommand('insertText',false,value))throw Error('Tidak bisa memasukkan teks suara.');
    if(auto){await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));const region=editor.closest('.chat-composer-region');const send=[...region.querySelectorAll('button')].find(b=>/^(Send|Kirim)$/.test(b.getAttribute('aria-label')||''));if(send&&!send.disabled)send.click();else setError('Teks siap. Tombol kirim belum tersedia; kirim setelah siap.');}
   }
  }catch(e){if(live.current){setError(String(e.message||e));setStatus('idle');}}
  finally{inFlight.current=false;if(live.current&&status==='recording')setStatus('idle');}
 }
 if(!api)return null;
 const label=status==='recording'?'Stop rekaman':status==='transcribing'?'Memproses suara…':'Voice command';
 const languageLabel=language==='id'?'ID + EN':language==='en'?'EN + ID':'Auto';
 const modeLabel=auto?'Send':'Review';
 const option=(value,title,description)=>$.jsx(EA,{value,className:'py-2',children:$.jsxs('div',{className:'flex flex-col gap-0.5',children:[$.jsx('span',{className:'text-ui-base',children:title}),$.jsx('span',{className:'text-ui-xs text-foreground-subtle',children:description})]})},value);
 return $.jsxs('div',{className:'relative flex shrink-0 items-center gap-0.5',children:[
 $.jsxs(X,{type:'button',variant:'ghost',size:'default','data-testid':'zcode-voice-button','aria-label':label,title:label,disabled:disabled||status==='transcribing',onClick:toggle,className:'h-8 rounded-lg px-2.5 gap-2 text-ui-base '+(status==='recording'?'bg-destructive/10 text-destructive':''),children:[$.jsx('svg',{viewBox:'0 0 24 24',width:18,height:18,fill:'none',stroke:'currentColor',strokeWidth:1.5,className:'shrink-0','aria-hidden':true,children:$.jsx('path',{d:status==='recording'?'M7 7h10v10H7z':'M9 5a3 3 0 0 1 6 0v7a3 3 0 0 1-6 0V5zm-3 6v1a6 6 0 0 0 12 0v-1M12 18v4M8 22h8'})}),$.jsx('span',{children:status==='recording'?'Stop':status==='transcribing'?'Memproses…':'Voice'})]}),
 $.jsxs(bA,{children:[
 $.jsx(xA,{asChild:true,children:$.jsxs(X,{type:'button',variant:'ghost',size:'default','aria-label':'Voice settings','data-testid':'zcode-voice-settings',title:'Speech language and send mode',disabled:status!=='idle',className:'h-8 rounded-lg px-2 gap-1.5 text-ui-base text-foreground-subtle',children:[$.jsx('span',{children:languageLabel}),$.jsx('span',{className:'text-foreground-subtlest',children:'·'}),$.jsx('span',{children:modeLabel}),$.jsx(Rs,{className:'size-3.5 shrink-0'})]})}),
 $.jsxs(SA,{side:'top',align:'start',sideOffset:8,className:'min-w-64',children:[
 $.jsx(DA,{children:'Speech language'}),
 $.jsxs(TA,{value:language,onValueChange:value=>{setLanguage(value);localStorage.setItem('zcode-voice-language',value);},children:[option('id','Indonesian + English','Prefer Indonesian, preserve English terms'),option('en','English + Indonesian','Prefer English, allow Indonesian speech'),option('auto','Auto detect','Choose the language based on speech')]}),
 $.jsx(OA,{}),$.jsx(DA,{children:'After speaking'}),
 $.jsxs(TA,{value:auto?'auto':'review',onValueChange:value=>{const enabled=value==='auto';setAuto(enabled);localStorage.setItem('zcode-voice-send-mode',enabled?'auto':'review');},children:[option('review','Review first','Insert into the chat box for review'),option('auto','Send automatically','Send the command after transcription')]})
 ]})
 ]}),
 error?$.jsx('div',{role:'status',className:'absolute bottom-full left-0 z-50 mb-2 w-72 rounded-lg border border-border bg-surface p-3 text-ui-sm text-destructive shadow-lg',children:error}):null
 ]});
}
