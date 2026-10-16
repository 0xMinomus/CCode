'use strict';

const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const { spawn } = require('node:child_process');
const { randomUUID } = require('node:crypto');

const LEVELS = new Set(['lite', 'full', 'ultra']);

function defaultSettings() {
  return {
    version: 1,
    rtk: { enabled: false },
    caveman: { enabled: false, level: 'full' },
    ponytail: { enabled: false, level: 'full' },
  };
}

function normalizeSettings(value) {
  const source = value && typeof value === 'object' ? value : {};
  const rtk = source.rtk && typeof source.rtk === 'object' ? source.rtk : {};
  const caveman = source.caveman && typeof source.caveman === 'object' ? source.caveman : {};
  const ponytail = source.ponytail && typeof source.ponytail === 'object' ? source.ponytail : {};
  return {
    version: 1,
    rtk: { enabled: rtk.enabled === true },
    caveman: { enabled: caveman.enabled === true, level: LEVELS.has(caveman.level) ? caveman.level : 'full' },
    ponytail: { enabled: ponytail.enabled === true, level: LEVELS.has(ponytail.level) ? ponytail.level : 'full' },
  };
}

function validateSettings(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('Token savers settings must be an object.');
  for (const key of ['rtk', 'caveman', 'ponytail']) {
    if (!value[key] || typeof value[key] !== 'object' || typeof value[key].enabled !== 'boolean') {
      throw new Error(`Token savers ${key} setting is invalid.`);
    }
  }
  for (const key of ['caveman', 'ponytail']) {
    if (!LEVELS.has(value[key].level)) throw new Error(`Token savers ${key} level is invalid.`);
  }
  return normalizeSettings(value);
}

function settingsPath(env = process.env) {
  const dataRoot = typeof env.CCODE_DATA_BASE_DIR === 'string' ? env.CCODE_DATA_BASE_DIR.trim() : '';
  return dataRoot ? path.join(dataRoot, '.ccode', 'v2', 'token-savers.json') : null;
}

function readSettings(env = process.env) {
  const file = settingsPath(env);
  if (!file) return defaultSettings();
  try {
    return normalizeSettings(JSON.parse(fs.readFileSync(file, 'utf8')));
  } catch (error) {
    if (error?.code === 'ENOENT') return defaultSettings();
    throw error;
  }
}

function writeSettings(value, env = process.env) {
  const file = settingsPath(env);
  if (!file) throw new Error('Standalone settings directory is unavailable.');
  const settings = validateSettings(value);
  const directory = path.dirname(file);
  fs.mkdirSync(directory, { recursive: true, mode: 0o700 });
  const temporary = `${file}.${process.pid}.${randomUUID()}.tmp`;
  try {
    fs.writeFileSync(temporary, `${JSON.stringify(settings, null, 2)}\n`, { encoding: 'utf8', flag: 'wx', mode: 0o600 });
    fs.chmodSync(temporary, 0o600);
    fs.renameSync(temporary, file);
  } finally {
    try { fs.unlinkSync(temporary); } catch (error) { if (error?.code !== 'ENOENT') throw error; }
  }
  return settings;
}

function managedRtkRoot(env = process.env) {
  const settings = settingsPath(env);
  return settings ? path.join(path.dirname(settings), 'tools', 'rtk') : null;
}

function isManagedRtkPath(file, env = process.env) {
  const root = managedRtkRoot(env);
  if (!root) return false;
  const relative = path.relative(root, file);
  return relative === '' || (!relative.startsWith(`..${path.sep}`) && relative !== '..' && !path.isAbsolute(relative));
}

function managedRtkPath(env = process.env) {
  const root = managedRtkRoot(env);
  if (!root) return null;
  try {
    const current = JSON.parse(fs.readFileSync(path.join(root, 'current.json'), 'utf8'));
    // The recorded version, not a literal, defines a managed install: a released bump must not
    // silently orphan a binary that is already installed.
    if (!current || current.edition !== 'oss' || typeof current.version !== 'string' || typeof current.directory !== 'string') return null;
    if (!/^v\d+(?:\.\d+)+-oss-(?:win32|linux)-x64-[a-f0-9-]+$/.test(current.directory) || !current.directory.startsWith('v' + current.version + '-oss-')) return null;
    const binary = path.join(root, current.directory, process.platform === 'win32' ? 'rtk.exe' : 'rtk');
    if (!fs.statSync(binary).isFile()) return null;
    fs.accessSync(binary, process.platform === 'win32' ? fs.constants.F_OK : fs.constants.X_OK);
    return binary;
  } catch { return null; }
}


