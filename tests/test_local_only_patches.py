import importlib
import json
import pathlib
import re
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
cloud = importlib.import_module('local_only.cloud')
plugins = importlib.import_module('local_only.plugins')


class ComputerUsePluginTests(unittest.TestCase):
    """The bundled Computer Use skill must drive the desktop MCP backends it ships with."""

    def test_the_skill_replaces_the_missing_runtime_with_the_mcp_loop(self):
        patched = plugins._patch(plugins.CUA_SKILL, plugins.CUA_SKILL_ANCHOR + '\n\nold body\n')
        self.assertIn('windows-desktop', patched)
        self.assertIn('linux-desktop', patched)
        self.assertIn('screen_read_text', patched)
        self.assertIn('Do not use', patched)
        self.assertIn('mcp__node_repl__js', patched)  # named only to forbid it
        self.assertNotIn('setupComputerUseRuntime', patched)
        with self.assertRaises(ValueError):
            plugins._patch(plugins.CUA_SKILL, 'a body without the pinned anchor')

    def test_the_plugin_doc_points_at_the_mcp_tools(self):
        patched = plugins._patch(plugins.CUA_DOC, 'original doc body\n')
        self.assertTrue(patched.startswith('> CCode ships this plugin'))
        self.assertIn('windows-desktop', patched)

    @unittest.skipUnless((plugins.BASELINE / plugins.CUA_SKILL).is_file(), 'pinned plugin baseline is not present')
    def test_the_pinned_skill_still_matches_the_rewrite_anchor(self):
        source = (plugins.BASELINE / plugins.CUA_SKILL).read_text()
        patched = plugins._patch(plugins.CUA_SKILL, source)
        self.assertTrue(patched.startswith('---\nname: computer-use\n'))
        self.assertNotIn('setupComputerUseRuntime', patched)


class SplitTopLevelTests(unittest.TestCase):
    def test_unicode_escape_inside_string_is_preserved(self):
        body = 'a("\\u5916\\u90E8"),b("\\u6253\\u5F00")'
        self.assertEqual(cloud._split_top_level(body), ['a("\\u5916\\u90E8")', 'b("\\u6253\\u5F00")'])

    def test_escaped_quote_and_nested_calls_stay_in_one_item(self):
        body = 'f("say \\"hi\\"",g(1,2)),h(`t${x}\\0y`)'
        self.assertEqual(cloud._split_top_level(body), ['f("say \\"hi\\"",g(1,2))', 'h(`t${x}\\0y`)'])

    def test_commas_inside_braces_do_not_split(self):
        self.assertEqual(cloud._split_top_level('a({x:1,y:2}),b'), ['a({x:1,y:2})', 'b'])


class DropRegistersTests(unittest.TestCase):
    def test_target_registers_are_removed_and_chain_kept(self):
        text = 'new R().register(keep,one()).register(drop,two({a:1})).register(keep2,three())'
        result = cloud.drop_registers(text, ('drop',))
        self.assertEqual(result, 'new R().register(keep,one()).register(keep2,three())')

    def test_nested_factory_arguments_are_removed_whole(self):
        text = 'x.register(drop,f({nested:g(1,2)},[3]))end'
        self.assertEqual(cloud.drop_registers(text, ('drop',)), 'xend')

    def test_other_symbols_are_untouched(self):
        text = 'x.register(keep,dropped)'
        self.assertEqual(cloud.drop_registers(text, ('drop',)), text)


