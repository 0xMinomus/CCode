'use strict';
// CCode addition: archive the files a task produced while it ran outside a
// project. The task itself keeps using the upstream conversation workspace and
// the UI is untouched; when the change summary reports produced files, their
// paths are copied here into a hidden per-task folder so a later task that
// regenerates the same name never overwrites the earlier result.
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const ARCHIVE_CHANNEL = 'ccode-task-archive:archive';
const FOLDER_CHANNEL = 'ccode-task-archive:folder';
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

function readIndex(root) {
  try {
    const data = JSON.parse(fs.readFileSync(path.join(root, INDEX_NAME), 'utf8'));
    return data && typeof data === 'object' && !Array.isArray(data) ? data : {};
  } catch {
    return {};
  }
}

function writeIndex(root, index) {
  fs.mkdirSync(root, { recursive: true });
  const target = path.join(root, INDEX_NAME);
  const temporary = target + '.tmp';
  fs.writeFileSync(temporary, JSON.stringify(index, null, 2) + '\n');
  fs.renameSync(temporary, target);
}

function folderFor(root, sessionId) {
  const index = readIndex(root);
  const stored = index[sessionId];
  if (typeof stored === 'string' && stored.startsWith(root + path.sep) && fs.existsSync(stored)) return stored;
  const folder = path.join(root, 'task-' + stamp(new Date()));
  fs.mkdirSync(folder, { recursive: true });
  index[sessionId] = folder;
  writeIndex(root, index);
  return folder;
}

function archive(options = {}, context = {}) {
  const { root, base } = defaults(context);
  const sessionId = typeof options.sessionId === 'string' ? options.sessionId.trim() : '';
  const workspacePath = typeof options.workspacePath === 'string' ? options.workspacePath.trim() : '';
  if (!sessionId || !workspacePath) return { ok: false, skipped: 'missing-input' };
  if (!base) return { ok: false, skipped: 'no-storage' };
  let resolvedBase;
  try {
    resolvedBase = fs.realpathSync(base);
  } catch {
    return { ok: false, skipped: 'no-storage' };
  }
  let resolvedWorkspace;
  try {
    resolvedWorkspace = fs.realpathSync(workspacePath);
  } catch {
    resolvedWorkspace = path.resolve(workspacePath);
  }
  if (resolvedWorkspace !== resolvedBase) return { ok: false, skipped: 'not-conversation' };
  const entries = Array.isArray(options.paths) ? [...new Set(options.paths)] : [];
  if (entries.length === 0) return { ok: false, skipped: 'no-files' };
  let folder;
  try {
    folder = folderFor(root, sessionId);
  } catch (error) {
    return { ok: false, error: String(error && error.message ? error.message : error) };
  }
  const copied = [];
  for (const entry of entries) {
    if (typeof entry !== 'string' || entry.trim() === '') continue;
    try {
      const absolute = path.isAbsolute(entry) ? entry : path.resolve(resolvedBase, entry);
      const real = fs.realpathSync(absolute);
      if (!inside(resolvedBase, real)) continue;
      const stat = fs.statSync(real);
      if (!stat.isFile() || stat.size > MAX_FILE_BYTES) continue;
      const relative = path.relative(resolvedBase, real);
      const destination = path.join(folder, relative);
      if (!inside(folder, destination)) continue;
      fs.mkdirSync(path.dirname(destination), { recursive: true });
      fs.copyFileSync(real, destination);
      copied.push(relative);
    } catch {
      // Deleted or unreadable files are skipped; the archive never blocks the change summary.
    }
  }
  return { ok: true, folder, copied };
}

function folder(options = {}, context = {}) {
  const { root } = defaults(context);
  const sessionId = typeof options.sessionId === 'string' ? options.sessionId.trim() : '';
  if (!sessionId) return { ok: false, skipped: 'missing-input' };
  const index = readIndex(root);
  const stored = index[sessionId];
  if (typeof stored !== 'string' || !fs.existsSync(stored)) return { ok: false, skipped: 'none' };
  return { ok: true, folder: stored };
}

function register({ ipcMain }) {
  ipcMain.handle(ARCHIVE_CHANNEL, (event, options) => archive(options));
  ipcMain.handle(FOLDER_CHANNEL, (event, options) => folder(options));
}

module.exports = { register, archive, folder, conversationDir };
