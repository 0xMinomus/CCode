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
INSTALLER = ROOT / 'src/main/rtk-installer.cjs'
NODE = shutil.which('node')

RTK_STUBS = {
    'posix': {
        'status': '#!/bin/sh\ncase "$RTK_TEST_STATUS" in\n  0) printf "%s\\n" "rtk rg --smart-case"; exit 0 ;;\n  2) exit 2 ;;\n  3) printf "%s\\n" "rtk rg --smart-case"; exit 3 ;;\n  *) exit 1 ;;\nesac\n',
        'gain': '#!/bin/sh\nif [ "$1" = "gain" ]; then printf "%s\\n" \'{"summary":{"total_saved":5},"daily":[{"date":"2025-01-01","saved_tokens":5}]}\' ; exit 0; fi\nexit 1\n',
    },
    'win32': {
        'status': '@echo off\r\nif "%RTK_TEST_STATUS%"=="0" (\r\n  echo rtk rg --smart-case\r\n  exit /b 0\r\n)\r\nif "%RTK_TEST_STATUS%"=="3" (\r\n  echo rtk rg --smart-case\r\n  exit /b 3\r\n)\r\nif "%RTK_TEST_STATUS%"=="2" exit /b 2\r\nexit /b 1\r\n',
        'gain': '@echo off\r\nif not "%~1"=="gain" exit /b 1\r\necho {"summary":{"total_saved":5},"daily":[{"date":"2025-01-01","saved_tokens":5}]}\r\nexit /b 0\r\n',
    },
}


def write_rtk_stub(folder, kind):
    if os.name == 'nt':
        binary = pathlib.Path(folder) / 'rtk.cmd'
        binary.write_text(RTK_STUBS['win32'][kind])
    else:
        binary = pathlib.Path(folder) / 'rtk'
        binary.write_text(RTK_STUBS['posix'][kind])
        binary.chmod(0o700)
    return binary


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
            if os.name == 'nt':
                self.skipTest('POSIX file mode 0o600 is not reported on Windows')
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
            write_rtk_stub(folder, 'status')
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
            write_rtk_stub(folder, 'gain')
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
 await assert.rejects(()=>handlers.get('ccode-token-savers:install-rtk')(untrusted),/only available/);
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

