#!/usr/bin/python3
"""Enrich explicitly registered Vansrouter models; preserve manual field overrides."""
import contextlib, copy, datetime, fcntl, hashlib, json, os, pathlib, sys, tempfile, time, urllib.request
ROOT=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parents[1]/'scripts'))
from data_backup import namespace_lock, namespace_root, private_dir, safe_path
CATALOG_URL='https://raw.githubusercontent.com/anomalyco/opencode/dev/packages/core/src/models-dev/snapshot.txt'
ALIASES={'oc':'opencode','ocg':'opencode-go','gq':'groq','cmc':'commandcode','or':'openrouter'}
# Local 9Router gateway: its /v1/models list drives discovery and grouping. The
# gateway answers unauthenticated local calls (verified), so the placeholder key
# below is not a secret; an existing 9Router provider keeps its own key instead.
GATEWAY_BASE_URL='http://127.0.0.1:20128/v1'
DISCOVERY_FAMILY_PREFIX='9router'
DISCOVERY_COMBO_GROUP='combo'
DISCOVERY_OVERFLOW_GROUP='lainnya'
DISCOVERY_GROUP_MIN=10
DISCOVERY_TTL_SECONDS=12*3600
DISCOVERY_FAILURE_BACKOFF=15*60
DISCOVERY_API_KEY_PLACEHOLDER='local-gateway'
# reasoning_effort values the gateway validates; "off" is only offered when the
# model metadata says thinking can be disabled, and the level list is only
# offered when the gateway reports effort support (never a label-only control).
DISCOVERY_EFFORT_LEVELS=('low','medium','high','xhigh','max')
# The manual-model-rule schema requires config.optionSpecs.reasoningLevel on every
# rule. Where the gateway does not verify effort support this inert placeholder is
# written instead (one value, nothing mapped), so the control never offers levels
# that would only rename themselves or be rejected upstream.
DISCOVERY_INERT_REASONING={'values':['disabled'],'map':'{}'}
# A single run never deletes more than this many models per provider; anything
# larger is treated as an external rewrite and refilled (see discovery_merge).
DISCOVERY_DELETE_LIMIT=5

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

def gateway_models(base_url=GATEWAY_BASE_URL, timeout=15):
    """Model entries the local gateway reports. Raises when it is unreachable."""
    request=urllib.request.Request(base_url.rstrip('/')+'/models',headers={'User-Agent':'ZCode-Standalone-Model-Discovery/1.0'})
    with urllib.request.urlopen(request,timeout=timeout) as response:payload=json.load(response)
    entries=payload.get('data') if isinstance(payload,dict) else payload
    if not isinstance(entries,list):raise ValueError('Gateway model list is not a list')
    models=[entry for entry in entries if isinstance(entry,dict) and isinstance(entry.get('id'),str) and '/' in entry['id']]
    if not models:raise ValueError('Gateway reported no usable models')
    return models

def namespace_of(model_id):
    return model_id.split('/',1)[0]

def discovery_groups(models, minimum=DISCOVERY_GROUP_MIN):
    """Combo first, then namespaces at/above the threshold, then the rest merged."""
    buckets={}
    for entry in models:buckets.setdefault(namespace_of(entry['id']),[]).append(entry)
    combos=buckets.pop(DISCOVERY_COMBO_GROUP,[])
    minimum=max(0,minimum)
    wide={key:value for key,value in buckets.items() if len(value)>=minimum}
    narrow=[entry for key,value in buckets.items() if len(value)<minimum for entry in value]
    groups=[]
    if combos:groups.append((DISCOVERY_COMBO_GROUP,combos))
    for key in sorted(wide,key=lambda key:(-len(wide[key]),key)):groups.append((key,wide[key]))
    if narrow:groups.append((DISCOVERY_OVERFLOW_GROUP,narrow))
    return groups

def discovery_provider(group_key):
    if group_key==DISCOVERY_COMBO_GROUP:return DISCOVERY_FAMILY_PREFIX,'9Router'
    return DISCOVERY_FAMILY_PREFIX+'-'+group_key,'9Router · '+group_key

def first_limit(*values):
    for value in values:
        if isinstance(value,int) and not isinstance(value,bool) and value>0:return value
    return None