class RemoteIpcTests(unittest.TestCase):
    body = ('function Ik(e){function t(){},"use strict",'
            'fe.on(k.OpenExternal,()=>{}),'
            'fe.handle(k.IsDockerAvailable,async()=>!0),'
            'fe.handle(k.ReportTelemetryEvent,async()=>{}),'
            'fe.on(k.RendererReady,()=>{}),'
            'fe.on(k.SyncTelemetryContext,()=>{}),'
            'Rk({reportRemoteUsageEvent:t,webRemoteControlManager:e.webRemoteControlManager}),'
            'fe.handle(k.ListSSHConfigAliases,async()=>[])}'
            's(Ik,"registerRemoteIpcHandlers");')

    def test_cloud_handlers_drop_and_local_handlers_stay(self):
        result = cloud._remote_ipc(self.body)
        self.assertIn('k.OpenExternal', result)
        self.assertIn('k.IsDockerAvailable', result)
        self.assertIn('k.ListSSHConfigAliases', result)
        self.assertNotIn('k.GetWebRemoteControlStatus', result)
        for dropped in ('k.RendererReady', 'Rk({reportRemoteUsageEvent'):
            self.assertNotIn(dropped, result)
        # The telemetry channel keeps exactly one local acknowledgement.
        self.assertEqual(result.count('k.ReportTelemetryEvent'), 1)
        self.assertEqual(result.count('k.SyncTelemetryContext'), 0)

    def test_result_has_no_comma_run_or_empty_call(self):
        result = cloud._remote_ipc(self.body)
        self.assertNotIn(',,', result)
        self.assertNotIn('(,,', result)

    def test_channels_without_owner_are_answered_locally(self):
        result = cloud._remote_ipc(self.body)
        for channel in ('k.ConnectRemote', 'k.CancelPendingRemoteConnection',
                        'k.BindRemoteWorkspaceSessionContext', 'k.DisposeRemoteSession',
                        'k.GetAutoUpdatePreferences', 'k.SetAutoDownloadAndInstallUpdates',
                        'k.OpenUpdateStatusWindow', 'k.AcknowledgePostUpdateReleaseNotes'):
            self.assertEqual(result.count('handle(' + channel + ','), 1, channel)
        self.assertIn('Remote connections are unavailable in the standalone build.', result)
        for removed in ('k.StartWebRemoteControl', 'k.StopWebRemoteControl', 'k.ResetWebRemoteControlPairing',
                        'k.GetWebRemoteControlStatus', 'Web remote control'):
            self.assertNotIn(removed, result)


class MainGuardTests(unittest.TestCase):
    def test_remaining_references_pass(self):
        text = ('const webRemoteControlManagerRef={current:null};webRemoteControlManagerRef.current?.x,'
                'reportEvent:async()=>{}')
        self.assertEqual(cloud.guard_main(text), text)

    def test_removed_bindings_and_call_sites_fail(self):
        for text in ('var Gr=1;Gr.syncAvailableWorkspaces()', 'jo.reportEvent({})',
                     'var Eg=1;Eg.init()', 'e.webRemoteControlManager?.disposeWindow(n)', 'webRemoteControlManager.disposeWindow(n)'):
            with self.assertRaises(ValueError):
                cloud.guard_main(text)

    def test_similar_names_are_not_flagged(self):
        text = 'Guardian=1;Egret();joins.join(",")'
        self.assertEqual(cloud.guard_main(text), text)

    def test_handler_dependency_gap_is_rejected(self):
        missing = 'function Ik(e){xa.handle(k.X,()=>e.helper())}s(Ik,"registerRemoteIpcHandlers");Ik({logger:w})'
        with self.assertRaises(ValueError):
            cloud.guard_remote_ipc_dependencies(missing)
        provided = 'function Ik(e){xa.handle(k.X,()=>e.helper())}s(Ik,"registerRemoteIpcHandlers");Ik({logger:w,helper:h})'
        self.assertEqual(cloud.guard_remote_ipc_dependencies(provided), provided)


class PatchedMainBundleTests(unittest.TestCase):
    """The removed services must leave no reachable reference in the built bundle."""
    baseline = ROOT / 'baselines' / 'ccode-3.14.5-original.asar'

    @classmethod
    def setUpClass(cls):
        if not cls.baseline.exists():
            raise unittest.SkipTest('pinned baseline asar is not present')
        sys.path.insert(0, str(ROOT / 'scripts'))
        from asar import Archive
        cls.text = cloud._main(Archive(cls.baseline).read('out/main/index.js').decode())

    def test_window_close_hook_has_no_remote_control_call(self):
        self.assertIn('window closed, killing host process', self.text)
        self.assertIsNone(re.search(r'(?<![\w$])webRemoteControlManager(?![\w$])', self.text),
                          'no bare manager reference remains (the Ref property is allowed)')

    def test_removed_service_and_telemetry_references_are_gone(self):
        self.assertNotIn('jo.reportEvent', self.text)
        for name in ('Rk', 'VP', 'zP', 'Eg', 'Gr', 'jo', 'webRemoteControlManager'):
            self.assertIsNone(re.search(r'(?<![\w$.])' + name + r'(?![\w$])', self.text), name)

    def test_local_inspection_providers_reach_the_handlers(self):
        for provider in ('isDockerDaemonAvailable:Gc', 'listAvailableWSLDistros:Kc',
                         'listAvailableDockerContainers:qc', 'listSSHConfigAliases:Zc'):
            self.assertIn(provider, self.text)


