import importlib
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
marketplace = importlib.import_module('local_only.marketplace')
rebrand = importlib.import_module('local_only.rebrand')
storage = importlib.import_module('local_only.storage')


def shipped_agent():
    """The agent text the build hands to this module: rebranded, then bootstrapped."""
    baseline = (ROOT / 'baselines/upstream-3.14.5-original-agent.cjs').read_text()
    return storage.patch_agent(rebrand.apply(baseline))

REMOTE_MARKETPLACE = rebrand.previous('ccode-plugins-official')
REMOTE_PLUGIN_DIR = rebrand.previous('.ccode-plugin')


def node_command():
    return shutil.which('node')


def runtime_source():
    return marketplace.render_runtime()


RUNTIME = runtime_source()

# One published payload, shaped like the official marketplace zips: the manifest
# lives under the upstream directory, its labels are Chinese-only, and the skill
# frontmatter describes the skill in Chinese.
PUBLISHED_MANIFEST = {
    'name': 'blender',
    'version': '0.2.3',
    'description': '在 ZCode 对话旁打开 Blender 场景：Agent 修改物体、材质、相机并渲染预览。',
    'description_i18n': {'en': 'Edit Blender scenes with an interactive 3D panel and MCP tools.',
                         'zh-CN': '在 ZCode 对话旁打开 Blender 场景。'},
    'author': {'name': 'ZCode'},
    'userConfig': {
        'blenderPath': {'type': 'file', 'title': 'Blender 可执行文件', 'description': '可选。留空时依次探测。'},
        'allowPython': {'type': 'boolean', 'title': '允许 run_python'},
        'engineDownloadDir': {'type': 'directory', 'title': '便携版 Blender 目录', 'description': ''},
    },
    'ui': {'surfaces': [{'id': 'blender', 'title': {'zh-CN': 'Blender', 'en-US': 'Blender'}}]},
    'mcpServers': {'blender': {'type': 'stdio', 'command': 'node',
                               'args': [f'${{{rebrand.previous("CCODE")}_PLUGIN_ROOT}}/dist/server.mjs'],
                               'env': {f'{rebrand.previous("CCODE")}_WORKSPACE_ROOT': f'${{{rebrand.previous("CCODE")}_PROJECT_DIR}}'}}},
}

PUBLISHED_SKILL = """---
name: blender
description: 用户要看、改、渲染 Blender 场景（.blend）时怎么用 blender 的工具
---

# Blender 插件
"""


class RuntimeContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.runtime = self.root / 'marketplace-compat.cjs'
        self.runtime.write_text(RUNTIME)
        self.plugin = self.root / 'plugin'
        (self.plugin / REMOTE_PLUGIN_DIR).mkdir(parents=True)
        (self.plugin / REMOTE_PLUGIN_DIR / 'plugin.json').write_text(json.dumps(PUBLISHED_MANIFEST, ensure_ascii=False))
        (self.plugin / 'skills/blender').mkdir(parents=True)
        (self.plugin / 'skills/blender/SKILL.md').write_text(PUBLISHED_SKILL, newline='\n')

    def run_node(self, script):
        command = node_command()
        if not command:
            self.skipTest('node is unavailable')
        result = subprocess.run([command, '-e', script], capture_output=True, text=True,
                                cwd=self.root, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def node_json(self, body):
        prefix = (f"const compat=require({json.dumps(str(self.runtime))});"
                  f"const REMOTE_MARKETPLACE={json.dumps(REMOTE_MARKETPLACE)};"
                  f"const REMOTE_DIR={json.dumps(REMOTE_PLUGIN_DIR)};"
                  f"const plugin={json.dumps(str(self.plugin))};"
                  "const out=[];"
                  "const check=(name,value,expected)=>{const ok=JSON.stringify(value)===JSON.stringify(expected);"
                  "out.push({name,ok,value});};")
        return json.loads(self.run_node(prefix + body + "console.log(JSON.stringify(out));"))

    def test_runtime_contracts(self):
        report = self.node_json(
            "check('manifestFiles',compat.manifestFiles(['.ccode-plugin/plugin.json']),"
            "['.ccode-plugin/plugin.json',REMOTE_DIR+'/plugin.json']);"
            "check('manifestAt',compat.manifestAt(plugin),true);"
            "check('acceptOfficialName',compat.acceptOfficialName(REMOTE_MARKETPLACE),true);"
            "check('rejectForeign',compat.acceptOfficialName('evil-marketplace'),false);"
            "const manifest={name:REMOTE_MARKETPLACE,raw:{name:REMOTE_MARKETPLACE}};"
            "compat.adoptOfficialName(manifest,'ccode-plugins-official');"
            "check('adopted',[manifest.name,manifest.raw.name],['ccode-plugins-official','ccode-plugins-official']);"
            "const ctx={loaded:{rootPath:'/root',id:'blender@ccode-plugins-official',name:'blender'},"
            "dataPath:'/data',workingDirectory:'/work'};"
            "check('remoteVar',compat.resolveRemoteVar(REMOTE_DIR.toUpperCase().slice(1)+'X',ctx),undefined);"
            "check('pluginRoot',compat.resolveRemoteVar('ZCODE_PLUGIN_ROOT',ctx),'/root');"
            "check('projectDir',compat.resolveRemoteVar('ZCODE_PROJECT_DIR',ctx),'/work');"
            "check('localVarUntouched',compat.resolveRemoteVar('CCODE_PLUGIN_ROOT',ctx),undefined);"
            "check('envAliases',Object.keys(compat.envAliases({rootPath:'/root',dataPath:'/data',id:'i',name:'n',workingDirectory:'/work'})).sort().join(','),"
            "'ZCODE_PLUGIN_DATA,ZCODE_PLUGIN_ID,ZCODE_PLUGIN_NAME,ZCODE_PLUGIN_ROOT,ZCODE_PROJECT_DIR');"
            "check('textNoUrl',compat.localizeText('Official ZCode plugins marketplace for ZCode'),"
            "'Official CCode plugins marketplace for CCode');"
            "check('mixedCase',compat.localizeText('Zcode MCP App Dev'),'Ccode MCP App Dev');"
            "check('lowerCase',compat.localizeText('zcode plugin'),'ccode plugin');"
            "check('urlKept',compat.localizeText('https://cdn-zcode.z.ai/zcode/official-plugin/assets'),"
            "'https://cdn-zcode.z.ai/zcode/official-plugin/assets');"
        )
        self.assertEqual([item['name'] for item in report if not item['ok']], [])

    def test_payload_localization_is_idempotent(self):
        report = self.node_json(
            "const first=compat.localizePluginTree(plugin);"
            "const second=compat.localizePluginTree(plugin);"
            "const manifest=JSON.parse(require('node:fs').readFileSync(plugin+'/'+REMOTE_DIR+'/plugin.json','utf8'));"
            "const skill=require('node:fs').readFileSync(plugin+'/skills/blender/SKILL.md','utf8');"
            "check('changedBoth',first,2);"
            "check('stable',second,0);"
            "check('description',manifest.description,'Edit Blender scenes with an interactive 3D panel and MCP tools.');"
            "check('author',manifest.author.name,'CCode');"
            "check('titleKeyed',manifest.userConfig.blenderPath.title,'Blender path');"
            "check('keyHumanized',manifest.userConfig.allowPython.title,'Allow python');"
            "check('emptyLabelKeyed',manifest.userConfig.engineDownloadDir.title,'Engine download dir');"
            "check('chineseDescriptionDropped',manifest.userConfig.blenderPath.description,undefined);"
            "check('translationKept',manifest.description_i18n['zh-CN'],'在 ZCode 对话旁打开 Blender 场景。');"
            "check('surfaceUntouched',manifest.ui.surfaces[0].title['en-US'],'Blender');"
            "check('skillEnglish',/^---\\nname: blender\\ndescription: \"Edit Blender scenes/.test(skill),true);"
            "check('skillBodyKept',skill.includes('# Blender 插件'),true);"
            "check('noCjkInSkillDescription',/[\\u4e00-\\u9fff]/.test(skill.split('---')[1]),false);"
        )
        self.assertEqual([item['name'] for item in report if not item['ok']], [])

    def test_payload_localization_keeps_local_manifest_and_missing_payloads(self):
        report = self.node_json(
            "const fs=require('node:fs');"
            "const path=require('node:path');"
            "const local=path.join(path.dirname(plugin),'local-plugin');"
            "fs.mkdirSync(local+'/.ccode-plugin',{recursive:true});"
            "fs.writeFileSync(local+'/.ccode-plugin/plugin.json',JSON.stringify({name:'plain',description:'Plain plugin'}));"
            "check('untouched',compat.localizePluginTree(local),0);"
            "check('missingRoot',compat.localizeResolved({path:local+'/absent'}),{path:local+'/absent'});"
        )
        self.assertEqual([item['name'] for item in report if not item['ok']], [])

    def test_bundled_skill_descriptions_lose_the_chinese_tokens(self):
        expected = {
            'documents-plugin/skills/docx/SKILL.md': "'export this docx as PDF/images'",
            'pdf-plugin/skills/pdf/SKILL.md': "'save/export as PDF'",
            'presentations-plugin/skills/pptx/SKILL.md': "'turn these slides into a PDF'",
            'spreadsheets-plugin/skills/xlsx/SKILL.md': "'export as CSV'",
        }
        script = ("const compat=require(%s);const fs=require('node:fs');const out=[];"
                  "for (const [file,marker] of Object.entries(%s)) {"
                  "const text=fs.readFileSync(%s+'/'+file,'utf8');"
                  "const value=/^description:\\s*(.*)$/m.exec(text)[1].replace(/^\"|\"$/g,'');"
                  "const cleaned=compat.deChineseDescription(value,null);"
                  "out.push({file,cjk:/[\\u4e00-\\u9fff]/.test(cleaned||''),keeps:!!cleaned&&cleaned.includes(marker),changed:cleaned!==value});}"
                  "console.log(JSON.stringify(out));" % (
                      json.dumps(str(self.runtime)), json.dumps(expected),
                      json.dumps(str(ROOT / 'app/resources/glm/packages'))))
        node = node_command()
        if not node:
            self.skipTest('node is unavailable')
        for row in json.loads(self.run_node(script)):
            self.assertFalse(row['cjk'], row['file'])
            self.assertTrue(row['keeps'], row['file'])
            self.assertTrue(row['changed'], row['file'])

    def test_published_descriptions_choose_the_english_variant(self):
        report = self.node_json(
            "check('chineseOnly',compat.deChineseDescription('在 CCode 对话旁打开 Blender 场景：修改物体与相机。','Edit Blender scenes.'),"
            "'Edit Blender scenes.');"
            "check('midSentenceKept',compat.deChineseDescription('Supports 中文 files with a fallback path.',null),null);"
            "check('englishKept',compat.deChineseDescription('Edit Blender scenes.',null),null);"
        )
        self.assertEqual([item['name'] for item in report if not item['ok']], [])

    def test_entry_localization_normalizes_display_text_only(self):
        report = self.node_json(
            "const entry={name:'blender',displayName:'Blender',description:'Official ZCode plugin',"
            "author:{name:'ZCode',url:'https://z.ai'},description_i18n:{en:'Edit scenes in ZCode'},"
            "icon:'https://cdn-zcode.z.ai/zcode/official-plugin/assets/blender/icon.png',skills:{blender:{description:'ZCode skill'}}};"
            "compat.localizeEntry(entry);"
            "check('description',entry.description,'Official CCode plugin');"
            "check('author',entry.author.name,'CCode');"
            "check('authorUrl',entry.author.url,'https://z.ai');"
            "check('i18n',entry.description_i18n.en,'Edit scenes in CCode');"
            "check('icon',entry.icon,'https://cdn-zcode.z.ai/zcode/official-plugin/assets/blender/icon.png');"
            "check('skill',entry.skills.blender.description,'CCode skill');"
            "check('name',entry.name,'blender');"
            "const named={name:'zcode-mcp-app-dev',description:'Develop apps'};"
            "compat.localizeEntry(named);"
            "check('derivedDisplayName',named.displayName,'ccode-mcp-app-dev');"
        )
        self.assertEqual([item['name'] for item in report if not item['ok']], [])


class PatchTests(unittest.TestCase):
    def test_patch_targets_the_shipped_agent(self):
        patched = marketplace.patch_agent(shipped_agent())
        for marker in ('ccodePluginCompat.acceptOfficialName(o.manifest.name)',
                       'ccodePluginCompat.manifestFiles([o8s,i8s,s8s])',
                       'ccodePluginCompat.manifestAt(e)',
                       'ccodePluginCompat.resolveRemoteVar(s,t)',
                       'ccodePluginCompat.localizeResolved(await ictResolved(e))',
                       'ccodePluginCompat.localizeManifestEntries(e)',
                       'function OJr(e){ccodePluginCompat.localizeManifestEntries(e);if(q8s(e))return e;'):
            self.assertIn(marker, patched)
        self.assertIn('const ccodePluginCompat=require("../marketplace/marketplace-compat.cjs");', patched)
        self.assertNotIn(REMOTE_MARKETPLACE, patched)
        self.assertNotIn(REMOTE_PLUGIN_DIR, patched)

    def test_patched_agent_is_valid_javascript(self):
        node = node_command()
        if not node:
            self.skipTest('node is unavailable')
        patched = marketplace.patch_agent(shipped_agent())
        with tempfile.TemporaryDirectory() as directory:
            target = pathlib.Path(directory) / 'ccode.cjs'
            target.write_text(patched)
            subprocess.run([node, '--check', str(target)], check=True)

    def test_anchors_are_unique(self):
        baseline = shipped_agent()
        marketplace.patch_agent(baseline)
        for anchor, _ in marketplace.PATCHES:
            with self.assertRaises(ValueError):
                marketplace.patch_agent(baseline * 2 if anchor == marketplace.RESOLVE_ANCHOR else baseline + anchor)

    def test_runtime_holds_only_the_derived_contracts(self):
        for placeholder, local in marketplace.PLACEHOLDERS:
            self.assertNotIn(placeholder, RUNTIME)
            self.assertIn(rebrand.previous(local), RUNTIME)
        probe = RUNTIME
        for _, local in marketplace.PLACEHOLDERS:
            probe = probe.replace(rebrand.previous(local), '')
        self.assertEqual(rebrand.leftover(probe), [])


if __name__ == '__main__':
    unittest.main()