def discovery_model_config(entry, catalog=None):
    """Manual model rule for one gateway entry, or None when no limits are known.

    Live gateway metadata wins; the models.dev snapshot the repo already syncs is
    the fallback for models the gateway lists without limits (e.g. the free
    OpenCode tier). Nothing is invented: when neither source knows the limits the
    model is skipped and reported instead.
    """
    caps=entry.get('capabilities') if isinstance(entry.get('capabilities'),dict) else {}
    meta=(metadata(entry['id'],catalog or {}) or {})
    limit=meta.get('limit') if isinstance(meta.get('limit'),dict) else {}
    context=first_limit(caps.get('contextWindow'),entry.get('context_length'),limit.get('context'))
    output=first_limit(caps.get('maxOutput'),entry.get('max_completion_tokens'),limit.get('output'))
    if not context or not output:return None
    inputs=[name for name in ((meta.get('modalities') or {}).get('input') or []) if isinstance(name,str)]
    def flag(name, modality):
        value=caps.get(name)
        return value if isinstance(value,bool) else modality in inputs
    properties={
        'contextWindow':context,
        'supportsJsonSchemaOutput':caps.get('structuredOutput') is True or meta.get('structured_output') is True,
        'supportsNativeWebSearch':caps.get('search') is True,
        # The gateway does not report mid-conversation system support, so it is
        # not claimed here (the app may otherwise inject messages the model rejects).
        'supportsMidConversationSystem':False,
        'inputFormat':{'supportsImage':flag('vision','image'),'supportsVideo':flag('videoInput','video'),'supportsPdf':flag('pdf','pdf')},
    }
    specs={'maxOutputTokens':{'max':output}}
    values=None
    if caps.get('reasoning') is True and caps.get('thinkingEffortSupported') is True:
        values=(['off'] if caps.get('thinkingCanDisable') is True else [])+list(DISCOVERY_EFFORT_LEVELS)
    else:
        # Snapshot levels are only offered when the gateway accepts the string, so
        # a model whose snapshot lists levels the gateway rejects cannot produce a
        # 400 from a control that looked supported.
        for option in (meta.get('reasoning_options') or []):
            if isinstance(option,dict) and option.get('type')=='effort':
                offered=[value for value in option.get('values') or [] if value in DISCOVERY_EFFORT_LEVELS]
                if offered:values=offered
                break
    specs['reasoningLevel']={'values':list(dict.fromkeys(values)),'map':'{"reasoning_effort": reasoningLevel}'} if values else copy.deepcopy(DISCOVERY_INERT_REASONING)
    return {'properties':properties,'optionSpecs':specs}

def catalog_model_matches():
    """Model patterns the bundled provider catalog still describes, or None if unknown."""
    try:
        path=ROOT.parents[1]/'app/resources/config/provider/zcode-builtin.json'
        data=json.loads(path.read_text())
        entries=((data.get('config') or {}).get('modelConfigRules') or {}).get('modelRules') or []
    except (OSError,ValueError):
        return None
    patterns={entry.get('modelMatch') for entry in entries if isinstance(entry.get('modelMatch'),str)}
    return patterns or None

