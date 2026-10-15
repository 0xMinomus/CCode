#!/usr/bin/python3
"""Build the Linux release artifacts (AppImage, .deb, .rpm) from the applied AppDir.

The merged release tree mirrors this repository closely enough that the packaged app
resolves what it looks for at runtime:

    <prefix>/app/                     AppDir (Electron binary + resources)
    <prefix>/services/<component>/    voice, desktop (screen-mcp), model-sync
    <prefix>/scripts/data_backup.py   imported by model-sync
    <prefix>/project.json             voice locates the project root by walking up to it
    <prefix>/ccode                    launcher (same namespace contract as scripts/run.sh)

Nothing here mutates the working tree: the stage is built with hardlinks and every file
this script edits is written through a replacement inode.
"""
import argparse
import datetime
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
APPLIED = ROOT / 'app'
STAGED = ROOT / 'runtime/build/resources'
DEFAULT_OUT = ROOT / 'runtime/release'
INPUT_DIR = ROOT / 'runtime/release-input'
PROJECT = json.loads((ROOT / 'project.json').read_text())
UPSTREAM_VERSION = PROJECT['upstream_version']
DEFAULT_VERSION = '1.0.0'
HOMEPAGE = 'https://github.com/0xMinomus/CCode'
MAINTAINER = 'CCode maintainers <0xMinomus@users.noreply.github.com>'
PREFIX = pathlib.Path('/opt/ccode')
COMPONENTS = {'model-sync': 'services/model-sync', 'voice': 'services/voice', 'desktop': 'services/desktop'}
ALL_COMPONENTS = ('model-sync', 'voice', 'desktop')
ICON_SIZES = (16, 24, 32, 48, 64, 128, 256, 512, 1024)
RUNTIME_NAME = 'runtime-x86_64'
RUNTIME_URL = 'https://github.com/AppImage/type2-runtime/releases/download/continuous/' + RUNTIME_NAME
RUNTIME_SHA256 = '156f4bdbde9c52d01814600013e0a273f0118dc2de98975f3c8c63427ec79074'
LAUNCHER = '''#!/usr/bin/env bash
# CCode launcher. Mirrors the standalone namespace contract of scripts/run.sh: private
# data directories under one root, the CCode_* environment the app reads, and the shared
# operations lock that keeps a backup or apply from running against a live app.
set -euo pipefail
here="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
root="${CCODE_STANDALONE_ROOT:-$HOME/.local/share/ccode}"
case "$root" in
  /*) ;;
  *) root="$PWD/$root" ;;
esac
case "$root" in
  /|"$HOME") echo "ccode: refusing an unsafe namespace root: $root" >&2; exit 2 ;;
esac
umask 077
mkdir -p -m 700 "$root/data/.ccode/v2" "$root/data/.ccode/cli/db" "$root/electron"
export CCODE_STANDALONE_ROOT="$root"
export CCODE_LOCAL_ONLY=1
export CCODE_DESKTOP_APPLICATION_NAME=ccode
export CCODE_DATA_BASE_DIR="$root/data"
export CCODE_DESKTOP_HOME_DIR="$root/data"
export DESKTOP_HOME_DIR="$root/data"
export CCODE_DESKTOP_USER_DATA_DIR="$root/electron"
export CCODE_STORAGE_DIR="$root/data/.ccode"
export STORAGE_DIR="$root/data/.ccode"
export CCODE_SESSION_DB_PATH="$root/data/.ccode/cli/db/db.sqlite"
lock="$(dirname "$root")/.$(basename "$root").operations.lock"
exec /usr/bin/flock --shared "$lock" "$here/app/ccode" "$@"
'''
WRAPPER = '''#!/bin/sh
# CCode entry point for package installs; the launcher lives with the application files.
exec /opt/ccode/ccode "$@"
'''
UNINSTALL_NOTE = '''# Uninstalling CCode

Remove the application files with the package manager, then delete your data:

```sh
sudo dnf remove ccode        # or: sudo apt remove ccode
rm -rf ~/.local/share/ccode  # tasks, sessions, provider keys, voice settings, MCP config
```

The AppImage is a single file: delete it and, if you want the data gone, the namespace above.
Data removal is irreversible; run `python3 scripts/data_backup.py backup --root ~/.local/share/ccode`
from a source checkout first if you want a snapshot.
'''


