'use strict';
// Windows runtime for the standalone model sync. Ports `services/model-sync/sync.py`
// (same CLI, namespace env, artifacts, constants, messages and JSON shape) so Auto
// Detect and an in-app/Task Scheduler timer work on targets without a Python runtime.
//
// Gateway override: `CCODE_MODEL_SYNC_GATEWAY` replaces `GATEWAY_BASE_URL` for
// discovery, grouping and the family match; unset it keeps the Linux constant, so
// the default behavior is unchanged.
//
// Documented differences from the Python module: POSIX `flock` has no portable Node
// equivalent, so the run guard is a create-exclusive `sync.lock` holding the pid (a
// lock whose process is gone, or a lock without a pid older than LOCK_STALE_MS, is
// stolen) and the shared namespace operations lock `.<root>.operations.lock` that
// `scripts/data_backup.py` and the launcher hold is not taken from Node.

const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { randomBytes } = require('node:crypto');
const { isDeepStrictEqual } = require('node:util');

const ROOT = __dirname;
const CATALOG_URL = 'https://raw.githubusercontent.com/anomalyco/opencode/dev/packages/core/src/models-dev/snapshot.txt';
const ALIASES = { oc: 'opencode', ocg: 'opencode-go', gq: 'groq', cmc: 'commandcode', or: 'openrouter' };
// Local 9Router gateway: its /v1/models list drives discovery and grouping. The
// gateway answers unauthenticated local calls (verified), so the placeholder key
// below is not a secret; an existing 9Router provider keeps its own key instead.
const GATEWAY_BASE_URL = 'http://127.0.0.1:20128/v1';
const DISCOVERY_FAMILY_PREFIX = '9router';
const DISCOVERY_COMBO_GROUP = 'combo';
const DISCOVERY_OVERFLOW_GROUP = 'lainnya';
const DISCOVERY_GROUP_MIN = 10;
const DISCOVERY_TTL_SECONDS = 12 * 3600;
const DISCOVERY_FAILURE_BACKOFF = 15 * 60;
const DISCOVERY_API_KEY_PLACEHOLDER = 'local-gateway';
// reasoning_effort values the gateway validates; "off" is only offered when the
// model metadata says thinking can be disabled, and the level list is only
// offered when the gateway reports effort support (never a label-only control).
const DISCOVERY_EFFORT_LEVELS = ['low', 'medium', 'high', 'xhigh', 'max'];
// The manual-model-rule schema requires config.optionSpecs.reasoningLevel on every
// rule. Where the gateway does not verify effort support this inert placeholder is
// written instead (one value, nothing mapped), so the control never offers levels
// that would only rename themselves or be rejected upstream.
const DISCOVERY_INERT_REASONING = { values: ['disabled'], map: '{}' };
// A single run never deletes more than this many models per provider; anything
// larger is treated as an external rewrite and refilled (see discoveryMerge).
const DISCOVERY_DELETE_LIMIT = 5;
// A lock holding no pid (or a pid that is gone) is only stolen after this long.
const LOCK_STALE_MS = 10 * 60 * 1000;

function sleep(ms) { return new Promise(resolve => setTimeout(resolve, ms)); }
function load(target, fallback) {
  try { return JSON.parse(fs.readFileSync(target, 'utf8')); } catch { return structuredClone(fallback); }
}

function atomic(target, value) {
  const dir = path.dirname(target);
  fs.mkdirSync(dir, { recursive: true, mode: 0o700 });
  const name = path.join(dir, `.${path.basename(target)}.${randomBytes(6).toString('hex')}`);
  try {
    fs.writeFileSync(name, `${JSON.stringify(value, null, 2)}\n`, { mode: 0o600 });
    fs.renameSync(name, target);
  } finally {
    if (fs.existsSync(name)) { try { fs.unlinkSync(name); } catch { /* already gone */ } }
  }
}

function expandUser(value) {
  return value.startsWith('~') ? path.join(os.homedir(), value.replace(/^~[\\/]?/, '')) : value;
}

function safePath(value) {
  const resolved = path.resolve(expandUser(String(value)));
  for (let current = resolved; ;) {
    let stat = null;
    try { stat = fs.lstatSync(current); } catch { stat = null; }
    if (stat && stat.isSymbolicLink()) throw new Error(`Symlink path refused: ${current}`);
    const parent = path.dirname(current);
    if (parent === current) break;
    current = parent;
  }
  return resolved;
}

function namespaceRoot(value) {
  const resolved = safePath(value || process.env.CCODE_STANDALONE_ROOT || path.join(os.homedir(), '.local', 'share', 'ccode'));
  const project = path.resolve(__dirname, '..', '..');
  const root = path.parse(resolved).root;
  const same = (left, right) => (process.platform === 'win32' ? left.toLowerCase() === right.toLowerCase() : left === right);
  if (same(resolved, root) || same(resolved, os.homedir()) || same(resolved, project)) throw new Error('Refusing an unsafe namespace root');
  return resolved;
}

