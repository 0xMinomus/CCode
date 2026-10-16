"""Windows Computer Use backend: MCP handshake, tool surface, pointer guard, shot geometry.

The MCP and module tests drive the real code with `node` and never touch a live desktop: the
takeover window gets an injected cursor source and a fake clock, the screenshot policy only
computes geometry, and the tool surface is read from the server's own `tools/list` reply.
Live capture is a manual check, not a unit test.
"""
import json
import pathlib
import queue
import subprocess
import threading
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
BACKEND = ROOT / 'services/desktop-win'
MAIN = BACKEND / 'main.cjs'

TOOL_NAMES = ['screen_screenshot', 'screen_read_text', 'screen_click', 'screen_type', 'screen_key',
              'screen_scroll', 'screen_wait_text', 'screen_verify', 'screen_sense', 'screen_focus']


def run_module(script, *arguments):
    """Evaluate a JS snippet that requires one backend module and prints JSON."""
    result = subprocess.run(['node', '-e', script, str(BACKEND), *[json.dumps(argument) for argument in arguments]],
                            check=True, capture_output=True, text=True, cwd=ROOT)
    return json.loads(result.stdout)


class McpProbe:
    """Raw JSON-RPC over the server's stdio, one line per message."""

    def __init__(self):
        self.process = subprocess.Popen(['node', str(MAIN)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE, text=True, encoding='utf-8', cwd=ROOT)
        self.lines = queue.Queue()
        self.reader = threading.Thread(target=self._pump, daemon=True)
        self.reader.start()

    def _pump(self):
        for line in self.process.stdout:
            if line.strip():
                self.lines.put(json.loads(line))
        self.lines.put(None)

    def send(self, message):
        self.process.stdin.write(json.dumps(message) + '\n')
        self.process.stdin.flush()

    def receive(self, timeout=45):
        message = self.lines.get(timeout=timeout)
        if message is None:
            raise AssertionError('The Windows desktop server closed its output: ' + self.process.stderr.read())
        return message

    def close(self):
        self.process.kill()
        self.process.wait(timeout=20)
        for pipe in (self.process.stdin, self.process.stdout, self.process.stderr):
            try: pipe.close()
            except Exception: pass


class McpHandshake(unittest.TestCase):
    def test_initialize_and_the_ten_tool_surface(self):
        probe = McpProbe()
        try:
            probe.send({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
                        'params': {'protocolVersion': '2025-06-18', 'capabilities': {},
                                   'clientInfo': {'name': 'probe', 'version': '1'}}})
            initialized = probe.receive()
            self.assertEqual(initialized['id'], 1)
            self.assertEqual(initialized['result']['serverInfo']['name'], 'windows-desktop')
            self.assertEqual(initialized['result']['protocolVersion'], '2025-06-18')
            self.assertIn('tools', initialized['result']['capabilities'])
            probe.send({'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list', 'params': {}})
            listed = probe.receive()
            names = [tool['name'] for tool in listed['result']['tools']]
            self.assertEqual(sorted(names), sorted(TOOL_NAMES))
            for tool in listed['result']['tools']:
                self.assertEqual(tool['inputSchema']['type'], 'object')
                self.assertTrue(tool['description'])
            probe.send({'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call',
                        'params': {'name': 'screen_teleport', 'arguments': {}}})
            unknown = probe.receive()
            self.assertTrue(unknown['result']['isError'])
            self.assertIn('Unknown tool', unknown['result']['content'][0]['text'])
            probe.send({'jsonrpc': '2.0', 'id': 4, 'method': 'ping', 'params': {}})
            self.assertEqual(probe.receive()['id'], 4)
        finally:
            probe.close()

    def test_an_unknown_method_is_rejected(self):
        probe = McpProbe()
        try:
            probe.send({'jsonrpc': '2.0', 'id': 9, 'method': 'resources/list', 'params': {}})
            reply = probe.receive()
            self.assertEqual(reply['error']['code'], -32601)
        finally:
            probe.close()


GUARD_SCRIPT = """
const { TakeoverGuard, DEFAULTS } = require(process.argv[1] + '/guard.cjs');
const scenario = JSON.parse(process.argv[2]);
let clock = 0;
let index = 0;
const points = scenario.points;
const cursor = async () => points[Math.min(index++, points.length - 1)];
const guard = new TakeoverGuard({ cursor, now: () => clock, limits: scenario.limits ?? DEFAULTS,
  sleep: ms => { clock += ms; return Promise.resolve(); } });
if (scenario.commanded) guard.record(scenario.commanded);
(async () => {
  try {
    const result = await guard.check(scenario.force === true);
    process.stdout.write(JSON.stringify({ verdict: result.verdict, clock }));
  } catch (error) {
    process.stdout.write(JSON.stringify({ stopped: error.stopped === true, name: error.name,
      message: error.message, clock }));
  }
})();
"""

LIMITS = {'idlePx': 8, 'idleMs': 120, 'takeoverMs': 400, 'pollMs': 100}
DRIVING = [{'x': 100 + index * 30, 'y': 200} for index in range(30)]


class TakeoverGuard(unittest.TestCase):
    def check(self, scenario):
        return run_module(GUARD_SCRIPT, scenario)

    def test_small_repeated_nudges_do_not_cancel_with_shared_desktop_policy(self):
        points = [{'x': 100 + index * 12, 'y': 200} for index in range(40)]
        result = self.check({'commanded': {'x': 0, 'y': 0}, 'points': points})
        self.assertEqual(result['verdict'], 'idle')

    def test_deliberate_movement_still_yields_with_shared_desktop_policy(self):
        result = self.check({'commanded': {'x': 0, 'y': 0}, 'points': DRIVING})
        self.assertTrue(result['stopped'])
        self.assertGreaterEqual(result['clock'], 2500)

    def test_a_parked_pointer_is_not_a_takeover(self):
        result = self.check({'limits': LIMITS, 'commanded': {'x': 900, 'y': 400}, 'points': [{'x': 902, 'y': 401}]})
        self.assertEqual(result['verdict'], 'quiet')

    def test_an_unreadable_cursor_proceeds_like_the_vendored_guard(self):
        result = self.check({'limits': LIMITS, 'points': [None]})
        self.assertEqual(result['verdict'], 'quiet')

    def test_sustained_movement_stops_with_STOPPED(self):
        result = self.check({'limits': LIMITS, 'commanded': {'x': 0, 'y': 0}, 'points': DRIVING})
        self.assertTrue(result['stopped'])
        self.assertIn('STOPPED', result['message'])
        self.assertIn('Never pass force=true', result['message'])

    def test_movement_that_stops_is_idle(self):
        result = self.check({'limits': LIMITS, 'commanded': {'x': 0, 'y': 0},
                             'points': [{'x': 10, 'y': 10}, {'x': 500, 'y': 600}, {'x': 500, 'y': 600},
                                        {'x': 500, 'y': 600}, {'x': 500, 'y': 600}]})
        self.assertEqual(result['verdict'], 'idle')

    def test_a_short_window_without_move_is_treated_as_a_nudge(self):
        result = self.check({'limits': LIMITS, 'commanded': {'x': 0, 'y': 0},
                             'points': [{'x': 10, 'y': 10}, {'x': 11, 'y': 11}, {'x': 11, 'y': 11}, {'x': 11, 'y': 11},
                                        {'x': 11, 'y': 11}, {'x': 11, 'y': 11}, {'x': 11, 'y': 11}]})
        self.assertEqual(result['verdict'], 'idle')

    def test_force_bypasses_without_waiting_on_the_user(self):
        result = self.check({'limits': LIMITS, 'commanded': {'x': 0, 'y': 0}, 'points': DRIVING, 'force': True})
        self.assertEqual(result['verdict'], 'forced')
        self.assertEqual(result['clock'], 0)

    def test_a_window_that_stays_unreadable_fails_open(self):
        result = self.check({'limits': LIMITS, 'commanded': {'x': 0, 'y': 0}, 'points': [{'x': 500, 'y': 600}, None]})
        self.assertEqual(result['verdict'], 'undecidable')
        self.assertGreaterEqual(result['clock'], 400)


CLASSIFY_SCRIPT = """
const { classifyPointerWindow } = require(process.argv[1] + '/guard.cjs');
const limits = { idlePx: 8, idleMs: 120, takeoverMs: 400 };
const cases = JSON.parse(process.argv[2]).map(samples => classifyPointerWindow(samples, limits));
process.stdout.write(JSON.stringify(cases));
"""


class PointerWindow(unittest.TestCase):
    def test_matches_the_linux_profile_verdicts(self):
        cases = [
            ([(0, 900, 400), (60, 902, 401), (150, 902, 401), (240, 901, 400)], 'idle'),
            ([(0, 10, 10), (20, 11, 11)], 'pending'),
            ([(time, 100 + time * 3, 200) for time in range(0, 500, 50)], 'driving'),
            ([(0, 10, 10), (50, 400, 600), (200, 400, 600), (400, 400, 600)], 'idle'),
            ([(0, 5, 5)], 'pending'),
            ([], 'pending'),
        ]
        payload = [[{'t': time, 'x': x, 'y': y} for time, x, y in samples] for samples, _ in cases]
        result = run_module(CLASSIFY_SCRIPT, payload)
        self.assertEqual(result, [expected for _, expected in cases])


SHOT_SCRIPT = """
const shot = require(process.argv[1] + '/shot.cjs');
const regions = JSON.parse(process.argv[2]);
const { maxEdge, maxOutputKb } = shot.limits({ MCP_SCREEN_MAX_EDGE: '1280', MCP_SCREEN_MAX_OUTPUT_KB: '250' });
const desktop = { x: 0, y: 0, width: 2560, height: 1600 };
const point = shot.viewToDesktop({ x: 640, y: 360 }, { origin: { x: 100, y: 50 }, scale: 0.5 });
const long = shot.limitText('x'.repeat(600 * 1024), maxOutputKb);
process.stdout.write(JSON.stringify({
  maxEdge, maxOutputKb, point,
  clamps: regions.map(region => shot.clampRegion(region, desktop)),
  plans: regions.map(region => shot.planCapture(region, desktop, maxEdge)),
  full: shot.planCapture(null, desktop, maxEdge),
  small: shot.scaleSize(800, 600, maxEdge),
  wide: shot.scaleSize(3840, 1080, maxEdge),
  huge: shot.scaleSize(6000, 2000, maxEdge),
  truncated: long.length, tail: long.slice(-120),
}));
"""

REGIONS = [[-100, -50, 400, 300], [2000, 1200, 900, 900], [5000, 5000, 10, 10]]


class ShotGeometry(unittest.TestCase):
    def setUp(self):
        self.result = run_module(SHOT_SCRIPT, REGIONS)

    def test_budgets_come_from_the_definition_environment(self):
        self.assertEqual(self.result['maxEdge'], 1280)
        self.assertEqual(self.result['maxOutputKb'], 250)

    def test_scaling_caps_the_longest_edge_and_reports_the_factor(self):
        self.assertEqual(self.result['full']['view'], {'width': 1280, 'height': 800, 'scale': 0.5})
        self.assertEqual(self.result['small'], {'width': 800, 'height': 600, 'scale': 1})
        self.assertEqual(self.result['wide']['width'], 1280)
        self.assertEqual(self.result['wide']['height'], 360)
        self.assertEqual(self.result['huge'], {'width': 1280, 'height': 427, 'scale': 1280 / 6000})

    def test_a_region_is_clamped_to_the_virtual_desktop(self):
        self.assertEqual(self.result['clamps'][0], {'x': 0, 'y': 0, 'width': 300, 'height': 250})
        self.assertIsNone(self.result['clamps'][2])
        self.assertEqual(self.result['plans'][0]['rect'], {'x': 0, 'y': 0, 'width': 300, 'height': 250})
        self.assertEqual(self.result['plans'][1]['rect'], {'x': 2000, 'y': 1200, 'width': 560, 'height': 400})
        self.assertEqual(self.result['plans'][1]['view']['width'], 560)

    def test_view_pixels_map_back_to_desktop_pixels(self):
        self.assertEqual(self.result['point'], {'x': 1380, 'y': 770})

    def test_a_runaway_text_result_is_truncated_to_the_budget(self):
        self.assertLessEqual(self.result['truncated'], 250 * 1024 + 300)
        self.assertIn('MCP_SCREEN_MAX_OUTPUT_KB', self.result['tail'])


SESSION_SCRIPT = """
const { Session, StaleElementError, classifySense, senseText } = require(process.argv[1] + '/session.cjs');
const session = new Session();
const view = session.openView({ x: 0, y: 0 }, { width: 1280, height: 800, scale: 1 });
const rows = [{ role: 'button', text: 'Save', x: 10, y: 20 }, { role: 'edit', text: 'Name', x: 30, y: 40 }];
const first = session.assign(rows);
const again = session.assign(rows);
let stale = null;
try { session.resolveElement('e99'); } catch (error) { stale = error instanceof StaleElementError; }
session.openView({ x: 0, y: 0 }, { width: 1280, height: 800, scale: 1 });
const after = session.assign([{ role: 'button', text: 'Save As', x: 10, y: 20 }]);
const sense = [];
for (const [name, before, after_] of [
  ['screen_click', { hash: 'a', topLevel: 3, foreground: { hwnd: 1, title: 'A' }, elements: null },
   { hash: 'a', topLevel: 3, foreground: { hwnd: 1, title: 'A' }, elements: null }],
  ['screen_key', { hash: 'a', topLevel: 3, foreground: { hwnd: 1, title: 'A' }, elements: null },
   { hash: 'b', topLevel: 3, foreground: { hwnd: 1, title: 'A' }, elements: null }],
  ['screen_type', { hash: 'a', topLevel: 3, foreground: { hwnd: 1, title: 'A' }, elements: null },
   { hash: 'a', topLevel: 3, foreground: { hwnd: 2, title: 'B' }, elements: null }],
  ['screen_click', { hash: 'a', topLevel: 3, foreground: { hwnd: 1, title: 'A' }, elements: null },
   { hash: 'a', topLevel: 4, foreground: { hwnd: 1, title: 'A' }, elements: null }],
]) { sense.push([name, classifySense({ name, before, after: after_ }).signal]); }
process.stdout.write(JSON.stringify({ view: view.id, ids: first.map(row => row.id), stable: again.map(row => row.id),
  afterView: after[0].id, stale, sense,
  noOp: senseText({ name: 'screen_click', before: { hash: 'a', topLevel: 3, foreground: { hwnd: 1 }, elements: null },
    after: { hash: 'a', topLevel: 3, foreground: { hwnd: 1 }, elements: null } }),
  empty: senseText(null) }));
"""


class SessionState(unittest.TestCase):
    def setUp(self):
        self.result = run_module(SESSION_SCRIPT)

    def test_ids_are_stable_while_the_element_list_is_unchanged(self):
        self.assertEqual(self.result['ids'], ['e1', 'e2'])
        self.assertEqual(self.result['stable'], ['e1', 'e2'])

    def test_a_changed_list_gets_fresh_ids(self):
        self.assertEqual(self.result['afterView'], 'e1')
        self.assertEqual(self.result['view'], 'view#1')

    def test_an_unknown_id_is_rejected(self):
        self.assertTrue(self.result['stale'])

    def test_the_change_signal_matches_the_linux_vocabulary(self):
        self.assertEqual(self.result['sense'], [['screen_click', 'no_op'], ['screen_key', 'changed'],
                                                ['screen_type', 'opened'], ['screen_click', 'modal']])

    def test_the_no_op_line_is_what_the_shot_skip_policy_keys_off(self):
        self.assertTrue(self.result['noOp'].startswith('SENSE '))
        self.assertIn('nothing changed', self.result['noOp'])
        self.assertIn('unknown', self.result['empty'])


HANDLER_SCRIPT = """
const MCP = process.argv[1];
const { createTools } = require(MCP + '/tools.cjs');
const { Session } = require(MCP + '/session.cjs');
const { StoppedError } = require(MCP + '/guard.cjs');
const calls = [];
let hashes = 0, constant = false, stop = false;
const foreground = { hwnd: 7, title: 'Probe', process: 'probe' };
const rect = { x: 10, y: 20, width: 800, height: 600 };
const rows = [
  { role: 'button', text: 'Save', x: 100, y: 200, left: 90, top: 190, width: 40, height: 20, enabled: true },
  { role: 'document', text: 'probe target', x: 300, y: 400, left: 20, top: 30, width: 700, height: 500, enabled: true },
];
const host = {
  close() {},
  async request(op, args) {
    calls.push({ op, args });
    switch (op) {
      case 'cursor': return { x: 400, y: 300 };
      case 'desktop': return { x: 0, y: 0, width: 2560, height: 1600 };
      case 'elements': return { focused: { ...foreground, rect }, rect, count: rows.length, elements: rows };
      case 'foreground': return { ...foreground, rect, topLevel: 2 };
      case 'screenshot': return { png: args.encode === false ? undefined : 'iVBORw0KGgo=', bytes: 12,
        sha256: constant ? 'constant' : 'h' + (++hashes), width: args.targetWidth, height: args.targetHeight, topLevel: 2, foreground };
      case 'click': return { clicked: args.button || 'left', count: args.double ? 2 : 1, x: args.x ?? 400, y: args.y ?? 300 };
      case 'type': return { typed: String(args.text).length };
      case 'key': return { keys: args.keys };
      case 'scroll': return { direction: args.direction, steps: args.amount };
      case 'focus': return { ...foreground, focused: true };
      default: throw new Error('unexpected helper op: ' + op);
    }
  },
};
const guard = { record() {}, async check(force) {
  if (stop && !force) throw new StoppedError('the pointer kept moving for 500 ms');
  return { verdict: 'quiet' };
} };
const server = createTools({ host, guard, session: new Session(),
  env: { MCP_SCREEN_MAX_EDGE: '1280', MCP_SCREEN_MAX_OUTPUT_KB: '250' } });
const text = result => (result.content || []).filter(part => part.type === 'text').map(part => part.text).join('\\n');
const json = result => JSON.parse(text(result));
const out = {};
(async () => {
  out.toolNames = server.tools.map(tool => tool.name);
  out.senseBeforeAction = text(await server.call('screen_sense', {}));
  const read = json(await server.call('screen_read_text', {}));
  out.readText = { view: read.view, origin: read.origin, size: read.size, focused: read.focused.title,
    ids: read.elements.map(row => row.id + ':' + row.role) };
  const click = await server.call('screen_click', { element: 'e2' });
  out.clickElement = { first: text(click).split('\\n')[0], sense: text(click).split('\\n')[1], parts: click.content.map(part => part.type) };
  const stale = await server.call('screen_click', { element: 'e99' });
  out.clickStale = { isError: stale.isError, text: text(stale).slice(0, 70) };
  out.clickUnknownView = text(await server.call('screen_click', { x: 5, y: 5, view_id: 'view#99' })).slice(0, 40);
  out.typeEmpty = (await server.call('screen_type', {})).isError;
  out.keyMissing = (await server.call('screen_key', {})).isError;
  const found = json(await server.call('screen_wait_text', { text: 'probe target', timeout_ms: 800 }));
  out.waitFound = { appeared: found.appeared, absent: found.absent, match: found.match };
  out.waitAbsent = (await server.call('screen_wait_text', { text: 'probe target', absent: true, timeout_ms: 250 })).isError;
  out.waitTimeout = text(await server.call('screen_wait_text', { text: 'nothing like this', timeout_ms: 250 })).slice(0, 300);
  constant = true;
  const noop = await server.call('screen_click', { element: 'e1' });
  out.noopClick = { parts: noop.content.map(part => part.type), last: text(noop).split('\\n').pop().slice(0, 40) };
  constant = false;
  stop = true;
  const blocked = await server.call('screen_click', { element: 'e1' });
  out.stopped = { isError: blocked.isError, text: text(blocked).slice(0, 60), hint: text(blocked).includes('Never pass force=true') };
  stop = false;
  out.clickArgs = calls.filter(call => call.op === 'click').map(call => [call.args.x, call.args.y]);
  out.verify = json(await server.call('screen_verify', { window: true }));
  out.screenshot = (await server.call('screen_screenshot', { region: [0, 0, 4000, 3000], annotate: true })).content.map(part => part.type);
  out.scroll = text(await server.call('screen_scroll', { direction: 'up', amount: 2 })).split('\\n')[0];
  out.focus = text(await server.call('screen_focus', { app: 'probe' })).slice(0, 30);
  out.unknownTool = (await server.call('screen_teleport', {})).isError;
  process.stdout.write(JSON.stringify(out));
})().catch(error => { process.stdout.write(JSON.stringify({ error: String(error && error.message) })); process.exit(1); });
"""


class ToolHandlers(unittest.TestCase):
    """The ten handlers against an injected helper and guard: no desktop, no PowerShell."""

    @classmethod
    def setUpClass(cls):
        cls.result = run_module(HANDLER_SCRIPT)

    def test_the_surface_is_the_documented_ten(self):
        self.assertEqual(sorted(self.result['toolNames']), sorted(TOOL_NAMES))
        self.assertIn('unknown', self.result['senseBeforeAction'])

    def test_read_text_returns_desktop_coordinates_and_stable_ids(self):
        read = self.result['readText']
        self.assertEqual(read['view'], 'view#1')
        self.assertEqual(read['origin'], {'x': 0, 'y': 0})
        self.assertEqual(read['size'], {'width': 2560, 'height': 1600})
        self.assertEqual(read['focused'], 'Probe')
        self.assertEqual(read['ids'], ['e1:button', 'e2:document'])

    def test_an_element_click_targets_its_centre_and_carries_a_sense_line(self):
        self.assertTrue(self.result['clickElement']['first'].startswith('clicked at desktop 300,400'))
        self.assertTrue(self.result['clickElement']['sense'].startswith('SENSE '))
        self.assertEqual(self.result['clickElement']['parts'], ['text', 'text', 'image'])
        self.assertEqual(self.result['clickArgs'], [[300, 400], [100, 200]])

    def test_an_unknown_element_or_view_is_rejected_before_input(self):
        self.assertTrue(self.result['clickStale']['isError'])
        self.assertIn('Unknown element id e99', self.result['clickStale']['text'])
        self.assertIn('Unknown view_id', self.result['clickUnknownView'])
        self.assertEqual(self.result['clickArgs'], [[300, 400], [100, 200]], 'no click may be injected for a stale target')

    def test_missing_arguments_are_refusals_not_crashes(self):
        self.assertTrue(self.result['typeEmpty'])
        self.assertTrue(self.result['keyMissing'])
        self.assertTrue(self.result['unknownTool'])

    def test_wait_text_reports_the_match_and_times_out_honestly(self):
        self.assertEqual(self.result['waitFound']['appeared'], True)
        self.assertEqual(self.result['waitFound']['absent'], False)
        self.assertEqual(self.result['waitFound']['match']['text'], 'probe target')
        self.assertTrue(self.result['waitAbsent'])
        self.assertIn('timed out after 250 ms', self.result['waitTimeout'])
        self.assertIn('Nothing matched', self.result['waitTimeout'])

    def test_an_unchanged_action_skips_the_image(self):
        self.assertEqual(self.result['noopClick']['parts'], ['text', 'text', 'text'])
        self.assertIn('shot skipped', self.result['noopClick']['last'])

    def test_a_takeover_reports_STOPPED_and_refuses_input(self):
        self.assertTrue(self.result['stopped']['isError'])
        self.assertIn('STOPPED', self.result['stopped']['text'])
        self.assertTrue(self.result['stopped']['hint'])

    def test_verify_screenshot_scroll_and_focus(self):
        self.assertIsNone(self.result['verify']['changed'])
        self.assertEqual(self.result['verify']['region'], {'x': 10, 'y': 20, 'width': 800, 'height': 600})
        self.assertEqual(self.result['screenshot'], ['text', 'text', 'image'])
        self.assertTrue(self.result['scroll'].startswith('scrolled up 2'))
        self.assertTrue(self.result['focus'].startswith('{"focused":true'))


HOST_SCRIPT = """
const { HelperHost } = require(process.argv[1] + '/host.cjs');
const EventEmitter = require('node:events');
const child = new EventEmitter();
child.killed = false; child.exitCode = null;
child.stdin = { lines: [], write(line, callback) { this.lines.push(String(line)); callback?.(); return true; } };
child.stdout = new EventEmitter(); child.stdout.setEncoding = () => {};
child.stderr = new EventEmitter(); child.stderr.setEncoding = () => {};
const host = new HelperHost({ spawn: () => child, timeout: 120 });
const answer = delay => setTimeout(() => {
  const line = child.stdin.lines.at(-1);
  if (line) child.stdout.emit('data', JSON.stringify({ id: JSON.parse(line).id, ok: true, data: {} }) + '\\n');
}, delay);
(async () => {
  const cold = host.request('cursor');
  answer(240);
  const coldData = await cold;
  let warmError = null;
  const warm = host.request('cursor');
  answer(240);
  try { await warm; } catch (error) { warmError = error.message; }
  process.stdout.write(JSON.stringify({ coldData, warmError }));
})();
"""


class HelperHostBudget(unittest.TestCase):
    """The first helper request waits for the cold start; later ones keep the base budget."""

    def test_the_cold_start_gets_a_longer_budget_than_later_requests(self):
        result = run_module(HOST_SCRIPT)
        self.assertEqual(result['coldData'], {})
        self.assertIn('timed out after 120 ms', result['warmError'])


if __name__ == '__main__':
    unittest.main()
