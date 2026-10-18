'use strict';
// CCode addition: the per-task folder for work started outside a project.
// Nothing is created when the app opens or a draft starts: the task keeps using
// the upstream conversation workspace, so the sidebar stays a single "Tasks"
// list and no folder name shows up in the UI. The moment the task (or the user)
// hands over a file, main copies it into `~/CCodeProject/task-<date>-<time>-<id>`
// keyed by session id, so a later task that regenerates the same name never
// overwrites the earlier result. The task menu ("Open in File Manager") and the
// change-summary rows resolve their target through this index, so the hidden
// conversation workspace never has to be shown to the user.
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const ARCHIVE_CHANNEL = 'ccode-task-archive:archive';
const FOLDER_CHANNEL = 'ccode-task-archive:folder';
const OPEN_CHANNEL = 'ccode-task-archive:open';
const RESOLVE_CHANNEL = 'ccode-task-archive:resolve';
const UPLOAD_CHANNEL = 'ccode-task-archive:upload';
const INDEX_NAME = '.task-folders.json';
// Media artifacts stay out of the archive; the workspace copy remains the
// reference. Raise this if large generated files should be archived too.
const MAX_FILE_BYTES = 64 * 1024 * 1024;

function stamp(date) {
  const pad = value => String(value).padStart(2, '0');
  return [
    date.getFullYear(),
    pad(date.getMonth() + 1),
    pad(date.getDate()),
    '-',
    pad(date.getHours()),
    pad(date.getMinutes()),
    pad(date.getSeconds()),
    '-',
    Math.random().toString(36).slice(2, 6)
  ].join('');
}

function conversationDir(env = process.env) {
  const storage = (env.CCODE_STORAGE_DIR || '').trim();
  return storage ? path.join(storage, 'workspace', 'default') : null;
}

function inside(parent, child) {
  const relative = path.relative(parent, child);
  return relative !== '' && !relative.startsWith('..') && !path.isAbsolute(relative);
}

function defaults(context = {}) {
  return {
    root: context.root || path.join(os.homedir(), 'CCodeProject'),
    base: context.base !== undefined ? context.base : conversationDir()
  };
}

// The index file is `{ sessions, files, latest }`; older builds wrote a flat
// `sessionId -> folder` map, which is absorbed into `sessions` on read.
function readIndex(root) {
  let raw = null;
  try {
    raw = JSON.parse(fs.readFileSync(path.join(root, INDEX_NAME), 'utf8'));
  } catch {
    raw = null;
  }
  const index = { sessions: {}, files: {}, latest: {} };
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return index;
  for (const [key, value] of Object.entries(raw)) {
    if (key === 'sessions' || key === 'files' || key === 'latest') continue;
    if (typeof value === 'string') index.sessions[key] = value;
  }
  if (raw.sessions && typeof raw.sessions === 'object' && !Array.isArray(raw.sessions)) {
    for (const [key, value] of Object.entries(raw.sessions)) if (typeof value === 'string') index.sessions[key] = value;
  }
  if (raw.latest && typeof raw.latest === 'object' && !Array.isArray(raw.latest)) {
    for (const [key, value] of Object.entries(raw.latest)) if (typeof value === 'string') index.latest[key] = value;
  }
  if (raw.files && typeof raw.files === 'object' && !Array.isArray(raw.files)) {
    for (const [workspace, entries] of Object.entries(raw.files)) {
      if (!entries || typeof entries !== 'object' || Array.isArray(entries)) continue;
      const map = {};
      for (const [name, value] of Object.entries(entries)) if (typeof value === 'string') map[name] = value;
      if (Object.keys(map).length > 0) index.files[workspace] = map;
    }
  }
  return index;
}

function writeIndex(root, index) {
  fs.mkdirSync(root, { recursive: true });
  const target = path.join(root, INDEX_NAME);
  const temporary = target + '.tmp';
  fs.writeFileSync(temporary, JSON.stringify(index, null, 2) + '\n');
  fs.renameSync(temporary, target);
}

// Index keys keep forward slashes so the renderer can hand the same
// workspace-relative path back on any platform.
function relativeKey(from, to) {
  return path.relative(from, to).split(path.sep).join('/');
}

