import json
import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'scripts')]
from asar import Archive
from local_only import rebrand, startup_prewarm

MODULE = ROOT / 'src/main/startup-prewarm.cjs'


class StartupPrewarmTests(unittest.TestCase):
    def node(self, body):
        script = r'''
const assert = require('node:assert/strict'), fs = require('node:fs'), os = require('node:os'), path = require('node:path');
const mod = require(process.argv[1]);
const home = fs.mkdtempSync(path.join(os.tmpdir(), 'ccode-prewarm-'));
const env = { LOCALAPPDATA: path.join(home, 'local'), XDG_CONFIG_HOME: path.join(home, 'config') };
const handlers = new Map(), ipc = { handle: (name, fn) => handlers.set(name, fn) };
const app = { getAppPath: () => path.join(home, 'resources', 'app.asar') };
try {
''' + body + r'''
} finally { fs.rmSync(home, { recursive: true, force: true }); }
'''
        subprocess.run(['node', '-e', script, str(MODULE)], check=True, capture_output=True, text=True, cwd=ROOT)

    def test_linux_default_enable_restart_disable_and_move(self):
        self.node(r'''
const options = { platform: 'linux', home, env: { ...env, APPIMAGE: '/home/user/CCode 100%.AppImage', APPDIR: '/tmp/.mount_ccode1' }, executable: '/tmp/.mount_ccode1/app/ccode', app, argv: ['ccode', '--hidden'] };
const value = mod.create(options); assert.equal(value.hidden, true); assert.equal(value.shouldStart(), true);
value.register(ipc);
const entry = path.join(env.XDG_CONFIG_HOME, 'autostart', mod.DESKTOP_NAME);
assert.match(fs.readFileSync(entry, 'utf8'), /Exec="\/home\/user\/CCode 100%%\.AppImage" --hidden/);
assert.doesNotMatch(fs.readFileSync(entry, 'utf8'), /\.mount_/);
const unrelated = path.join(path.dirname(entry), 'other.desktop'); fs.writeFileSync(unrelated, 'mine');
value.save(false); assert.equal(fs.existsSync(entry), false);
const disabled = mod.create(options); disabled.register(ipc);
assert.equal(disabled.snapshot().enabled, false); assert.equal(disabled.shouldStart(), false);
assert.equal(fs.existsSync(entry), false); assert.equal(fs.readFileSync(unrelated, 'utf8'), 'mine');
const moved = mod.create({ ...options, env: { ...options.env, APPIMAGE: '/home/user/New CCode.AppImage' } });
moved.save(true); assert.match(fs.readFileSync(entry, 'utf8'), /New CCode\.AppImage/);
''')

    def test_linux_refuses_unowned_entries_bad_state_and_transient_mount(self):
        self.node(r'''
const options = { platform: 'linux', home, env, executable: '/opt/ccode/app/ccode', app };
const entry = path.join(env.XDG_CONFIG_HOME, 'autostart', mod.DESKTOP_NAME);
fs.mkdirSync(path.dirname(entry), { recursive: true }); fs.writeFileSync(entry, '[Desktop Entry]\nExec=other\n');
const value = mod.create(options); assert.throws(() => value.save(true), /left unchanged/);
assert.equal(fs.readFileSync(entry, 'utf8'), '[Desktop Entry]\nExec=other\n');
assert.throws(() => mod.stableExecutable('linux', {}, '/tmp/.mount_CCode123/app/ccode'), /temporary mount/);
assert.throws(() => mod.stableExecutable('linux', { APPIMAGE: 'relative.AppImage' }, '/opt/app/ccode'), /invalid/);
const root = path.join(home, '.local/share/ccode'); fs.mkdirSync(root, { recursive: true });
fs.writeFileSync(path.join(root, 'startup-prewarm.json'), '{broken');
const broken = mod.create(options); assert.equal(broken.snapshot().supported, false);
assert.throws(() => broken.save(true)); assert.equal(fs.readFileSync(entry, 'utf8'), '[Desktop Entry]\nExec=other\n');
''')

    def test_desktop_exec_escaping_and_owned_disable_without_stable_executable(self):
        self.node(r'''
const escaped = mod.desktopCommand('/home/user/a"$`\\100%.AppImage');
assert.equal(escaped, '"/home/user/a' + '\\\\"' + '\\\\$' + '\\\\`' + '\\\\\\\\' + '100%%.AppImage" --hidden');
const options = { platform: 'linux', home, env, executable: '/opt/ccode/app/ccode', app };
mod.create(options).save(true);
const mounted = mod.create({ ...options, executable: '/tmp/.mount_CCode123/app/ccode' });
mounted.save(false);
assert.equal(fs.existsSync(path.join(env.XDG_CONFIG_HOME, 'autostart', mod.DESKTOP_NAME)), false);
''')

    def test_windows_registry_ownership_move_disable_and_exact_arguments(self):
        self.node(r'''
let current = null; const writes = [];
const execFileSync = (exe, args, options) => {
  assert.equal(options.windowsHide, true);
  if (exe.endsWith('powershell.exe')) {
    assert.equal(args[0], '-NoProfile'); assert.equal(args[2], '-EncodedCommand');
    const script = Buffer.from(args[3], 'base64').toString('utf16le');
    assert.match(script, /Registry.*CurrentUser.OpenSubKey/);
    return JSON.stringify({ value: current });
  }
  assert.equal(exe, 'C:\\Windows\\System32\\reg.exe');
  writes.push(args);
  if (args[0] === 'add') current = args[args.indexOf('/d') + 1];
  if (args[0] === 'delete') current = null;
  return '';
};
const options = { platform: 'win32', home, env, app, execFileSync, executable: 'C:\\Program Files\\CCode\\app\\CCode.exe' };
const value = mod.create(options); value.register(ipc);
assert.equal(current, '"C:\\Program Files\\CCode\\app\\CCode.exe" --hidden');
assert.deepEqual(writes[0], ['add', mod.RUN_KEY, '/v', mod.RUN_NAME, '/t', 'REG_SZ', '/d', current, '/f']);
const moved = mod.create({ ...options, executable: 'D:\\CCode\\app\\CCode.exe' }); moved.register(ipc);
assert.equal(current, '"D:\\CCode\\app\\CCode.exe" --hidden');
moved.save(false); assert.equal(current, null);
const restarted = mod.create(options); restarted.register(ipc); assert.equal(current, null);
current = '"C:\\Unrelated.exe"'; const count = writes.length;
assert.throws(() => restarted.save(true), /left unchanged/); assert.equal(writes.length, count);
''')

    def test_hidden_window_reveal_keeps_same_renderer_and_ignores_destroyed_window(self):
        self.node(r'''
const value = mod.create({ platform: 'linux', home, env, argv: ['ccode', '--hidden'] });
const calls = [], win = { once: () => {}, isDestroyed: () => false, isMinimized: () => true,
  setSkipTaskbar: x => calls.push(['taskbar', x]), webContents: { setBackgroundThrottling: x => calls.push(['throttle', x]) },
  maximize: () => calls.push('maximize'), restore: () => calls.push('restore'), show: () => calls.push('show'), focus: () => calls.push('focus') };
value.track(win, true); value.track({ once: () => {}, isDestroyed: () => true }, false);
assert.deepEqual(calls, []); value.reveal(); assert.equal(value.hidden, false);
assert.deepEqual(calls, [['taskbar', false], ['throttle', true], 'maximize', 'restore', 'show', 'focus']);
value.reveal(); assert.equal(calls.length, 6);
''')

    def test_ipc_only_local_main_frame_and_isolated_root_never_autostarts(self):
        self.node(r'''
const options = { platform: 'linux', home, env, executable: '/opt/ccode/app/ccode', app };
const value = mod.create(options); value.register(ipc);
const { pathToFileURL } = require('node:url');
const frame = { url: pathToFileURL(path.join(app.getAppPath(), 'out/renderer/index.html')).href };
const event = { senderFrame: frame, sender: { mainFrame: frame } };
assert.equal(handlers.get('ccode-startup-prewarm:get')(event).enabled, true);
assert.throws(() => handlers.get('ccode-startup-prewarm:set')(event, 'false'), /boolean/);
for (const url of ['https://example.com/out/renderer/index.html', pathToFileURL(path.join(home, 'other/out/renderer/index.html')).href]) {
  const other = { url }; assert.equal(mod.trusted({ senderFrame: other, sender: { mainFrame: other } }, app), false);
}
assert.equal(mod.trusted({ senderFrame: { ...frame }, sender: { mainFrame: frame } }, app), false);
const isolated = mod.create({ ...options, root: path.join(home, 'smoke') }); isolated.register(ipc);
assert.equal(isolated.snapshot().supported, false); assert.throws(() => isolated.save(true), /isolated/);
''')

    def test_pinned_main_and_native_general_anchors(self):
        project = json.loads((ROOT / 'project.json').read_text())
        archive = Archive(ROOT / project['baseline'])
        main = rebrand.apply(archive.read(project['main_asset']).decode())
        patched = startup_prewarm.patch_main(main)
        self.assertEqual(patched.count('requestSingleInstanceLock('), main.count('requestSingleInstanceLock('))
        self.assertIn('if(t.includes("--hidden"))return;ccodeStartup.reveal();if(OC(', patched)
        self.assertIn('show:!ccodeStartup.hidden,skipTaskbar:ccodeStartup.hidden', patched)
        self.assertIn('backgroundThrottling:!ccodeStartup.hidden', patched)
        self.assertIn('ccodeStartup.track(n,o.maximized)', patched)
        self.assertIn('Zo.ensurePrimaryWindow("second-instance")', patched)
        self.assertIn('if(i!=="app-ready")ccodeStartup.reveal();', patched)
        self.assertIn('Promise.resolve(ga(n,"index",e.bootstrap))', patched)
        self.assertIn('e.spawnHostProcess(t,r,', patched)
        self.assertNotIn(startup_prewarm.DOM_READY, patched)
        with self.assertRaises(ValueError):
            startup_prewarm.patch_main(main.replace(startup_prewarm.SINGLE_INSTANCE, 'changed'))
        renderer = rebrand.apply(archive.read(project['renderer_asset']).decode())
        ui = startup_prewarm.patch_renderer(renderer)
        self.assertIn('b?(0,$.jsx)(CCodeStartupPrewarm,{}):null,', ui)
        self.assertIn('return $.jsx(Z1,', ui)
        self.assertIn('control: $.jsx(Xx,', ui)
        self.assertIn('window.ccodeStartupPrewarm.set(enabled)', ui)

    def test_uninstaller_removes_only_current_install_owned_run_command(self):
        from pack_windows import NSIS
        self.assertIn('ReadRegStr $0 HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Run" "CCodeStartupPrewarm"', NSIS)
        self.assertIn('${If} $0 == \'$\\"$INSTDIR\\app\\CCode.exe$\\" --hidden\'', NSIS)
        self.assertIn('DeleteRegValue HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Run" "CCodeStartupPrewarm"', NSIS)


if __name__ == '__main__':
    unittest.main()
