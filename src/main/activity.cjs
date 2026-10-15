// Local-only activity summary: user prompts per day and streak, read straight
// from the agent session database. No network, no cloud service, no agent RPC.
const fs = require('node:fs'), path = require('node:path'), os = require('node:os');
const CACHE_MS = 20000, WINDOW_DAYS = 30;
const MACHINE_SESSION_TYPES = "('subagent_child','workflow_child','nested_workflow_child','workflow_parent')";
let cache = { at: 0, value: null };

const PROMPT_QUERY = `SELECT m.time_created AS created FROM message m JOIN session s ON s.id = m.session_id
WHERE json_valid(m.data) AND json_extract(m.data,'$.role') = 'user'
AND json_extract(m.data,'$.automationId') IS NULL
AND json_extract(m.data,'$.offPeakTaskId') IS NULL
AND json_extract(m.data,'$.botDeliveryTarget') IS NULL
AND s.task_type NOT IN ${MACHINE_SESSION_TYPES}`;

function pad(n) { return String(n).padStart(2, '0'); }
function dayKey(date) { return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`; }
function shiftDay(key, delta) {
  const [y, m, d] = key.split('-').map(Number);
  const date = new Date(y, m - 1, d);
  date.setDate(date.getDate() + delta);
  return dayKey(date);
}
function countDays(timestamps) {
  const counts = {};
  for (const value of timestamps) {
    const ms = Number(value);
    if (!Number.isFinite(ms) || ms <= 0) continue;
    const key = dayKey(new Date(ms));
    counts[key] = (counts[key] || 0) + 1;
  }
  return counts;
}
function summarize(counts, today = dayKey(new Date())) {
  const days = Object.keys(counts).sort();
  const active = days.filter(day => (counts[day] || 0) > 0);
  let longest = 0, run = 0, previous = null;
  for (const day of active) {
    run = previous && shiftDay(previous, 1) === day ? run + 1 : 1;
    if (run > longest) longest = run;
    previous = day;
  }
  // A streak stays "current" when today is still empty but yesterday was active.
  let cursor = counts[today] ? today : shiftDay(today, -1);
  let current = 0;
  while (counts[cursor]) { current += 1; cursor = shiftDay(cursor, -1); }
  const history = active.map(day => ({ day, prompts: counts[day] }));
  const perYear = {};
  for (const day of active) {
    const year = day.slice(0, 4);
    perYear[year] = (perYear[year] || 0) + counts[day];
  }
  return {
    today: counts[today] || 0,
    total: active.reduce((sum, day) => sum + counts[day], 0),
    activeDays: active.length,
    currentStreak: current,
    longestStreak: longest,
    firstDay: active[0] || null,
    lastDay: active[active.length - 1] || null,
    byDay: history.slice(-WINDOW_DAYS),
    days: history,
    years: Object.keys(perYear).sort().map(year => ({ year, prompts: perYear[year] })),
  };
}

function sessionDbPath() {
  const fromEnv = process.env.CCODE_SESSION_DB_PATH?.trim();
  if (fromEnv) return fromEnv;
  const storage = process.env.CCODE_STORAGE_DIR?.trim();
  if (storage) return path.join(storage, 'cli', 'db', 'db.sqlite');
  return null;
}

// ---------------------------------------------------------------------------
// Auto Detect: run the standalone model discovery for the local 9Router gateway
// on demand (the button beside "+ Add model" in Model settings). The sync script
// talks to the user's own gateway; nothing leaves the machine.
const { spawn } = require('node:child_process');
const DETECT_TIMEOUT_MS = 120000;
const GATEWAY_BASE_URL = 'http://127.0.0.1:20128/v1';
let detection = null;

function projectRoot() { return path.resolve(__dirname, '..', '..', '..'); }

// Auto Detect runs the standalone Python script on Linux. Windows targets have no
// Python runtime, so they run the Node port through the Electron binary acting as
// Node; both write the same artifacts into the same namespace.
function detectionCommand() {
  if (process.platform === 'win32') {
    // process.resourcesPath is the deployed <install>/resources; the fallback only
    // covers running this file outside Electron.
    const resources = process.resourcesPath ?? path.resolve(__dirname, '..', '..', 'app', 'resources');
    const script = path.join(resources, 'model-sync', 'main.cjs');
    if (!fs.existsSync(script)) return { error: `Model sync script is missing: ${script}` };
    return { command: process.execPath, script, env: { ELECTRON_RUN_AS_NODE: '1' } };
  }
  const script = path.join(projectRoot(), 'services', 'model-sync', 'sync.py');
  if (!fs.existsSync(script)) return { error: `Model sync script is missing: ${script}` };
  return { command: '/usr/bin/python3', script, env: {} };
}

function namespacePaths() {
  const root = process.env.CCODE_STANDALONE_ROOT?.trim();
  if (!root) return null;
  return {
    root,
    config: path.join(root, 'data', '.ccode', 'v2', 'provider_config.json'),
    state: path.join(root, 'model-sync'),
  };
}

function detectionSummary(configPath) {
  const data = JSON.parse(fs.readFileSync(configPath, 'utf8'));
  const providers = data?.config?.providerConfigRules?.providerRules ?? [];
  const rules = data?.config?.modelConfigRules?.manualProviderModelRules ?? [];
  const family = providers.filter(provider =>
    String(provider?.providerId ?? '').startsWith('9router') || provider?.config?.api?.baseUrl === GATEWAY_BASE_URL);
  return {
    providers: family.length,
    models: family.reduce((sum, provider) => sum + (provider?.config?.personalModelIds?.length ?? 0), 0),
    rules: rules.length,
    names: family.map(provider => provider?.providerName ?? provider?.providerId ?? ''),
  };
}

function detectionOutcome(log, code) {
  if (!/Gateway models: \d+/.test(log)) return { ok: false, error: 'The 9Router gateway did not answer. Is it running?' };
  if (/Refusing to drop/.test(log)) return { ok: false, error: 'Refused to write a configuration that would remove existing models.' };
  if (/Config changed concurrently/.test(log)) return { ok: false, error: 'CCode was saving settings at the same time. Try Auto Detect again.' };
  if (code !== 0) return { ok: false, error: `Model discovery failed (exit ${code}).` };
  return { ok: true };
}

function runDetection() {
  if (detection) return detection;
  detection = (async () => {
    const paths = namespacePaths();
    if (!paths) return { ok: false, error: 'The standalone namespace is not available in this window.' };
    const target = detectionCommand();
    if (target.error) return { ok: false, error: target.error };
    const started = Date.now();
    const result = await new Promise(resolve => {
      const child = spawn(target.command, [target.script, '--discover', '--bootstrap'], {
        env: { ...process.env, ...target.env, CCODE_STANDALONE_ROOT: paths.root, CCODE_MODEL_SYNC_CONFIG: paths.config, CCODE_MODEL_SYNC_STATE: paths.state },
        stdio: ['ignore', 'pipe', 'pipe'],
      });
      let text = '';
      const timer = setTimeout(() => child.kill('SIGTERM'), DETECT_TIMEOUT_MS);
      child.stdout.on('data', chunk => { text += chunk; });
      child.stderr.on('data', chunk => { text += chunk; });
      child.on('error', error => { clearTimeout(timer); resolve({ code: null, text: `${text}${error?.message ?? error}` }); });
      child.on('close', code => { clearTimeout(timer); resolve({ code, text }); });
    });
    const seconds = Math.round((Date.now() - started) / 1000);
    const log = result.text.trim();
    const outcome = detectionOutcome(log, result.code);
    if (!outcome.ok) return { ok: false, seconds, error: outcome.error, log: log.slice(-300) };
    let summary = null;
    try { summary = detectionSummary(paths.config); } catch { /* the summary is optional */ }
    const skipped = /Skipped models without limits: (\d+)/.exec(log);
    return { ok: true, seconds, skipped: skipped ? Number(skipped[1]) : null, ...(summary ?? {}), log: log.slice(-400) };
  })().finally(() => { detection = null; });
  return detection;
}

function readTimestamps(dbPath) {
  const { DatabaseSync, backup } = require('node:sqlite');
  const query = db => db.prepare(PROMPT_QUERY).all().map(row => row.created);
  try {
    const db = new DatabaseSync(dbPath, { readOnly: true });
    try {
      db.exec('PRAGMA busy_timeout=1500');
      return query(db);
    } finally { try { db.close(); } catch {} }
  } catch (error) {
    // A WAL database can refuse a read-only handle while the agent writes: take a
    // snapshot copy instead of ever touching the live file.
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ccode-activity-'));
    const copy = path.join(dir, 'snapshot.sqlite');
    const source = new DatabaseSync(dbPath);
    try {
      source.exec('PRAGMA busy_timeout=2500');
      return backup(source, copy).then(() => {
        const snapshot = new DatabaseSync(copy, { readOnly: true });
        try { return query(snapshot); } finally { try { snapshot.close(); } catch {} }
      }).finally(() => {
        try { source.close(); } catch {}
        try { fs.rmSync(dir, { recursive: true, force: true }); } catch {}
      });
    } catch (failure) {
      try { source.close(); } catch {}
      try { fs.rmSync(dir, { recursive: true, force: true }); } catch {}
      throw failure;
    }
  }
}

async function collect(dbPath, today) {
  const counts = countDays(await readTimestamps(dbPath));
  return summarize(counts, today);
}

exports.register = ({ app, ipcMain }) => {
  function trusted(event) {
    const frame = event.senderFrame;
    return frame === event.sender.mainFrame && frame.url.startsWith('file://') && frame.url.includes('/out/renderer/index.html');
  }
  ipcMain.handle('ccode-activity:summary', async event => {
    if (!trusted(event)) throw Error('Activity is only available in the local CCode window.');
    if (cache.value && Date.now() - cache.at < CACHE_MS) return cache.value;
    const dbPath = sessionDbPath();
    if (!dbPath || !fs.existsSync(dbPath)) return { available: false, error: 'The local session database is not available yet.' };
    try {
      const value = { available: true, generatedAt: Date.now(), ...(await collect(dbPath)) };
      cache = { at: Date.now(), value };
      return value;
    } catch (error) {
      return { available: false, error: `Activity could not read local history: ${error?.message ?? error}` };
    }
  });
  ipcMain.handle('ccode-detect:run', async event => {
    if (!trusted(event)) throw Error('Auto Detect is only available in the local CCode window.');
    try {
      return await runDetection();
    } catch (error) {
      return { ok: false, error: `Auto Detect failed: ${error?.message ?? error}` };
    }
  });
  app.on('before-quit', () => { cache = { at: 0, value: null }; });
};

exports.summarize = summarize;
exports.countDays = countDays;
exports.dayKey = dayKey;
exports.shiftDay = shiftDay;
exports.sessionDbPath = sessionDbPath;
exports.collect = collect;
exports.promptQuery = PROMPT_QUERY;
exports.runDetection = runDetection;
exports.detectionCommand = detectionCommand;
exports.detectionOutcome = detectionOutcome;
exports.detectionSummary = detectionSummary;
exports.namespacePaths = namespacePaths;