def discovery_merge(data, models, state, catalog=None, base_url=GATEWAY_BASE_URL, bootstrap=False, minimum=DISCOVERY_GROUP_MIN, catalog_matches=None):
    """Extend the 9Router provider family with gateway models, preserving user choices.

    User intent is respected in both directions: a model the user disabled stays
    disabled (present in modelOrder/manual rules but absent from personalModelIds),
    a model the user deleted is remembered and never resurrected, and a manual rule
    the user edited by hand is left untouched.
    """
    out=copy.deepcopy(data);newstate=copy.deepcopy(state);changes=[]
    cfg=out.setdefault('config',{})
    providers=cfg.setdefault('providerConfigRules',{}).setdefault('providerRules',[])
    model_cfg=cfg.setdefault('modelConfigRules',{})
    rules=model_cfg.setdefault('manualProviderModelRules',[])
    smart_rules=model_cfg.setdefault('providerModelRules',[])
    discovery=newstate.setdefault('discovery',{})
    owned=discovery.setdefault('rules',{})
    removed=set(discovery.get('removed',[]))
    # Automatic runs fill the groups that exist; only an explicit request (the Auto
    # Detect button, `make models` → bootstrap) creates or rebuilds the family, so a
    # group the user deleted in the UI stays deleted until they ask for it again.
    allow_new=bool(bootstrap)

    def is_family(provider):
        return str(provider.get('providerId','')).startswith(DISCOVERY_FAMILY_PREFIX) or \
            ((provider.get('config') or {}).get('api') or {}).get('baseUrl')==base_url

    def is_smart(provider_id,model_id):
        """Catalog (smart) rules and manual rules cannot describe the same model.

        A stored smart rule only counts while the bundled catalog still describes
        the model: a rule left behind for a model the catalog no longer defines is
        inert (the host cannot render it), so discovery replaces it with a manual
        rule instead of leaving the model unusable.
        """
        stored=next((rule for rule in smart_rules if rule.get('providerId')==provider_id and rule.get('modelId')==model_id),None)
        if stored is not None:return catalog_matches is None or model_id in catalog_matches
        provider=next((item for item in providers if item.get('providerId')==provider_id),None)
        builtin=((provider or {}).get('config') or {}).get('builtinModelIds') or []
        return model_id in builtin

    family=[provider for provider in providers if is_family(provider)]
    if not family and not bootstrap:return out,newstate,changes,'no-provider'
    # Distinguish a handful of user deletions from an external rewrite (or wipe) of
    # the file. The decision is made once, from the whole provider family: many
    # missing ids, or a provider left with nothing, is a rewrite and discovery
    # refills instead of blacklisting every model as "deleted by the user".
    vanished={}
    for provider in family:
        provider_id=str(provider.get('providerId'))
        pc=provider.get('config') or {}
        present=set(pc.get('personalModelIds') or [])|set(pc.get('modelOrder') or [])
        owned_keys=[item for item in owned if item.startswith(provider_id+'/')]
        missing=[item for item in owned_keys if item.split('/',1)[1] not in present]
        if missing:vanished[provider_id]=(missing,present)
    total_vanished=sum(len(missing) for missing,_ in vanished.values())
    emptied=[provider_id for provider_id,(_,present) in vanished.items() if not present]
    if 0<total_vanished<=DISCOVERY_DELETE_LIMIT and not emptied:
        for provider_id,(missing,_present) in vanished.items():
            for item in missing:removed.add(item.split('/',1)[1])
    elif total_vanished:
        print('Provider family missing',total_vanished,'models; refilling instead of treating them as deleted')
    for missing,_present in vanished.values():
        for item in missing:owned.pop(item,None)
    # Prefer a family member that already carries a real key, so a key the user
    # pasted into any one group becomes the key of the whole family.
    anchor=next((provider for provider in family
                 if ((provider.get('config') or {}).get('access') or {}).get('apiKey')
                 and ((provider.get('config') or {}).get('access') or {}).get('apiKey')!=DISCOVERY_API_KEY_PLACEHOLDER),
                family[0] if family else None)
    access=copy.deepcopy((anchor or {}).get('config',{}).get('access') or {'type':'api-key','apiKey':DISCOVERY_API_KEY_PLACEHOLDER})

    rejected=[];planned=[]
    for group_key,entries in discovery_groups(models,minimum):
        kept=[]
        for entry in entries:
            config=discovery_model_config(entry,catalog)
            if config is None:rejected.append(entry['id'])
            else:kept.append((entry['id'],config))
        if kept:planned.append((group_key,kept))

    for group_key,entries in planned:
        provider_id,name=discovery_provider(group_key)
        provider=next((item for item in providers if item.get('providerId')==provider_id),None)
        if provider is None:
            if not allow_new:continue          # automatic runs never create groups
            provider={'providerId':provider_id,'providerName':name,'enabled':True,
                      'config':{'group':'standard-personal','access':copy.deepcopy(access),
                                'api':{'type':'openai-chat-completions','baseUrl':base_url},
                                'personalModelIds':[],'modelOrder':[]}}
            providers.append(provider);changes.append('provider:'+provider_id)
        pc=provider.setdefault('config',{})
        pc.setdefault('group','standard-personal')
        pc.setdefault('api',{'type':'openai-chat-completions','baseUrl':base_url})
        current_access=pc.get('access') or {}
        # One key for the whole family: adopt the anchor's key when this provider
        # still carries the placeholder, so the user pastes a real key only once.
        if not current_access.get('apiKey') or current_access.get('apiKey')==DISCOVERY_API_KEY_PLACEHOLDER:
            pc['access']=copy.deepcopy(access)
        enabled=pc.setdefault('personalModelIds',[])
        order=pc.setdefault('modelOrder',[])
        available={model_id for model_id,_ in entries}
        known=set(order)|set(enabled)|{rule.get('modelId') for rule in rules if rule.get('providerId')==provider_id}
        for model_id,config in entries:
            if model_id in removed:
                # The user re-added a model they had deleted: hand it back to discovery.
                if model_id in enabled:removed.discard(model_id)
                continue
            key=provider_id+'/'+model_id
            new_model=model_id not in known
            if new_model:
                new_config=copy.deepcopy(config)
                rules.append({'providerId':provider_id,'modelId':model_id,'config':new_config})
                if model_id not in order:order.append(model_id)
                if model_id not in enabled:enabled.append(model_id)
                owned[key]=copy.deepcopy(new_config);changes.append(model_id)
                continue
            # A model the host still knows (rule present) but which is missing from the
            # provider's lists is re-listed: its rule keeps the on/off switch, so a
            # model the user switched off comes back off, and a list rewritten elsewhere
            # is repaired instead of leaving models unusable.
            if model_id not in order:order.append(model_id);changes.append('order:'+model_id)
            if model_id not in enabled:enabled.append(model_id);changes.append('listed:'+model_id)
            rule=next((item for item in rules if item.get('providerId')==provider_id and item.get('modelId')==model_id),None)
            if is_smart(provider_id,model_id):
                # The catalog already describes this model: keep it selectable but
                # never write a second (manual) rule for it. A manual rule we wrote
                # earlier is removed so the host schema stops rejecting the file.
                if model_id not in order:order.append(model_id)
                if rule is not None:
                    rules.remove(rule);owned.pop(key,None);changes.append('smart:'+model_id)
                continue
            stale=next((item for item in smart_rules if item.get('providerId')==provider_id and item.get('modelId')==model_id),None)
            if stale is not None:
                # The catalog no longer defines this model: drop the inert smart rule
                # so the manual rule below can describe it (both at once is invalid).
                smart_rules.remove(stale);changes.append('stale-smart:'+model_id)
            if new_model:
                new_config=copy.deepcopy(config)
                rules.append({'providerId':provider_id,'modelId':model_id,'config':new_config})
                if model_id not in order:order.append(model_id)
                owned[key]=copy.deepcopy(new_config);changes.append(model_id)
                continue
            if rule is None:
                # known only because a rule exists for it elsewhere: recreate the rule
                rules.append({'providerId':provider_id,'modelId':model_id,'config':copy.deepcopy(config)})
                owned[key]=copy.deepcopy(config);changes.append(model_id)
                continue
            # The host stores the per-model on/off switch as config.enabled on the
            # rule, so metadata refreshes must carry that user choice over instead
            # of overwriting or dropping it.
            current_config=rule.get('config') or {}
            user_flags={name:value for name,value in current_config.items() if name=='enabled'}
            metadata={name:value for name,value in current_config.items() if name!='enabled'}
            previous=owned.get(key)
            if previous is None:
                owned[key]=copy.deepcopy(metadata)          # hand-written rule, adopted as ours-once
            elif metadata==previous:
                refreshed={**copy.deepcopy(config),**user_flags}
                if refreshed!=current_config:
                    rule['config']=refreshed;owned[key]=copy.deepcopy(config);changes.append(model_id)
    discovery['removed']=sorted(removed)
    discovery['skipped']=sorted(set(rejected))
    discovery['groups']={discovery_provider(group_key)[0]:len(entries) for group_key,entries in planned}
    provider_order=cfg.setdefault('providerOrder',[])
    for group_key,_ in planned:
        provider_id,_name=discovery_provider(group_key)
        if provider_id not in provider_order:provider_order.append(provider_id)
    return out,newstate,changes,'ok' if planned else 'empty'


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

