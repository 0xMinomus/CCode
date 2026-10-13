"""Profile zcode-fast: tool surface, post-shot defaults, dan kebijakan pointer.

Tes di sini menjalankan kode profil yang benar-benar dipakai backend desktop (bukan menyalin
logikanya), dengan modul server/input/capture palsu supaya tidak perlu portal atau gi.
"""
import importlib
import os
import pathlib
import sys
import types
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
DESKTOP = ROOT / 'services/desktop'

os.environ.setdefault('ZCODE_CUA_POLL_S', '0')
os.environ.setdefault('ZCODE_CUA_IDLE_MS', '120')
os.environ.setdefault('ZCODE_CUA_TAKEOVER_MS', '400')
os.environ.pop('MCP_SCREEN_WAIT_MODE', None)

sys.path.insert(0, str(DESKTOP))
profile = importlib.import_module('zcode_fast_profile')


class _UserControlError(RuntimeError):
    pass


class _FakeInput(types.ModuleType):
    UserControlError = _UserControlError
    StaleViewError = type('StaleViewError', (RuntimeError,), {})

    def __init__(self):
        super().__init__('input')
        self.calls = []
        self.raise_first = True

    def guard_user(self, force=False):
        self.calls.append(force)
        if force:
            return
        if self.raise_first:
            raise _UserControlError('user moved the mouse to (5, 5); I last left it at (500, 500)')

    def type_text(self, args):
        return {'content': []}


class _FakeCapture(types.ModuleType):
    WAIT_MODE = 'poll'

    def __init__(self, positions=None):
        super().__init__('capture')
        self.positions = list(positions or [])
        self.i = 0

    def cursor_pos(self, refresh=True, prefer_node=None):
        if not self.positions:
            return None
        pos = self.positions[min(self.i, len(self.positions) - 1)]
        self.i += 1
        return pos


def _build_ns(positions):
    def handler(name):
        def fn(args):
            return {'content': [], 'args': args, 'name': name}
        return fn

    tools = [
        {'name': name, 'description': 'base'}
        for name in [
            'screen_screenshot', 'screen_list_monitors', 'screen_move_mouse', 'screen_click',
            'screen_scroll', 'screen_drag', 'screen_key', 'screen_type', 'screen_do',
            'screen_read_text', 'screen_wait_text', 'screen_verify', 'screen_sense',
            'screen_focus', 'screen_read_page', 'screen_watch', 'screen_reload', 'screen_diag',
            'screen_tour', 'screen_session', 'screen_read_selection',
        ]
    ]

    def maybe_shot(args, content, t0):
        return list(content)

    ns = {
        'TOOLS': tools,
        'HANDLERS': {t['name']: handler(t['name']) for t in tools},
        'INSTRUCTIONS': 'base',
        '_txt': lambda text: {'type': 'text', 'text': text},
        '_maybe_shot': maybe_shot,
        'grounding': types.SimpleNamespace(warmup=lambda: None, warmed=False),
        'inp': _FakeInput(),
        'state': types.SimpleNamespace(SESSION={'cmd_node': 7}),
        'capture': _FakeCapture(positions),
        'os': os,
        'time': importlib.import_module('time'),
    }
    return ns


class PointerWindow(unittest.TestCase):
    def test_parked_pointer_is_not_takeover(self):
        samples = [(0, 900, 400), (60, 902, 401), (150, 902, 401), (240, 901, 400)]
        self.assertEqual(profile.classify_pointer_window(samples), 'idle')

    def test_short_window_is_pending(self):
        self.assertEqual(profile.classify_pointer_window([(0, 10, 10), (20, 11, 11)]), 'pending')

    def test_continuous_driving_yields(self):
        samples = [(t, 100 + t * 3, 200) for t in range(0, 500, 50)]
        self.assertEqual(profile.classify_pointer_window(samples), 'driving')

    def test_movement_that_stops_is_idle(self):
        samples = [(0, 10, 10), (50, 400, 600), (200, 400, 600), (400, 400, 600)]
        self.assertEqual(profile.classify_pointer_window(samples), 'idle')

    def test_single_sample_is_pending(self):
        self.assertEqual(profile.classify_pointer_window([(0, 5, 5)]), 'pending')
        self.assertEqual(profile.classify_pointer_window([]), 'pending')


class PolicyInstall(unittest.TestCase):
    def test_pointer_wrapper_proceeds_when_pointer_is_parked(self):
        ns = _build_ns([(900, 400)])
        profile.install_pointer_policy(ns)
        ns['inp'].guard_user(False)  # must not raise: pointer is quiet
        self.assertEqual(ns['inp'].calls, [False])

    def test_pointer_wrapper_yields_when_user_keeps_driving(self):
        ns = _build_ns(None)
        capture = ns['capture']

        def moving(refresh=True, prefer_node=None):
            capture.i += 10
            return (100 + capture.i, 200)

        capture.cursor_pos = moving
        profile.install_pointer_policy(ns)
        with self.assertRaises(_UserControlError):
            ns['inp'].guard_user(False)

    def test_pointer_wrapper_fails_open_when_cursor_unreadable(self):
        ns = _build_ns([])
        profile.install_pointer_policy(ns)
        ns['inp'].guard_user(False)  # no samples -> fail open, like the vendored guard

    def test_force_bypasses_the_policy(self):
        ns = _build_ns(None)
        profile.install_pointer_policy(ns)
        ns['inp'].guard_user(True)
        self.assertEqual(ns['inp'].calls, [True])