class HostServiceStubTests(unittest.TestCase):
    text = ('a.register(x,keep()).register(y,cloud({v:1})).register(y,remote.thing)'
            '.register(z,cloud2())')

    def test_stubbed_symbols_are_answered_and_dropped_ones_removed(self):
        result = cloud.apply_service_boundary(self.text, {'y': '{local:!0}'}, ('z',))
        self.assertEqual(result, 'a.register(x,keep()).register(y,{local:!0}).register(y,{local:!0})')

    def test_untouched_symbols_keep_their_chains(self):
        result = cloud.apply_service_boundary(self.text, {}, ('z',))
        self.assertEqual(result, 'a.register(x,keep()).register(y,cloud({v:1})).register(y,remote.thing)')


class PatchedHostBundleTests(unittest.TestCase):
    """Channels the local UI still reads must answer instead of timing out."""
    baseline = ROOT / 'baselines' / 'ccode-3.14.5-original.asar'

    @classmethod
    def setUpClass(cls):
        if not cls.baseline.exists():
            raise unittest.SkipTest('pinned baseline asar is not present')
        sys.path.insert(0, str(ROOT / 'scripts'))
        from asar import Archive
        cls.text = cloud._host(Archive(cls.baseline).read('out/host/index.js').decode())

    def test_cloud_services_are_stubbed_or_dropped(self):
        # Only the surfaces that stay local get a stub; usage stats and coding
        # plan went away with their UI, so their channels are unregistered.
        self.assertIn('.register(ea,{getSnapshot:async()=>({pluginStoreOrder:null})})', self.text)
        self.assertIn('.register(Dl,{list:async()=>({code:0,data:[]})})', self.text)
        self.assertIn('.register(Ol,{codingPlanProviderId:()=>Ot.bigmodelIndividualCodingPlan,', self.text)
        for symbol in ('eD', 'Rm', 'Ml', 'xl'):
            self.assertNotIn(f'.register({symbol},', self.text)
        for factory in ('.register(ea,e.', '.register(ea,q_(', '.register(Dl,e.', 'Lp({apiClient', '.register(xl,Dp(', '.register(Ol,mn)', '.register(Ol,g)'):
            self.assertNotIn(factory, self.text)

    def test_builtin_catalog_is_never_refreshed_from_the_account_endpoint(self):
        # The remote release is written over the active catalog cache, so a
        # standalone fetch could replace the patched catalog and costs a network
        # round trip on every provider-settings refresh.
        self.assertIn('refreshCCodeBuiltin(t){return Promise.resolve("skipped")}', self.text)
        self.assertIn('refresh(t={}){return Promise.resolve("skipped");', self.text)
        self.assertNotIn(cloud.BUILTIN_REFRESH_FACADE, self.text)
        self.assertNotIn(cloud.BUILTIN_REFRESH_SYNC, self.text)


