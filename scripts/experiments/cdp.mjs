import fs from 'node:fs';
const tabs=await (await fetch('http://127.0.0.1:9224/json/list')).json();const tab=tabs.find(t=>t.type==='page'&&t.url.includes('index.html'));if(!tab)throw Error('Test window not available');
const ws=new WebSocket(tab.webSocketDebuggerUrl);await new Promise((r,j)=>{ws.onopen=r;ws.onerror=j});let seq=0;const pending=new Map();ws.onmessage=ev=>{const x=JSON.parse(ev.data);if(x.id){pending.get(x.id)?.(x);pending.delete(x.id)}};
const call=(method,params={})=>new Promise(r=>{let id=++seq;pending.set(id,r);ws.send(JSON.stringify({id,method,params}))});
const res=await call('Runtime.evaluate',{expression:process.argv[2]||'document.body.innerText.slice(0,12000)',returnByValue:true,awaitPromise:true});console.log(JSON.stringify(res.result));
if(process.argv[3]){const shot=await call('Page.captureScreenshot',{format:'png'});fs.writeFileSync(process.argv[3],Buffer.from(shot.result.data,'base64'));}
ws.close();