def run(command, **kwargs):
    kwargs.setdefault('check', True)
    return subprocess.run([str(part) for part in command], cwd=ROOT, **kwargs)


def sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def copy_tree(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(destination, ignore_errors=True)
    run(['cp', '-a', str(source), str(destination)])


def normalize_modes(tree):
    """Make the tree readable by the user who installs it.

    The working tree is written with a 077 umask, so `app.asar` and the local service
    state are owner-only; a package built from those modes would install an application
    an ordinary user cannot read. Symlinks are left alone: chmod follows them.
    """
    for entry in sorted(tree.rglob('*')):
        if entry.is_symlink():
            continue
        try:
            if entry.is_dir():
                os.chmod(entry, 0o755)
            elif entry.is_file():
                os.chmod(entry, 0o755 if entry.stat().st_mode & 0o111 else 0o644)
        except FileNotFoundError:
            continue


def strip_local_state(tree):
    """Drop per-machine state and refuse to ship anything that holds user keys."""
    removable = ('services/model-sync/backups', 'services/model-sync/catalog.json',
                 'services/model-sync/state.json', 'services/model-sync/sync.lock')
    for relative in removable:
        path = tree / relative
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)
    offenders = sorted(str(path) for path in tree.rglob('provider_config*.json'))
    offenders += sorted(str(path) for pattern in ('services/*/state.json', 'services/*/sync.lock',
                                                  'services/*/backups')
                        for path in tree.glob(pattern))
    if offenders:
        raise SystemExit('Local state would ship in the release tree:\n  '
                         + '\n  '.join(offenders[:10]))


def sanitize(tree):
    """Drop build caches and relocatable-venv leftovers."""
    for cache in sorted(tree.rglob('__pycache__'), reverse=True):
        shutil.rmtree(cache, ignore_errors=True)
    for compiled in tree.rglob('*.pyc'):
        compiled.unlink(missing_ok=True)
    for venv in sorted(tree.glob('services/*/.venv')):
        runner = venv / 'bin'
        if not runner.is_dir():
            continue
        # The app spawns these interpreters by path; console scripts and activators only
        # carry the build machine's absolute paths.
        for script in runner.iterdir():
            if script.name not in ('python', 'python3', 'python3.14'):
                script.unlink(missing_ok=True)
        config = venv / 'pyvenv.cfg'
        if config.is_file():
            kept = [line for line in config.read_text().splitlines()
                    if not line.startswith(('command =', 'executable ='))]
            config.write_text('\n'.join(kept) + '\n')


def assert_no_personal_paths(tree):
    """Refuse to ship the build machine's own paths, exactly like the release checklist."""
    marker = str(pathlib.Path.home())
    found = subprocess.run(['grep', '-rlF', '-e', marker, str(tree)], capture_output=True, text=True)
    if found.returncode not in (0, 1):
        raise SystemExit(f'Release path scan failed: {found.stderr.strip()}')
    offenders = [line for line in found.stdout.splitlines() if line.strip()]
    if offenders:
        raise SystemExit('Personal paths would ship in the release tree:\n  '
                         + '\n  '.join(offenders[:10]))


