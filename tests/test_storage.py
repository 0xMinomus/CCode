"""CCode modification: standalone namespace selection across desktop platforms."""
import json
import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from local_only import storage


class StandaloneNamespaceTests(unittest.TestCase):
    def test_platform_defaults_and_explicit_override_keep_all_paths_isolated(self):
        cases = [
            ('linux', {}, '/users/test/.local/share/ccode'),
            ('win32', {'LOCALAPPDATA': r'C:\Users\Test\AppData\Local'}, r'C:\Users\Test\AppData\Local\CCode'),
            ('win32', {}, r'C:\Users\Test\AppData\Local\CCode'),
            ('win32', {'CCODE_STANDALONE_ROOT': r'D:\isolated'}, r'D:\isolated'),
        ]
        for platform, environment, expected in cases:
            with self.subTest(platform=platform, environment=environment):
                script = '''const vm=require('node:vm'),path=require('node:path');
const platform=JSON.parse(process.argv[1]),env=JSON.parse(process.argv[2]);
const context={process:{platform,env},ccodeStandalonePath:platform==='win32'?path.win32:path.posix,
ccodeStandaloneOs:{homedir:()=>platform==='win32'?'C:\\\\Users\\\\Test':'/users/test'}};
vm.runInNewContext(JSON.parse(process.argv[3]),context);
console.log(JSON.stringify(env));'''
                result = json.loads(subprocess.check_output(
                    ['node', '-e', script, json.dumps(platform), json.dumps(environment), json.dumps(storage._ENV_BODY)], text=True))
                self.assertEqual(result['CCODE_STANDALONE_ROOT'], expected)
                separator = '\\' if platform == 'win32' else '/'
                self.assertEqual(result['CCODE_STORAGE_DIR'], expected + separator + 'data' + separator + '.ccode')
                self.assertEqual(result['CCODE_DESKTOP_USER_DATA_DIR'], expected + separator + 'electron')
                self.assertEqual(result['CCODE_SESSION_DB_PATH'], result['CCODE_STORAGE_DIR'] + separator + 'cli' + separator + 'db' + separator + 'db.sqlite')
