"""The desktop MCP entry the app seeds itself, on either platform.

One backend per platform, resolved from the tree the application runs from: `linux-desktop`
points at the packaged screen-mcp launcher on Linux, `windows-desktop` at the Node backend run
by Electron-as-Node. Platform-specific expectations are gated inside the tests so the Linux
release keeps its shipped behaviour.
"""
import json
import os
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE = ROOT / 'src/main/mcp-catalog.cjs'
WINDOWS = os.name == 'nt'
DESKTOP = 'windows-desktop' if WINDOWS else 'linux-desktop'
OTHER = 'linux-desktop' if WINDOWS else 'windows-desktop'
LEGACY = 'fedora-desktop'

BOOTSTRAP = ('const mod=require(process.argv[1]);'
             'mod.bootstrap({root:process.argv[2],resourcesPath:process.argv[3]});'
             'process.stdout.write(JSON.stringify({paths:mod.paths({root:process.argv[2],resourcesPath:process.argv[3]}),'
             'node:process.execPath,platform:process.platform}));')
TRUSTED = ('const mod=require(process.argv[1]);'
           'process.stdout.write(JSON.stringify(JSON.parse(process.argv[2]).map(([url,sameFrame])=>{'
           'const frame={url};return mod.trusted({senderFrame:frame,sender:{mainFrame:sameFrame?frame:{url}}});})));')


