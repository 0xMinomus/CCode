'use strict';
const fs = require('node:fs'), path = require('node:path'), os = require('node:os');
const { execFileSync } = require('node:child_process');
const RUN_KEY = 'HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run';
const RUN_NAME = 'CCodeStartupPrewarm', DESKTOP_NAME = 'ccode-startup-prewarm.desktop';
const OWNER = 'X-CCode-Startup-Prewarm=true';
function defaultRoot(platform, env, home) {
  return platform === 'win32' ? path.join(env.LOCALAPPDATA?.trim() || path.join(home, 'AppData', 'Local'), 'CCode') : path.join(home, '.local/share/ccode');
}
function read(file) {
  try { return fs.readFileSync(file, 'utf8'); } catch (error) { if (error.code === 'ENOENT') return null; throw error; }
}
function atomic(file, value) {
  fs.mkdirSync(path.dirname(file), { recursive: true, mode: 0o700 });
  const temp = file + '.' + process.pid + '.' + require('node:crypto').randomUUID();
  try { fs.writeFileSync(temp, value, { flag: 'wx', mode: 0o600 }); fs.renameSync(temp, file); }
  finally { fs.rmSync(temp, { force: true }); }
}
function stableExecutable(platform, env, executable) {
  const candidate = platform === 'linux' && env.APPIMAGE ? env.APPIMAGE : executable;
  const paths = platform === 'win32' ? path.win32 : path.posix;
  if (typeof candidate !== 'string' || !paths.isAbsolute(candidate) || /[\x00-\x1f\x7f]/.test(candidate)) throw Error('Startup executable path is invalid.');
  if (platform === 'linux' && (/\/\.mount_[^/]+(?:\/|$)/.test(candidate) || env.APPDIR && paths.resolve(candidate).startsWith(paths.resolve(env.APPDIR) + '/'))) throw Error('Startup needs the stable AppImage file, not its temporary mount.');
  if (platform === 'win32' && candidate.includes('"')) throw Error('Startup executable path is invalid.');
  return candidate;
}
function desktopCommand(executable) {
  // Desktop Entry Exec has its own quoting rules, not shell quoting. Percent is a field code.
  const quoted = executable.replace(/["`$\\]/g, '\\$&');
  return '"' + quoted.replace(/\\/g, '\\\\').replace(/%/g, '%%') + '" --hidden';
}
function trusted(event, app) {
  if (!event.senderFrame || event.senderFrame !== event.sender.mainFrame) return false;
  try {
    const url = new URL(event.senderFrame.url);
    const { fileURLToPath } = require('node:url');
    return url.protocol === 'file:' && path.resolve(fileURLToPath(url)) === path.resolve(app.getAppPath(), 'out/renderer/index.html');
  } catch { return false; }
}
function create(options = {}) {
  const platform = options.platform || process.platform, env = options.env || process.env;
  const home = options.home || os.homedir(), app = options.app;
  const root = path.resolve(options.root || env.CCODE_STANDALONE_ROOT?.trim() || defaultRoot(platform, env, home));
  const stateFile = path.join(root, 'startup-prewarm.json');
  const supported = platform === 'win32' || platform === 'linux';
  const isolated = root !== path.resolve(defaultRoot(platform, env, home));
  const windows = new Map();
  let state = { enabled: true }, error = null, hidden = supported && (options.argv || process.argv).includes('--hidden');
  try {
    const raw = read(stateFile);
    if (raw !== null) {
      state = JSON.parse(raw);
      if (!state || typeof state !== 'object' || Array.isArray(state) || typeof state.enabled !== 'boolean' || state.command !== undefined && typeof state.command !== 'string') throw Error('Invalid startup preference file.');
    }
  } catch (cause) { state = null; error = cause.message; }
  const exec = options.execFileSync || execFileSync;
  const reg = path.win32.join(env.SystemRoot || 'C:\\Windows', 'System32', 'reg.exe');
  function registry(args) { return exec(reg, args, { encoding: 'utf8', windowsHide: true, timeout: 10000, stdio: ['ignore', 'pipe', 'pipe'] }); }
  function currentRegistry() {
    const script = '[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false);$ErrorActionPreference="Stop";'
      + '$key=[Microsoft.Win32.Registry]::CurrentUser.OpenSubKey("Software\\Microsoft\\Windows\\CurrentVersion\\Run");'
      + 'try{$value=$null;if($key -and $key.GetValueNames() -contains "CCodeStartupPrewarm") {'
      + 'if($key.GetValueKind("CCodeStartupPrewarm") -ne [Microsoft.Win32.RegistryValueKind]::String){throw "Startup registry value has an unsupported type."};'
      + '$value=$key.GetValue("CCodeStartupPrewarm")};@{value=$value}|ConvertTo-Json -Compress}finally{if($key){$key.Dispose()}}';
    const powershell = path.win32.join(env.SystemRoot || 'C:\\Windows', 'System32', 'WindowsPowerShell', 'v1.0', 'powershell.exe');
    const raw = exec(powershell, ['-NoProfile', '-NonInteractive', '-EncodedCommand', Buffer.from(script, 'utf16le').toString('base64')],
      { encoding: 'utf8', windowsHide: true, timeout: 10000, stdio: ['ignore', 'pipe', 'pipe'] });
    const value = JSON.parse(raw.replace(/^\uFEFF/, '')).value;
    if (value !== null && typeof value !== 'string') throw Error('Startup registry value is invalid.');
    return value;
  }
  function sync(enabled, owned = state.command) {
    if (!supported) throw Error('Login startup is available on Windows and Linux only.');
    if (isolated) throw Error('Login startup is not changed for an isolated CCode data root.');
    let command = state.command;
    if (enabled) {
      const executable = stableExecutable(platform, env, options.executable || process.execPath);
      command = platform === 'win32' ? '"' + executable + '" --hidden' : desktopCommand(executable);
    }
    if (platform === 'win32') {
      const current = currentRegistry();
      if (current !== null && current !== command && current !== owned) throw Error('Another startup entry uses the CCode startup name; it was left unchanged.');
      if (enabled && current !== command) registry(['add', RUN_KEY, '/v', RUN_NAME, '/t', 'REG_SZ', '/d', command, '/f']);
      else if (!enabled && current !== null) registry(['delete', RUN_KEY, '/v', RUN_NAME, '/f']);
    } else {
      const config = env.XDG_CONFIG_HOME || path.join(home, '.config');
      if (!path.isAbsolute(config)) throw Error('XDG_CONFIG_HOME must be an absolute path.');
      const entry = path.join(config, 'autostart', DESKTOP_NAME), current = read(entry);
      if (current !== null && !current.split(/\r?\n/).includes(OWNER)) throw Error('Another startup entry uses the CCode startup filename; it was left unchanged.');
      const content = '[Desktop Entry]\nType=Application\nName=CCode\nComment=Preload CCode workspace at login\nExec=' + command + '\nTerminal=false\nNoDisplay=true\n' + OWNER + '\n';
      if (enabled && current !== content) atomic(entry, content);
      else if (!enabled && current !== null) fs.unlinkSync(entry);
    }
    return command;
  }
  function snapshot() { return { enabled: state?.enabled ?? false, supported: supported && !isolated && state !== null, error }; }
  function save(enabled) {
    if (typeof enabled !== 'boolean') throw Error('Startup preference must be a boolean.');
    if (!state) throw Error(error);
    const command = sync(enabled);
    const next = { enabled, command };
    try { atomic(stateFile, JSON.stringify(next, null, 2) + '\n'); }
    catch (cause) {
      try { sync(state.enabled, command); } catch (rollback) { console.warn('[startup-prewarm] Could not restore previous login entry:', rollback.message); }
      throw cause;
    }
    state = next; error = null;
    return snapshot();
  }
  function register(ipcMain) {
    if (state && supported && !isolated) {
      try { save(state.enabled); } catch (cause) { error = cause.message; console.warn('[startup-prewarm]', error); }
    } else if (isolated) error = 'Login startup is not changed for an isolated CCode data root.';
    ipcMain.handle('ccode-startup-prewarm:get', event => {
      if (!trusted(event, app)) throw Error('Startup settings require the local CCode window.');
      return snapshot();
    });
    ipcMain.handle('ccode-startup-prewarm:set', (event, enabled) => {
      if (!trusted(event, app)) throw Error('Startup settings require the local CCode window.');
      return save(enabled);
    });
  }
  function track(win, maximized) {
    if (!hidden) return;
    windows.set(win, maximized);
    win.once('closed', () => windows.delete(win));
  }
  function reveal() {
    hidden = false;
    for (const [win, maximized] of windows) {
      if (win.isDestroyed()) continue;
      win.setSkipTaskbar(false);
      win.webContents.setBackgroundThrottling(true);
      if (maximized) win.maximize();
      if (win.isMinimized()) win.restore();
      win.show();
      win.focus();
    }
    windows.clear();
  }
  return { get hidden() { return hidden; }, shouldStart: () => !hidden || !!state?.enabled, register, snapshot, save, track, reveal };
}
module.exports = { create, stableExecutable, desktopCommand, trusted, RUN_KEY, RUN_NAME, DESKTOP_NAME };
