import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from local_only import branding, rebrand


class BrandSourceTests(unittest.TestCase):
    def test_glyph_paths_come_from_the_brand_svg(self):
        paths = branding.glyph_paths()
        self.assertEqual(len(paths), 3)
        self.assertTrue(all(path.startswith('M') for path in paths))

    def test_mark_component_draws_the_ccode_glyph(self):
        component = branding.mark_component()
        for path in branding.glyph_paths():
            self.assertIn(path, component)
        self.assertIn('viewBox:`', component)
        self.assertNotIn('CCode', component)
        self.assertEqual(component.count('$.jsx'), 4)

    def test_lockup_and_mark_data_uris_are_self_contained(self):
        for svg in (branding._lockup_svg(), branding._mark_svg()):
            self.assertTrue(svg.startswith('<svg'))
            self.assertNotIn('<metadata>', svg)
        uri = branding.data_uri(branding._lockup_svg())
        self.assertTrue(uri.startswith('data:image/svg+xml,'))
        self.assertNotIn('<', uri)
        self.assertNotIn('#', uri)

    def test_glyph_box_is_square_and_covers_the_mark(self):
        left, top, width, height = branding._glyph_box()
        self.assertEqual(width, height)
        points = []
        for path in branding.glyph_paths():
            tokens = branding._tokens(path)
            index = 0
            while index < len(tokens):
                step = 3 if tokens[index] in 'ML' else 8 if tokens[index] == 'A' else 1
                if step > 1:
                    points.append((float(tokens[index + step - 2]), float(tokens[index + step - 1])))
                index += step
        for x, y in points:
            self.assertGreaterEqual(x, left)
            self.assertLessEqual(x, left + width)
            self.assertGreaterEqual(y, top)
            self.assertLessEqual(y, top + height)


class RenameTests(unittest.TestCase):
    def test_rename_covers_every_contract_shape(self):
        source = 'ZCODE_TAP=1;ccode-vansrouter;.zcode;xZCodeY;ZCode'
        self.assertEqual(rebrand.apply(source), 'CCODE_TAP=1;ccode-vansrouter;.ccode;xCCodeY;CCode')

    def test_rename_is_single_pass_and_does_not_double_substitute(self):
        once = rebrand.apply('zcode ZCode ZCODE')
        self.assertEqual(once, 'ccode CCode CCODE')
        self.assertEqual(rebrand.apply(once), once)

    def test_leftover_and_assert_clean_report_a_survivor(self):
        self.assertEqual(rebrand.leftover('x ZCode y zcode z'), ['ZCode', 'zcode'])
        self.assertEqual(rebrand.leftover('CCODE ccode'), [])
        rebrand.assert_clean('CCODE ccode', 'out/main/index.cjs')
        with self.assertRaisesRegex(ValueError, 'Unbranded product name'):
            rebrand.assert_clean('a=`About ZCode`', 'out/renderer/index.html')

    def test_previous_restores_the_upstream_spelling(self):
        self.assertEqual(rebrand.previous('ccode-on-steroids'), 'zcode-on-steroids')
        self.assertEqual(rebrand.previous(rebrand.apply('.zcode ZCode ZCODE')), '.zcode ZCode ZCODE')

    def test_absolute_urls_are_kept_verbatim(self):
        source = 'see https://cdn-zcode.z.ai/zcode/official-plugin/assets/x/icon.png and ZCode'
        self.assertEqual(rebrand.apply(source),
                         'see https://cdn-zcode.z.ai/zcode/official-plugin/assets/x/icon.png and CCode')
        self.assertEqual(rebrand.leftover(source), ['ZCode'])
        self.assertEqual(rebrand.leftover('https://cdn-zcode.z.ai/zcode/x'), [])
        rebrand.assert_clean('fetch("https://cdn-zcode.z.ai/zcode/x")', 'out/main/index.js')

    def test_guard_checks_only_the_upstream_mark(self):
        branding.guard('a=`About CCode`;b=`CCode Protocol`', 't')
        with self.assertRaisesRegex(ValueError, 'Upstream product mark'):
            branding.guard(f'<path d="{branding.LEGACY_MARK_PREFIXES[0]}Z"/>', 't')
        with self.assertRaisesRegex(ValueError, 'mark viewBox'):
            branding.guard(f'<svg viewBox="{branding.LEGACY_VIEW_BOX}"/>', 't')


class LegacyMarkTests(unittest.TestCase):
    def test_inline_mark_is_replaced_in_html_and_jsx(self):
        html = ('<svg width="118"\n          height="100"\n          fill="none"\n'
                '          viewBox="0 0 256 218">\n'
                f'          <path d="{branding.LEGACY_MARK_PREFIXES[0]}L116.48 25.6022Z" />\n'
                f'          <path d="{branding.LEGACY_MARK_PREFIXES[1]}L102.401 217.732H0Z" />\n'
                f'          <path d="{branding.LEGACY_MARK_PREFIXES[2]}L139.65 192.134Z" />\n        </svg>')
        for text in (html, html.replace('d="M', 'd:`M').replace('" />', '`} />')):
            updated = branding._replace_legacy_mark(text)
            for marker in branding.LEGACY_MARK_PREFIXES:
                self.assertNotIn(marker, updated)
            for path in branding.glyph_paths():
                self.assertIn(path, updated)
            self.assertIn('viewBox="' + branding._view_box(branding._glyph_box()) + '"', updated)
            self.assertIn('width="100"', updated)

    def test_guard_rejects_a_surviving_mark(self):
        with self.assertRaisesRegex(ValueError, 'Upstream product mark'):
            branding.guard(f'<path d="{branding.LEGACY_MARK_PREFIXES[0]}Z"/>', 't')
        with self.assertRaisesRegex(ValueError, 'mark viewBox'):
            branding.guard('<svg viewBox="0 0 256 218"/>', 't')


class ScaledPathTests(unittest.TestCase):
    def test_arc_parameters_keep_their_seven_values(self):
        scaled = branding.scaled_path('M0,0 A36.0,36.0 0 0 1 547.0,256.9 Z', 2.0, 10, 20)
        arguments = scaled.split('A')[1].split('Z')[0].split()
        self.assertEqual(arguments[:5], ['72', '72', '0', '0', '1'])
        self.assertEqual(arguments[5:], ['1104', '533.8'])

    def test_lines_are_scaled_and_translated(self):
        self.assertEqual(branding.scaled_path('M160.0,212.0 L510.0,811.0 Z', 0.5, 4, 8),
                         'M84 114L259 413.5Z')


if __name__ == '__main__':
    unittest.main()
