'use strict';

const fs = require('node:fs');
const path = require('node:path');
const https = require('node:https');
const { spawn } = require('node:child_process');
const { createHash, randomUUID } = require('node:crypto');

// Official Apache-2.0 edition, built with --no-default-features. Never substitute the BUSL engine edition.
const VERSION = '1.0.1';
const RELEASES = Object.freeze({
  'win32-x64': Object.freeze({ name: 'rtk-oss-x86_64-pc-windows-msvc.zip', size: 5708680, sha256: '0e53e2eca471e15fbd3636e64e6bc0b182cbc278ed0339c80450a2dd03f4cd6b', binary: 'rtk.exe', binarySha256: '4346e25f54d4a4aaa39809d8384e59193d6646d8b008f9f9a90acaea5d6b37da', licenseSha256: '0d4d6a722737b8a3f9bd40868011f8d6522650eb93b6f3c36bf780bb54210a5f' }),
  'linux-x64': Object.freeze({ name: 'rtk-oss-x86_64-unknown-linux-musl.tar.gz', size: 5766270, sha256: 'a44e8ffc43981100b4ddf1710399a1649a6c874591aa6d0c0727fe6cbd983c41', binary: 'rtk', binarySha256: '38b915f2a52ce4b7ef7d6dc3966aaeccb9f754731b2933571bf85026bcba8677', licenseSha256: '33f694a31d9f9df3e292a9413a3cdb0113fa72698e2c719f657ff6b53165dcc4' }),
});

function downloadRelease(release) {
  const url = `https://github.com/rtk-ai/rtk/releases/download/v${VERSION}/${release.name}`;
  return new Promise((resolve, reject) => {
    let request, response, finished = false;
    const finish = (error, bytes) => {
      if (finished) return;
      finished = true;
      clearTimeout(timer);
      if (error) { request?.destroy(); response?.destroy(); reject(error); }
      else resolve(bytes);
    };
    const timer = setTimeout(() => finish(Error('RTK download timed out. Try again.')), 90_000);
    const fetch = (address, redirects) => {
      const target = new URL(address);
      if (target.protocol !== 'https:' || !['github.com', 'release-assets.githubusercontent.com', 'objects.githubusercontent.com'].includes(target.hostname) || target.username || target.password || (target.port && target.port !== '443')) {
        finish(Error('RTK download redirected outside the official release hosts.')); return;
      }
      request = https.get(target, { headers: { 'User-Agent': 'CCode-RTK-installer', Accept: 'application/octet-stream' } }, incoming => {
        response = incoming;
        if ([301, 302, 303, 307, 308].includes(incoming.statusCode)) {
          incoming.resume();
          if (!incoming.headers.location || redirects >= 5) { finish(Error('RTK download has too many redirects.')); return; }
          try { fetch(new URL(incoming.headers.location, target), redirects + 1); } catch (error) { finish(error); }
          return;
        }
        if (incoming.statusCode !== 200) { finish(Error(`RTK download failed (HTTP ${incoming.statusCode}). Try again.`)); return; }
        const chunks = []; let size = 0;
        incoming.on('data', chunk => {
          size += chunk.length;
          if (size > release.size) { finish(Error('RTK download exceeded the pinned release size.')); return; }
          chunks.push(chunk);
        });
        incoming.once('error', error => finish(error));
        incoming.once('aborted', () => finish(Error('RTK download was interrupted. Try again.')));
        incoming.once('end', () => {
          if (finished) return;
          const bytes = Buffer.concat(chunks, size);
          if (size !== release.size || createHash('sha256').update(bytes).digest('hex') !== release.sha256) {
            finish(Error('RTK SHA256 verification failed. Nothing was installed.')); return;
          }
          finish(null, bytes);
        });
      });
      request.once('error', error => finish(error));
    };
    fetch(url, 0);
  });
}

function extractArchive(archive, destination, release, env = process.env) {
  const tar = process.platform === 'win32' ? path.join(env.SystemRoot || 'C:\\Windows', 'System32', 'tar.exe') : '/usr/bin/tar';
  return new Promise((resolve, reject) => {
    const child = spawn(tar, ['-xf', archive, '-C', destination, release.binary, 'LICENSE'], { env, stdio: ['ignore', 'ignore', 'pipe'], windowsHide: true });
    let errorText = '', settled = false;
    const finish = error => { if (settled) return; settled = true; clearTimeout(timer); error ? reject(error) : resolve(); };
    const timer = setTimeout(() => { child.kill(); finish(Error('RTK archive extraction timed out.')); }, 30_000);
    child.stderr.on('data', chunk => { if (errorText.length < 2048) errorText += chunk.toString('utf8'); });
    child.once('error', error => finish(Error(`RTK archive extraction could not start: ${error.message}`)));
    child.once('close', code => finish(code === 0 ? null : Error(`RTK archive extraction failed: ${errorText.trim() || code}`)));
  });
}