class TokenSaversInstallTests(unittest.TestCase):
    def test_tampered_download_never_extracts_or_enables_and_can_retry(self):
        with tempfile.TemporaryDirectory() as folder:
            script = f'''const r=require({json.dumps(str(RUNTIME))}), i=require({json.dumps(str(INSTALLER))});
const fs=require('node:fs'),assert=require('node:assert/strict');
const env={{PATH:'',HOME:{json.dumps(folder)},USERPROFILE:{json.dumps(folder)},CCODE_DATA_BASE_DIR:{json.dumps(folder)}}};
const runtime={{...r,resolveRtkPath:()=>null}};
(async()=>{{
 let downloads=0,extractions=0;
 const options={{runtime,env,platform:'win32',arch:'x64',download:async()=>{{downloads++;return Buffer.from('tampered')}},extract:async()=>{{extractions++}}}};
 const first=i.installRtk(options),same=i.installRtk(options);
 assert.equal(first,same);
 await assert.rejects(first,/SHA256 verification failed/);
 await assert.rejects(i.installRtk(options),/SHA256 verification failed/);
 assert.equal(downloads,2);assert.equal(extractions,0);
 assert.equal(r.readSettings(env).rtk.enabled,false);
 assert.deepEqual(fs.readdirSync(r.managedRtkRoot(env)),[]);
 await assert.rejects(i.installRtk({{...options,platform:'darwin'}}),/Windows x64 and Linux x64 only/);
 console.log(JSON.stringify({{downloads,extractions}}));
}})().catch(error=>{{console.error(error);process.exitCode=1}});'''
            self.assertEqual(run_node(script), {'downloads': 2, 'extractions': 0})

    def test_managed_install_checks_contracts_before_atomic_activation_and_enables(self):
        with tempfile.TemporaryDirectory() as folder:
            script = f'''const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),crypto=require('node:crypto');
const assert=require('node:assert/strict'),r=require({json.dumps(str(RUNTIME))});
const real=require({json.dumps(str(INSTALLER))}), release=real.RELEASES[process.platform+'-x64'];
const env={{PATH:'',HOME:{json.dumps(folder)},USERPROFILE:{json.dumps(folder)},CCODE_DATA_BASE_DIR:{json.dumps(folder)}}};
const payload=Buffer.alloc(release.size),binary=Buffer.from('fake binary'),license=Buffer.from('fake license');
// Only transport and executable boundaries are simulated; filesystem activation remains real.
const moduleObject={{exports:{{}}}};
const localRequire=name=>name==='node:crypto'?{{...crypto,createHash:()=>{{let bytes;return{{update(value){{bytes=value;return this}},digest(){{return bytes===payload?release.sha256:bytes.equals(binary)?release.binarySha256:release.licenseSha256}}}}}}}}:require(name);
vm.runInNewContext(fs.readFileSync({json.dumps(str(INSTALLER))},'utf8'),{{require:localRequire,module:moduleObject,process,Buffer,URL,setTimeout,clearTimeout}});
const i=moduleObject.exports,calls=[];let contractFailure=false;
const runtime={{...r,resolveRtkPath:()=>null,runRtk:async(args,options)=>{{
 calls.push(args.join(' '));
 assert.equal(fs.existsSync(path.join(r.managedRtkRoot(env),'current.json')),false);
 if(args[0]==='--version')return{{code:0,stdout:'rtk 1.0.1'}};
 if(args[0]==='rewrite')return args[1]==='git status'?{{code:contractFailure?2:3,stdout:'rtk git status'}}:{{code:1,stdout:''}};
 return{{code:0,stdout:'{{"summary":{{"total_saved":0}},"daily":[]}}'}};
}}}};
const options={{runtime,env,download:async()=>payload,extract:async(archive,destination)=>{{
 assert.equal(fs.existsSync(archive),true);
 fs.writeFileSync(path.join(destination,release.binary),binary);fs.writeFileSync(path.join(destination,'LICENSE'),license);
}}}};
(async()=>{{
 contractFailure=true;await assert.rejects(i.installRtk(options),/rewrite contract/);
 assert.deepEqual(fs.readdirSync(r.managedRtkRoot(env)),[]);assert.equal(r.readSettings(env).rtk.enabled,false);
 contractFailure=false;calls.length=0;
 const settings=await i.installRtk(options);
 assert.equal(settings.rtk.enabled,true);assert.equal(r.readSettings(env).rtk.enabled,true);
 const installed=r.managedRtkPath(env);assert.ok(installed);assert.equal(fs.readFileSync(installed,'utf8'),'fake binary');
 assert.deepEqual(calls,['--version','rewrite git status','rewrite ccode-rtk-contract-no-match','gain --daily --format json']);
 const userBin=path.join({json.dumps(folder)},'bin');fs.mkdirSync(userBin);
 const userExecutable=path.join(userBin,process.platform==='win32'?'rtk.exe':'rtk');fs.writeFileSync(userExecutable,'user');fs.chmodSync(userExecutable,0o700);
 env.PATH=[path.dirname(installed),userBin].join(path.delimiter);
 assert.equal(r.resolveRtkPath(env),userExecutable);
 assert.equal(env.PATH.split(path.delimiter)[0],path.dirname(installed));
 console.log(JSON.stringify({{enabled:settings.rtk.enabled,calls:calls.length}}));
}})().catch(error=>{{console.error(error);process.exitCode=1}});'''
            self.assertEqual(run_node(script), {'enabled': True, 'calls': 4})

    def test_release_pins_are_literal_values(self):
        script = f'''const i=require({json.dumps(str(INSTALLER))});
const releases=Object.fromEntries(Object.entries(i.RELEASES).map(([key,value])=>[key,{{name:value.name,size:value.size,sha256:value.sha256,binary:value.binary,binarySha256:value.binarySha256,licenseSha256:value.licenseSha256}}]));
console.log(JSON.stringify({{version:i.VERSION,releases}}));'''
        pinned = run_node(script)
        self.assertEqual(pinned['version'], '1.0.1')
        self.assertEqual(pinned['releases']['win32-x64'], {
            'name': 'rtk-oss-x86_64-pc-windows-msvc.zip', 'size': 5708680,
            'sha256': '0e53e2eca471e15fbd3636e64e6bc0b182cbc278ed0339c80450a2dd03f4cd6b',
            'binary': 'rtk.exe', 'binarySha256': '4346e25f54d4a4aaa39809d8384e59193d6646d8b008f9f9a90acaea5d6b37da',
            'licenseSha256': '0d4d6a722737b8a3f9bd40868011f8d6522650eb93b6f3c36bf780bb54210a5f'})
        self.assertEqual(pinned['releases']['linux-x64'], {
            'name': 'rtk-oss-x86_64-unknown-linux-musl.tar.gz', 'size': 5766270,
            'sha256': 'a44e8ffc43981100b4ddf1710399a1649a6c874591aa6d0c0727fe6cbd983c41',
            'binary': 'rtk', 'binarySha256': '38b915f2a52ce4b7ef7d6dc3966aaeccb9f754731b2933571bf85026bcba8677',
            'licenseSha256': '33f694a31d9f9df3e292a9413a3cdb0113fa72698e2c719f657ff6b53165dcc4'})

    def test_managed_rewrite_binds_path_inside_the_approved_command(self):
        with tempfile.TemporaryDirectory(prefix="ccode rtk '") as folder:
            managed = pathlib.Path(folder) / '.ccode/v2/tools/rtk'
            directory = managed / ('v1.0.1-oss-' + ('win32' if os.name == 'nt' else 'linux') + '-x64-abcdef')
            directory.mkdir(parents=True)
            write_rtk_stub(directory, 'status')
            # Windows production binary is .exe; inject only the executable resolver for the .cmd fixture.
            script = f'''const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const file={json.dumps(str(RUNTIME))},moduleObject={{exports:{{}}}};
const source=fs.readFileSync(file,'utf8').replace('const executable = resolveRtkPath(env);','const executable = env.RTK_TEST_EXECUTABLE;');
vm.runInNewContext(source,{{require,module:moduleObject,process,Buffer,setTimeout,clearTimeout}});
const r=moduleObject.exports;
const env={{PATH:'',HOME:{json.dumps(folder)},USERPROFILE:{json.dumps(folder)},CCODE_DATA_BASE_DIR:{json.dumps(folder)},RTK_TEST_STATUS:'3',RTK_TEST_EXECUTABLE:{json.dumps(str(directory / ('rtk.cmd' if os.name == 'nt' else 'rtk')))}}};
r.writeSettings({{rtk:{{enabled:true}},caveman:{{enabled:false,level:'full'}},ponytail:{{enabled:false,level:'full'}}}},env);
(async()=>{{
 const input={{command:'git status'}};let approved;
 const allowed=await r.needsShellApproval(input,{{}},async value=>{{approved=value.command;return false}},{{env}});
 assert.equal(allowed,false);assert.equal(approved,input.command);
 assert.ok(input.command.startsWith('export PATH='));assert.ok(input.command.endsWith(':"$PATH"; rtk rg --smart-case'));
 assert.ok(input.command.includes("'\\\\''"));assert.equal(env.PATH,'');
 console.log(JSON.stringify({{allowed,bound:true}}));
}})().catch(error=>{{console.error(error);process.exitCode=1}});'''
            self.assertEqual(run_node(script), {'allowed': False, 'bound': True})

    def test_existing_user_rtk_is_verified_without_downloading_or_replacing(self):
        with tempfile.TemporaryDirectory() as folder:
            script = f'''const r=require({json.dumps(str(RUNTIME))}),i=require({json.dumps(str(INSTALLER))});
const assert=require('node:assert/strict'),fs=require('node:fs');
const env={{CCODE_DATA_BASE_DIR:{json.dumps(folder)}}};
let calls=0;
const runtime={{...r,resolveRtkPath:()=>'/user/rtk',isManagedRtkPath:()=>false,runRtk:async(args)=>{{calls++;
 if(args[0]==='--version')return{{code:0,stdout:'rtk 0.51.0'}};
 if(args[0]==='rewrite')return args[1]==='git status'?{{code:3,stdout:'rtk git status'}}:{{code:1,stdout:''}};
 return{{code:0,stdout:'{{"daily":[]}}'}};
}}}};
(async()=>{{
 const settings=await i.installRtk({{runtime,env,download:()=>{{throw Error('must not download')}}}});
 assert.equal(settings.rtk.enabled,true);assert.equal(fs.existsSync(r.managedRtkRoot(env)),false);
 console.log(JSON.stringify({{calls}}));
}})().catch(error=>{{console.error(error);process.exitCode=1}});'''
            self.assertEqual(run_node(script), {'calls': 4})

    def test_contract_failures_do_not_enable_existing_rtk(self):
        with tempfile.TemporaryDirectory() as folder:
            script = f'''const r=require({json.dumps(str(RUNTIME))}),i=require({json.dumps(str(INSTALLER))});
const assert=require('node:assert/strict');
const env={{CCODE_DATA_BASE_DIR:{json.dumps(folder)}}};
(async()=>{{
 for(const bad of ['version','rewrite','no-match','gain']){{
  const runtime={{...r,resolveRtkPath:()=>'/user/rtk',isManagedRtkPath:()=>false,runRtk:async(args)=>{{
   if(args[0]==='--version')return{{code:0,stdout:bad==='version'?'not rtk':'rtk 1.0.1'}};
   if(args[0]==='rewrite'&&args[1]==='git status')return{{code:bad==='rewrite'?2:3,stdout:'rtk git status'}};
   if(args[0]==='rewrite')return{{code:1,stdout:bad==='no-match'?'unexpected':''}};
   return{{code:0,stdout:bad==='gain'?'not json':'{{"daily":[]}}'}};
  }}}};
  await assert.rejects(i.installRtk({{runtime,env}}));assert.equal(r.readSettings(env).rtk.enabled,false);
 }}
 console.log(JSON.stringify({{enabled:r.readSettings(env).rtk.enabled}}));
}})().catch(error=>{{console.error(error);process.exitCode=1}});'''
            self.assertEqual(run_node(script), {'enabled': False})

    def test_panel_install_loading_retry_and_enabled_toggle_use_native_slot(self):
        script = f'''const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const state=[],effects=[];let cursor=0,resolveInstall,rejectInstall,calls=0;
const settings={{version:1,rtk:{{enabled:false}},caveman:{{enabled:false,level:'full'}},ponytail:{{enabled:false,level:'full'}}}};
const api={{snapshot:async()=>({{settings,rtk:{{available:false,daily:[],error:'RTK is not installed.',installSupported:true}}}}),installRtk:()=>{{calls++;return new Promise((resolve,reject)=>{{resolveInstall=resolve;rejectInstall=reject}})}}}};
const Q={{useState:initial=>{{const index=cursor++;if(!(index in state))state[index]=initial;return[state[index],value=>{{state[index]=typeof value==='function'?value(state[index]):value}}]}},useEffect:effect=>{{if(!effects.length)effects.push(effect)}}}};
const jsx=(type,props)=>({{type,props}}),moduleObject={{exports:{{}}}};
vm.runInNewContext(fs.readFileSync({json.dumps(str(PANEL))},'utf8'),{{module:moduleObject,window:{{ccodeTokenSavers:api}},Q,$:{{jsx,jsxs:jsx}},Q1:'NativeGroup',Z1:'NativeRow',X:'NativeButton',Xx:'NativeToggle',uA:'NativeTooltip',Intl,Date,Map,Math,Number,String}});
const render=()=>{{cursor=0;return moduleObject.exports.CCodeTokenSaversPanel()}};
const nodes=tree=>Array.isArray(tree)?tree.flatMap(nodes):!tree||typeof tree!=='object'?[]:[tree,...nodes(tree.props?.control),...nodes(tree.props?.children)];
const find=(tree,testid)=>nodes(tree).find(node=>node.props?.['data-testid']===testid);
(async()=>{{
 render();effects[0]();await new Promise(setImmediate);
 let tree=render(),button=find(tree,'ccode-token-savers-rtk-install');
 assert.ok(button,'RTK Install must render after the initial asynchronous snapshot resolves');
 assert.equal(button.type,'NativeButton');assert.equal(button.props.children,'Install');
 assert.equal(find(tree,'ccode-token-savers-rtk-unavailable'),undefined);
 let pending=button.props.onClick();tree=render();button=find(tree,'ccode-token-savers-rtk-install');
 assert.equal(button.props.children,'Installing…');assert.equal(button.props.disabled,true);
 rejectInstall(Error('Download interrupted. Try again.'));await pending;
 tree=render();button=find(tree,'ccode-token-savers-rtk-install');assert.equal(button.props.children,'Retry');
 assert.equal(find(tree,'ccode-token-savers-install-error').props.role,'alert');
 pending=button.props.onClick();resolveInstall({{settings:{{...settings,rtk:{{enabled:true}}}},rtk:{{available:true,daily:[],error:null}}}});await pending;
 tree=render();assert.equal(find(tree,'ccode-token-savers-rtk-install'),undefined);
 const row=nodes(tree).find(node=>node.type==='NativeRow'&&node.props.label==='RTK');
 assert.equal(row.props.control.type,'NativeToggle');assert.equal(row.props.control.props.checked,true);
 assert.equal(calls,2);console.log(JSON.stringify({{calls,enabled:true}}));
}})().catch(error=>{{console.error(error);process.exitCode=1}});'''
        self.assertEqual(run_node(script), {'calls': 2, 'enabled': True})

    def test_preload_installer_patch_uses_unique_guarded_anchor(self):
        import sys
        sys.path.insert(0, str(ROOT / 'src'))
        from local_only import token_savers
        source = 'save:(settings)=>ipcRenderer.invoke("ccode-token-savers:save",settings)'
        patched = token_savers.patch_preload(source)
        self.assertIn('installRtk:()=>ipcRenderer.invoke("ccode-token-savers:install-rtk")', patched)
        with self.assertRaises(ValueError):
            token_savers.patch_preload('anchor missing')



if __name__ == '__main__':
    unittest.main()
