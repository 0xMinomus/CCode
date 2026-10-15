import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from local_only import default_commands

SEED_MODULE = ROOT / 'src/main/commands.cjs'
CATEGORY_MODULE = ROOT / 'src/renderer/default-commands.js'
COMMAND_SOURCES = ROOT / 'src/commands'


class DefaultCommandTests(unittest.TestCase):
    def node(self, script, *arguments):
        return subprocess.run(['node', '-e', script, *map(str, arguments)], check=True,
                              capture_output=True, text=True, cwd=ROOT).stdout.strip()

    def seed(self, storage, resources):
        script = ('const {seedDefaultCommands}=require(process.argv[1]);'
                  'process.stdout.write(JSON.stringify(seedDefaultCommands({storageDir:process.argv[2],resourceDir:process.argv[3]})));')
        return json.loads(self.node(script, SEED_MODULE, storage, resources))

    def test_seeding_updates_only_unchanged_defaults_and_respects_deletions(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            resources = root / 'defaults'
            shutil.copytree(COMMAND_SOURCES, resources)
            storage = root / 'storage'
            commands = storage / 'commands'
            commands.mkdir(parents=True)
            custom = commands / 'review.md'
            custom.write_text('user command\n')

            first = self.seed(storage, resources)
            self.assertEqual(first['seeded'], 11)
            self.assertEqual(custom.read_text(), 'user command\n')
            expected = sorted(path.name for path in COMMAND_SOURCES.glob('*.md'))
            self.assertEqual(sorted(path.name for path in commands.glob('*.md')), expected)

            prd = commands / 'prd.md'
            (resources / 'prd.md').write_text((resources / 'prd.md').read_text() + '\nUpdated default.\n')
            self.assertEqual(self.seed(storage, resources)['updated'], 1)
            self.assertTrue(prd.read_text().endswith('Updated default.\n'))

            design = commands / 'design.md'
            design.write_text('user-edited command\n')
            (resources / 'design.md').write_text((resources / 'design.md').read_text() + '\nNew default.\n')
            self.seed(storage, resources)
            self.assertEqual(design.read_text(), 'user-edited command\n')

            deleted = commands / 'task-plan.md'
            deleted.unlink()
            self.seed(storage, resources)
            self.assertFalse(deleted.exists())

    def test_invalid_marker_fails_closed_before_changing_commands(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            resources = root / 'defaults'
            shutil.copytree(COMMAND_SOURCES, resources)
            storage = root / 'storage'
            self.seed(storage, resources)
            commands = storage / 'commands'
            before = (commands / 'prd.md').read_bytes()
            marker = commands / '.ccode-default-commands.json'
            marker.write_text('{"version": 999, "commands": {}}\n')
            script = ('const {seedDefaultCommands}=require(process.argv[1]);'
                      'seedDefaultCommands({storageDir:process.argv[2],resourceDir:process.argv[3]});')
            result = subprocess.run(['node', '-e', script, str(SEED_MODULE), str(storage), str(resources)],
                                    capture_output=True, text=True, cwd=ROOT)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual((commands / 'prd.md').read_bytes(), before)

    def test_ui_groups_default_names_and_keeps_user_commands(self):
        script = ('const fs=require("node:fs");const mod={exports:{}};'
                  'new Function("module","exports",fs.readFileSync(process.argv[1],"utf8"))(mod,mod.exports);'
                  'const {CCodeDefaultCommandGroups}=mod.exports;'
                  'const items=[{name:"/security-review"},{name:"prd.md"},'
                  '{filePath:"/user/commands/design.md"},{name:"custom-command"},'
                  '{name:"tech-spec"},{name:"review"}];'
                  'process.stdout.write(JSON.stringify(CCodeDefaultCommandGroups(items).map(group=>({'
                  'title:group.title,names:group.items.map(item=>item.name??item.filePath)}))));')
        groups = json.loads(self.node(script, CATEGORY_MODULE))
        self.assertEqual([group['title'] for group in groups], ['Documents', 'Quality', 'Custom'])
        self.assertEqual(groups[0]['names'], ['prd.md', '/user/commands/design.md', 'tech-spec'])
        self.assertEqual(groups[1]['names'], ['/security-review', 'review'])
        self.assertEqual(groups[2]['names'], ['custom-command'])

    def test_slash_catalog_merges_enabled_commands_after_native_refresh(self):
        script = ('const fs=require("node:fs");const mod={exports:{}};'
                  'new Function("module","exports",fs.readFileSync(process.argv[1],"utf8"))(mod,mod.exports);'
                  'const {CCodeMergeSlashCommands}=mod.exports;'
                  'const commands=CCodeMergeSlashCommands('
                  '[{name:"goal",source:"builtin"},{name:"stale",source:"custom"}],'
                  '[{name:"design",description:"Write a design spec",argumentHint:"<request>",enabled:true},'
                  '{name:"disabled",enabled:false},{name:"goal",enabled:true},'
                  '{name:"/design",description:"Duplicate",enabled:true}]);'
                  'process.stdout.write(JSON.stringify(commands));')
        commands = json.loads(self.node(script, CATEGORY_MODULE))
        self.assertEqual([command['name'] for command in commands], ['goal', 'design'])
        self.assertEqual(commands[1], {
            'name': 'design',
            'description': 'Write a design spec',
            'inputHint': '/design <request>',
            'source': 'custom',
        })


    def test_all_packaged_defaults_have_a_category(self):
        script = ('const fs=require("node:fs");const mod={exports:{}};'
                  'new Function("module","exports",fs.readFileSync(process.argv[1],"utf8"))(mod,mod.exports);'
                  'const {CCodeDefaultCommandGroups}=mod.exports;'
                  'const names=fs.readdirSync(process.argv[2]).filter(file=>file.endsWith(".md")).map(file=>file.slice(0,-3));'
                  'process.stdout.write(JSON.stringify(CCodeDefaultCommandGroups(names.map(name=>({name}))).map(group=>'
                  '({title:group.title,names:group.items.map(item=>item.name)}))));')
        groups = json.loads(self.node(script, CATEGORY_MODULE, COMMAND_SOURCES))
        self.assertEqual([(group['title'], len(group['names'])) for group in groups],
                         [('Documents', 6), ('Development', 3), ('Quality', 3)])


if __name__ == '__main__':
    unittest.main()
