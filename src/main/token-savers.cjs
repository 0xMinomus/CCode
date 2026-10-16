'use strict';

const runtime = require('./token-savers-runtime.cjs');
const installer = require('./rtk-installer.cjs');

async function snapshot() {
  let settings = runtime.defaultSettings(), settingsError = null;
  try { settings = runtime.readSettings(); } catch (error) { settingsError = `Settings could not be read: ${error?.message ?? error}`; }
  const executable = runtime.resolveRtkPath();
  const rtk = { enabled: settings.rtk.enabled, available: !!executable, path: executable, daily: [], totalSaved: 0, updatedAt: Date.now(), error: executable ? null : 'RTK is not installed.', installSupported: process.arch === 'x64' && ['win32', 'linux'].includes(process.platform), installVersion: installer.VERSION, installEdition: 'Apache-2.0' };
  if (executable) {
    const result = await runtime.runRtk(['gain', '--daily', '--format', 'json'], { executable, timeoutMs: 4000, maxBytes: 1_048_576 });
    if (!result.available) {
      rtk.available = false;
      rtk.error = 'RTK could not be started.';
    } else if (result.error || result.code !== 0) {
      rtk.error = result.error || 'RTK analytics could not be read.';
    } else {
      try { Object.assign(rtk, runtime.parseRtkAnalytics(result.stdout)); }
      catch { rtk.error = 'RTK returned invalid analytics data.'; }
    }
  }
  return { settings, settingsError, rtk };
}

function register({ ipcMain }) {
  function trusted(event) {
    const frame = event.senderFrame;
    return frame === event.sender.mainFrame && frame.url.startsWith('file://') && frame.url.includes('/out/renderer/index.html');
  }
  ipcMain.handle('ccode-token-savers:snapshot', async event => {
    if (!trusted(event)) throw Error('Token savers are only available in the local CCode window.');
    return snapshot();
  });
  ipcMain.handle('ccode-token-savers:save', async (event, settings) => {
    if (!trusted(event)) throw Error('Token savers are only available in the local CCode window.');
    return runtime.writeSettings(settings);
  });
  ipcMain.handle('ccode-token-savers:install-rtk', async event => {
    if (!trusted(event)) throw Error('Token savers are only available in the local CCode window.');
    await installer.installRtk({ runtime });
    return snapshot();
  });
}

module.exports = { register, snapshot };
