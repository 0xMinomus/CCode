"""The native plugin gate owns both the n8n MCP and the full skill set."""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from local_only import n8n_plugin, storage


class N8nPluginLifecycleTests(unittest.TestCase):
    def test_activation_controls_mcp_and_all_skills(self):
        baseline = ROOT / 'baselines/zcode-3.14.5-original-agent.cjs'
        executable = ROOT / 'app/ccode'
        if not baseline.is_file() or not executable.is_file():
            self.skipTest('pinned agent and Electron runtime are unavailable')
        expected = sorted(path.name for path in (ROOT / 'src/plugins/n8n/skills').iterdir()
                          if (path / 'SKILL.md').is_file())
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            agent = root / 'resources/glm/zcode.cjs'
            agent.parent.mkdir(parents=True)
            agent.write_text(n8n_plugin.patch_agent(storage.patch_agent(baseline.read_text())))
            shutil.copytree(ROOT / 'src/plugins/n8n', root / 'resources/mcp/plugins/n8n')
            env = {**os.environ, 'ZCODE_STANDALONE_ROOT': str(root / 'namespace'), 'ELECTRON_RUN_AS_NODE': '1'}

            def cli(*args):
                result = subprocess.run([str(executable), str(agent), *args], cwd=root, env=env,
                                        capture_output=True, text=True, timeout=60)
                self.assertEqual(result.returncode, 0, result.stderr)
                return json.loads(result.stdout)

            def n8n():
                return next(plugin for plugin in cli('plugins', 'list', '--json')
                            if plugin['id'] == n8n_plugin.PLUGIN_ID)

            def skills():
                return sorted(skill['name'] for skill in cli('skills', 'list', '--json')['skills']
                              if skill['name'] in expected)

            self.assertFalse(n8n()['enabled'])
            self.assertEqual(skills(), [])
            cli('plugins', 'enable', n8n_plugin.PLUGIN_ID, '--json')
            self.assertEqual(n8n()['mcpServerNames'], ['plugin:n8n:n8n'])
            self.assertEqual(skills(), expected)
            cli('plugins', 'disable', n8n_plugin.PLUGIN_ID, '--json')
            self.assertEqual(n8n()['mcpServerNames'], [])
            self.assertEqual(skills(), [])

    def test_host_skills_follow_standalone_plugin_enablement(self):
        baseline = ROOT / 'baselines/zcode-3.14.5-original.asar'
        if not baseline.is_file():
            self.skipTest('pinned app baseline is unavailable')
        sys.path.insert(0, str(ROOT / 'scripts'))
        from asar import Archive
        archive = Archive(baseline)
        patched = {}
        storage.patch_archive(archive, patched, json.loads((ROOT / 'project.json').read_text())['renderer_asset'])
        host = patched['out/host/index.js'].decode()
        start = host.index('import{access as kge,appendFile as Pge,')
        end = host.index('i(tR,"createSkillsService");', start) + len('i(tR,"createSkillsService");')
        expected = sorted(path.name for path in (ROOT / 'src/plugins/n8n/skills').iterdir()
                          if (path / 'SKILL.md').is_file())
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            data = root / 'namespace/data'
            home = root / 'unrelated-home'
            cache = data / '.zcode/cli/plugins/cache/zcode-plugins-official/n8n/1.0.0'
            shutil.copytree(ROOT / 'src/plugins/n8n', cache)
            config = data / '.zcode/cli/config.json'
            config.write_text(json.dumps({'plugins': {'enabledPlugins': {n8n_plugin.PLUGIN_ID: True}}}))
            unrelated = home / '.zcode/cli/config.json'
            unrelated.parent.mkdir(parents=True)
            unrelated.write_text(json.dumps({'plugins': {'enabledPlugins': {n8n_plugin.PLUGIN_ID: False}}}))
            original_unrelated = unrelated.read_bytes()
            resources = root / 'resources'
            for name, _ in archive.entries():
                if name.startswith('node_modules/yaml/'):
                    target = resources / 'app.asar' / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(archive.read(name))
            script = resources / 'app.asar/out/host/check.mjs'
            script.parent.mkdir(parents=True)
            script.write_text(
                'const i=value=>value,y=()=>{},Hs="SKILL.md",ul=10,pc=name=>!name.startsWith("."),uc=new Set(),'
                'Ai=()=>process.env.ZCODE_DATA_BASE_DIR;\n' + host[start:end] +
                '\nconst service=tR({isDesktopRuntime:true});'
                'const enabled=await service.list({workspacePath:process.env.ZCODE_DATA_BASE_DIR,provider:"glm"});'
                'await import("node:fs/promises").then(fs=>fs.writeFile(WK,JSON.stringify({plugins:{enabledPlugins:{"n8n@zcode-plugins-official":false}}})));'
                'const disabled=await service.list({workspacePath:process.env.ZCODE_DATA_BASE_DIR,provider:"glm"});'
                'console.log(JSON.stringify({enabled,disabled}));')
            env = {**os.environ, 'HOME': str(home), 'ZCODE_DATA_BASE_DIR': str(data),
                   'ZCODE_STORAGE_DIR': str(data / '.zcode')}
            result = subprocess.run(['node', str(script)], env=env, capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            listings = json.loads(result.stdout)
            self.assertEqual(sorted(skill['name'] for skill in listings['enabled']['skills']
                                    if skill.get('pluginName') == 'n8n'), expected)
            self.assertFalse(any(skill.get('pluginName') == 'n8n' for skill in listings['disabled']['skills']))
            self.assertEqual(unrelated.read_bytes(), original_unrelated)
