"""Small ASAR reader/writer; preserves unpacked entries and file integrity metadata."""
import copy,hashlib,json,os,pathlib,struct,tempfile
class Archive:
 def __init__(self,path):
  self.path=pathlib.Path(path)
  with self.path.open('rb') as f:
   h=f.read(16)
   if len(h)!=16:raise ValueError('Invalid ASAR header')
   self.header=json.loads(f.read(struct.unpack('<I',h[12:16])[0]))
   self.start=8+struct.unpack('<I',h[4:8])[0]
  self.index=dict(self.entries())
 def entries(self,tree=None,prefix=''):
  for name,value in (tree or self.header).get('files',{}).items():
   full=(prefix+'/'+name).lstrip('/')
   if 'files' in value:yield from self.entries(value,full)
   elif not value.get('unpacked') and 'offset' in value:yield full,value
 def read(self,name):
  entry=self.index.get(name)
  if entry is None:raise KeyError(name)
  with self.path.open('rb') as f:f.seek(self.start+int(entry['offset']));return f.read(entry['size'])
 def write(self,destination,replacements):
  unknown=set(replacements)-{n for n,_ in self.entries()}
  if unknown:raise KeyError('Unknown ASAR entries: '+str(unknown))
  header=copy.deepcopy(self.header);payloads=[];offset=0
  for name,entry in self.entries(header):
   data=replacements.get(name)
   if data is None:data=self.read(name)
   entry['offset']=str(offset);entry['size']=len(data);offset+=len(data);payloads.append(data)
   if 'integrity' in entry:
    block=entry['integrity'].get('blockSize',4194304)
    blocks=[hashlib.sha256(data[i:i+block]).hexdigest() for i in range(0,len(data),block)] or [hashlib.sha256(b'').hexdigest()]
    entry['integrity']={'algorithm':'SHA256','hash':hashlib.sha256(data).hexdigest(),'blockSize':block,'blocks':blocks}
  encoded=json.dumps(header,separators=(',',':')).encode();pad=(-len(encoded))%4;size=4+len(encoded)+pad
  destination=pathlib.Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
  fd,temp=tempfile.mkstemp(prefix='.'+destination.name,dir=destination.parent)
  try:
   with os.fdopen(fd,'wb') as f:
    f.write(struct.pack('<IIII',4,4+size,size,len(encoded)));f.write(encoded);f.write(b'\0'*pad)
    for data in payloads:f.write(data)
    f.flush();os.fsync(f.fileno())
   os.replace(temp,destination)
  finally:
   if os.path.exists(temp):os.unlink(temp)