function privateDir(dir) {
  const target = safePath(dir);
  fs.mkdirSync(target, { recursive: true, mode: 0o700 });
  fs.chmodSync(target, 0o700);
  return target;
}

function isInside(parent, child) {
  const relative = path.relative(parent, child);
  return relative !== '' && !relative.startsWith('..') && !path.isAbsolute(relative);
}

function storagePaths() {
  const config = process.env.CCODE_MODEL_SYNC_CONFIG;
  const state = process.env.CCODE_MODEL_SYNC_STATE;
  if (Boolean(config) !== Boolean(state)) throw new Error('Set both CCODE_MODEL_SYNC_CONFIG and CCODE_MODEL_SYNC_STATE');
  if (config) {
    const configPath = safePath(config);
    const stateRoot = safePath(state);
    const root = namespaceRoot(process.env.CCODE_STANDALONE_ROOT || path.dirname(stateRoot));
    if (!isInside(root, configPath) || !isInside(root, stateRoot)) throw new Error('Standalone sync paths must be inside their namespace');
    return [configPath, stateRoot, root];
  }
  // The existing upstream timer intentionally keeps its original config and state.
  return [path.join(os.homedir(), '.ccode', 'v2', 'provider_config.json'), ROOT, null];
}

function parseArgs(argv = []) {
  const args = { discover: false, bootstrap: false };
  for (const token of argv) {
    if (token === '--discover') args.discover = true;
    else if (token === '--bootstrap') args.bootstrap = true;
    else if (token === '-h' || token === '--help') args.help = true;
    else {
      const error = new Error(`unrecognized arguments: ${token}`);
      error.exitCode = 2;
      throw error;
    }
  }
  return args;
}

function gatewayBaseUrl(env = process.env) {
  const value = typeof env.CCODE_MODEL_SYNC_GATEWAY === 'string' ? env.CCODE_MODEL_SYNC_GATEWAY.trim() : '';
  return value || GATEWAY_BASE_URL;
}

function metadata(modelId, catalog) {
  if (!modelId.includes('/') || modelId.startsWith('combo/')) return null;
  const [prefix, mid] = [modelId.slice(0, modelId.indexOf('/')), modelId.slice(modelId.indexOf('/') + 1)];
  if (mid.endsWith(')') && mid.includes('(')) return null; // fixed effort suffix remains authoritative
  const provider = ALIASES[prefix] ?? prefix;
  return catalog?.[provider]?.models?.[mid] ?? null;
}

function dedupe(values) { return [...new Set(values)]; }

function reasoningSpec(meta, modelId) {
  const options = meta.reasoning_options;
  if (options === undefined || options === null) return null;
  const effort = options.find(option => option?.type === 'effort');
  if (effort) {
    const values = effort.values ?? [];
    if (values.length && values.every(value => typeof value === 'string' && value.trim())) {
      return { values: dedupe(values), map: '{"reasoning_effort": reasoningLevel}' };
    }
  }
  if (options.some(option => option?.type === 'toggle')) {
    const family = `${meta.family ?? ''} ${modelId}`.toLowerCase();
    let expression = null;
    if (family.includes('ling-')) expression = '{"reasoning": {"enabled": reasoningLevel == "enabled"}}';
    else if (['longcat', 'mimo', 'glm', 'deepseek'].some(name => family.includes(name))) expression = '{"thinking": {"type": reasoningLevel == "disabled" ? "disabled" : "enabled"}}';
    else if (family.includes('qwen')) expression = '{"enable_thinking": reasoningLevel == "enabled"}';
    else return null; // a toggle needs a known provider wire format
    return { values: ['disabled', 'enabled'], map: expression };
  }
  if (Array.isArray(options) && options.length === 0 && 'reasoning' in meta) {
    return { values: [meta.reasoning ? 'enabled' : 'disabled'], map: '{}' };
  }
  return null;
}

function placeholder(spec) {
  return spec === undefined || spec === null
    || (isDeepStrictEqual(spec.values, ['disabled', 'enabled']) && String(spec.map ?? '{}').trim() === '{}');
}

