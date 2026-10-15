"""The native plugin gate owns both the n8n MCP and the full skill set."""
import json
import functools
import hashlib
import http.server
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
import threading
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from local_only import n8n_plugin, rebrand, storage


class N8nPluginLifecycleTests(unittest.TestCase):
    def test_activation_controls_mcp_and_all_skills(self):
        baseline = ROOT / json.loads((ROOT / 'project.json').read_text())['agent_baseline']
        executable = ROOT / 'app/ccode'
        artifact = ROOT / 'runtime/release-plugin/ccode-n8n-plugin-1.0.0.zip'
        if not baseline.is_file() or not executable.is_file() or not artifact.is_file():
            self.skipTest('pinned agent, Electron runtime, and packaged n8n zip are required')
        expected = sorted(path.name for path in (ROOT / 'src/plugins/n8n/skills').iterdir()
                          if (path / 'SKILL.md').is_file())
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            agent = root / 'resources/glm/ccode.cjs'
            agent.parent.mkdir(parents=True)
            packages = agent.parent / 'packages'
            packages.mkdir()
            (packages / 'ccode-guide-plugin').symlink_to(ROOT / 'app/resources/glm/packages/ccode-guide-plugin',
                                                        target_is_directory=True)
            handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(artifact.parent))
            server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            self.addCleanup(server.server_close)
            self.addCleanup(server.shutdown)
            manifest = json.loads(n8n_plugin.MANIFEST.read_text())
            pinned = manifest['plugins'][0]['source']['sha256']
            self.assertEqual(hashlib.sha256(artifact.read_bytes()).hexdigest(), pinned)
            manifest['plugins'][0]['source']['url'] = f'http://127.0.0.1:{server.server_port}/{artifact.name}'
            local_manifest = root / 'marketplace.json'
            local_manifest.write_text(json.dumps(manifest))
            with patch.object(n8n_plugin, 'MANIFEST', local_manifest):
                agent.write_text(n8n_plugin.patch_agent(storage.patch_agent(rebrand.apply(baseline.read_text()))))
            env = {**os.environ, 'CCODE_STANDALONE_ROOT': str(root / 'namespace'), 'ELECTRON_RUN_AS_NODE': '1'}

            def cli(*args):
                result = subprocess.run([str(executable), str(agent), *args], cwd=root, env=env,
                                        capture_output=True, text=True, timeout=180)
                self.assertEqual(result.returncode, 0, result.stderr)
                return json.loads(result.stdout)

            def n8n():
                return next(plugin for plugin in cli('plugins', 'list', '--json')
                            if plugin['id'] == n8n_plugin.PLUGIN_ID)

            def skills():
                return sorted(skill['name'] for skill in cli('skills', 'list', '--json')['skills']
                              if skill['name'] in expected)

            listing = cli('plugins', 'list', '--available', '--json')
            self.assertFalse(any(plugin['id'] == n8n_plugin.PLUGIN_ID for plugin in listing['installed']))
            self.assertTrue(any(plugin['id'] == n8n_plugin.PLUGIN_ID for plugin in listing['available']))
            cache = root / 'namespace/data/.ccode/cli/plugins/cache/ccode-plugins-official/n8n'
            self.assertFalse(cache.exists())
            self.assertEqual(skills(), [])
            cli('plugins', 'install', n8n_plugin.PLUGIN_ID, '--json')
            cli('plugins', 'enable', n8n_plugin.PLUGIN_ID, '--json')
            self.assertEqual(n8n()['mcpServerNames'], ['plugin:n8n:n8n'])
            self.assertEqual(skills(), expected)
            installed = pathlib.Path(n8n()['rootPath'])
            sdk = installed / 'node_modules/@modelcontextprotocol/sdk/dist/esm/client'
            script = root / 'handshake.cjs'
            script.write_text(
                '(async()=>{const {pathToFileURL}=require("node:url");'
                f'const base={json.dumps(str(sdk))};'
                'const {Client}=await import(pathToFileURL(base+"/index.js"));'
                'const {StdioClientTransport}=await import(pathToFileURL(base+"/stdio.js"));'
                'const client=new Client({name:"ccode-n8n-smoke",version:"1.0.0"});'
                'const transport=new StdioClientTransport({command:process.execPath,'
                f'args:[{json.dumps(str(agent))},"__ccode-plugin-host",'
                f'{json.dumps(str(installed / "dist/mcp/server.js"))}],'
                'env:{...process.env,ELECTRON_RUN_AS_NODE:"1",'
                'N8N_API_URL:"http://127.0.0.1:5678",N8N_API_KEY:"isolated-handshake-only",'
                f'CCODE_PLUGIN_DATA:{json.dumps(str(root / "plugin-data"))}' + '},stderr:"pipe"});'
                'transport.stderr?.on("data",chunk=>process.stderr.write(chunk));'
                'try{await client.connect(transport);const result=await client.listTools();'
                'console.log(JSON.stringify({tools:result.tools.map(tool=>tool.name)}));}'
                'finally{await client.close();}})().catch(e=>{console.error(e);process.exitCode=1});')
            handshake = subprocess.run([str(executable), str(script)], env=env, cwd=root,
                                       capture_output=True, text=True, timeout=120)
            self.assertEqual(handshake.returncode, 0, handshake.stderr)
            self.assertTrue({'search_nodes', 'get_node', 'validate_workflow'}.issubset(
                json.loads(handshake.stdout)['tools']), handshake.stdout)
            cli('plugins', 'disable', n8n_plugin.PLUGIN_ID, '--json')
            self.assertEqual(n8n()['mcpServerNames'], [])
            self.assertEqual(skills(), [])

    def test_host_skills_follow_standalone_plugin_enablement(self):
        baseline = ROOT / json.loads((ROOT / 'project.json').read_text())['baseline']
        if not baseline.is_file():
            self.skipTest('pinned app baseline is unavailable')
        sys.path.insert(0, str(ROOT / 'scripts'))
        from asar import Archive
        from build import Rebranded
        archive = Archive(baseline)
        patched = {}
        storage.patch_archive(Rebranded(archive, patched), patched,
                              json.loads((ROOT / 'project.json').read_text())['renderer_asset'])
        host = patched['out/host/index.js'].decode()
        start = host.index('import{access as kge,appendFile as Pge,')
        end = host.index('i(tR,"createSkillsService");', start) + len('i(tR,"createSkillsService");')
        expected = sorted(path.name for path in (ROOT / 'src/plugins/n8n/skills').iterdir()
                          if (path / 'SKILL.md').is_file())
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            data = root / 'namespace/data'
            home = root / 'unrelated-home'
            cache = data / '.ccode/cli/plugins/cache/ccode-plugins-official/n8n/1.0.0'
            shutil.copytree(ROOT / 'src/plugins/n8n', cache)
            config = data / '.ccode/cli/config.json'
            config.write_text(json.dumps({'plugins': {'enabledPlugins': {n8n_plugin.PLUGIN_ID: True}}}))
            unrelated = home / '.ccode/cli/config.json'
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
                'Ai=()=>process.env.CCODE_DATA_BASE_DIR;\n' + host[start:end] +
                '\nconst service=tR({isDesktopRuntime:true});'
                'const enabled=await service.list({workspacePath:process.env.CCODE_DATA_BASE_DIR,provider:"glm"});'
                'await import("node:fs/promises").then(fs=>fs.writeFile(WK,JSON.stringify({plugins:{enabledPlugins:{"n8n@ccode-plugins-official":false}}})));'
                'const disabled=await service.list({workspacePath:process.env.CCODE_DATA_BASE_DIR,provider:"glm"});'
                'console.log(JSON.stringify({enabled,disabled}));')
            env = {**os.environ, 'HOME': str(home), 'CCODE_DATA_BASE_DIR': str(data),
                   'CCODE_STORAGE_DIR': str(data / '.ccode')}
            result = subprocess.run(['node', str(script)], env=env, capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            listings = json.loads(result.stdout)
            self.assertEqual(sorted(skill['name'] for skill in listings['enabled']['skills']
                                    if skill.get('pluginName') == 'n8n'), expected)
            self.assertFalse(any(skill.get('pluginName') == 'n8n' for skill in listings['disabled']['skills']))
            self.assertEqual(unrelated.read_bytes(), original_unrelated)
