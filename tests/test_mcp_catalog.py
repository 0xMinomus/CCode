import json
import pathlib
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE = ROOT / 'src/main/mcp-catalog.cjs'


class DesktopServerSeedTests(unittest.TestCase):
    """The desktop MCP server points at whichever tree the application runs from."""

    def bootstrap(self, resources, root):
        script = ('const mod=require(process.argv[1]);'
                  'mod.bootstrap({root:process.argv[2],resourcesPath:process.argv[3]});'
                  'process.stdout.write(JSON.stringify(mod.paths({root:process.argv[2],resourcesPath:process.argv[3]})));')
        return json.loads(subprocess.run(['node', '-e', script, str(MODULE), str(root), str(resources)],
                                         check=True, capture_output=True, text=True, cwd=ROOT).stdout)

    def tree(self, temporary):
        root = pathlib.Path(temporary)
        (root / 'project.json').write_text('{}')
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

    def test_the_server_is_registered_for_the_running_tree(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temporary:
            root, resources = self.tree(temporary)
            self.bootstrap(resources, root)
            server = self.servers(root)['linux-desktop']
            self.assertEqual(server['command'], str(root / 'services/desktop/bin/screen-mcp'))
            self.assertEqual(server['args'], [])
            self.assertEqual(server['env']['SCREEN_PYTHON'], str(root / 'services/desktop/.venv/bin/python'))
            self.assertEqual(server['env']['MCP_SCREEN_PROFILE'], 'ccode-fast')
            marker = json.loads((root / 'mcp/default-seed.json').read_text())
            self.assertIn('linux-desktop', marker['seeded'])

    def test_a_moved_tree_refreshes_the_command_and_keeps_user_settings(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temporary:
            root, resources = self.tree(temporary)
            self.write_servers(root, {'linux-desktop': {'command': '/tmp/.mount_old/services/desktop/bin/screen-mcp',
                                                        'env': {'MCP_SCREEN_PROFILE': 'custom', 'KEEP': '1'}}})
            (root / 'mcp').mkdir()
            (root / 'mcp/default-seed.json').write_text(json.dumps({'seeded': ['linux-desktop']}))
            self.bootstrap(resources, root)
            server = self.servers(root)['linux-desktop']
            self.assertEqual(server['command'], str(root / 'services/desktop/bin/screen-mcp'))
            self.assertEqual(server['env']['MCP_SCREEN_PROFILE'], 'custom')
            self.assertEqual(server['env']['KEEP'], '1')
            self.assertIn('MCP_SCREEN_ATSPI', server['env'])

    def test_a_deleted_server_stays_deleted(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temporary:
            root, resources = self.tree(temporary)
            self.bootstrap(resources, root)
            self.write_servers(root, {})
            self.bootstrap(resources, root)
            self.assertNotIn('linux-desktop', self.servers(root))

    def test_the_legacy_name_is_adopted_with_its_settings(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temporary:
            root, resources = self.tree(temporary)
            self.write_servers(root, {'fedora-desktop': {'command': '/old/tree/screen-mcp', 'enabled': True,
                                                         'env': {'MCP_SCREEN_MAX_EDGE': '900'}}})
            self.bootstrap(resources, root)
            servers = self.servers(root)
            self.assertNotIn('fedora-desktop', servers)
            server = servers['linux-desktop']
            self.assertIs(server['enabled'], True)
            self.assertEqual(server['env']['MCP_SCREEN_MAX_EDGE'], '900')
            self.assertEqual(server['command'], str(root / 'services/desktop/bin/screen-mcp'))


if __name__ == '__main__':
    unittest.main()