function trimmed(value) {
  return typeof value === 'string' ? value.trim() : '';
}

function existingFolder(root, candidate) {
  if (typeof candidate !== 'string' || !candidate.startsWith(root + path.sep)) return null;
  try {
    return fs.statSync(candidate).isDirectory() ? candidate : null;
  } catch {
    return null;
  }
}

function ensureFolder(root, index, sessionId) {
  const known = existingFolder(root, index.sessions[sessionId]);
  if (known) return known;
  const folder = path.join(root, 'task-' + stamp(new Date()));
  fs.mkdirSync(folder, { recursive: true });
  index.sessions[sessionId] = folder;
  return folder;
}

function remember(index, workspacePath, relative, folder) {
  index.latest[workspacePath] = folder;
  const map = index.files[workspacePath] || (index.files[workspacePath] = {});
  map[relative] = folder;
}

// Resolve the conversation workspace a request refers to, or null when the
// request is not about the no-project workspace at all.
function resolveWorkspace(workspacePath, base) {
  if (!workspacePath || !base) return null;
  let resolvedBase;
  try {
    resolvedBase = fs.realpathSync(base);
  } catch {
    return null;
  }
  let resolved;
  try {
    resolved = fs.realpathSync(workspacePath);
  } catch {
    resolved = path.resolve(workspacePath);
  }
  return resolved === resolvedBase ? resolvedBase : null;
}

function failure(error) {
  return { ok: false, error: String(error && error.message ? error.message : error) };
}

function archive(options = {}, context = {}) {
  const { root, base } = defaults(context);
  const sessionId = trimmed(options.sessionId);
  const workspacePath = trimmed(options.workspacePath);
  if (!sessionId || !workspacePath) return { ok: false, skipped: 'missing-input' };
  const workspace = resolveWorkspace(workspacePath, base);
  if (!workspace) return { ok: false, skipped: 'not-conversation' };
  const entries = Array.isArray(options.paths) ? [...new Set(options.paths)] : [];
  const pending = [];
  for (const entry of entries) {
    const candidate = trimmed(entry);
    if (!candidate) continue;
    try {
      const real = fs.realpathSync(path.isAbsolute(candidate) ? candidate : path.resolve(workspace, candidate));
      if (!inside(workspace, real)) continue;
      const stat = fs.statSync(real);
      if (!stat.isFile() || stat.size > MAX_FILE_BYTES) continue;
      pending.push({ source: real, relative: relativeKey(workspace, real) });
    } catch {
      // Deleted or unreadable files are skipped; the archive never blocks the
      // change summary.
    }
  }
  if (pending.length === 0) return { ok: false, skipped: 'no-files' };
  const index = readIndex(root);
  let folder;
  try {
    folder = ensureFolder(root, index, sessionId);
  } catch (error) {
    return failure(error);
  }
  const copied = [];
  for (const item of pending) {
    try {
      const destination = path.join(folder, ...item.relative.split('/'));
      if (!inside(folder, destination)) continue;
      fs.mkdirSync(path.dirname(destination), { recursive: true });
      fs.copyFileSync(item.source, destination);
      remember(index, workspacePath, item.relative, folder);
      copied.push(item.relative);
    } catch {
      // Same contract as above: a failed copy only drops that one entry.
    }
  }
  if (copied.length === 0) return { ok: false, skipped: 'no-files' };
  try {
    writeIndex(root, index);
  } catch (error) {
    return failure(error);
  }
  return { ok: true, folder, copied };
}