def parse_args(argv=None):
    import argparse
    parser=argparse.ArgumentParser(description='Sync standalone model metadata and discover 9Router gateway models.')
    parser.add_argument('--discover',action='store_true',help='Refresh the gateway model list now, ignoring the TTL.')
    parser.add_argument('--bootstrap',action='store_true',help='Create the 9Router provider family when it does not exist yet.')
    return parser.parse_args(argv)

def model_inventory(data):
    """Count enabled personal models per provider, for the destructive-write guard."""
    providers=((data.get('config') or {}).get('providerConfigRules') or {}).get('providerRules') or []
    return {(provider.get('providerId'),model_id)
            for provider in providers
            for model_id in ((provider.get('config') or {}).get('personalModelIds') or [])}

def commit(config, raw, out, state_root, namespace, changes):
    """Write the merged config once, with backup and an in-flight-save recheck.

    Returns True when the file was written, False when there was nothing to do, and
    "concurrent" when another writer (the app saving settings) moved the file first:
    the caller retries from a fresh read instead of dropping the update.
    """
    if not changes:return False
    if config.read_bytes()!=raw:
        print('Config changed concurrently; retrying from a fresh read');return 'concurrent'
    # Safety net for any writer bug (ours or the app's): this sync only ever adds
    # models, so a result that drops part of the inventory is refused and the file
    # is left untouched.
    before,after=model_inventory(json.loads(raw)),model_inventory(out)
    if len(before)>=5 and len(after)<len(before):
        print(f'Refusing to drop {len(before)-len(after)} of {len(before)} enabled models; config left untouched')
        return 'refused'
    backups=state_root/'backups';backups.mkdir(exist_ok=True,mode=0o700)
    if namespace:private_dir(backups)
    name='provider_config-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.json'
    backup=backups/name;backup.write_bytes(raw);backup.chmod(0o600)
    # Recheck after backup so an in-flight UI save does not get overwritten.
    if config.read_bytes()!=raw:
        print('Config changed concurrently; retrying from a fresh read');return 'concurrent'
    atomic(config,out)
    for old in sorted(backups.glob('provider_config-*.json'))[:-10]:old.unlink()
    return True

