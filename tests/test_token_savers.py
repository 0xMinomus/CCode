import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
RUNTIME = ROOT / 'src/main/token-savers-runtime.cjs'
MAIN = ROOT / 'src/main/token-savers.cjs'
PANEL = ROOT / 'src/renderer/token-savers-panel.js'
NODE = shutil.which('node')


def run_node(script, extra_env=None):
    if NODE is None:
        raise unittest.SkipTest('node is unavailable')
    env = dict(os.environ)
    env.update(extra_env or {})
    result = subprocess.run([NODE, '-e', script], capture_output=True, text=True, env=env, timeout=30)
    if result.returncode != 0:
        raise AssertionError(f'node failed: {result.stderr.strip()}')
    return json.loads(result.stdout)


class TokenSaversSettingsTests(unittest.TestCase):
    def test_defaults_are_off_and_settings_persist_in_the_standalone_namespace(self):
        with tempfile.TemporaryDirectory() as folder:
            script = f'''const a=require({json.dumps(str(RUNTIME))});
const assert=require('node:assert/strict');
assert.deepEqual(a.readSettings(),a.defaultSettings());
const input={{version:1,rtk:{{enabled:true}},caveman:{{enabled:true,level:'ultra'}},ponytail:{{enabled:false,level:'lite'}}}};
const saved=a.writeSettings(input);
assert.deepEqual(a.readSettings(),input);
console.log(JSON.stringify({{saved,path:a.settingsPath()}}));'''
            data_root = pathlib.Path(folder) / 'data'
            result = run_node(script, {'CCODE_DATA_BASE_DIR': str(data_root)})
            expected = data_root / '.ccode/v2/token-savers.json'
            self.assertEqual(pathlib.Path(result['path']), expected)
            self.assertEqual(result['saved']['caveman'], {'enabled': True, 'level': 'ultra'})
            self.assertEqual(expected.stat().st_mode & 0o777, 0o600)

    def test_prompt_modes_are_opt_in_and_preserve_existing_instructions(self):
        with tempfile.TemporaryDirectory() as folder:
            script = f'''const a=require({json.dumps(str(RUNTIME))});
const assert=require('node:assert/strict');
const env={{...process.env,CCODE_DATA_BASE_DIR:{json.dumps(folder)}}};
const original={{content:'Workspace rules',bytesRead:14,sources:[{{fileName:'AGENTS.md'}}]}};
assert.equal(a.applyPromptModes(original,env),original);
a.writeSettings({{rtk:{{enabled:false}},caveman:{{enabled:true,level:'full'}},ponytail:{{enabled:true,level:'ultra'}}}},env);
const result=a.applyPromptModes(original,env);
assert.match(result.content,/Workspace rules/);
assert.match(result.content,/Caveman \\(full\\)/);
assert.match(result.content,/Ponytail \\(ultra\\)/);
assert.deepEqual(result.sources,original.sources);
assert.match(a.applyPromptModes(undefined,env).content,/Ponytail \\(ultra\\)/);
console.log(JSON.stringify({{content:result.content}}));'''
            output = run_node(script)
            self.assertIn('Workspace rules', output['content'])
            self.assertIn('Caveman (full)', output['content'])
            self.assertIn('Ponytail (ultra)', output['content'])

    def test_invalid_mode_is_rejected_before_a_write(self):
        with tempfile.TemporaryDirectory() as folder:
            script = f'''const a=require({json.dumps(str(RUNTIME))});
const assert=require('node:assert/strict');
assert.throws(()=>a.writeSettings({{rtk:{{enabled:false}},caveman:{{enabled:true,level:'max'}},ponytail:{{enabled:false,level:'full'}}}}),/level is invalid/);
console.log(JSON.stringify({{path:a.settingsPath()}}));'''
            result = run_node(script, {'CCODE_DATA_BASE_DIR': folder})
            self.assertFalse(pathlib.Path(result['path']).exists())