function enrich(data, catalog, state) {
  const out = structuredClone(data);
  const newstate = structuredClone(state);
  const changes = [];
  const cfg = out.config ?? {};
  const providers = cfg.providerConfigRules?.providerRules ?? [];
  const modelCfg = (cfg.modelConfigRules ??= {});
  const rules = (modelCfg.manualProviderModelRules ??= []);
  const managed = (newstate.managed ??= {});
  for (const provider of providers) {
    if (provider.providerId !== 'vansrouter') continue;
    const pc = provider.config ?? {};
    if (pc.api?.type !== 'openai-chat-completions') continue;
    for (const mid of pc.personalModelIds ?? []) {
      const meta = metadata(mid, catalog);
      if (!meta) continue;
      const desired = reasoningSpec(meta, mid);
      if (!desired) continue;
      const key = `vansrouter/${mid}`;
      let rule = rules.find(item => item?.providerId === 'vansrouter' && item?.modelId === mid) ?? null;
      if (rule === null) {
        const limit = meta.limit && typeof meta.limit === 'object' ? meta.limit : {};
        const inputs = (meta.modalities?.input ?? []).filter(name => typeof name === 'string');
        const props = {
          contextWindow: Math.max(1, limit.context || 128000),
          supportsJsonSchemaOutput: false,
          supportsNativeWebSearch: false,
          supportsMidConversationSystem: true,
          inputFormat: { supportsImage: inputs.includes('image'), supportsVideo: false, supportsPdf: false },
        };
        rule = { providerId: 'vansrouter', modelId: mid, config: { properties: props, optionSpecs: {} } };
        rules.push(rule);
      }
      const specs = (rule.config.optionSpecs ??= {});
      const current = specs.reasoningLevel;
      const previous = managed[key];
      if (previous !== undefined && previous !== null && !isDeepStrictEqual(current, previous)) continue; // user changed this field
      if ((previous === undefined || previous === null) && !placeholder(current) && !isDeepStrictEqual(current, desired)) continue; // explicit mapping belongs to the user
      if (!isDeepStrictEqual(current, desired)) {
        specs.reasoningLevel = desired;
        changes.push(mid);
      }
      managed[key] = structuredClone(desired);
    }
  }
  return [out, newstate, changes];
}

async function fetchJson(url, timeoutMs, headers) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, { headers, signal: controller.signal });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return await response.json();
  } finally {
    clearTimeout(timer);
  }
}

async function refreshCatalog(cacheRoot = ROOT) {
  const target = path.join(cacheRoot, 'catalog.json');
  let stat = null;
  try { stat = fs.statSync(target); } catch { stat = null; }
  if (stat && Date.now() / 1000 - stat.mtimeMs / 1000 < 86400) return load(target, {});
  try {
    const catalog = await fetchJson(CATALOG_URL, 20000, { 'User-Agent': 'CCode-Vansrouter-Metadata-Sync/1.0' });
    if (!catalog || typeof catalog !== 'object' || Array.isArray(catalog) || !('opencode' in catalog)) throw new Error('invalid catalog');
    atomic(target, catalog);
  } catch (error) {
    console.log('Catalog refresh unavailable; using cached metadata:', error?.name ?? 'Error');
  }
  return load(target, {});
}

async function gatewayModels(baseUrl = gatewayBaseUrl(), timeout = 15) {
  const url = `${String(baseUrl).replace(/\/+$/, '')}/models`;
  const payload = await fetchJson(url, timeout * 1000, { 'User-Agent': 'CCode-Standalone-Model-Discovery/1.0' });
  const entries = payload && typeof payload === 'object' && !Array.isArray(payload) ? payload.data : payload;
  if (!Array.isArray(entries)) throw new Error('Gateway model list is not a list');
  const models = entries.filter(entry => entry && typeof entry === 'object' && typeof entry.id === 'string' && entry.id.includes('/'));
  if (!models.length) throw new Error('Gateway reported no usable models');
  return models;
}

function namespaceOf(modelId) { return modelId.includes('/') ? modelId.slice(0, modelId.indexOf('/')) : modelId; }

function discoveryGroups(models, minimum = DISCOVERY_GROUP_MIN) {
  const buckets = new Map();
  for (const entry of models) {
    const key = namespaceOf(entry.id);
    if (!buckets.has(key)) buckets.set(key, []);
    buckets.get(key).push(entry);
  }
  const combos = buckets.get(DISCOVERY_COMBO_GROUP) ?? [];
  buckets.delete(DISCOVERY_COMBO_GROUP);
  const floor = Math.max(0, minimum);
  const wide = [...buckets].filter(([, value]) => value.length >= floor);
  const narrow = [...buckets].filter(([, value]) => value.length < floor).flatMap(([, value]) => value);
  const groups = [];
  if (combos.length) groups.push([DISCOVERY_COMBO_GROUP, combos]);
  for (const [key, value] of wide.sort(([leftKey, left], [rightKey, right]) => right.length - left.length || (leftKey < rightKey ? -1 : leftKey > rightKey ? 1 : 0))) {
    groups.push([key, value]);
  }
  if (narrow.length) groups.push([DISCOVERY_OVERFLOW_GROUP, narrow]);
  return groups;
}

