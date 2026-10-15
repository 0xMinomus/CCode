import hashlib
import json
import pathlib
import struct
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import pack_windows


class ExecutableIntegrityTests(unittest.TestCase):
    def asar(self, path, header):
        encoded = json.dumps(header).encode()
        padding = (-len(encoded)) % 4
        size = 4 + len(encoded) + padding
        path.write_bytes(struct.pack('<IIII', 4, 4 + size, size, len(encoded)) + encoded + bytes(padding))
        return hashlib.sha256(encoded).hexdigest()

    def test_stale_disabled_vendor_hash_is_recorded_and_replaced_without_flipping_fuses(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            source, candidate, executable = root / 'source.asar', root / 'candidate.asar', root / 'CCode.exe'
            source_hash = self.asar(source, {'files': {}})
            candidate_hash = self.asar(candidate, {'files': {'native.node': {'size': 0, 'unpacked': True}}})
            old = '0' * 64
            record = json.dumps([{'file': 'resources\\app.asar', 'alg': 'SHA256', 'value': old}], separators=(',', ':')).encode()
            data = bytearray(1024)
            wire = pack_windows.FUSE_SENTINEL + b'\x01\x09101100011'
            data[256:256 + len(wire)] = wire
            data[512:512 + len(record)] = record
            executable.write_bytes(data)
            entries = [(('INTEGRITY', 'ELECTRONASAR', 1033), 512, len(record), 0)]
            with mock.patch.object(pack_windows, 'pe_resources', return_value=(64, 128, entries)):
                evidence = pack_windows.patch_executable(executable, source, candidate, root)
            changed = executable.read_bytes()
            result = json.loads(changed[512:512 + len(record)])
            self.assertEqual(result[0]['value'], candidate_hash)
            self.assertEqual(changed[256:256 + len(wire)], wire)
            self.assertFalse(evidence['vendor_embedded_header_matches'])
            self.assertEqual(evidence['vendor_actual_header_sha256'], source_hash)
            self.assertEqual(evidence['vendor_embedded_header_sha256'], old)

    def test_enabled_validation_with_stale_vendor_hash_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            source = root / 'source.asar'
            self.asar(source, {'files': {}})
            record = json.dumps([{'file': 'resources\\app.asar', 'alg': 'SHA256', 'value': '0' * 64}]).encode()
            data = bytearray(1024)
            wire = pack_windows.FUSE_SENTINEL + b'\x01\x09101110011'
            data[256:256 + len(wire)] = wire
            data[512:512 + len(record)] = record
            executable = root / 'CCode.exe'
            executable.write_bytes(data)
            entries = [(('INTEGRITY', 'ELECTRONASAR', 1033), 512, len(record), 0)]
            with mock.patch.object(pack_windows, 'pe_resources', return_value=(64, 128, entries)):
                with self.assertRaisesRegex(ValueError, 'enables validation'):
                    pack_windows.patch_executable(executable, source, source, root)
            self.assertEqual(executable.read_bytes(), data)


if __name__ == '__main__':
    unittest.main()
