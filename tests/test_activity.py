import json
import os
import pathlib
import shutil
import sqlite3
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE = ROOT / 'src/main/activity.cjs'
PANEL = ROOT / 'src/renderer/activity-panel.js'
DAY = 86400000

_node = None


def node_command():
    """Return a node invocation whose `require('node:sqlite')` works, or None."""
    global _node
    if _node is not None:
        return _node or None
    candidates = []
    plain = shutil.which('node')
    if plain:
        candidates.append([plain])
        candidates.append([plain, '--experimental-sqlite'])
    electron = ROOT / 'app/ccode'
    if electron.exists():
        candidates.append([str(electron)])
    probe = "try{require('node:sqlite');console.log('yes')}catch(e){console.log('no')}"
    for command in candidates:
        env = dict(os.environ)
        if command[0].endswith('ccode'):
            env['ELECTRON_RUN_AS_NODE'] = '1'
        else:
            env.pop('ELECTRON_RUN_AS_NODE', None)
        try:
            result = subprocess.run(command + ['-e', probe], capture_output=True, text=True, env=env, timeout=60)
        except (OSError, subprocess.SubprocessError):
            continue
        if result.stdout.strip().endswith('yes'):
            _node = command
            return command
    _node = []
    return None


def run_node(script, extra_env=None):
    command = node_command()
    if command is None:
        raise unittest.SkipTest('no node runtime with node:sqlite available')
    env = dict(os.environ)
    env.update(extra_env or {})
    if command[0].endswith('zcode'):
        env['ELECTRON_RUN_AS_NODE'] = '1'
    result = subprocess.run(command + ['-e', script], capture_output=True, text=True, env=env, timeout=120)
    if result.returncode != 0:
        raise AssertionError(f'node failed: {result.stderr.strip()}')
    return result.stdout.strip()


def fixture_db(path):
    con = sqlite3.connect(path)
    con.executescript('''
        CREATE TABLE session (id text primary key, parent_id text, task_type text not null default 'interactive');
        CREATE TABLE message (id text primary key, session_id text not null, time_created integer not null, data text not null);
    ''')
    for session, parent, task_type in (('s1', None, 'interactive'), ('s2', 's1', 'subagent_child'), ('s3', None, 'interactive')):
        con.execute('INSERT INTO session (id, parent_id, task_type) VALUES (?,?,?)', (session, parent, task_type))
    now = 1791820800000  # fixed epoch ms; day boundaries are derived by the module
    today = run_node(f"const a=require({json.dumps(str(MODULE))});console.log(a.dayKey(new Date({now})))")
    today_ms = int(run_node(f"const a=require({json.dumps(str(MODULE))});console.log(new Date(a.dayKey(new Date({now}))).getTime())"))
    def add(id_, session, when, role, extra=None):
        con.execute('INSERT INTO message (id, session_id, time_created, data) VALUES (?,?,?,?)',
                    (id_, session, when, json.dumps({'role': role, **(extra or {})})))
    add('m1', 's1', today_ms + 3600000, 'user')
    add('m2', 's1', today_ms + 7200000, 'user')
    add('m3', 's2', today_ms + 3600000, 'user')
    add('m4', 's1', today_ms + 3600000, 'user', {'automationId': 'auto-1'})
    add('m5', 's1', today_ms + 3600000, 'assistant')
    con.execute('INSERT INTO message (id, session_id, time_created, data) VALUES (?,?,?,?)', ('m6', 's1', today_ms + 3600000, 'not-json'))
    add('m7', 's3', today_ms - DAY + 3600000, 'user')
    add('m8', 's3', today_ms - 2 * DAY + 3600000, 'user')
    con.commit()
    con.close()
    return today


