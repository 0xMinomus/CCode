import importlib
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
cloud = importlib.import_module('local_only.cloud')


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
        self.assertIn('k.GetWebRemoteControlStatus', result)
        for dropped in ('k.RendererReady', 'Rk({reportRemoteUsageEvent'):
            self.assertNotIn(dropped, result)
        # The telemetry channel keeps exactly one local acknowledgement.
        self.assertEqual(result.count('k.ReportTelemetryEvent'), 1)
        self.assertEqual(result.count('k.SyncTelemetryContext'), 0)

    def test_result_has_no_comma_run_or_empty_call(self):
        result = cloud._remote_ipc(self.body)
        self.assertNotIn(',,', result)
        self.assertNotIn('(,,', result)


if __name__ == '__main__':
    unittest.main()