class PatchedRendererBundleTests(unittest.TestCase):
    """Account surfaces and paid-plan labels are gone from the renderer."""
    baseline = ROOT / 'baselines' / 'ccode-3.14.5-original.asar'

    @classmethod
    def setUpClass(cls):
        if not cls.baseline.exists():
            raise unittest.SkipTest('pinned baseline asar is not present')
        sys.path.insert(0, str(ROOT / 'scripts'))
        from asar import Archive
        cls.text = cloud._renderer(Archive(cls.baseline).read('out/renderer/assets/styles-C4MhEMbW.js').decode())

    def test_draft_greeting_background_is_plain(self):
        # The faded CCode mark behind the draft greeting is replaced by a null child;
        # the greeting paragraph itself must stay in place.
        self.assertNotIn('children:(0,$.jsx)(Qgt,{className:`h-full w-full`})', self.text)
        self.assertIn('"data-v4-draft-greeting":`true`', self.text)
        self.assertIn('function Qgt({className:e})', self.text, 'the mark component stays defined for other callers')

    def test_paid_plan_badge_is_disabled(self):
        self.assertIn('function S6t({item:e}){let{intl:t}=q();return null;', self.text)

    def test_subscription_surfaces_are_deleted(self):
        # The two composer upgrade buttons are gone; the profile-menu plan/usage
        # section returns null before it can render or poll entitlements.
        self.assertNotIn('variant:`default`,size:`sm`,onClick:o,className:Z(d,`button-gradient gap-1.5', self.text)
        self.assertNotIn('size:`xs`,className:Z(`h-6 shrink-0 gap-1 px-2 text-ui-sm`', self.text)
        self.assertIn('function Qen({state:e,onUsageClick:t,onUpgradeClick:n}){return null;', self.text)

    def test_account_provider_families_are_emptied(self):
        self.assertIn('Q1e=[];new Map(Q1e.map(', self.text)
        self.assertIn('$1e=[];function e0e(e){', self.text)
        self.assertNotIn('displayName:`Z.ai`', self.text)
        self.assertNotIn('purchaseUrl:`https://z.ai/manage-apikey/subscription`', self.text)

    def test_provider_picker_has_no_zhipu_group(self):
        self.assertNotIn('{id:`zhipu`,templates:', self.text)
        self.assertIn('{id:`other`,templates:e.filter(e=>!u.includes(e.templateId))}', self.text)

    def test_usage_page_renders_the_local_activity_panel(self):
        self.assertIn('function Xwn({activeTab:e,providerSourcesLoading:t,workspaceIdentity:n,workspacePath:r,selectedCodingPlanSource:i}){return $.jsx(CCodeActivityPanel,{})}', self.text)
        self.assertNotIn('b===`usage`?(0,$.jsx)(YOn,', self.text, 'app/coding-plan tab bar is gone')

    def test_model_settings_navigation_has_no_account_preset_group(self):
        # The preset group is never filtered out when empty, so it must be dropped
        # from the navigation array instead of left waiting on an account source.
        self.assertIn("y=(0,Q.useMemo)(()=>[{id:`custom`,", self.text)
        self.assertNotIn('{id:`preset`,title:h.formatMessage({id:`settings.modelProvider.presetTitle`})', self.text)
        self.assertNotIn('settings.modelProvider.presetTitle', self.text)

    def test_custom_provider_group_survives(self):
        self.assertIn('items:g.map(e=>({key:G5(e.providerId),type:`custom`,label:tN(e),provider:e,statusActive:e.executable===!0}))}', self.text)

    def test_account_preset_loading_gate_is_pinned_off(self):
        self.assertNotIn('presetLoading:tt', self.text, 'no view receives the account loading source')
        self.assertIn('presetLoading:!1,customLoading:nt,', self.text)
        self.assertIn('presetLoading:!1,codingPlanAuthError:ve,', self.text)


    def test_provider_empty_state_replaces_the_stuck_loading_card(self):
        # No provider configured => no selectable nav item => upstream keeps the
        # detail pane on its common.loading card forever. Standalone must render
        # the empty state instead, and only while the picker is closed.
        self.assertIn('!ie&&(p?.length??0)===0?(0,$.jsx)(CCodeProviderEmptyState,{}):ie?', self.text)
        self.assertIn('function CCodeProviderEmptyState(){', self.text)
        self.assertIn('settings.modelProvider.empty', self.text)
        self.assertIn('settings.modelProvider.addProviderDescription', self.text)


class PatchedIntlBundleTests(unittest.TestCase):
    """Account-era labels are renamed for the local Activity feature."""
    baseline = ROOT / 'baselines' / 'ccode-3.14.5-original.asar'

    @classmethod
    def setUpClass(cls):
        if not cls.baseline.exists():
            raise unittest.SkipTest('pinned baseline asar is not present')
        sys.path.insert(0, str(ROOT / 'scripts'))
        from asar import Archive
        cls.text = cloud._intl(Archive(cls.baseline).read(cloud.INTL).decode())


    def test_usage_page_is_named_activity(self):
        self.assertIn('"settings.usageTitle":`Activity`', self.text)
        self.assertIn('"settings.usageTitle":`活跃度`', self.text)
        self.assertNotIn('"settings.usageTitle":`Usage stats`', self.text)

    def test_upgrade_wording_is_dropped_from_the_model_error(self):
        self.assertIn('"chat.error.noAvailableModel":`No model available. Set a custom model.`', self.text)
        self.assertNotIn('Upgrade or set a custom model', self.text)
        self.assertNotIn('请开通编程套餐', self.text)


class McpCatalogRendererTests(unittest.TestCase):
    def test_optional_entries_do_not_render_an_optional_badge(self):
        script = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs'), vm = require('node:vm');
