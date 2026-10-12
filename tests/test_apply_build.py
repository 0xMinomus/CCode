import contextlib
import hashlib
import importlib.util
import io
import json
import pathlib
import struct
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
spec = importlib.util.spec_from_file_location('apply_build', ROOT / 'scripts/apply_build.py')
apply_build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(apply_build)


def identity_archive():
    payload = json.dumps({'name': 'zcode-on-steroids'}).encode()
    header = json.dumps({'files': {'package.json': {'offset': '0', 'size': len(payload)}}}).encode()
    padding = (-len(header)) % 4
    size = 4 + len(header) + padding
    return struct.pack('<IIII', 4, 4 + size, size, len(header)) + header + b'\0' * padding + payload


class PromotionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.staged = self.root / 'runtime/build/resources'
        self.target = self.root / 'app/resources'
        self.names = ['app.asar', 'glm/zcode.cjs', 'voice/main.cjs']
        self.previous = {}
        for name in self.names:
            old = ('previous:' + name).encode()
            self.previous[name] = old
            for base in [self.staged, self.target]:
                (base / name).parent.mkdir(parents=True, exist_ok=True)
            (self.target / name).write_bytes(old)
            (self.staged / name).write_bytes(identity_archive() if name == 'app.asar' else ('new:' + name).encode())
        (self.root / 'project.json').write_text(json.dumps({'application_name': 'zcode-on-steroids'}))
        proof = {'application_name': 'zcode-on-steroids', 'sha256': {
            name: hashlib.sha256((self.staged / name).read_bytes()).hexdigest() for name in self.names}}
        (self.staged / 'build-manifest.json').write_text(json.dumps(proof))
        patch = mock.patch.object(apply_build, 'ROOT', self.root)
        patch.start()
        self.addCleanup(patch.stop)

    def test_modified_staged_resource_cannot_replace_current_app(self):
        (self.staged / 'glm/zcode.cjs').write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
            apply_build.main()
        for name in self.names:
            self.assertEqual((self.target / name).read_bytes(), self.previous[name])

    def test_partial_promotion_restores_all_previous_resources(self):
        real_replace = apply_build.os.replace

        def fail_second_resource(source, destination):
            if pathlib.Path(destination) == self.target / 'glm/zcode.cjs':
                raise OSError('simulated filesystem failure')
            return real_replace(source, destination)

        with mock.patch.object(apply_build.os, 'replace', side_effect=fail_second_resource):
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaisesRegex(OSError, 'filesystem failure'):
                apply_build.main()
        for name in self.names:
            self.assertEqual((self.target / name).read_bytes(), self.previous[name])
            self.assertFalse((self.target / name).with_name(pathlib.Path(name).name + '.new').exists())


if __name__ == '__main__':
    unittest.main()