// A file the user attached in the composer: the bytes are handed over once and
// stored next to the files the task itself produced.
function upload(options = {}, context = {}) {
  const { root, base } = defaults(context);
  const sessionId = trimmed(options.sessionId);
  const workspacePath = trimmed(options.workspacePath);
  if (!sessionId || !workspacePath) return { ok: false, skipped: 'missing-input' };
  const workspace = resolveWorkspace(workspacePath, base);
  if (!workspace) return { ok: false, skipped: 'not-conversation' };
  const fileName = path.basename(trimmed(options.fileName).split(/[\\/]/).pop() || '');
  if (!fileName || fileName === '.' || fileName === '..') return { ok: false, skipped: 'missing-input' };
  const data = typeof options.dataBase64 === 'string' ? options.dataBase64 : '';
  if (!data) return { ok: false, skipped: 'missing-input' };
  let buffer;
  try {
    buffer = Buffer.from(data, 'base64');
  } catch {
    return { ok: false, skipped: 'invalid-data' };
  }
  if (buffer.length === 0) return { ok: false, skipped: 'invalid-data' };
  if (buffer.length > MAX_FILE_BYTES) return { ok: false, skipped: 'too-large' };
  const index = readIndex(root);
  let folder;
  try {
    folder = ensureFolder(root, index, sessionId);
  } catch (error) {
    return failure(error);
  }
  const destination = path.join(folder, fileName);
  if (!inside(folder, destination)) return { ok: false, skipped: 'invalid-name' };
  try {
    fs.writeFileSync(destination, buffer);
    remember(index, workspacePath, fileName, folder);
    writeIndex(root, index);
  } catch (error) {
    return failure(error);
  }
  return { ok: true, folder, file: fileName };
}

// The task menu asks for the folder behind the conversation the user is looking
// at; the session id matches the archive key, the task id and the workspace
// path are fallbacks for ids that arrive in a different shape.
function folder(options = {}, context = {}) {
  const { root } = defaults(context);
  const index = readIndex(root);
  for (const candidate of [trimmed(options.sessionId), trimmed(options.taskId)]) {
    const found = existingFolder(root, candidate ? index.sessions[candidate] : null);
    if (found) return { ok: true, folder: found };
  }
  const workspacePath = trimmed(options.workspacePath);
  if (workspacePath) {
    const found = existingFolder(root, index.latest[workspacePath]);
    if (found) return { ok: true, folder: found, fallback: 'workspace' };
  }
  return { ok: false, skipped: 'none' };
}

// The change-summary rows know the workspace and the relative path, not the
// session id: prefer the archived copy, otherwise the live workspace file.
function resolve(options = {}, context = {}) {
  const { root } = defaults(context);
  const workspacePath = trimmed(options.workspacePath);
  const relPath = trimmed(options.relPath);
  if (!workspacePath || !relPath) return { ok: false, skipped: 'missing-input' };
  const direct = path.isAbsolute(relPath) ? relPath : path.join(workspacePath, ...relPath.split(/[\\/]/));
  const index = readIndex(root);
  const map = index.files[workspacePath] || {};
  const archived = existingFolder(root, map[relPath.split(path.sep).join('/')]);
  if (archived) {
    const copy = path.join(archived, ...relPath.split(/[\\/]/));
    if (inside(archived, copy) && fs.existsSync(copy)) return { ok: true, path: copy, archived: true };
  }
  if (fs.existsSync(direct)) return { ok: true, path: direct, archived: false };
  return { ok: false, skipped: 'missing' };
}

async function openFolder(options = {}, context = {}) {
  const shell = context.shell;
  const target = trimmed(options.path);
  if (!target || !shell) return { ok: false, skipped: 'missing-input' };
  let stat;
  try {
    stat = fs.statSync(target);
  } catch {
    return { ok: false, skipped: 'missing' };
  }
  try {
    if (!stat.isDirectory()) {
      shell.showItemInFolder(target);
      return { ok: true, path: target };
    }
    // The launcher is not awaited: on Linux `shell.openPath` resolves only
    // after the file manager finishes activating, which can stall the IPC
    // reply (observed as "reply was never sent" / a never-settling invoke).
    // The stat above is the check; whether a window appears is the user's
    // confirmation.
    Promise.resolve(shell.openPath(target)).catch(() => {});
    return { ok: true, path: target };
  } catch (error) {
    return failure(error);
  }
}

function register({ ipcMain, shell } = {}) {
  ipcMain.handle(ARCHIVE_CHANNEL, (event, options) => archive(options));
  ipcMain.handle(FOLDER_CHANNEL, (event, options) => folder(options));
  ipcMain.handle(OPEN_CHANNEL, (event, options) => openFolder(options, { shell }));
  ipcMain.handle(RESOLVE_CHANNEL, (event, options) => resolve(options));
  ipcMain.handle(UPLOAD_CHANNEL, (event, options) => upload(options));
}

module.exports = { register, archive, folder, upload, resolve, openFolder, conversationDir };