function resolveRtkPath(env = process.env) {
  const candidates = [];
  const directories = String(env.PATH ?? '').split(path.delimiter).filter(directory => directory && !isManagedRtkPath(directory, env));
  const home = env.HOME?.trim() || env.USERPROFILE?.trim() || os.homedir();
  if (process.platform === 'win32') {
    const names = ['rtk.exe', 'rtk.cmd'];
    for (const directory of directories) for (const name of names) candidates.push(path.join(directory, name));
    for (const directory of [path.join(home, '.local', 'bin'), path.join(home, '.cargo', 'bin')]) for (const name of names) candidates.push(path.join(directory, name));
  } else {
    for (const directory of directories) candidates.push(path.join(directory, 'rtk'));
    candidates.push(path.join(home, '.local', 'bin', 'rtk'), path.join(home, '.cargo', 'bin', 'rtk'), '/usr/local/bin/rtk', '/usr/bin/rtk');
  }
  for (const candidate of new Set(candidates)) {
    try {
      if (!fs.statSync(candidate).isFile()) continue;
      fs.accessSync(candidate, process.platform === 'win32' ? fs.constants.F_OK : fs.constants.X_OK);
      return candidate;
    } catch {}
  }
  return managedRtkPath(env);
}

function quoteCmdArgument(value) {
  return `"${String(value).replace(/"/g, '""')}"`;
}

function spawnRtk(executable, args, options) {
  if (process.platform === 'win32' && /\.(?:cmd|bat)$/i.test(executable)) {
    const line = [executable, ...args].map(quoteCmdArgument).join(' ');
    return spawn(process.env.ComSpec || 'cmd.exe', ['/d', '/s', '/c', `"${line}"`], { ...options, windowsVerbatimArguments: true });
  }
  return spawn(executable, args, options);
}

function runRtk(args, options = {}) {
  const env = options.env ?? process.env;
  const executable = options.executable ?? resolveRtkPath(env);
  if (!executable) return Promise.resolve({ available: false, code: null, stdout: '', stderr: '', error: 'RTK was not found.' });
  return new Promise(resolve => {
    let child;
    try {
      child = spawnRtk(executable, args, { cwd: options.cwd, env, stdio: ['ignore', 'pipe', 'pipe'], windowsHide: true });
    } catch (error) {
      resolve({ available: false, code: null, stdout: '', stderr: '', error: error?.message ?? String(error) });
      return;
    }
    let stdout = '', stderr = '', bytes = 0, settled = false;
    const maxBytes = options.maxBytes ?? 1_048_576;
    const finish = value => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve(value);
    };
    const timer = setTimeout(() => {
      child.kill('SIGTERM');
      finish({ available: true, code: null, stdout, stderr, error: 'RTK timed out.' });
    }, options.timeoutMs ?? 3000);
    timer.unref?.();
    const collect = (target, chunk) => {
      bytes += chunk.length;
      if (bytes > maxBytes) {
        child.kill('SIGTERM');
        finish({ available: true, code: null, stdout, stderr, error: 'RTK output exceeded the limit.' });
        return;
      }
      if (target === 'stdout') stdout += chunk.toString('utf8');
      else stderr += chunk.toString('utf8');
    };
    child.stdout.on('data', chunk => collect('stdout', chunk));
    child.stderr.on('data', chunk => collect('stderr', chunk));
    child.once('error', error => finish({ available: false, code: null, stdout, stderr, error: error?.message ?? String(error) }));
    child.once('close', (code, signal) => finish({ available: true, code, signal, stdout, stderr, error: null }));
  });
}