class AutoDetectTests(unittest.TestCase):
    def test_detection_summary_counts_only_the_gateway_family(self):
        with tempfile.TemporaryDirectory() as folder:
            config = pathlib.Path(folder) / 'provider_config.json'
            config.write_text(json.dumps({'config': {
                'providerConfigRules': {'providerRules': [
                    {'providerId': '9router', 'providerName': '9Router',
                     'config': {'api': {'baseUrl': 'http://127.0.0.1:20128/v1'}, 'personalModelIds': ['combo/a', 'combo/b']}},
                    {'providerId': '9router-cmc', 'providerName': '9Router · cmc',
                     'config': {'api': {'baseUrl': 'http://127.0.0.1:20128/v1'}, 'personalModelIds': ['cmc/x']}},
                    {'providerId': 'vansrouter', 'providerName': 'Vansrouter',
                     'config': {'api': {'baseUrl': 'https://elsewhere.example/v1'}, 'personalModelIds': ['other/y']}},
                ]},
                'modelConfigRules': {'manualProviderModelRules': [{'modelId': 'combo/a'}]},
            }}))
            summary = json.loads(run_node(
                f"const a=require({json.dumps(str(MODULE))});"
                f"console.log(JSON.stringify(a.detectionSummary({json.dumps(str(config))})))"))
        self.assertEqual(summary['providers'], 2, 'only the local gateway family counts')
        self.assertEqual(summary['models'], 3)
        self.assertEqual(summary['rules'], 1)
        self.assertEqual(summary['names'], ['9Router', '9Router · cmc'])

    def test_detection_outcome_explains_failures(self):
        cases = [
            ('Model discovery unavailable; keeping current config: URLError', 0, False, 'gateway'),
            ('Gateway models: 441\nRefusing to drop 12 of 433 enabled models; config left untouched', 0, False, 'Refused'),
            ('Gateway models: 441\nConfig changed concurrently; retry on next pass', 0, False, 'Try Auto Detect again'),
            ('Gateway models: 441\nUpdated provider config: 12 entry(ies)', 0, True, None),
        ]
        for log, code, expected_ok, fragment in cases:
            outcome = json.loads(run_node(
                f"const a=require({json.dumps(str(MODULE))});"
                f"console.log(JSON.stringify(a.detectionOutcome({json.dumps(log)},{code})))"))
            self.assertEqual(outcome['ok'], expected_ok, log)
            if fragment:
                self.assertIn(fragment, outcome['error'])

    def test_namespace_paths_come_from_the_standalone_root(self):
        paths = json.loads(run_node(
            f"const a=require({json.dumps(str(MODULE))});"
            "console.log(JSON.stringify(a.namespacePaths()))",
            extra_env={'ZCODE_STANDALONE_ROOT': '/tmp/ns-root'}))
        self.assertEqual(paths['config'], '/tmp/ns-root/data/.zcode/v2/provider_config.json')
        self.assertEqual(paths['state'], '/tmp/ns-root/model-sync')


class ActivitySummaryTests(unittest.TestCase):
    def test_summarize_counts_streak_and_window(self):
        script = (
            f"const a=require({json.dumps(str(MODULE))});"
            "const counts={'2026-10-10':2,'2026-10-11':1,'2026-10-13':3};"
            "console.log(JSON.stringify(a.summarize(counts,'2026-10-13')))"
        )
        summary = json.loads(run_node(script))
        self.assertEqual(summary['today'], 3)
        self.assertEqual(summary['total'], 6)
        self.assertEqual(summary['activeDays'], 3)
        self.assertEqual(summary['longestStreak'], 2)
        self.assertEqual(summary['currentStreak'], 1)
        self.assertEqual(summary['firstDay'], '2026-10-10')
        self.assertEqual(summary['lastDay'], '2026-10-13')
        self.assertEqual(summary['byDay'][-1], {'day': '2026-10-13', 'prompts': 3})

    def test_history_and_years_are_returned(self):
        script = (
            f"const a=require({json.dumps(str(MODULE))});"
            "const counts={'2025-12-31':2,'2026-01-01':1,'2026-10-13':3};"
            "console.log(JSON.stringify(a.summarize(counts,'2026-10-13')))"
        )
        summary = json.loads(run_node(script))
        self.assertEqual([row['day'] for row in summary['days']],
                         ['2025-12-31', '2026-01-01', '2026-10-13'])
        self.assertEqual(summary['years'], [{'year': '2025', 'prompts': 2}, {'year': '2026', 'prompts': 4}])

    def test_streak_survives_an_empty_today(self):
        script = (
            f"const a=require({json.dumps(str(MODULE))});"
            "const counts={'2026-10-11':1,'2026-10-12':4};"
            "console.log(JSON.stringify(a.summarize(counts,'2026-10-13')))"
        )
        summary = json.loads(run_node(script))
        self.assertEqual(summary['today'], 0)
        self.assertEqual(summary['currentStreak'], 2)

    def test_day_shift_crosses_month_and_year(self):
        script = (
            f"const a=require({json.dumps(str(MODULE))});"
            "console.log(JSON.stringify([a.shiftDay('2026-10-01',-1),a.shiftDay('2026-12-31',1),a.shiftDay('2026-03-01',-1)]))"
        )
        self.assertEqual(json.loads(run_node(script)), ['2026-09-30', '2027-01-01', '2026-02-28'])


