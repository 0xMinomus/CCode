const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),{spawn}=require('node:child_process'),readline=require('node:readline');
exports.register=({app,ipcMain})=>{
 let project=__dirname;
 while(!fs.existsSync(path.join(project,'project.json'))){const parent=path.dirname(project);if(parent===project)throw Error('CCode project root not found.');project=parent;}
 const root=path.join(project,'services/voice');
 let worker=null,ready=null,recording=null,sequence=0;const jobs=new Map();
 function trusted(event){const frame=event.senderFrame;return frame===event.sender.mainFrame&&frame.url.startsWith('file://')&&frame.url.includes('/out/renderer/index.html');}
 function requireTrusted(event){if(!trusted(event))throw Error('Voice input is only available in the local CCode window.');}
 function startWorker(){
  if(worker&&ready)return ready;
  worker=spawn(path.join(root,'.venv/bin/python'),['-u',path.join(root,'worker.py')],{stdio:['pipe','pipe','pipe'],env:{...process.env,HF_HUB_OFFLINE:'1',TOKENIZERS_PARALLELISM:'false'}});
  const current=worker;
  ready=new Promise((resolve,reject)=>{
   const timeout=setTimeout(()=>reject(Error('Speech model startup timed out.')),30000);
   readline.createInterface({input:current.stdout}).on('line',line=>{let result;try{result=JSON.parse(line)}catch{return}if(result.ready){clearTimeout(timeout);resolve();return}const job=jobs.get(result.id);if(job){jobs.delete(result.id);clearTimeout(job.timer);result.error?job.reject(Error(result.error)):job.resolve(result)}});
   current.once('error',e=>{clearTimeout(timeout);reject(e)});
   current.once('exit',()=>{clearTimeout(timeout);reject(Error('Speech recognition stopped.'));for(const j of jobs.values()){clearTimeout(j.timer);j.reject(Error('Speech recognition stopped.'))}jobs.clear();if(worker===current){worker=null;ready=null;}});
  });
  // No transcript or audio is written to app logs.
  current.stderr.on('data',()=>{});ready.catch(()=>{});return ready;
 }
 function cleanup(rec){clearTimeout(rec.timer);try{fs.rmSync(rec.dir,{recursive:true,force:true})}catch{}}
 async function stopRecorder(rec){
  clearTimeout(rec.timer);
  if(rec.proc.exitCode===null&&rec.proc.signalCode===null){
   const done=new Promise(r=>rec.proc.once('exit',r));rec.proc.kill('SIGINT');
   await Promise.race([done,new Promise(r=>setTimeout(()=>{rec.proc.kill('SIGKILL');r()},2000))]);
  }
 }
 ipcMain.handle('zcode-voice:start',async (event,options)=>{
  requireTrusted(event);if(recording)throw Error('A voice recording is already in progress.');
  startWorker();const dir=fs.mkdtempSync(path.join(os.tmpdir(),'zcode-voice-'));const file=path.join(dir,'input.wav');
  const proc=spawn('/usr/bin/pw-record',['--rate','16000','--channels','1','--format','s16',file],{stdio:['ignore','ignore','pipe']});
  const rec={proc,dir,file,owner:event.sender.id,language:['id','en','auto'].includes(options?.language)?options.language:'id',timer:null};recording=rec;
  proc.stderr.on('data',()=>{});proc.once('error',()=>{if(recording===rec)recording=null;cleanup(rec)});
  rec.timer=setTimeout(async()=>{if(recording===rec){recording=null;await stopRecorder(rec);cleanup(rec);if(!event.sender.isDestroyed())event.sender.send('zcode-voice:timeout')}},60000);
  event.sender.once('destroyed',async()=>{if(recording===rec){recording=null;await stopRecorder(rec);cleanup(rec)}});
  await new Promise(r=>setTimeout(r,150));
  if(proc.exitCode!==null){recording=null;cleanup(rec);throw Error('Microphone could not start. Check the Fedora input device.');}
  return {recording:true};
 });
 ipcMain.handle('zcode-voice:stop',async event=>{
  requireTrusted(event);const rec=recording;if(!rec||rec.owner!==event.sender.id)throw Error('No voice recording is active in this window.');recording=null;
  try{
   await stopRecorder(rec);if(!fs.existsSync(rec.file)||fs.statSync(rec.file).size<1000)return {text:''};
   await startWorker();const id=++sequence;
   return await new Promise((resolve,reject)=>{const timer=setTimeout(()=>{jobs.delete(id);reject(Error('Transcription timed out.'))},60000);jobs.set(id,{resolve,reject,timer});worker.stdin.write(JSON.stringify({id,path:rec.file,language:rec.language})+'\n');});
  }finally{cleanup(rec)}
 });
 ipcMain.handle('zcode-voice:cancel',async event=>{requireTrusted(event);const rec=recording;if(rec&&rec.owner===event.sender.id){recording=null;await stopRecorder(rec);cleanup(rec)}return {cancelled:true};});
 app.on('before-quit',()=>{if(recording){recording.proc.kill('SIGINT');cleanup(recording);recording=null}worker?.kill('SIGTERM')});
};