class TokenSaversRtkTests(unittest.TestCase):
    def test_rewrite_and_approval_follow_rtk_decisions(self):
        with tempfile.TemporaryDirectory() as folder:
            binary = pathlib.Path(folder) / 'rtk'
            binary.write_text('#!/bin/sh\ncase "$RTK_TEST_STATUS" in\n  0) printf "%s\\n" "rtk rg --smart-case"; exit 0 ;;\n  2) exit 2 ;;\n  3) printf "%s\\n" "rtk rg --smart-case"; exit 3 ;;\n  *) exit 1 ;;\nesac\n')
            binary.chmod(0o700)
            script = f'''const a=require({json.dumps(str(RUNTIME))});
const assert=require('node:assert/strict');
const env={{PATH:{json.dumps(folder)},HOME:{json.dumps(folder)},CCODE_DATA_BASE_DIR:{json.dumps(folder)},RTK_TEST_STATUS:'0'}};
a.writeSettings({{rtk:{{enabled:true}},caveman:{{enabled:false,level:'full'}},ponytail:{{enabled:false,level:'full'}}}},env);
(async()=>{{
 const input={{command:'rg report'}}, context={{toolCallId:'call-1'}};
 const allowed=await a.needsShellApproval(input,context,async(value,ctx)=>value===input&&ctx===context,{{cwd:{json.dumps(folder)},env}});
 const unchanged=await a.rewriteShellCommand('rg report',{{cwd:{json.dumps(folder)},env:{{...env,RTK_TEST_STATUS:'1'}}}});
 const unchangedInput={{command:'rg report'}};
 let approvalCalls=0;
 const unchangedApproval=await a.needsShellApproval(unchangedInput,context,async()=>{{approvalCalls++;return true;}},{{cwd:{json.dumps(folder)},env:{{...env,RTK_TEST_STATUS:'1'}}}});
 const statusTwo=await a.needsShellApproval({{command:'rm -rf target'}},context,false,{{cwd:{json.dumps(folder)},env:{{...env,RTK_TEST_STATUS:'2'}}}}).then(()=>null,error=>error.message);
 const statusThreeInput={{command:'rg report'}};
 const statusThree=await a.needsShellApproval(statusThreeInput,context,async()=>true,{{cwd:{json.dumps(folder)},env:{{...env,RTK_TEST_STATUS:'3'}}}});
 const disabledEnv={{...env,RTK_TEST_STATUS:'2',CCODE_DATA_BASE_DIR:{json.dumps(str(pathlib.Path(folder) / 'disabled'))}}};
 const disabled=await a.rewriteShellCommand('rm -rf target',{{cwd:{json.dumps(folder)},env:disabledEnv}});
 assert.equal(allowed,true);
 assert.equal(input.command,'rtk rg --smart-case');
 assert.equal(unchanged.kind,'unchanged');
 assert.equal(unchangedApproval,true);
 assert.equal(unchangedInput.command,'rg report');
 assert.equal(approvalCalls,1);
 assert.match(statusTwo,/unexpected shell-command status/);
 assert.equal(statusThree,true);
 assert.equal(statusThreeInput.command,'rtk rg --smart-case');
 assert.equal(disabled.kind,'unchanged');
 console.log(JSON.stringify({{allowed,input,unchanged,unchangedApproval,statusTwo,statusThree,statusThreeInput,disabled}}));
}})().catch(error=>{{console.error(error);process.exitCode=1}});'''
            results = run_node(script)
            self.assertEqual(results['input']['command'], 'rtk rg --smart-case')
            self.assertEqual(results['unchanged']['kind'], 'unchanged')
            self.assertTrue(results['unchangedApproval'])
            self.assertEqual(results['statusTwo'], 'RTK returned an unexpected shell-command status.')
            self.assertTrue(results['statusThree'])
            self.assertEqual(results['statusThreeInput']['command'], 'rtk rg --smart-case')
            self.assertEqual(results['disabled']['kind'], 'unchanged')

    def test_main_ipc_persists_settings_and_returns_local_rtk_analytics(self):
        with tempfile.TemporaryDirectory() as folder:
            binary = pathlib.Path(folder) / 'rtk'
            binary.write_text('#!/bin/sh\nif [ "$1" = "gain" ]; then printf "%s\\n" \'{"summary":{"total_saved":5},"daily":[{"date":"2025-01-01","saved_tokens":5}]}\' ; exit 0; fi\nexit 1\n')
            binary.chmod(0o700)
            script = f'''const main=require({json.dumps(str(MAIN))});
const assert=require('node:assert/strict');
const handlers=new Map();
main.register({{ipcMain:{{handle:(channel,handler)=>handlers.set(channel,handler)}}}});
(async()=>{{
 const frame={{url:'file:///tmp/out/renderer/index.html'}};
 const trusted={{senderFrame:frame,sender:{{mainFrame:frame}}}};
 const untrusted={{senderFrame:{{url:frame.url}},sender:{{mainFrame:{{url:frame.url}}}}}};
 const settings={{version:1,rtk:{{enabled:true}},caveman:{{enabled:false,level:'full'}},ponytail:{{enabled:true,level:'lite'}}}};
 await assert.rejects(()=>handlers.get('ccode-token-savers:save')(untrusted,settings),/only available/);
 const saved=await handlers.get('ccode-token-savers:save')(trusted,settings);
 const data=await handlers.get('ccode-token-savers:snapshot')(trusted);
 assert.deepEqual(saved,settings);
 assert.deepEqual(data.settings,settings);
 assert.equal(data.rtk.totalSaved,5);
 assert.deepEqual(data.rtk.daily,[{{day:'2025-01-01',savedTokens:5}}]);
 console.log(JSON.stringify({{settings:data.settings,totalSaved:data.rtk.totalSaved,daily:data.rtk.daily}}));
}})().catch(error=>{{console.error(error);process.exitCode=1}});'''
            result = run_node(script, {
                'PATH': folder,
                'HOME': folder,
                'CCODE_DATA_BASE_DIR': str(pathlib.Path(folder) / 'data'),
            })
            self.assertEqual(result['settings']['ponytail'], {'enabled': True, 'level': 'lite'})
            self.assertEqual(result['totalSaved'], 5)
            self.assertEqual(result['daily'], [{'day': '2025-01-01', 'savedTokens': 5}])

    def test_analytics_parser_and_chart_cover_thirty_days_across_year_boundary(self):
        script = f'''const r=require({json.dumps(str(RUNTIME))});
const fs=require('node:fs'), panel={{exports:{{}}}};
new Function('module',fs.readFileSync({json.dumps(str(PANEL))},'utf8'))(panel);
const p=panel.exports, assert=require('node:assert/strict');
const data=r.parseRtkAnalytics({{summary:{{total_saved:7}},daily:[
 {{date:'2025-12-31',saved_tokens:4}},{{date:'2025-12-31',saved_tokens:2}},{{date:'2026-01-02',saved_tokens:1}},
 {{date:'2026-02-30',saved_tokens:99}},{{date:'2026-01-01',saved_tokens:-5}}
]}});
const chart=p.CCodeTokenSaversChartSeries(data.daily,'2026-01-02');
assert.equal(chart.length,30);
assert.equal(chart[0].day,'2025-12-04');
assert.equal(chart[27].savedTokens,6);
assert.equal(chart[28].savedTokens,0);
assert.equal(chart[29].savedTokens,1);
assert.equal(data.totalSaved,7);
console.log(JSON.stringify({{first:chart[0],last:chart[29],total:chart.reduce((sum,row)=>sum+row.savedTokens,0)}}));'''
        result = run_node(script)
        self.assertEqual(result, {'first': {'day': '2025-12-04', 'savedTokens': 0},
                                  'last': {'day': '2026-01-02', 'savedTokens': 1}, 'total': 7})


if __name__ == '__main__':
    unittest.main()