class ActivityDatabaseTests(unittest.TestCase):
    def test_prompt_query_filters_machine_and_invalid_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = pathlib.Path(tmp) / 'db.sqlite'
            today = fixture_db(db)
            script = (
                f"const a=require({json.dumps(str(MODULE))});"
                f"a.collect({json.dumps(str(db))},{json.dumps(today)}).then(s=>console.log(JSON.stringify(s)))"
            )
            summary = json.loads(run_node(script))
            self.assertEqual(summary['today'], 2, 'interactive user prompts only')
            self.assertEqual(summary['total'], 4)
            self.assertEqual(summary['activeDays'], 3)
            self.assertEqual(summary['currentStreak'], 3)
            self.assertEqual([row['day'] for row in summary['byDay']], sorted(row['day'] for row in summary['byDay']))

    def test_missing_database_reports_unavailable(self):
        script = (
            f"const a=require({json.dumps(str(MODULE))});"
            "console.log(JSON.stringify(a.sessionDbPath()))"
        )
        env = {'ZCODE_SESSION_DB_PATH': '', 'ZCODE_STORAGE_DIR': '/tmp/zcode-activity-test'}
        self.assertEqual(json.loads(run_node(script, env)), '/tmp/zcode-activity-test/cli/db/db.sqlite')


PANEL_LOADER = ("const fs=require('fs');const mod={exports:{}};"
                "new Function('module','exports',fs.readFileSync(PANEL_PATH,'utf8'))(mod,mod.exports);"
                "const p=mod.exports;")


