#!/usr/bin/env python3
import json,sys,pathlib,time,subprocess
import numpy as np
from faster_whisper import WhisperModel
from terminology import PROMPT,TECH_HINTS,normalize_terms
root=pathlib.Path(__file__).resolve().parent
model=WhisperModel(str(root/'model'),device='cpu',compute_type='int8',cpu_threads=8,num_workers=1,local_files_only=True)
print(json.dumps({'ready':True}),flush=True)
for line in sys.stdin:
    try:
        req=json.loads(line);path=req['path'];t=time.monotonic()
        decoded=subprocess.run(['/usr/bin/ffmpeg','-v','error','-i',path,'-f','f32le','-ar','16000','-ac','1','pipe:1'],capture_output=True,check=True,timeout=20)
        audio=np.frombuffer(decoded.stdout,dtype=np.float32)
        language=req.get('language','id')
        if language not in ('id','en'):
            _,_,probabilities=model.detect_language(audio=audio)
            language=max((x for x in probabilities if x[0] in ('id','en')),key=lambda x:x[1])[0]
        segments,info=model.transcribe(audio,beam_size=2,best_of=1,temperature=0.0,language=language,vad_filter=True,condition_on_previous_text=False,
            initial_prompt=PROMPT,hotwords=TECH_HINTS)
        text=normalize_terms(' '.join(s.text.strip() for s in segments).strip())
        print(json.dumps({'id':req['id'],'text':text,'language':info.language,'seconds':round(time.monotonic()-t,2)},ensure_ascii=False),flush=True)
    except Exception as e:
        print(json.dumps({'id':req.get('id') if 'req' in locals() else None,'error':str(e)}),flush=True)
