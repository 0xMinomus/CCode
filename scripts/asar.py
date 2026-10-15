"""Small ASAR reader/writer; preserves unpacked entries and file integrity metadata.

CCode modification: safe Windows native overlays with unpacked header entries.
"""
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
 def all_entries(self,tree=None,prefix=''):
  for name,value in (self.header if tree is None else tree).get('files',{}).items():
   full=prefix+name
   if 'files' in value:yield from self.all_entries(value,full+'/')
   else:yield full,value
 @staticmethod
 def parts(name):
  if not isinstance(name,str) or not name or '\\' in name or ':' in name or '\0' in name:
   raise ValueError('Unsafe ASAR path: '+repr(name))
  parts=name.split('/')
  reserved={'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(1,10)),*(f'LPT{i}' for i in range(1,10))}
  if any(not part or part.endswith(('.', ' ')) or any(ord(char)<32 for char in part)
         or part.split('.')[0].upper() in reserved for part in parts):
   raise ValueError('Unsafe ASAR path: '+repr(name))
  return parts
 @staticmethod
 def integrity(data,block=4194304):
  return {'algorithm':'SHA256','hash':hashlib.sha256(data).hexdigest(),'blockSize':block,
          'blocks':[hashlib.sha256(data[i:i+block]).hexdigest() for i in range(0,len(data),block)] or [hashlib.sha256(b'').hexdigest()]}
 def read(self,name):
  entry=self.index.get(name)
  if entry is None:raise KeyError(name)
  with self.path.open('rb') as f:f.seek(self.start+int(entry['offset']));return f.read(entry['size'])
 def write(self,destination,replacements,renames=None,transform=None,unpacked=None,remove=()):
  renames=dict(renames or {})
  unknown=set(replacements)-{n for n,_ in self.entries()}
  if unknown:raise KeyError('Unknown ASAR entries: '+str(unknown))
  header=copy.deepcopy(self.header)
  unpacked=dict(unpacked or {})
  for name in (*renames,*renames.values(),*unpacked,*remove):self.parts(name)
  if set(remove)&(set(replacements)|set(renames)):raise ValueError('Conflicting ASAR removal')
  for name in remove:
   tree=header
   for part in self.parts(name)[:-1]:
    tree=tree.get('files',{}).get(part,{})
   if name.split('/')[-1] not in tree.get('files',{}):raise KeyError('Unknown ASAR removal: '+name)
   del tree['files'][name.split('/')[-1]]
  for source,target in renames.items():
   if source not in self.index:raise KeyError('Unknown ASAR entry to rename: '+source)
   if target==source:raise ValueError('ASAR rename target is not free: '+target)
  for source,target in renames.items():
   source_parts=source.split('/');target_parts=target.split('/')
   tree=header
   for part in source_parts[:-1]:tree=tree['files'][part]
   entry=tree['files'].pop(source_parts[-1])
   tree=header
   for part in target_parts[:-1]:
    tree=tree['files'].setdefault(part,{'files':{}})
    if 'files' not in tree:raise ValueError('ASAR parent is not a directory: '+target)
   if target_parts[-1] in tree['files']:raise ValueError('ASAR rename target is not free: '+target)
   tree['files'][target_parts[-1]]=entry
  originals={target:source for source,target in renames.items()}
  for name,data in unpacked.items():
   tree=header;parts=self.parts(name)
   for part in parts[:-1]:
    tree=tree['files'].setdefault(part,{'files':{}})
    if 'files' not in tree:raise ValueError('ASAR parent is not a directory: '+name)
   old=tree['files'].get(parts[-1])
   if old is not None and not old.get('unpacked'):raise ValueError('ASAR overlay conflicts with packed entry or directory: '+name)
   tree['files'][parts[-1]]={'size':len(data),'unpacked':True,'integrity':self.integrity(data)}
  if unpacked or renames:
   spellings={}
   for name,_ in self.all_entries(header):
    parts=name.split('/')
    for end in range(1,len(parts)+1):
     prefix='/'.join(parts[:end]);spellings.setdefault(prefix.casefold(),set()).add(prefix)
   for name in (*unpacked,*renames.values()):
    parts=self.parts(name)
    for end in range(1,len(parts)+1):
     if len(spellings['/'.join(parts[:end]).casefold()])>1:
      raise ValueError('ASAR paths conflict on a case-insensitive filesystem: '+name)
  payloads=[];offset=0
  for name,entry in self.entries(header):
   original=originals.get(name,name)
   data=replacements.get(original)
   if data is None:data=self.read(original)
   if transform is not None:data=transform(name,data)
   entry['offset']=str(offset);entry['size']=len(data);offset+=len(data);payloads.append(data)
   if 'integrity' in entry:
    block=entry['integrity'].get('blockSize',4194304)
    entry['integrity']=self.integrity(data,block)
  encoded=json.dumps(header,separators=(',',':')).encode();pad=(-len(encoded))%4;size=4+len(encoded)+pad
  destination=pathlib.Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
  unpacked_root=pathlib.Path(str(destination)+'.unpacked')
  for name in unpacked:
   target=unpacked_root.joinpath(*self.parts(name))
   for parent in (target,*target.parents):
    if parent.is_symlink():raise ValueError('ASAR unpacked destination contains a symlink: '+str(parent))
  for name,data in unpacked.items():
   target=unpacked_root.joinpath(*self.parts(name));target.parent.mkdir(parents=True,exist_ok=True)
   target.write_bytes(data)
  fd,temp=tempfile.mkstemp(prefix='.'+destination.name,dir=destination.parent)
  try:
   with os.fdopen(fd,'wb') as f:
    f.write(struct.pack('<IIII',4,4+size,size,len(encoded)));f.write(encoded);f.write(b'\0'*pad)
    for data in payloads:f.write(data)
    f.flush();os.fsync(f.fileno())
   os.replace(temp,destination)
  finally:
   if os.path.exists(temp):os.unlink(temp)