class ObservationPolicy(unittest.TestCase):
    def _run(self, content):
        ns = _build_ns([])
        profile.install_observation_policy(ns)
        return ns['_maybe_shot']({'shot': True}, content, 0.0)

    def _texts(self, out):
        return ' '.join(str(item.get('text', '')) for item in out)

    def test_skips_the_image_when_sense_reports_no_change(self):
        content = [
            {'type': 'text', 'text': 'clicked 900,400'},
            {'type': 'text', 'text': 'SENSE {}\nhints: nothing changed — last action may have been a no-op/misclick'},
            {'type': 'image', 'data': 'x' * 32, 'mimeType': 'image/webp'},
        ]
        out = self._run(content)
        self.assertFalse(any(item.get('type') == 'image' for item in out))
        self.assertIn('clicked 900,400', self._texts(out))
        self.assertIn('shot skipped', self._texts(out))

    def test_keeps_the_image_when_the_screen_changed(self):
        content = [
            {'type': 'text', 'text': 'SENSE {}\nhints: 2 new element(s)'},
            {'type': 'image', 'data': 'x' * 32, 'mimeType': 'image/webp'},
        ]
        self.assertTrue(any(item.get('type') == 'image' for item in self._run(content)))

    def test_keeps_the_image_when_there_is_no_sense_line_yet(self):
        content = [{'type': 'image', 'data': 'x' * 32, 'mimeType': 'image/webp'}]
        self.assertTrue(any(item.get('type') == 'image' for item in self._run(content)))

    def test_kill_switch_keeps_the_image(self):
        os.environ['ZCODE_CUA_SKIP_UNCHANGED_SHOT'] = '0'
        try:
            content = [
                {'type': 'text', 'text': 'SENSE {}\nhints: nothing changed — nope'},
                {'type': 'image', 'data': 'x' * 32, 'mimeType': 'image/webp'},
            ]
            self.assertTrue(any(item.get('type') == 'image' for item in self._run(content)))
        finally:
            os.environ.pop('ZCODE_CUA_SKIP_UNCHANGED_SHOT', None)


class LazyWarmup(unittest.TestCase):
    def test_install_replaces_the_prefetch_with_a_noop(self):
        ns = _build_ns([])
        before = ns['grounding'].warmup
        profile.install_lazy_warmup(ns)
        self.assertIsNot(ns['grounding'].warmup, before)
        ns['grounding'].warmup()  # must be callable and harmless

    def test_env_keeps_the_prefetch(self):
        os.environ['ZCODE_CUA_WARMUP'] = '1'
        try:
            ns = _build_ns([])
            before = ns['grounding'].warmup
            profile.install_lazy_warmup(ns)
            self.assertIs(ns['grounding'].warmup, before)
        finally:
            os.environ.pop('ZCODE_CUA_WARMUP', None)


class ToolSurface(unittest.TestCase):
    def setUp(self):
        self.ns = _build_ns([])
        fake_gi = types.ModuleType('gi')
        repository = types.ModuleType('gi.repository')
        repository.Gio = types.SimpleNamespace(AppInfo=types.SimpleNamespace(get_all=lambda: []))
        fake_gi.repository = repository
        sys.modules['gi'] = fake_gi
        sys.modules['gi.repository'] = repository
        profile.install(self.ns)

    def test_keeps_cheap_perception_and_targeting_tools(self):
        names = {t['name'] for t in self.ns['TOOLS']}
        for expected in ['screen_read_text', 'screen_wait_text', 'screen_verify', 'screen_sense',
                         'screen_focus', 'desktop_open_app', 'screen_click', 'screen_screenshot']:
            self.assertIn(expected, names)

    def test_drops_slow_and_destructive_tools(self):
        names = {t['name'] for t in self.ns['TOOLS']}
        for unwanted in ['screen_reload', 'screen_tour', 'screen_watch', 'screen_read_page',
                         'screen_session', 'screen_read_selection', 'screen_diag']:
            self.assertNotIn(unwanted, names)

    def test_click_description_teaches_element_targeting(self):
        click = next(t for t in self.ns['TOOLS'] if t['name'] == 'screen_click')
        self.assertIn('element=<id>', click['description'])
        shot = next(t for t in self.ns['TOOLS'] if t['name'] == 'screen_screenshot')
        self.assertIn('annotate=true', shot['description'])
        self.assertIn('region=', shot['description'])

    def test_actions_default_to_post_shot_and_settle(self):
        for name in ['screen_click', 'screen_key', 'screen_type', 'screen_do']:
            result = self.ns['HANDLERS'][name]({'x': 1, 'y': 2})
            self.assertEqual(result['args']['shot'], True, name)
            self.assertEqual(result['args']['settle'], 250, name)

    def test_waits_for_damage_instead_of_polling(self):
        self.assertEqual(self.ns['capture'].WAIT_MODE, 'hybrid')

    def test_instructions_point_at_text_first_loop_and_pointer_policy(self):
        text = self.ns['INSTRUCTIONS']
        self.assertIn('screen_read_text', text)
        self.assertIn('element=<id>', text)
        self.assertIn('parked pointer', text.replace('A parked pointer', 'parked pointer'))
        self.assertIn('Never pass force=true', text)


if __name__ == '__main__':
    unittest.main()