function discoveryProvider(groupKey) {
  if (groupKey === DISCOVERY_COMBO_GROUP) return [DISCOVERY_FAMILY_PREFIX, '9Router'];
  return [`${DISCOVERY_FAMILY_PREFIX}-${groupKey}`, `9Router \u00b7 ${groupKey}`];
}

function firstLimit(...values) {
  for (const value of values) {
    if (Number.isInteger(value) && value > 0) return value;
  }
  return null;
}

function discoveryModelConfig(entry, catalog = null) {
  const caps = entry.capabilities && typeof entry.capabilities === 'object' ? entry.capabilities : {};
  const meta = metadata(entry.id, catalog ?? {}) ?? {};
  const limit = meta.limit && typeof meta.limit === 'object' ? meta.limit : {};
  const context = firstLimit(caps.contextWindow, entry.context_length, limit.context);
  const output = firstLimit(caps.maxOutput, entry.max_completion_tokens, limit.output);
  if (!context || !output) return null;
  const inputs = (meta.modalities?.input ?? []).filter(name => typeof name === 'string');
  const flag = (name, modality) => (typeof caps[name] === 'boolean' ? caps[name] : inputs.includes(modality));
  const properties = {
    contextWindow: context,
    supportsJsonSchemaOutput: caps.structuredOutput === true || meta.structured_output === true,
    supportsNativeWebSearch: caps.search === true,
    // The gateway does not report mid-conversation system support, so it is
    // not claimed here (the app may otherwise inject messages the model rejects).
    supportsMidConversationSystem: false,
    inputFormat: { supportsImage: flag('vision', 'image'), supportsVideo: flag('videoInput', 'video'), supportsPdf: flag('pdf', 'pdf') },
  };
  const specs = { maxOutputTokens: { max: output } };
  let values = null;
  if (caps.reasoning === true && caps.thinkingEffortSupported === true) {
    values = (caps.thinkingCanDisable === true ? ['off'] : []).concat(DISCOVERY_EFFORT_LEVELS);
  } else {
    // Snapshot levels are only offered when the gateway accepts the string, so
    // a model whose snapshot lists levels the gateway rejects cannot produce a
    // 400 from a control that looked supported.
    for (const option of meta.reasoning_options ?? []) {
      if (option && typeof option === 'object' && option.type === 'effort') {
        const offered = (option.values ?? []).filter(value => DISCOVERY_EFFORT_LEVELS.includes(value));
        if (offered.length) values = offered;
        break;
      }
    }
  }
  specs.reasoningLevel = values ? { values: dedupe(values), map: '{"reasoning_effort": reasoningLevel}' } : structuredClone(DISCOVERY_INERT_REASONING);
  return { properties, optionSpecs: specs };
}

function catalogModelMatches() {
  const candidates = [];
  if (process.resourcesPath) candidates.push(path.join(process.resourcesPath, 'config', 'provider', 'ccode-builtin.json'));
  candidates.push(path.resolve(__dirname, '..', '..', 'app', 'resources', 'config', 'provider', 'ccode-builtin.json'));
  for (const target of candidates) {
    let entries = null;
    try {
      const data = JSON.parse(fs.readFileSync(target, 'utf8'));
      entries = data?.config?.modelConfigRules?.modelRules ?? [];
    } catch { continue; }
    const patterns = new Set(entries.filter(entry => typeof entry?.modelMatch === 'string').map(entry => entry.modelMatch));
    return patterns.size ? patterns : null;
  }
  return null;
}

