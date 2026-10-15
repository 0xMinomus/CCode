#!/usr/bin/env python3
"""Package the downloadable n8n plugin, including its locked offline runtime."""
import argparse
import hashlib
import json
import pathlib
import shutil
import stat
import subprocess
import tempfile
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'src/plugins/n8n'


def pack(output):
    package = json.loads((SOURCE / 'package.json').read_text())
    manifest = json.loads((SOURCE / '.ccode-plugin/plugin.json').read_text())
    if package['version'] != manifest['version'] or package['dependencies'] != {'n8n-mcp': '2.92.1'}:
        raise ValueError('Plugin version and pinned dependency must match the release contract')
    skills = list((SOURCE / 'skills').glob('*/SKILL.md'))
    if len(skills) != 15:
        raise ValueError('The n8n plugin must include all 15 skills')
    output.mkdir(parents=True, exist_ok=True)
    artifact = output / f"ccode-n8n-plugin-{package['version']}.zip"
    with tempfile.TemporaryDirectory(prefix='ccode-n8n-pack-') as temporary:
        stage = pathlib.Path(temporary) / 'n8n'
        shutil.copytree(SOURCE, stage, ignore=shutil.ignore_patterns('node_modules', '__pycache__', '*.pyc'))
        shutil.copyfile(ROOT / 'LICENSE', stage / 'LICENSE')
        subprocess.run(['npm', 'ci', '--omit=dev', '--ignore-scripts', '--no-audit', '--no-fund'],
                       cwd=stage, check=True, timeout=300)
        if not (stage / 'node_modules/n8n-mcp/dist/mcp/stdio-wrapper.js').is_file():
            raise ValueError('Locked n8n MCP executable missing')
        # Native zip installation rejects symlinks. npm executable shims are not
        # used: Electron loads the entrypoint and its dependencies directly.
        with zipfile.ZipFile(artifact, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for source in sorted(stage.rglob('*')):
                relative = source.relative_to(stage)
                if '.bin' in relative.parts or source.is_dir():
                    continue
                if source.is_symlink():
                    raise ValueError(f'Unsupported plugin symlink: {relative}')
                info = zipfile.ZipInfo(relative.as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
                info.create_system = 3
                mode = 0o755 if source.stat().st_mode & stat.S_IXUSR else 0o644
                info.external_attr = (stat.S_IFREG | mode) << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, source.read_bytes(), compresslevel=9)
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    print(json.dumps({'path': str(artifact), 'sizeBytes': artifact.stat().st_size, 'sha256': digest}, indent=2))
    return artifact, digest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=pathlib.Path, default=ROOT / 'runtime/release-plugin')
    pack(parser.parse_args().output.resolve())