class DesktopServerSeedTests(unittest.TestCase):
    """The desktop MCP server points at whichever tree the application runs from."""

    def bootstrap(self, resources, root):
        return json.loads(subprocess.run(['node', '-e', BOOTSTRAP, str(MODULE), str(root), str(resources)],
                                         check=True, capture_output=True, text=True, cwd=ROOT).stdout)

    def tree(self, temporary):
        root = pathlib.Path(temporary)
        (root / 'project.json').write_text('{}')
        if WINDOWS:
            (root / 'services/desktop-win').mkdir(parents=True)
            (root / 'services/desktop-win/main.cjs').write_text('')
        else:
            binary = root / 'services/desktop/bin'
            binary.mkdir(parents=True)
            (binary / 'screen-mcp').write_text('#!/bin/sh\n')
            (root / 'services/desktop/.venv/bin').mkdir(parents=True)
            (root / 'services/desktop/.venv/bin/python').write_text('')
        resources = root / 'app/resources'
        (resources / 'mcp').mkdir(parents=True)
        (resources / 'mcp/catalog.json').write_text('[]')
        (resources / 'launch.cjs').write_text('')
        return root, resources

    def servers(self, root):
        return json.loads((root / 'data/.ccode/cli/config.json').read_text())['mcp']['servers']

    def write_servers(self, root, servers):
        config = root / 'data/.ccode/cli/config.json'
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text(json.dumps({'mcp': {'servers': servers}}))

    def seed_marker(self, root, seeded):
        (root / 'mcp').mkdir(parents=True, exist_ok=True)
        (root / 'mcp/default-seed.json').write_text(json.dumps({'seeded': seeded}))

    def test_the_server_is_registered_for_the_running_tree(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, resources = self.tree(temporary)
            state = self.bootstrap(resources, root)
            self.assertEqual(state['platform'], 'win32' if WINDOWS else 'linux')
            server = self.servers(root)[DESKTOP]
            if WINDOWS:
                self.assertEqual(server['command'], state['node'])
                self.assertEqual(server['args'], [str(root / 'services/desktop-win/main.cjs')])
                self.assertEqual(server['env']['ELECTRON_RUN_AS_NODE'], '1')
                self.assertEqual(server['env']['MCP_SCREEN_PROFILE'], 'ccode-fast')
                self.assertEqual(server['env']['MCP_SCREEN_MAX_EDGE'], '1280')
                self.assertEqual(server['env']['MCP_SCREEN_MAX_OUTPUT_KB'], '250')
            else:
                self.assertEqual(server['command'], str(root / 'services/desktop/bin/screen-mcp'))
                self.assertEqual(server['args'], [])
                self.assertEqual(server['env']['SCREEN_PYTHON'], str(root / 'services/desktop/.venv/bin/python'))
                self.assertEqual(server['env']['MCP_SCREEN_PROFILE'], 'ccode-fast')
                self.assertEqual(server['env']['MCP_SCREEN_ATSPI'], '1')
            self.assertNotIn(OTHER, self.servers(root))
            marker = json.loads((root / 'mcp/default-seed.json').read_text())
            self.assertIn(DESKTOP, marker['seeded'])

    def test_a_moved_tree_refreshes_the_target_and_keeps_user_settings(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, resources = self.tree(temporary)
            stale = ('C:/old/CCode/resources/desktop-win/main.cjs' if WINDOWS
                     else '/tmp/.mount_old/services/desktop/bin/screen-mcp')
            self.write_servers(root, {DESKTOP: {'command': stale, 'env': {'MCP_SCREEN_PROFILE': 'custom', 'KEEP': '1'}}})
            self.seed_marker(root, [DESKTOP])
            state = self.bootstrap(resources, root)
            server = self.servers(root)[DESKTOP]
            self.assertEqual(server['command'], state['node'] if WINDOWS else str(root / 'services/desktop/bin/screen-mcp'))
            self.assertEqual(server['env']['MCP_SCREEN_PROFILE'], 'custom')
            self.assertEqual(server['env']['KEEP'], '1')
            self.assertIn('ELECTRON_RUN_AS_NODE' if WINDOWS else 'MCP_SCREEN_ATSPI', server['env'])

    def test_a_deleted_server_stays_deleted(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, resources = self.tree(temporary)
            self.bootstrap(resources, root)
            self.write_servers(root, {})
            self.bootstrap(resources, root)
            self.assertNotIn(DESKTOP, self.servers(root))

    @unittest.skipIf(WINDOWS, 'fedora-desktop predates the rename on Linux only')
    def test_the_legacy_name_is_adopted_with_its_settings(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, resources = self.tree(temporary)
            self.write_servers(root, {LEGACY: {'command': '/old/tree/screen-mcp', 'enabled': True,
                                               'env': {'MCP_SCREEN_MAX_EDGE': '900'}}})
            self.bootstrap(resources, root)
            servers = self.servers(root)
            self.assertNotIn(LEGACY, servers)
            server = servers[DESKTOP]
            self.assertIs(server['enabled'], True)
            self.assertEqual(server['env']['MCP_SCREEN_MAX_EDGE'], '900')
            self.assertEqual(server['command'], str(root / 'services/desktop/bin/screen-mcp'))

    @unittest.skipUnless(WINDOWS, 'no such entry can exist on Linux')
    def test_linux_entries_are_left_untouched_on_windows(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, resources = self.tree(temporary)
            linux = {'command': '/usr/bin/screen-mcp', 'env': {'SCREEN_PYTHON': '/usr/bin/python3'}}
            self.write_servers(root, {'linux-desktop': linux, LEGACY: {'command': '/old/tree/screen-mcp'}})
            self.bootstrap(resources, root)
            servers = self.servers(root)
            self.assertEqual(servers['linux-desktop'], linux, 'the other platform id is never adopted or rewritten')
            self.assertEqual(servers[LEGACY], {'command': '/old/tree/screen-mcp'},
                             'the legacy rename is Linux-only, so nothing is migrated here')
            self.assertIn(DESKTOP, servers)

    def test_the_default_root_is_the_platform_namespace(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, resources = self.tree(temporary)
            script = ('const mod=require(process.argv[1]),os=require("node:os");'
                      'process.stdout.write(JSON.stringify({root:mod.paths({resourcesPath:process.argv[2]}).root,'
                      'home:os.homedir(),local:process.env.LOCALAPPDATA||""}));')
            environment = {key: value for key, value in os.environ.items() if key != 'CCODE_STANDALONE_ROOT'}
            environment['LOCALAPPDATA'] = 'C:/Users/test/AppData/Local'
            state = json.loads(subprocess.run(['node', '-e', script, str(MODULE), str(resources)], check=True,
                                              capture_output=True, text=True, cwd=ROOT, env=environment).stdout)
            if WINDOWS:
                self.assertEqual(state['root'], os.path.normpath(os.path.join(state['local'], 'CCode')))
            else:
                self.assertEqual(state['root'], os.path.join(state['home'], '.local/share/ccode'))
            environment.pop('LOCALAPPDATA')
            fallback = json.loads(subprocess.run(['node', '-e', script, str(MODULE), str(resources)], check=True,
                                                 capture_output=True, text=True, cwd=ROOT, env=environment).stdout)
            if WINDOWS:
                self.assertEqual(fallback['root'], os.path.normpath(os.path.join(fallback['home'], 'AppData', 'Local', 'CCode')))
                self.assertNotEqual(fallback['root'], state['root'])
            else:
                self.assertEqual(fallback['root'], state['root'])

    def test_only_the_local_renderer_frame_is_trusted(self):
        cases = [
            ['file:///opt/CCode/app/resources/app.asar/out/renderer/index.html', True],
            ['file:///resources/app.asar/out/renderer/index.html', True],
            ['file:///C:/Users/test%20user/CCode/app/resources/app.asar/out/renderer/index.html', True],
            ['file:///C:/Program%20Files/CCode/resources/app.asar/out/renderer/index.html', True],
            ['https://example.com/out/renderer/index.html', False],
            ['file:///opt/CCode/app/resources/app.asar/out/renderer/other.html', False],
            ['file:///opt/CCode/app/resources/app.asar/out/renderer/index.html', False],
        ]
        result = json.loads(subprocess.run(['node', '-e', TRUSTED, str(MODULE), json.dumps(cases)], check=True,
                                          capture_output=True, text=True, cwd=ROOT).stdout)
        self.assertEqual(result, [expected for _, expected in cases])


if __name__ == '__main__':
    unittest.main()
