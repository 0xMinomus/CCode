import hashlib
import json
import pathlib
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'scripts'))
from asar import Archive


class NativeOverlayTests(unittest.TestCase):
    def source(self, directory):
        path = directory / 'original.asar'
        header = {'files': {'main.js': {'offset': '0', 'size': 2, 'integrity': Archive.integrity(b'js')},
                            'linux.node': {'size': 3, 'unpacked': True}}}
        encoded = json.dumps(header).encode()
        padding = (-len(encoded)) % 4
        size = 4 + len(encoded) + padding
        path.write_bytes(struct.pack('<IIII', 4, 4 + size, size, len(encoded)) + encoded + bytes(padding) + b'js')
        return Archive(path)

    def test_windows_native_overlay_preserves_packed_data_and_header_integrity(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            archive = self.source(root)
            name = 'node_modules/node-pty/prebuilds/win32-x64/conpty.node'
            target = root / 'candidate.asar'
            archive.write(target, {}, remove=['linux.node'], unpacked={name: b'MZnative'})
            result = Archive(target)
            self.assertEqual(result.read('main.js'), b'js')
            entries = dict(result.all_entries())
            self.assertNotIn('linux.node', entries)
            self.assertTrue(entries[name]['unpacked'])
            self.assertNotIn('offset', entries[name])
            self.assertEqual(entries[name]['integrity']['hash'], hashlib.sha256(b'MZnative').hexdigest())
            self.assertEqual(pathlib.Path(str(target) + '.unpacked', name).read_bytes(), b'MZnative')
            self.assertEqual(archive.read('main.js'), b'js')
            self.assertIn('linux.node', dict(archive.all_entries()))

    def test_overlay_rejects_traversal_conflicts_and_destination_symlinks(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            archive = self.source(root)
            for name in ('../escape', '/absolute', 'C:/drive', 'a\\escape', 'a/../escape', '.. /escape', 'a./escape', 'NUL.node', 'main.js', 'main.js/child', 'MAIN.JS', 'MAIN.JS/child'):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    archive.write(root / 'candidate.asar', {}, unpacked={name: b'x'})
            target = root / 'linked.asar'
            pathlib.Path(str(target) + '.unpacked').symlink_to(root, target_is_directory=True)
            with self.assertRaises(ValueError):
                archive.write(target, {}, unpacked={'escape.node': b'x'})
            self.assertFalse((root / 'escape.node').exists())

    def test_existing_replace_rename_and_transform_contract(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            archive = self.source(root)
            archive.write(root / 'changed.asar', {'main.js': b'new'}, renames={'main.js': 'dir/app.js'}, transform=lambda name, data: data.upper())
            changed = Archive(root / 'changed.asar')
            self.assertEqual(changed.read('dir/app.js'), b'NEW')
            self.assertIn('linux.node', dict(changed.all_entries()))
            self.assertEqual(changed.index['dir/app.js']['integrity'], Archive.integrity(b'NEW'))


if __name__ == '__main__':
    unittest.main()