def copy_tree(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    linked = subprocess.run(['cp', '-al', str(source), str(destination)], capture_output=True)
    if linked.returncode != 0:
        # A failed hardlink pass still leaves a partial directory behind; a fallback copy
        # would nest the source inside it.
        shutil.rmtree(destination, ignore_errors=True)
        run(['cp', '-a', str(source), str(destination)])


def write_launchers(tree):
    launcher = tree / 'ccode'
    launcher.write_text(LAUNCHER)
    launcher.chmod(0o755)


def write_desktop_entries(tree, version):
    entry = ('[Desktop Entry]\n'
             'Name=CCode\n'
             'Exec=AppRun %U\n'
             'Terminal=false\n'
             'Type=Application\n'
             'Icon=ccode\n'
             'StartupWMClass=ccode\n'
             f'X-AppImage-Version={version}\n'
             f'Comment=CCode {version}\n'
             'MimeType=x-scheme-handler/ccode;\n'
             'Categories=Development;\n')
    (tree / 'ccode.desktop').write_text(entry)
    # The AppDir ships its own desktop entry (AppImage desktop integration reads it) and
    # the upstream copy still advertises the pre-rebrand URL scheme.
    (tree / 'app/ccode.desktop').write_text(entry)
    tree_icons = tree / 'usr/share/icons/hicolor/1024x1024/apps'
    tree_icons.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / 'assets/icons/ccode-1024.png', tree_icons / 'ccode.png')
    os.chmod(tree_icons / 'ccode.png', 0o644)
    for alias in ('.DirIcon', 'ccode.png'):
        link = tree / alias
        link.unlink(missing_ok=True)
        link.symlink_to('usr/share/icons/hicolor/1024x1024/apps/ccode.png')


def stage_system(destination, version):
    """Files that belong to the system layout, kept out of the AppDir."""
    if destination.exists():
        shutil.rmtree(destination)
    entry = ('[Desktop Entry]\n'
             'Name=CCode\n'
             'Exec=/usr/bin/ccode %U\n'
             'Terminal=false\n'
             'Type=Application\n'
             'Icon=ccode\n'
             'StartupWMClass=ccode\n'
             f'Comment=CCode {version}\n'
             'MimeType=x-scheme-handler/ccode;\n'
             'Categories=Development;\n')
    applications = destination / 'usr/share/applications'
    applications.mkdir(parents=True)
    (applications / 'ccode.desktop').write_text(entry)
    icons = destination / 'usr/share/icons/hicolor'
    for size in ICON_SIZES:
        target = icons / f'{size}x{size}/apps/ccode.png'
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / 'assets/icons' / f'ccode-{size}.png', target)
        os.chmod(target, 0o644)
    binary = destination / 'usr/bin'
    binary.mkdir(parents=True)
    (binary / 'ccode').write_text(WRAPPER)
    os.chmod(binary / 'ccode', 0o755)
    docs = destination / 'usr/share/doc/ccode'
    docs.mkdir(parents=True)
    for source, name in ((ROOT / 'LICENSE', 'copyright'), (ROOT / 'LICENSE', 'LICENSE'),
                         (ROOT / 'NOTICE.md', 'NOTICE.md'),
                         (ROOT / 'docs/THIRD_PARTY.md', 'THIRD_PARTY.md'),
                         (destination.parent / 'CCode/UNINSTALL.md', 'UNINSTALL.md')):
        if source.is_file():
            shutil.copy2(source, docs / name)
            os.chmod(docs / name, 0o644)
    return destination


def write_metadata(tree, version):
    (tree / 'project.json').write_text(json.dumps({
        'project': 'ccode',
        'upstream_version': UPSTREAM_VERSION,
        'upstream_artifact': PROJECT['baseline'],
        'application_name': PROJECT['application_name'],
        'release_version': version,
    }, indent=2) + '\n')
    docs = tree / 'docs'
    docs.mkdir(exist_ok=True)
    shutil.copy2(ROOT / 'docs/THIRD_PARTY.md', docs / 'THIRD_PARTY.md')
    os.chmod(docs / 'THIRD_PARTY.md', 0o644)
    for name in ('LICENSE', 'NOTICE.md'):
        shutil.copy2(ROOT / name, tree / name)
        os.chmod(tree / name, 0o644)
    (tree / 'UNINSTALL.md').write_text(UNINSTALL_NOTE)