def main(argv=None):
    args=parse_args(argv)
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
            for attempt in range(3):
                status=run_once(args,config,state_root,namespace)
                if status!='concurrent':break
                time.sleep(0.4)



def run_once(args, config, state_root, namespace):
    """One discover-enrich-commit pass; "concurrent" tells the caller to retry."""
    if not config.exists():return 'missing'
    raw=config.read_bytes();data=json.loads(raw)
    state=load(state_root/'state.json',{'managed':{}})
    pristine=copy.deepcopy(state)
    discovery=state.setdefault('discovery',{})
    changes=[];models=None
    providers=((data.get('config') or {}).get('providerConfigRules') or {}).get('providerRules') or []
    family=[provider for provider in providers
            if str(provider.get('providerId','')).startswith(DISCOVERY_FAMILY_PREFIX)
            or (((provider.get('config') or {}).get('api') or {}).get('baseUrl')==GATEWAY_BASE_URL)]
    due=time.time()-float(discovery.get('fetchedAt') or 0)>=DISCOVERY_TTL_SECONDS
    cooling=time.time()-float(discovery.get('failedAt') or 0)<DISCOVERY_FAILURE_BACKOFF
    # A provider just added from the UI has nothing to select yet, and a
    # provider we have never grouped is new as well: fill both right away
    # instead of waiting for the TTL.
    grouped=discovery.get('groups') or {}
    needs_fill=any(not ((provider.get('config') or {}).get('personalModelIds'))
                   or str(provider.get('providerId')) not in grouped for provider in family)
    if args.bootstrap and not family:due=True
    if args.discover or ((due or needs_fill) and family and not cooling):
        try:
            models=gateway_models()
            discovery['fetchedAt']=time.time()
            discovery.pop('failedAt',None)
            print('Gateway models:',len(models))
        except Exception as error:
            models=None
            discovery['failedAt']=time.time()
            print('Model discovery unavailable; keeping current config:',type(error).__name__)
    elif not family and not args.bootstrap and not discovery.get('hintShown'):
        discovery['hintShown']=True
        print('No 9Router provider yet; add one in Model settings or run with --bootstrap')
    catalog=refresh_catalog(state_root)
    out,newstate,changes=enrich(data,catalog,state)
    if models:
        out,newstate,found,status=discovery_merge(out,models,newstate,catalog,bootstrap=bool(args.bootstrap),
                                                  catalog_matches=catalog_model_matches())
        if status=='ok':
            print('Discovered groups:',', '.join(f'{key}={value}' for key,value in sorted(newstate['discovery'].get('groups',{}).items())))
            skipped=newstate['discovery'].get('skipped') or []
            if skipped:print('Skipped models without limits:',len(skipped))
        changes=changes+found
    status=commit(config,raw,out,state_root,namespace,changes)
    if status is True:print('Updated provider config:',len(changes),'entry(ies)')
    elif status=='concurrent':print('Config changed concurrently; retry on next pass')
    if newstate!=pristine:atomic(state_root/'state.json',newstate)
    return status if changes else 'no-change'



if __name__=='__main__':main()