function discoveryMerge(data, models, state, catalog = null, baseUrl = GATEWAY_BASE_URL, bootstrap = false, minimum = DISCOVERY_GROUP_MIN, catalogMatches = null) {
  const out = structuredClone(data);
  const newstate = structuredClone(state);
  const changes = [];
  const cfg = (out.config ??= {});
  const providers = ((cfg.providerConfigRules ??= {}).providerRules ??= []);
  const modelCfg = (cfg.modelConfigRules ??= {});
  const rules = (modelCfg.manualProviderModelRules ??= []);
  const smartRules = (modelCfg.providerModelRules ??= []);
  const discovery = (newstate.discovery ??= {});
  const owned = (discovery.rules ??= {});
  const removed = new Set(Array.isArray(discovery.removed) ? discovery.removed : []);
  // Automatic runs fill the groups that exist; only an explicit request (the Auto
  // Detect button, `make models` → bootstrap) creates or rebuilds the family, so a
  // group the user deleted in the UI stays deleted until they ask for it again.
  const allowNew = Boolean(bootstrap);

  const isFamily = provider => String(provider?.providerId ?? '').startsWith(DISCOVERY_FAMILY_PREFIX)
    || ((provider?.config ?? {}).api ?? {}).baseUrl === baseUrl;
  // Catalog (smart) rules and manual rules cannot describe the same model: a rule
  // left behind for a model the catalog no longer defines is inert, so discovery
  // replaces it with a manual rule instead of leaving the model unusable.
  const isSmart = (providerId, modelId) => {
    const stored = smartRules.find(rule => rule?.providerId === providerId && rule?.modelId === modelId);
    if (stored != null) return catalogMatches == null ? true : catalogMatches.has(modelId);
    const provider = providers.find(item => item?.providerId === providerId);
    const builtin = ((provider ?? {}).config ?? {}).builtinModelIds ?? [];
    return builtin.includes(modelId);
  };

  const family = providers.filter(isFamily);
  if (!family.length && !bootstrap) return [out, newstate, changes, 'no-provider'];
  // Distinguish a handful of user deletions from an external rewrite (or wipe) of
  // the file. The decision is made once, from the whole provider family: many
  // missing ids, or a provider left with nothing, is a rewrite and discovery
  // refills instead of blacklisting every model as "deleted by the user".
  const vanished = new Map();
  for (const provider of family) {
    const providerId = String(provider.providerId);
    const pc = provider.config ?? {};
    const present = new Set([...(pc.personalModelIds ?? []), ...(pc.modelOrder ?? [])]);
    const missing = Object.keys(owned).filter(item => item.startsWith(`${providerId}/`) && !present.has(item.slice(item.indexOf('/') + 1)));
    if (missing.length) vanished.set(providerId, { missing, present });
  }
  const totalVanished = [...vanished.values()].reduce((sum, entry) => sum + entry.missing.length, 0);
  const emptied = [...vanished.values()].filter(entry => entry.present.size === 0).length;
  if (totalVanished > 0 && totalVanished <= DISCOVERY_DELETE_LIMIT && !emptied) {
    for (const { missing } of vanished.values()) {
      for (const item of missing) removed.add(item.slice(item.indexOf('/') + 1));
    }
  } else if (totalVanished > 0) {
    console.log('Provider family missing', totalVanished, 'models; refilling instead of treating them as deleted');
  }
  for (const { missing } of vanished.values()) {
    for (const item of missing) delete owned[item];
  }
  // Prefer a family member that already carries a real key, so a key the user
  // pasted into any one group becomes the key of the whole family.
  const anchor = family.find(provider => {
    const apiKey = ((provider.config ?? {}).access ?? {}).apiKey;
    return apiKey && apiKey !== DISCOVERY_API_KEY_PLACEHOLDER;
  }) ?? family[0] ?? null;
  const access = structuredClone(((anchor ?? {}).config ?? {}).access ?? { type: 'api-key', apiKey: DISCOVERY_API_KEY_PLACEHOLDER });

  const rejected = [];
  const planned = [];
  for (const [groupKey, entries] of discoveryGroups(models, minimum)) {
    const kept = [];
    for (const entry of entries) {
      const config = discoveryModelConfig(entry, catalog);
      if (config === null) rejected.push(entry.id);
      else kept.push([entry.id, config]);
    }
    if (kept.length) planned.push([groupKey, kept]);
  }

  for (const [groupKey, entries] of planned) {
    const [providerId, providerName] = discoveryProvider(groupKey);
    let provider = providers.find(item => item?.providerId === providerId);
    if (provider === undefined) {
      if (!allowNew) continue; // automatic runs never create groups
      provider = {
        providerId, providerName, enabled: true,
        config: { group: 'standard-personal', access: structuredClone(access), api: { type: 'openai-chat-completions', baseUrl }, personalModelIds: [], modelOrder: [] },
      };
      providers.push(provider);
      changes.push(`provider:${providerId}`);
    }
    const pc = (provider.config ??= {});
    if (pc.group === undefined) pc.group = 'standard-personal';
    if (pc.api === undefined) pc.api = { type: 'openai-chat-completions', baseUrl };
    const currentAccess = pc.access ?? {};
    // One key for the whole family: adopt the anchor's key when this provider
    // still carries the placeholder, so the user pastes a real key only once.
    if (!currentAccess.apiKey || currentAccess.apiKey === DISCOVERY_API_KEY_PLACEHOLDER) pc.access = structuredClone(access);
    const enabled = (pc.personalModelIds ??= []);
    const order = (pc.modelOrder ??= []);
    const known = new Set([...order, ...enabled, ...rules.filter(rule => rule?.providerId === providerId).map(rule => rule?.modelId)]);
    for (const [modelId, config] of entries) {
      if (removed.has(modelId)) {
        // The user re-added a model they had deleted: hand it back to discovery.
        if (enabled.includes(modelId)) removed.delete(modelId);
        continue;
      }
      const key = `${providerId}/${modelId}`;
      const newModel = !known.has(modelId);
      if (newModel) {
        const newConfig = structuredClone(config);
        rules.push({ providerId, modelId, config: newConfig });
        if (!order.includes(modelId)) order.push(modelId);
        if (!enabled.includes(modelId)) enabled.push(modelId);
        owned[key] = structuredClone(newConfig);
        changes.push(modelId);
        continue;
      }
      // A model the host still knows (rule present) but which is missing from the
      // provider's lists is re-listed: its rule keeps the on/off switch, so a
      // model the user switched off comes back off, and a list rewritten elsewhere
      // is repaired instead of leaving models unusable.
      if (!order.includes(modelId)) { order.push(modelId); changes.push(`order:${modelId}`); }
      if (!enabled.includes(modelId)) { enabled.push(modelId); changes.push(`listed:${modelId}`); }
      const rule = rules.find(item => item?.providerId === providerId && item?.modelId === modelId) ?? null;
      if (isSmart(providerId, modelId)) {
        // The catalog already describes this model: keep it selectable but
        // never write a second (manual) rule for it. A manual rule we wrote
        // earlier is removed so the host schema stops rejecting the file.
        if (!order.includes(modelId)) order.push(modelId);
        if (rule !== null) {
          rules.splice(rules.indexOf(rule), 1);
          delete owned[key];
          changes.push(`smart:${modelId}`);
        }
        continue;
      }
      const stale = smartRules.find(item => item?.providerId === providerId && item?.modelId === modelId) ?? null;
      if (stale !== null) {
        // The catalog no longer defines this model: drop the inert smart rule
        // so the manual rule below can describe it (both at once is invalid).
        smartRules.splice(smartRules.indexOf(stale), 1);
        changes.push(`stale-smart:${modelId}`);
      }
      if (newModel) {
        const newConfig = structuredClone(config);
        rules.push({ providerId, modelId, config: newConfig });
        if (!order.includes(modelId)) order.push(modelId);
        owned[key] = structuredClone(newConfig);
        changes.push(modelId);
        continue;
      }
      if (rule === null) {
        // known only because a rule exists for it elsewhere: recreate the rule
        rules.push({ providerId, modelId, config: structuredClone(config) });
        owned[key] = structuredClone(config);
        changes.push(modelId);
        continue;
      }
      // The host stores the per-model on/off switch as config.enabled on the
      // rule, so metadata refreshes must carry that user choice over instead
      // of overwriting or dropping it.
      const currentConfig = rule.config ?? {};
      const userFlags = {};
      const metaOnly = {};
      for (const [name, value] of Object.entries(currentConfig)) {
        if (name === 'enabled') userFlags[name] = value;
        else metaOnly[name] = value;
      }
      const previous = owned[key];
      if (previous === undefined || previous === null) {
        owned[key] = structuredClone(metaOnly); // hand-written rule, adopted as ours-once
      } else if (isDeepStrictEqual(metaOnly, previous)) {
        const refreshed = { ...structuredClone(config), ...userFlags };
        if (!isDeepStrictEqual(refreshed, currentConfig)) {
          rule.config = refreshed;
          owned[key] = structuredClone(config);
          changes.push(modelId);
        }
      }
    }
  }
  discovery.removed = [...removed].sort();
  discovery.skipped = [...new Set(rejected)].sort();
  discovery.groups = {};
  for (const [groupKey, entries] of planned) discovery.groups[discoveryProvider(groupKey)[0]] = entries.length;
  const providerOrder = (cfg.providerOrder ??= []);
  for (const [groupKey] of planned) {
    const providerId = discoveryProvider(groupKey)[0];
    if (!providerOrder.includes(providerId)) providerOrder.push(providerId);
  }
  return [out, newstate, changes, planned.length ? 'ok' : 'empty'];
}