def stage_tree(destination, components, version):
    if destination.exists():
        shutil.rmtree(destination)
    copy_tree(APPLIED, destination / 'app')
    for name in components:
        copy_tree(ROOT / COMPONENTS[name], destination / COMPONENTS[name])
    if 'model-sync' in components:
        (destination / 'scripts').mkdir(exist_ok=True)
        shutil.copy2(ROOT / 'scripts/data_backup.py', destination / 'scripts/data_backup.py')
        os.chmod(destination / 'scripts/data_backup.py', 0o644)
    write_launchers(destination)
    write_desktop_entries(destination, version)
    write_metadata(destination, version)
    strip_local_state(destination)
    sanitize(destination)
    normalize_modes(destination)
    assert_no_personal_paths(destination)
    return destination


def fetch_runtime():
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    runtime = INPUT_DIR / RUNTIME_NAME
    if not runtime.is_file() or sha256(runtime) != RUNTIME_SHA256:
        run(['curl', '-fsSL', '-o', str(runtime), RUNTIME_URL])
    if sha256(runtime) != RUNTIME_SHA256:
        raise SystemExit(f'AppImage runtime checksum mismatch: {runtime}')
    runtime.chmod(0o755)
    return runtime


def build_appimage(tree, out, version):
    appdir = out / 'CCode.AppDir'
    if appdir.exists():
        shutil.rmtree(appdir)
    os.replace(tree, appdir)
    shutil.copy2(appdir / 'ccode', appdir / 'AppRun')
    os.chmod(appdir / 'AppRun', 0o755)
    payload = out / 'payload.squashfs'
    run(['mksquashfs', str(appdir), str(payload), '-root-owned', '-noappend',
         '-comp', 'zstd', '-no-progress'])
    artifact = out / f'CCode-{version}-x86_64.AppImage'
    with open(artifact, 'wb') as target, open(fetch_runtime(), 'rb') as runtime, open(payload, 'rb') as body:
        shutil.copyfileobj(runtime, target)
        shutil.copyfileobj(body, target)
    artifact.chmod(0o755)
    payload.unlink()
    return artifact


def build_tree_payload(tree, system, out):
    """Lay out the filesystem tree shared by the .deb and .rpm packages."""
    package = out / 'package'
    if package.exists():
        shutil.rmtree(package)
    (package / 'opt').mkdir(parents=True)
    os.replace(tree, package / 'opt/ccode')
    (package / 'opt/ccode/AppRun').unlink(missing_ok=True)
    os.replace(system / 'usr', package / 'usr')
    shutil.rmtree(system, ignore_errors=True)
    return package


def build_deb(package, out, version, installed_size_kb):
    control = package / 'DEBIAN'
    control.mkdir(exist_ok=True)
    (control / 'control').write_text(
        '\n'.join([
            'Package: ccode',
            f'Version: {version}',
            'Section: devel',
            'Priority: optional',
            'Architecture: amd64',
            f'Maintainer: {MAINTAINER}',
            f'Installed-Size: {installed_size_kb}',
            'Depends: python3 (>= 3.10)',
            'Recommends: ffmpeg, pipewire-utils, python3-gobject, gstreamer1-plugins-base',
            f'Homepage: {HOMEPAGE}',
            'Description: CCode, a local-first coding agent workspace',
            ' An unofficial Apache-2.0 fork of ZCode with no account requirement: your tasks,',
            ' sessions, provider keys, and local services stay in ~/.local/share/ccode.',
        ]) + '\n')
    (control / 'postinst').write_text(
        '#!/bin/sh\nset -e\n[ -x /usr/bin/update-desktop-database ] && update-desktop-database -q || true\n'
        '[ -x /usr/bin/gtk-update-icon-cache ] && gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true\n'
        'exit 0\n')
    os.chmod(control / 'postinst', 0o755)
    artifact = out / f'ccode_{version}_amd64.deb'
    run(['dpkg-deb', '--build', '--root-owner-group', str(package), str(artifact)])
    return artifact