async function verifyContracts(runtime, executable, env, cwd, pinned = false) {
  const run = args => runtime.runRtk(args, { executable, env, cwd, timeoutMs: 8000 });
  const version = await run(['--version']);
  if (version.error || version.code !== 0 || !/^rtk\s+\d+\.\d+\.\d+/i.test(version.stdout.trim()) || (pinned && !/^rtk\s+1\.0\.1(?:\s|$)/i.test(version.stdout.trim()))) throw Error('RTK version verification failed.');
  const rewrite = await run(['rewrite', 'git status']);
  if (rewrite.error || ![0, 3].includes(rewrite.code) || !/^rtk\s+git\s+status$/.test(rewrite.stdout.trim())) throw Error('RTK does not support the required shell rewrite contract.');
  const noMatch = await run(['rewrite', 'ccode-rtk-contract-no-match']);
  if (noMatch.error || noMatch.code !== 1 || noMatch.stdout.trim()) throw Error('RTK does not support the required no-match contract.');
  const gain = await run(['gain', '--daily', '--format', 'json']);
  if (gain.error || gain.code !== 0) throw Error('RTK does not support the required daily analytics contract.');
  runtime.parseRtkAnalytics(gain.stdout);
}

const installations = new Map();
function installRtk(options) {
  const { runtime, env = process.env } = options;
  const root = runtime.managedRtkRoot(env);
  if (!root) return Promise.reject(Error('Standalone settings directory is unavailable.'));
  if (installations.has(root)) return installations.get(root);
  const pending = install({ ...options, env, root }).finally(() => installations.delete(root));
  installations.set(root, pending);
  return pending;
}

async function install({ runtime, env, root, platform = process.platform, arch = process.arch, download = downloadRelease, extract = extractArchive }) {
  const release = RELEASES[`${platform}-${arch}`];
  if (!release) throw Error('One-click RTK installation supports Windows x64 and Linux x64 only.');
  // Validate settings before downloading; never replace unreadable user preferences with defaults.
  runtime.readSettings(env);
  const existing = runtime.resolveRtkPath(env);
  if (existing && !runtime.isManagedRtkPath(existing, env)) {
    await verifyContracts(runtime, existing, env, undefined);
    const settings = runtime.readSettings(env);
    return runtime.writeSettings({ ...settings, rtk: { enabled: true } }, env);
  }
  fs.mkdirSync(root, { recursive: true, mode: 0o700 });
  const directory = `v${VERSION}-oss-${platform}-${arch}-${randomUUID()}`;
  const temporary = fs.mkdtempSync(path.join(root, '.install-'));
  const content = path.join(temporary, 'content'), target = path.join(root, directory);
  const pointer = path.join(root, 'current.json'), pointerTemporary = path.join(root, `.current-${randomUUID()}.tmp`);
  let promoted = false, activated = false;
  try {
    const bytes = await download(release);
    // Enforce pins here as well as in the HTTP reader, before any extraction or execution.
    if (bytes.length !== release.size || createHash('sha256').update(bytes).digest('hex') !== release.sha256) throw Error('RTK SHA256 verification failed. Nothing was installed.');
    const archive = path.join(temporary, release.name);
    fs.writeFileSync(archive, bytes, { flag: 'wx', mode: 0o600 });
    fs.mkdirSync(content, { mode: 0o700 });
    await extract(archive, content, release, env);
    for (const [name, digest] of [[release.binary, release.binarySha256], ['LICENSE', release.licenseSha256]]) {
      const file = path.join(content, name);
      if (!fs.lstatSync(file).isFile() || createHash('sha256').update(fs.readFileSync(file)).digest('hex') !== digest) throw Error(`RTK ${name} verification failed. Nothing was installed.`);
    }
    const executable = path.join(content, release.binary);
    fs.chmodSync(executable, 0o700);
    const probe = path.join(temporary, 'probe');
    fs.mkdirSync(probe, { mode: 0o700 });
    await verifyContracts(runtime, executable, { ...env, RTK_DB_PATH: path.join(probe, 'history.db'), RTK_TELEMETRY_DISABLED: '1' }, probe, true);
    // A user RTK added during download still takes precedence, including its own contract validation.
    const selected = runtime.resolveRtkPath(env);
    if (selected && !runtime.isManagedRtkPath(selected, env)) {
      await verifyContracts(runtime, selected, env, undefined);
    } else {
      fs.renameSync(content, target); promoted = true;
      fs.writeFileSync(pointerTemporary, JSON.stringify({ version: VERSION, edition: 'oss', directory }) + '\n', { flag: 'wx', mode: 0o600 });
      fs.renameSync(pointerTemporary, pointer); activated = true;
      // A superseded install or a crashed run leaves directories nothing selects any more.
      for (const entry of fs.readdirSync(root)) {
        if (entry === directory || entry === 'current.json') continue;
        const superseded = /^v\d+(?:\.\d+)+-oss-(?:win32|linux)-x64-[a-f0-9-]+$/.test(entry);
        const interrupted = entry.startsWith('.install-') && path.join(root, entry) !== temporary;
        if (superseded || interrupted) fs.rmSync(path.join(root, entry), { recursive: true, force: true });
      }
    }
    const settings = runtime.readSettings(env);
    return runtime.writeSettings({ ...settings, rtk: { enabled: true } }, env);
  } finally {
    fs.rmSync(pointerTemporary, { force: true });
    fs.rmSync(temporary, { recursive: true, force: true });
    if (promoted && !activated) fs.rmSync(target, { recursive: true, force: true });
  }
}

module.exports = { VERSION, RELEASES, downloadRelease, extractArchive, verifyContracts, installRtk };