async function rewriteShellCommand(command, options = {}) {
  const env = options.env ?? process.env;
  let settings;
  try { settings = readSettings(env); } catch { return { kind: 'error', error: 'Token saver settings are unavailable.' }; }
  if (!settings.rtk.enabled || typeof command !== 'string' || !command.trim() || command.includes('\n') || /^\s*(?:command\s+)?rtk(?:\s|$)/.test(command)) {
    return { kind: 'unchanged' };
  }
  const executable = resolveRtkPath(env);
  if (!executable) return { kind: 'error', error: 'RTK is enabled, but its executable was not found.' };
  const result = await runRtk(['rewrite', command], { executable, cwd: options.cwd, env, timeoutMs: options.timeoutMs ?? 1000, maxBytes: 65_536 });
  if (!result.available || result.error) return { kind: 'error', error: 'RTK could not inspect this shell command.' };
  if (result.code === 1 && !result.stdout.trim()) return { kind: 'unchanged' };
  // Status 3 rewrites while leaving approval to the host, just like status 0 here.
  if (result.code !== 0 && result.code !== 3) return { kind: 'error', error: 'RTK returned an unexpected shell-command status.' };
  const rewritten = String(result.stdout ?? '').trim();
  if (!rewritten || rewritten.includes('\n') || !/^rtk(?:\s|$)/.test(rewritten)) {
    return { kind: 'error', error: 'RTK returned an invalid shell-command rewrite.' };
  }
  const directory = path.dirname(executable);
  const target = path.resolve(directory);
  const onPath = !isManagedRtkPath(executable, env) && String(env.PATH ?? '').split(path.delimiter)
    .some(entry => entry && (process.platform === 'win32' ? path.resolve(entry).toLowerCase() === target.toLowerCase() : path.resolve(entry) === target));
  if (onPath) return { kind: 'rewrite', command: rewritten };
  // Bash snapshots may freeze PATH before installation. Bind the selected RTK in the approved command itself.
  const shellDirectory = process.platform === 'win32' ? directory.replace(/\\/g, '/').replace(/^([A-Za-z]):\//, (_, drive) => `/${drive.toLowerCase()}/`) : directory;
  const quoted = `'${shellDirectory.replace(/'/g, `'\\''`)}'`;
  return { kind: 'rewrite', command: `export PATH=${quoted}:"$PATH"; ${rewritten}` };
}

async function needsShellApproval(input, context, original, options = {}) {
  const experimental = context?.experimental_context;
  const cwd = options.cwd ?? experimental?.workingDirectory ?? experimental?.cwd ?? experimental?.workspaceRoot;
  const decision = await rewriteShellCommand(input?.command, { ...options, cwd });
  if (decision.kind === 'error') throw new Error(decision.error);
  if (decision.kind === 'rewrite' && (!input || typeof input !== 'object' || !Reflect.set(input, 'command', decision.command))) {
    throw new Error('RTK could not safely apply its shell-command rewrite.');
  }
  if (typeof original === 'function') return !!(await original(input, context));
  return original === true;
}

function applyPromptModes(userInstructions, env = process.env) {
  let settings;
  try { settings = readSettings(env); } catch { return userInstructions; }
  const directives = [];
  if (settings.caveman.enabled) {
    const copy = {
      lite: 'Use concise, direct prose. Keep every technical fact and caveat.',
      full: 'Use caveman voice: answer first, remove ceremony, and preserve all technical substance.',
      ultra: 'Use maximum compression and fragments when clear. Preserve negations, code, paths, numbers, and safety details.',
    }[settings.caveman.level];
    directives.push(`Caveman (${settings.caveman.level}): ${copy}`);
  }
  if (settings.ponytail.enabled) {
    const copy = {
      lite: 'Prefer existing code and the smallest safe change. Skip speculative additions.',
      full: 'Follow the efficiency ladder: reuse existing code, then stdlib, platform features, installed dependencies, and only then minimal new code.',
      ultra: 'Reject unnecessary work and abstractions aggressively. Never simplify away correctness, security, validation, or requested scope.',
    }[settings.ponytail.level];
    directives.push(`Ponytail (${settings.ponytail.level}): ${copy}`);
  }
  if (directives.length === 0) return userInstructions;
  const addition = `## Token savers\n${directives.join('\n')}`;
  if (typeof userInstructions === 'string') return [userInstructions, addition].filter(Boolean).join('\n\n');
  const content = typeof userInstructions?.content === 'string' ? userInstructions.content : '';
  return { ...(userInstructions && typeof userInstructions === 'object' ? userInstructions : {}), content: [content, addition].filter(Boolean).join('\n\n') };
}

function validDay(value) {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const [year, month, day] = value.split('-').map(Number);
  return new Date(Date.UTC(year, month - 1, day)).toISOString().slice(0, 10) === value;
}

function tokenCount(value) {
  const number = Number(value);
  return Number.isFinite(number) && number > 0 ? Math.floor(number) : 0;
}

function parseRtkAnalytics(output) {
  const value = typeof output === 'string' ? JSON.parse(output) : output;
  if (!value || typeof value !== 'object' || !Array.isArray(value.daily)) throw new Error('RTK analytics has an invalid shape.');
  const counts = new Map();
  for (const row of value.daily) {
    const day = row?.date;
    if (!validDay(day)) continue;
    counts.set(day, (counts.get(day) ?? 0) + tokenCount(row.saved_tokens));
  }
  const daily = [...counts].sort(([a], [b]) => a.localeCompare(b)).slice(-366).map(([day, savedTokens]) => ({ day, savedTokens }));
  const total = daily.reduce((sum, row) => sum + row.savedTokens, 0);
  return { daily, totalSaved: tokenCount(value.summary?.total_saved) || total };
}

module.exports = { defaultSettings, normalizeSettings, validateSettings, settingsPath, readSettings, writeSettings, managedRtkRoot, managedRtkPath, isManagedRtkPath, resolveRtkPath, runRtk, rewriteShellCommand, needsShellApproval, applyPromptModes, parseRtkAnalytics };