def build_rpm(package, out, version, installed_size_kb):
    rpm_version = version.replace('+', '.')
    spec = out / 'ccode.spec'
    spec.write_text(f'''%global __brp_check_rpaths %{{nil}}
%global __brp_mangle_shebangs %{{nil}}
Name: ccode
Version: {rpm_version}
Release: 1%{{?dist}}
Summary: Local-first coding agent workspace (unofficial ZCode fork)
License: Apache-2.0
URL: {HOMEPAGE}
AutoReqProv: no
Requires: python3 >= 3.10
Recommends: ffmpeg
Recommends: pipewire-utils
Recommends: python3-gobject
Recommends: gstreamer1-plugins-base
BuildArch: x86_64

%description
An unofficial Apache-2.0 fork of ZCode with no account requirement: tasks, sessions,
provider keys, and local services stay inside the user's own data namespace.

%install
mkdir -p %{{buildroot}}
cp -a {package}/opt %{{buildroot}}/opt
cp -a {package}/usr %{{buildroot}}/usr

%files
/opt/ccode
/usr/bin/ccode
/usr/share/applications/ccode.desktop
/usr/share/icons/hicolor
/usr/share/doc/ccode

%posttrans
[ -x /usr/bin/update-desktop-database ] && update-desktop-database -q || true
[ -x /usr/bin/gtk-update-icon-cache ] && gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
exit 0

%changelog
* {datetime.date.today().strftime('%a %b %d %Y')} {MAINTAINER} - {rpm_version}-1
- Linux release built from the applied AppDir, upstream {UPSTREAM_VERSION}.
''')
    top = out / 'rpmbuild'
    artifact_dir = top / 'RPMS/x86_64'
    if top.exists():
        shutil.rmtree(top)
    run(['rpmbuild', '-bb', '--define', f'_topdir {top}', '--define', '_build_id_links none',
         '--buildroot', str(top / 'buildroot'), str(spec)])
    produced = sorted(artifact_dir.glob('ccode-*.rpm'))
    if len(produced) != 1:
        raise SystemExit(f'rpmbuild produced {len(produced)} artifacts')
    artifact = out / f'ccode-{version}-1.x86_64.rpm'
    shutil.move(str(produced[0]), artifact)
    return artifact