const sandbox = {
  Q: { useState: value => [value, () => {}] },
  $: { jsx: (type, props) => ({ type, props }), jsxs: (type, props) => ({ type, props }) },
  Ps: 'Icon',
  X: 'Button',
  module: { exports: {} }
};
vm.runInNewContext(fs.readFileSync('./src/renderer/mcp-catalog.js', 'utf8'), sandbox);
const { CCodeMcpCatalogRow } = sandbox.module.exports;
for (const [id, name] of [['lsp', 'LSP'], ['ripgrep', 'Ripgrep'], ['other', 'Other MCP']]) {
  const row = CCodeMcpCatalogRow({ entry: { id, name, default: false, description: '' }, onInstalled: async () => {} });
  assert.equal(JSON.stringify(row).includes('Optional'), false, `${name} must not show an Optional badge`);
}
const defaultRow = CCodeMcpCatalogRow({ entry: { id: 'context7', name: 'Context7', default: true, description: '' }, onInstalled: async () => {} });
assert.equal(JSON.stringify(defaultRow).includes('Default'), true);
"""
        result = subprocess.run(['node', '-e', script], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


class PatchedAgentBundleTests(unittest.TestCase):
    """The marketplace catalog never carries paid-plan plugins."""
    baseline = ROOT / 'baselines' / 'ccode-3.14.5-original-agent.cjs'

    @classmethod
    def setUpClass(cls):
        if not cls.baseline.exists():
            raise unittest.SkipTest('pinned agent baseline is not present')
        sys.path.insert(0, str(ROOT / 'src'))
        import importlib
        storage = importlib.import_module('local_only.storage')
        cls.text = cloud.patch_agent(storage.patch_agent(cls.baseline.read_text()))

    def test_zhipu_provider_families_are_removed(self):
        self.assertIn('wXe=[],QZi=new Map(', self.text)
        self.assertNotIn('rootDomain:"z.ai"', self.text)
        self.assertNotIn('startPlanProviderId:rm.zaiStartPlan', self.text)

    def test_paid_plan_entries_are_filtered_out(self):
        self.assertIn('if(l.length===0||a.requiresPaidPlan===!0)return null;', self.text)
        self.assertNotIn('if(l.length===0)return null;', self.text.split('function jOe(')[0],
                         'the catalog builder no longer keeps paid-plan entries')
        self.assertEqual(self.text.count('delete t.requiresPaidPlan'), 1, 'install manifest still strips the flag')


    def test_image_search_mcp_is_excluded_without_filtering_other_plugins(self):
        start = self.text.index('function Pat(e){')
        end = self.text.index('function Q3s(e,t){', start)
        resolver = self.text[start:end]
        overview_start = self.text.index('function Qzs(e,t,n,o,s,a){')
        overview_end = self.text.index('function e7s(e){', overview_start)
        overview = self.text[overview_start:overview_end]
        script = f"""
function eBs() {{ return {{}}; }}
function Q3s(loaded, key) {{ return `plugin:${{loaded.manifest.name}}:${{key}}`; }}
function nBs(config) {{ return config; }}
function gre() {{ throw new Error('unexpected MCP config read'); }}
function BOe() {{ return null; }}
function Oat() {{ return []; }}
{resolver}
{overview}
const imageSearch = Pat({{loaded:{{id:'image-search@ccode-plugins-official',manifest:{{name:'image-search'}}}},definitions:{{image_search:{{type:'http'}},other:{{type:'stdio'}}}},diagnostics:[]}});
const otherPlugin = Pat({{loaded:{{id:'other',manifest:{{name:'other'}}}},definitions:{{image_search:{{type:'http'}}}},diagnostics:[]}});
function pluginOverview(name) {{
  return Qzs(
    {{id:`${{name}}@ccode-plugins-official`,manifest:{{author:null,homepage:'',name,description:name,version:'1.0.0'}},manifestPath:'/plugin/manifest.json',marketplace:'ccode-plugins-official',rootPath:'/plugin',source:'official'}},
    {{commandRoots:[],hookDetails:[],skillCount:0,skillRoots:[],mcpServers:{{}}}},
    '/data',true,['image_search'],{{}}
  );
}}
console.log(JSON.stringify({{imageSearch,otherPlugin,imageSearchOverview:pluginOverview('image-search'),otherOverview:pluginOverview('other')}}));
"""
        result = subprocess.run(['node', '-e', script], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        servers = json.loads(result.stdout)
        self.assertEqual(servers['imageSearch'], {'plugin:image-search:other': {'type': 'stdio'}})
        self.assertEqual(servers['otherPlugin'], {'plugin:other:image_search': {'type': 'http'}})
        self.assertEqual(servers['imageSearchOverview']['declaredMcpServerNames'], [])
        self.assertEqual(servers['otherOverview']['declaredMcpServerNames'], ['image_search'])

if __name__ == '__main__':
    unittest.main()