class ActivityPanelTests(unittest.TestCase):
    def panel_script(self, body):
        return f"const PANEL_PATH={json.dumps(str(PANEL))};" + PANEL_LOADER + body

    def grid(self, counts, year):
        script = self.panel_script(
            f"const counts=new Map(Object.entries({json.dumps(counts)}));"
            f"const grid=p.ZCodeActivityGrid(counts,{json.dumps(year)});"
            "console.log(JSON.stringify({weeks:grid.weeks.length,months:grid.months,"
            "days:grid.weeks.flat().filter(Boolean).map(c=>c.day),"
            "filled:grid.weeks.flat().filter(c=>c&&c.prompts).map(c=>c.day)}))"
        )
        return json.loads(run_node(script))

    def test_the_grid_is_always_one_calendar_year(self):
        grid = self.grid({'2026-10-05': 4}, '2026')
        self.assertEqual(grid['days'][0], '2026-01-01')
        self.assertEqual(grid['days'][-1], '2026-12-31')
        self.assertEqual(len(grid['days']), 365, 'a fixed January-December grid')
        self.assertEqual(len(grid['days']), len(set(grid['days'])), 'no duplicate cells')
        self.assertTrue(52 <= grid['weeks'] <= 54, grid['weeks'])
        self.assertEqual(grid['filled'], ['2026-10-05'])

    def test_year_window_keeps_leap_day_and_bounds(self):
        grid = self.grid({'2024-02-29': 7}, '2024')
        self.assertEqual(grid['days'][0], '2024-01-01')
        self.assertEqual(grid['days'][-1], '2024-12-31')
        self.assertEqual(len(grid['days']), 366)
        self.assertEqual(grid['filled'], ['2024-02-29'])

    def test_month_labels_are_english_and_cover_every_column(self):
        script = self.panel_script(
            "const grid=p.ZCodeActivityGrid(new Map(),'2026');"
            "const spans=p.ZCodeActivityMonthSpans(grid.months);"
            "console.log(JSON.stringify({names:p.ZCodeActivityMonthNames,"
            "labels:grid.months.filter(Boolean),spans:spans.map(g=>[g.label,g.span]),"
            "covered:spans.reduce((s,g)=>s+g.span,0),weeks:grid.weeks.length}))"
        )
        result = json.loads(run_node(script))
        self.assertEqual(result['names'],
                         ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'])
        self.assertEqual(result['labels'], result['names'], 'a year grid labels January through December')
        self.assertEqual([label for label, _ in result['spans']], result['names'])
        self.assertEqual(result['covered'], result['weeks'], 'every column belongs to a month group')
        for label, span in result['spans']:
            self.assertGreaterEqual(span, 1, label)

    def test_year_segments_follow_history_and_end_on_the_current_year(self):
        script = self.panel_script(
            "console.log(JSON.stringify({"
            "history:p.ZCodeActivityYears([{year:'2025',prompts:2},{year:'2026',prompts:4}],2026),"
            "currentOnly:p.ZCodeActivityYears([],2027),"
            "deduped:p.ZCodeActivityYears([{year:'2026'},{year:'2024'},{year:'2026'}],2026),"
            "noHistory:p.ZCodeActivityYears(undefined,2026)}))"
        )
        years = json.loads(run_node(script))
        self.assertEqual(years['history'], ['2025', '2026'])
        self.assertEqual(years['history'][-1], '2026', 'the newest year is the last segment')
        self.assertEqual(years['currentOnly'], ['2027'], 'the current year is always offered')
        self.assertEqual(years['deduped'], ['2024', '2026'])
        self.assertEqual(years['noHistory'], ['2026'])

    def test_cells_hover_with_the_bundled_zcode_tooltip(self):
        stub = (
            "const jsx=(type,props)=>({type,props});"
            "const Q={Fragment:'f',useState:()=>[null,()=>{}],useMemo:fn=>fn(),useEffect:()=>{}};"
            "const Tooltip=props=>props;Tooltip.isTooltip=true;"
            "const rendered={exports:{}};"
            "new Function('module','exports','$','Q','uA',fs.readFileSync(PANEL_PATH,'utf8'))"
            "(rendered,rendered.exports,{jsx,jsxs:jsx},Q,Tooltip);"
        )
        script = f"const fs=require('fs');const PANEL_PATH={json.dumps(str(PANEL))};" + stub + (
            "const solid=rendered.exports.ZCodeActivityCell({cell:{day:'2026-10-05',prompts:4}});"
            "const empty=rendered.exports.ZCodeActivityCell({cell:{day:'2026-01-02',prompts:0}});"
            "console.log(JSON.stringify({"
            "wrapper:solid.type&&solid.type.isTooltip===true,tooltip:solid.props.title,"
            "boxClass:solid.props.children.props.className,boxTitle:solid.props.children.props.title??null,"
            "boxStyle:solid.props.children.props.style,emptyTooltip:empty.props.title}))"
        )
        result = json.loads(run_node(script))
        self.assertTrue(result['wrapper'], 'the cell renders through the bundled tooltip component')
        self.assertEqual(result['tooltip'], '2026-10-05\n4 prompts')
        self.assertIsNone(result['boxTitle'], 'no native browser tooltip')
        self.assertIn('aspect-square', result['boxClass'])
        self.assertIn('hover:border-border-hover', result['boxClass'], 'hover uses the app border token')
        self.assertEqual(result['boxStyle'], {'backgroundColor': 'var(--color-usage-heatmap-2)'})
        self.assertEqual(result['emptyTooltip'], '2026-01-02\n0 prompts')

    def test_stats_render_prompt_metrics_with_day_units(self):
        script = self.panel_script(
            "console.log(JSON.stringify(p.ZCodeActivityStats("
            "{today:2,currentStreak:3,longestStreak:5,activeDays:7,total:1234})"
            ".map(s=>[s.label,s.value])))"
        )
        stats = json.loads(run_node(script))
        self.assertEqual([row[0] for row in stats],
                         ['Prompts today', 'Current streak', 'Longest streak', 'Active days', 'Total prompts'])
        self.assertEqual([row[1] for row in stats[:4]], ['2', '3 d', '5 d', '7'])
        self.assertTrue(stats[4][1].startswith('1') and stats[4][1] != '1234',
                        f'large counts are abbreviated: {stats[4][1]}')

    def test_number_labels_are_english(self):
        script = self.panel_script(
            "console.log(JSON.stringify(["
            "p.ZCodeActivityNumber(0,'en-US'),p.ZCodeActivityNumber(24,'en-US'),"
            "p.ZCodeActivityNumber(1234,'en-US'),p.ZCodeActivityNumber(1200000,'en-US')]))"
        )
        self.assertEqual(json.loads(run_node(script)), ['0', '24', '1.2K', '1.2M'])

    def test_heat_colors_use_the_upstream_usage_ramp(self):
        script = self.panel_script(
            "console.log(JSON.stringify([0,1,3,6,10].map(p.ZCodeActivityHeatColor)))"
        )
        self.assertEqual(json.loads(run_node(script)),
                         [f'var(--color-usage-heatmap-{level})' for level in range(5)])


if __name__ == '__main__':
    unittest.main()