function modelInventory(data) {
  const providers = data?.config?.providerConfigRules?.providerRules ?? [];
  const inventory = new Set();
  for (const provider of providers) {
    for (const modelId of provider?.config?.personalModelIds ?? []) {
      inventory.add(`${provider?.providerId}\u0000${modelId}`);
    }
  }
  return inventory;
}

function timestamp(date = new Date()) {
  const pad = value => String(value).padStart(2, '0');
  const micros = String(date.getMilliseconds()).padStart(3, '0') + '000';
  return `${date.getFullYear()}${pad(date.getMonth() + 1)}${pad(date.getDate())}-${pad(date.getHours())}${pad(date.getMinutes())}${pad(date.getSeconds())}-${micros}`;
}

function commit(config, raw, out, stateRoot, namespace, changes) {
  if (!changes.length) return false;
  const current = () => fs.readFileSync(config);
  if (!current().equals(raw)) {
    console.log('Config changed concurrently; retrying from a fresh read');
    return 'concurrent';
  }
  // Safety net for any writer bug (ours or the app's): this sync only ever adds
  // models, so a result that drops part of the inventory is refused and the file
  // is left untouched.
  const before = modelInventory(JSON.parse(raw.toString('utf8')));
  const after = modelInventory(out);
  if (before.size >= 5 && after.size < before.size) {
    console.log(`Refusing to drop ${before.size - after.size} of ${before.size} enabled models; config left untouched`);
    return 'refused';
  }
  const backups = path.join(stateRoot, 'backups');
  fs.mkdirSync(backups, { recursive: true, mode: 0o700 });
  if (namespace) privateDir(backups);
  fs.writeFileSync(path.join(backups, `provider_config-${timestamp()}.json`), raw, { mode: 0o600 });
  // Recheck after backup so an in-flight UI save does not get overwritten.
  if (!current().equals(raw)) {
    console.log('Config changed concurrently; retrying from a fresh read');
    return 'concurrent';
  }
  atomic(config, out);
  const existing = fs.readdirSync(backups).filter(name => /^provider_config-.*\.json$/.test(name)).sort();
  for (const old of existing.slice(0, Math.max(0, existing.length - 10))) {
    try { fs.unlinkSync(path.join(backups, old)); } catch { /* keep the others */ }
  }
  return true;
}

