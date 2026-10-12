#!/usr/bin/python3
"""Enrich explicitly registered Vansrouter models; preserve manual field overrides."""
import contextlib, copy, datetime, fcntl, hashlib, json, os, pathlib, sys, tempfile, time, urllib.request
ROOT=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parents[1]/'scripts'))
from data_backup import namespace_lock, namespace_root, private_dir, safe_path
CATALOG_URL='https://raw.githubusercontent.com/anomalyco/opencode/dev/packages/core/src/models-dev/snapshot.txt'
ALIASES={'oc':'opencode','ocg':'opencode-go','gq':'groq','cmc':'commandcode','or':'openrouter'}

def load(path, default):
    try:return json.loads(path.read_text())
    except (OSError,ValueError):return copy.deepcopy(default)

def atomic(path, value):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd,name=tempfile.mkstemp(prefix='.'+path.name+'.',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as f:json.dump(value,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
        os.chmod(name,0o600);os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)

def metadata(model_id,catalog):
    if '/' not in model_id or model_id.startswith('combo/'):return None
    prefix,mid=model_id.split('/',1)
    if mid.endswith(')') and '(' in mid:return None # fixed effort suffix remains authoritative
    provider=ALIASES.get(prefix,prefix)
    return catalog.get(provider,{}).get('models',{}).get(mid)

def reasoning_spec(meta, model_id):
    options=meta.get('reasoning_options')
    if options is None:return None
    effort=next((x for x in options if x.get('type')=='effort'),None)
    if effort:
        values=effort.get('values',[])
        if values and all(isinstance(v,str) and v.strip() for v in values):
            return {'values':list(dict.fromkeys(values)),'map':'{"reasoning_effort": reasoningLevel}'}
    if any(x.get('type')=='toggle' for x in options):
        family=(meta.get('family','')+' '+model_id).lower()
        if 'ling-' in family:
            expr='{"reasoning": {"enabled": reasoningLevel == "enabled"}}'
        elif any(x in family for x in ['longcat','mimo','glm','deepseek']):
            expr='{"thinking": {"type": reasoningLevel == "disabled" ? "disabled" : "enabled"}}'
        elif 'qwen' in family:
            expr='{"enable_thinking": reasoningLevel == "enabled"}'
        else:return None # a toggle needs a known provider wire format
        return {'values':['disabled','enabled'],'map':expr}
    if options==[] and 'reasoning' in meta:
        return {'values':['enabled' if meta['reasoning'] else 'disabled'],'map':'{}'}
    return None

def placeholder(spec):
    return spec is None or (spec.get('values')==['disabled','enabled'] and spec.get('map','{}').strip()=='{}')

def enrich(data,catalog,state):
    out=copy.deepcopy(data);newstate=copy.deepcopy(state);changes=[]
    cfg=out.get('config',{});providers=cfg.get('providerConfigRules',{}).get('providerRules',[])
    model_cfg=cfg.setdefault('modelConfigRules',{})
    rules=model_cfg.setdefault('manualProviderModelRules',[])
    managed=newstate.setdefault('managed',{})
    for provider in providers:
        if provider.get('providerId')!='vansrouter':continue
        pc=provider.get('config',{})
        if pc.get('api',{}).get('type')!='openai-chat-completions':continue
        ids=pc.get('personalModelIds',[])
        for mid in ids:
            meta=metadata(mid,catalog)
            if not meta:continue
            desired=reasoning_spec(meta,mid)
            if not desired:continue
            key='vansrouter/'+mid
            rule=next((x for x in rules if x.get('providerId')=='vansrouter' and x.get('modelId')==mid),None)
            if rule is None:
                inputs=meta.get('modalities',{}).get('input',[])
                props={'contextWindow':max(1,meta.get('limit',{}).get('context') or 128000),
                    'supportsJsonSchemaOutput':False,'supportsNativeWebSearch':False,'supportsMidConversationSystem':True,
                    'inputFormat':{'supportsImage':'image' in inputs,'supportsVideo':False,'supportsPdf':False}}
                rule={'providerId':'vansrouter','modelId':mid,'config':{'properties':props,'optionSpecs':{}}};rules.append(rule)
            specs=rule['config'].setdefault('optionSpecs',{})
            current=specs.get('reasoningLevel');previous=managed.get(key)
            if previous is not None and current!=previous:
                continue # user changed this field; never overwrite it
            if previous is None and not placeholder(current) and current!=desired:
                continue # preexisting explicit mapping belongs to the user
            if current!=desired:
                specs['reasoningLevel']=desired;changes.append(mid)
            managed[key]=copy.deepcopy(desired)
    return out,newstate,changes

def refresh_catalog(cache_root=None):
    path=(cache_root or ROOT)/'catalog.json'
    if path.exists() and time.time()-path.stat().st_mtime<86400:return load(path,{})
    try:
        req=urllib.request.Request(CATALOG_URL,headers={'User-Agent':'ZCode-Vansrouter-Metadata-Sync/1.0'})
        with urllib.request.urlopen(req,timeout=20) as r:catalog=json.load(r)
        if not isinstance(catalog,dict) or 'opencode' not in catalog:raise ValueError('invalid catalog')
        atomic(path,catalog)
    except Exception as e:
        print('Catalog refresh unavailable; using cached metadata:',type(e).__name__)
    return load(path,{})

def storage_paths():
    config=os.environ.get('ZCODE_MODEL_SYNC_CONFIG')
    state=os.environ.get('ZCODE_MODEL_SYNC_STATE')
    if bool(config)!=bool(state):
        raise ValueError('Set both ZCODE_MODEL_SYNC_CONFIG and ZCODE_MODEL_SYNC_STATE')
    if config:
        config=safe_path(config);state=safe_path(state)
        root=namespace_root(os.environ.get('ZCODE_STANDALONE_ROOT') or state.parent)
        if root not in config.parents or root not in state.parents:
            raise ValueError('Standalone sync paths must be inside their namespace')
        return config,state,root
    # The existing upstream timer intentionally keeps its original config and state.
    return pathlib.Path.home()/'.zcode/v2/provider_config.json',ROOT,None

def main():
    os.umask(0o077)
    config,state_root,namespace=storage_paths()
    guard=namespace_lock(namespace,exclusive=False) if namespace else contextlib.nullcontext()
    with guard:
        if namespace:
            private_dir(state_root)
            for name in ('catalog.json','state.json','backups'):
                safe_path(state_root/name)
        else:state_root.mkdir(parents=True,exist_ok=True)
        lock_path=state_root/'sync.lock'
        if namespace:safe_path(lock_path)
        fd=os.open(lock_path,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
        os.fchmod(fd,0o600)
        with os.fdopen(fd,'a') as lock:
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:return
            if not config.exists():return
            raw=config.read_bytes();data=json.loads(raw)
            state=load(state_root/'state.json',{'managed':{}})
            out,newstate,changes=enrich(data,refresh_catalog(state_root),state)
            if changes:
                if config.read_bytes()!=raw:
                    print('Config changed concurrently; retry on next timer run');return
                backups=state_root/'backups';backups.mkdir(exist_ok=True,mode=0o700)
                if namespace:private_dir(backups)
                name='provider_config-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.json'
                backup=backups/name;backup.write_bytes(raw);backup.chmod(0o600)
                # Recheck after backup so an in-flight UI save does not get overwritten.
                if config.read_bytes()!=raw:return
                atomic(config,out)
                for old in sorted(backups.glob('provider_config-*.json'))[:-10]:old.unlink()
                print('Updated reasoning metadata:',', '.join(changes))
            if newstate!=state:atomic(state_root/'state.json',newstate)
if __name__=='__main__':main()
