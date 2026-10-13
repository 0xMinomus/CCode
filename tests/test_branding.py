import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from local_only import branding


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
        self.assertNotIn('ZCode', component)
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
    def test_visible_copy_is_renamed(self):
        self.assertEqual(branding._rename('title:"About ZCode"', 't'), 'title:"About CCode"')
        self.assertEqual(branding._rename('`ZCode / ${hd(F)}`', 't'), '`CCode / ${hd(F)}`')

    def test_legacy_product_name_collapses(self):
        self.assertEqual(branding._rename('`ZCode on Steroids`', 't'), '`CCode`')

    def test_identifiers_symbols_and_keys_are_untouched(self):
        source = 'a=ti.ZCodeTask;b=`settings.zcodeMcp`;c={"toggleZCodeStdioTap":"ZCode"}'
        self.assertEqual(branding._rename(source, 't'), source.replace(':"ZCode"', ':"CCode"'))
        self.assertEqual(branding._rename('a=`ZCode Protocol/1`;b=`ZCode`', 't'), 'a=`ZCode Protocol/1`;b=`CCode`')
        self.assertEqual(branding._rename('q(o,"ZCode","Local Storage","leveldb");b="ZCode"', 't'),
                         'q(o,"ZCode","Local Storage","leveldb");b="CCode"')

    def test_rename_refuses_a_bundle_without_the_product_name(self):
        with self.assertRaisesRegex(ValueError, 'No product name to rename'):
            branding._rename('const a=1;', 't')

    def test_guard_reports_unprotected_leftovers(self):
        branding.guard('a=`CCode`;b=`ZCode Protocol`', 't')
        with self.assertRaisesRegex(ValueError, 'Unbranded product name'):
            branding.guard('a=`About ZCode`', 't')

    def test_regex_literals_and_comments_are_not_strings(self):
        source = 'const re=/[\'"]ZCode/;// "ZCode"\nconst s="ZCode";'
        self.assertEqual(branding._rename(source, 't'), 'const re=/[\'"]ZCode/;// "ZCode"\nconst s="CCode";')


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