function processAlive(pid) {
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return error?.code === 'EPERM';
  }
}

function lockIsStale(lockPath) {
  let stat = null;
  try { stat = fs.statSync(lockPath); } catch { return true; }
  let pid = null;
  try { pid = Number.parseInt(fs.readFileSync(lockPath, 'utf8').trim(), 10); } catch { pid = null; }
  if (Number.isInteger(pid) && pid > 0) return !processAlive(pid);
  return Date.now() - stat.mtimeMs > LOCK_STALE_MS;
}

function acquireLock(lockPath) {
  for (let attempt = 0; attempt < 2; attempt += 1) {
    try {
      const fd = fs.openSync(lockPath, 'wx', 0o600);
      try { fs.writeSync(fd, `${process.pid}\n`); } finally { fs.closeSync(fd); }
      return () => { try { fs.unlinkSync(lockPath); } catch { /* already gone */ } };
    } catch (error) {
      if (error?.code !== 'EEXIST') throw error;
      if (!lockIsStale(lockPath)) return null;
      try { fs.unlinkSync(lockPath); } catch { /* raced another reclaimer */ }
    }
  }
  return null;
}

function sortedEntries(value) {
  return Object.entries(value).sort(([left], [right]) => (left < right ? -1 : left > right ? 1 : 0));
}

async function runOnce(args, config, stateRoot, namespace) {
  if (!fs.existsSync(config)) return 'missing';
  const raw = fs.readFileSync(config);
  const data = JSON.parse(raw.toString('utf8'));
  const state = load(path.join(stateRoot, 'state.json'), { managed: {} });
  const pristine = structuredClone(state);
  const discovery = (state.discovery ??= {});
  const baseUrl = gatewayBaseUrl();
  let changes = [];
  let models = null;
  const providers = data?.config?.providerConfigRules?.providerRules ?? [];
  const family = providers.filter(provider => String(provider?.providerId ?? '').startsWith(DISCOVERY_FAMILY_PREFIX)
    || ((provider?.config ?? {}).api ?? {}).baseUrl === baseUrl);
  let due = Date.now() / 1000 - (Number(discovery.fetchedAt) || 0) >= DISCOVERY_TTL_SECONDS;
  const cooling = Date.now() / 1000 - (Number(discovery.failedAt) || 0) < DISCOVERY_FAILURE_BACKOFF;
  // A provider just added from the UI has nothing to select yet, and a
  // provider we have never grouped is new as well: fill both right away
  // instead of waiting for the TTL.
  const grouped = discovery.groups ?? {};
  const needsFill = family.some(provider => !((provider?.config ?? {}).personalModelIds ?? []).length
    || !Object.prototype.hasOwnProperty.call(grouped, String(provider?.providerId)));
  if (args.bootstrap && !family.length) due = true;
  if (args.discover || ((due || needsFill) && family.length && !cooling)) {
    try {
      models = await gatewayModels(baseUrl);
      discovery.fetchedAt = Date.now() / 1000;
      delete discovery.failedAt;
      console.log('Gateway models:', models.length);
    } catch (error) {
      models = null;
      discovery.failedAt = Date.now() / 1000;
      console.log('Model discovery unavailable; keeping current config:', error?.name ?? 'Error');
    }
  } else if (!family.length && !args.bootstrap && !discovery.hintShown) {
    discovery.hintShown = true;
    console.log('No 9Router provider yet; add one in Model settings or run with --bootstrap');
  }
  const catalog = await refreshCatalog(stateRoot);
  let out;
  let newstate;
  [out, newstate, changes] = enrich(data, catalog, state);
  if (models?.length) {
    let found;
    let status;
    [out, newstate, found, status] = discoveryMerge(out, models, newstate, catalog, baseUrl, Boolean(args.bootstrap), DISCOVERY_GROUP_MIN, catalogModelMatches());
    if (status === 'ok') {
      console.log('Discovered groups:', sortedEntries(newstate.discovery?.groups ?? {}).map(([key, value]) => `${key}=${value}`).join(', '));
      const skipped = newstate.discovery?.skipped ?? [];
      if (skipped.length) console.log('Skipped models without limits:', skipped.length);
    }
    changes = changes.concat(found);
  }
  const status = commit(config, raw, out, stateRoot, namespace, changes);
  if (status === true) console.log('Updated provider config:', changes.length, 'entry(ies)');
  else if (status === 'concurrent') console.log('Config changed concurrently; retry on next pass');
  if (!isDeepStrictEqual(newstate, pristine)) atomic(path.join(stateRoot, 'state.json'), newstate);
  return changes.length ? status : 'no-change';
}