def installed_size_kb(package):
    total = 0
    for entry in package.rglob('*'):
        if entry.is_symlink() or not entry.is_file():
            continue
        total += entry.stat().st_size
    return max(1, total // 1024)


def write_release_notes(out, version, components, artifacts):
    lines = [
        f'# CCode {version} (Linux x86_64)',
        '',
        f'Upstream artifact: ZCode {UPSTREAM_VERSION} ({PROJECT["baseline"]})',
        'License: Apache-2.0. This is an unofficial fork; ZCode is not affiliated with it.',
        '',
        '## Contents',
        '',
        '- The desktop application and its bundled agent backend, skills, commands, MCP catalog.',
        f'- Optional services: {", ".join(components) if components else "none"}.',
        '',
        '## Requirements',
        '',
        '- Linux x86_64 with a desktop session; Python 3.10+ for the optional services.',
        '- Voice input needs PipeWire tools (`pw-record`) plus `ffmpeg`.',
        '- Computer Use needs the system layer that cannot be bundled: PyGObject, GStreamer',
        '  with base and PipeWire plugins, PipeWire, a portal backend, and `wl-clipboard`.',
        '',
        '## Data',
        '',
        'Everything lives in `~/.local/share/ccode`. Upstream data directories are never read.',
        '',
        '## Running the AppImage',
        '',
        'The AppImage mounts itself and starts CCode directly. Where AppImageLauncher is',
        'installed it also moves the file into `~/Applications` and registers its own desktop',
        'entry and icons (an `appimagekit_*` entry under `~/.local/share`), which is what',
        'AppImageLauncher does for every AppImage on that machine.',
        '',
        '## Artifacts',
        '',
    ]
    for artifact, digest in artifacts:
        lines.append(f'- `{artifact}`  sha256 `{digest}`')
    lines += ['', 'Verify with `sha256sum -c SHA256SUMS`.', '']
    (out / 'release-notes.md').write_text('\n'.join(lines))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', default=DEFAULT_VERSION)
    parser.add_argument('--components', default=','.join(ALL_COMPONENTS))
    parser.add_argument('--formats', default='appimage,deb,rpm')
    parser.add_argument('--out', type=pathlib.Path, default=DEFAULT_OUT)
    parser.add_argument('--keep-stage', action='store_true')
    args = parser.parse_args()

    components = tuple(name for name in args.components.split(',') if name)
    unknown = [name for name in components if name not in COMPONENTS]
    if unknown:
        raise SystemExit(f'Unknown components: {", ".join(unknown)}')
    formats = tuple(name for name in args.formats.split(',') if name)
    unknown = [name for name in formats if name not in ('appimage', 'deb', 'rpm')]
    if unknown:
        raise SystemExit(f'Unknown formats: {", ".join(unknown)}')
    for name in ('mksquashfs', 'dpkg-deb', 'rpmbuild'):
        if shutil.which(name) is None:
            raise SystemExit(f'{name} is required; install squashfs-tools, dpkg, and rpm-build')

    if not (STAGED / 'app.asar').is_file():
        raise SystemExit('No staged build; run `make build` first')
    for staged, applied in ((STAGED / 'app.asar', APPLIED / 'resources/app.asar'),
                            (STAGED / 'glm/ccode.cjs', APPLIED / 'resources/glm/ccode.cjs')):
        if sha256(staged) != sha256(applied):
            raise SystemExit(f'{applied.name} differs between app/ and the staged build; run `make apply`')

    version = f'{args.version}+upstream.{UPSTREAM_VERSION}'
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    print(f'Staging CCode {version} with components: {", ".join(components) or "none"}')
    tree = stage_tree(out / 'CCode', components, version)
    artifacts = []
    if 'appimage' in formats:
        artifact = build_appimage(tree, out, version)
        artifacts.append(artifact)
        print(f'AppImage: {artifact.name} ({artifact.stat().st_size / (1 << 20):.1f} MiB)')
        tree = None
    if 'deb' in formats or 'rpm' in formats:
        if tree is None:
            tree = stage_tree(out / 'CCode', components, version)
        system = stage_system(out / 'system', version)
        package = build_tree_payload(tree, system, out)
        size_kb = installed_size_kb(package)
        if 'deb' in formats:
            artifacts.append(build_deb(package, out, version, size_kb))
            print(f'deb: {artifacts[-1].name} ({artifacts[-1].stat().st_size / (1 << 20):.1f} MiB)')
        if 'rpm' in formats:
            artifacts.append(build_rpm(package, out, version, size_kb))
            print(f'rpm: {artifacts[-1].name} ({artifacts[-1].stat().st_size / (1 << 20):.1f} MiB)')
        if not args.keep_stage:
            shutil.rmtree(package)
    if not args.keep_stage and tree is not None:
        shutil.rmtree(tree, ignore_errors=True)
    if not artifacts:
        raise SystemExit('Nothing was built')
    digests = [(artifact.name, sha256(artifact)) for artifact in artifacts]
    (out / 'SHA256SUMS').write_text(''.join(f'{digest}  {name}\n' for name, digest in digests))
    write_release_notes(out, version, components, digests)
    print(f'Wrote SHA256SUMS and release-notes.md in {out}')


if __name__ == '__main__':
    main()