async function main(argv = process.argv.slice(2)) {
  const args = parseArgs(argv);
  if (args.help) {
    console.log('usage: model-sync [-h] [--discover] [--bootstrap]');
    return;
  }
  process.umask(0o077);
  const [config, stateRoot, namespace] = storagePaths();
  if (namespace) {
    privateDir(stateRoot);
    for (const name of ['catalog.json', 'state.json', 'backups']) safePath(path.join(stateRoot, name));
  } else {
    fs.mkdirSync(stateRoot, { recursive: true });
  }
  const lockPath = path.join(stateRoot, 'sync.lock');
  if (namespace) safePath(lockPath);
  const release = acquireLock(lockPath);
  if (release === null) return; // another run holds the guard: exit quietly
  try {
    for (let attempt = 0; attempt < 3; attempt += 1) {
      const status = await runOnce(args, config, stateRoot, namespace);
      if (status !== 'concurrent') break;
      await sleep(400);
    }
  } finally {
    release();
  }
}

if (require.main === module) {
  main().catch(error => {
    console.error(`${error?.name ?? 'Error'}: ${error?.message ?? error}`);
    process.exitCode = error?.exitCode ?? 1;
  });
}

exports.ROOT = ROOT;
exports.CATALOG_URL = CATALOG_URL;
exports.ALIASES = ALIASES;
exports.GATEWAY_BASE_URL = GATEWAY_BASE_URL;
exports.DISCOVERY_FAMILY_PREFIX = DISCOVERY_FAMILY_PREFIX;
exports.DISCOVERY_COMBO_GROUP = DISCOVERY_COMBO_GROUP;
exports.DISCOVERY_OVERFLOW_GROUP = DISCOVERY_OVERFLOW_GROUP;
exports.DISCOVERY_GROUP_MIN = DISCOVERY_GROUP_MIN;
exports.DISCOVERY_TTL_SECONDS = DISCOVERY_TTL_SECONDS;
exports.DISCOVERY_FAILURE_BACKOFF = DISCOVERY_FAILURE_BACKOFF;
exports.DISCOVERY_API_KEY_PLACEHOLDER = DISCOVERY_API_KEY_PLACEHOLDER;
exports.DISCOVERY_EFFORT_LEVELS = DISCOVERY_EFFORT_LEVELS;
exports.DISCOVERY_INERT_REASONING = DISCOVERY_INERT_REASONING;
exports.DISCOVERY_DELETE_LIMIT = DISCOVERY_DELETE_LIMIT;
exports.load = load;
exports.atomic = atomic;
exports.safePath = safePath;
exports.namespaceRoot = namespaceRoot;
exports.privateDir = privateDir;
exports.storagePaths = storagePaths;
exports.parseArgs = parseArgs;
exports.gatewayBaseUrl = gatewayBaseUrl;
exports.metadata = metadata;
exports.reasoningSpec = reasoningSpec;
exports.placeholder = placeholder;
exports.enrich = enrich;
exports.refreshCatalog = refreshCatalog;
exports.gatewayModels = gatewayModels;
exports.namespaceOf = namespaceOf;
exports.discoveryGroups = discoveryGroups;
exports.discoveryProvider = discoveryProvider;
exports.firstLimit = firstLimit;
exports.discoveryModelConfig = discoveryModelConfig;
exports.catalogModelMatches = catalogModelMatches;
exports.discoveryMerge = discoveryMerge;
exports.modelInventory = modelInventory;
exports.commit = commit;
exports.lockIsStale = lockIsStale;
exports.acquireLock = acquireLock;
exports.runOnce = runOnce;
exports.main = main;
