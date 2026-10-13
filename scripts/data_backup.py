#!/usr/bin/python3
"""Private standalone snapshots; SQLite uses its backup API, restore is offline."""
import argparse
import contextlib
import datetime
import fcntl
import hashlib
import json
import os
import pathlib
import shutil
import sqlite3
import stat
import tempfile
import urllib.parse

PROJECT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_ROOT = pathlib.Path.home() / '.local/share/ccode'
# Namespace of the ZCode-era standalone variant; `install_local.py` migrates it once.
DEFAULT_LEGACY_ROOT = pathlib.Path.home() / '.local/share/zcode-on-steroids'
TRANSIENT = {'SingletonLock', 'SingletonSocket', 'SingletonCookie'}


def safe_path(value):
    path = pathlib.Path(os.path.abspath(os.path.expanduser(str(value))))
    for component in (path, *path.parents):
        if component.is_symlink():
            raise ValueError(f'Symlink path refused: {component}')
    return path


def namespace_root(value=None):
    path = safe_path(value or os.environ.get('ZCODE_STANDALONE_ROOT') or DEFAULT_ROOT)
    if path in (pathlib.Path('/'), pathlib.Path.home(), PROJECT):
        raise ValueError('Refusing an unsafe namespace root')
    return path


def private_dir(path):
    path = safe_path(path)
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)
    return path


def atomic_json(path, value):
    safe_path(path)
    private_dir(path.parent)
    fd, name = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(name, 0o600)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


@contextlib.contextmanager
def namespace_lock(root, exclusive=True):
    safe_path(root)
    root.parent.mkdir(parents=True, exist_ok=True)
    path = safe_path(root.parent / ('.' + root.name + '.operations.lock'))
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, 'a') as lock:
        try:
            fcntl.flock(lock, (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH) | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError('Standalone app or another storage operation is active') from error
        yield


def assert_offline(root):
    """Refuse when a process uses this namespace, including a direct-launched default app."""
    executable = str((PROJECT / 'app/ccode').resolve())
    marker = ('ZCODE_STANDALONE_ROOT=' + str(root)).encode()
    default = pathlib.Path(DEFAULT_ROOT)
    same_default = pathlib.Path(root) == default
    for process in pathlib.Path('/proc').iterdir():
        if not process.name.isdigit() or int(process.name) == os.getpid():
            continue
        try:
            if marker in (process / 'environ').read_bytes().split(b'\0'):
                raise ValueError('Close the standalone app before restoring data')
            if not same_default or os.readlink(process / 'exe') != executable:
                continue
            overrides = [value for value in (process / 'environ').read_bytes().split(b'\0')
                         if value.startswith(b'ZCODE_STANDALONE_ROOT=')]
            if not overrides:
                # A direct launch sets no environment, so it always uses the default root.
                raise ValueError('Close the standalone app before restoring data')
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            continue


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def is_sqlite(path):
    with path.open('rb') as stream:
        return stream.read(16) == b'SQLite format 3\x00'


def database(path):
    return sqlite3.connect('file:' + urllib.parse.quote(str(path), safe='/') + '?mode=ro', uri=True, timeout=10)



def snapshot_database(source, target):
    """Copy a live SQLite database through the backup API into one standalone file."""
    with contextlib.closing(database(source)) as incoming, contextlib.closing(sqlite3.connect(target)) as outgoing:
        incoming.backup(outgoing)
        outgoing.execute('PRAGMA journal_mode=DELETE')
        outgoing.commit()
    for suffix in ('-wal', '-shm', '-journal'):
        target.with_name(target.name + suffix).unlink(missing_ok=True)


def check_database(path):
    with contextlib.closing(database(path)) as connection:
        if connection.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
            raise ValueError(f'SQLite integrity check failed: {path.name}')


def tree_entries(root, skip_transient=False):
    entries = []
    for parent, dirs, files in os.walk(root, followlinks=False):
        for name in sorted(dirs + files):
            path = pathlib.Path(parent) / name
            relative = path.relative_to(root).as_posix()
            mode = path.lstat().st_mode
            if skip_transient and name in TRANSIENT and relative.startswith('electron/'):
                if name in dirs:
                    dirs.remove(name)
                continue
            if stat.S_ISLNK(mode) or not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
                raise ValueError(f'Unsafe snapshot entry: {relative}')
            entries.append((relative, path, mode))
    return sorted(entries)


def validate_snapshot(snapshot):
    snapshot = safe_path(snapshot)
    tree_entries(snapshot)
    manifest = json.loads((snapshot / 'manifest.json').read_text())
    if not isinstance(manifest, dict) or manifest.get('format') != 1 or not isinstance(manifest.get('entries'), list):
        raise ValueError('Unsupported snapshot manifest')
    files = snapshot / 'files'
    if not files.is_dir():
        raise ValueError('Snapshot files directory is missing')
    expected = {}
    for entry in manifest['entries']:
        if not isinstance(entry, dict):
            raise ValueError('Invalid snapshot entry')
        relative = entry.get('path')
        if not isinstance(relative, str):
            raise ValueError('Invalid snapshot path')
        rel = pathlib.PurePosixPath(relative)
        if rel.is_absolute() or '..' in rel.parts or not rel.parts or rel.as_posix() != relative or relative in expected:
            raise ValueError('Unsafe or duplicate snapshot path')
        kind = entry.get('kind')
        if kind not in ('directory', 'file', 'sqlite'):
            raise ValueError('Invalid snapshot entry kind')
        path = safe_path(files / relative)
        if kind == 'directory':
            if not path.is_dir():
                raise ValueError(f'Missing snapshot directory: {relative}')
        else:
            if not path.is_file() or digest(path) != entry.get('sha256') or path.stat().st_size != entry.get('size'):
                raise ValueError(f'Snapshot checksum mismatch: {relative}')
            if kind == 'sqlite':
                check_database(path)
        expected[relative] = entry
    actual = {relative for relative, _, _ in tree_entries(files)}
    if actual != set(expected):
        raise ValueError('Snapshot file inventory does not match manifest')
    return manifest


def backup(root, destination=None):
    root = namespace_root(root)
    if not root.is_dir():
        raise ValueError('Standalone namespace does not exist')
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S-%f')
    destination = safe_path(destination or root.parent / (root.name + '-backups') / stamp)
    if destination == root or root in destination.parents or destination in root.parents:
        raise ValueError('Snapshot must be outside the standalone namespace')
    if destination.exists():
        raise ValueError('Snapshot destination already exists')
    private_dir(destination.parent)
    with namespace_lock(root):
        assert_offline(root)
        stage = pathlib.Path(tempfile.mkdtemp(prefix='.snapshot-', dir=destination.parent))
        try:
            files = private_dir(stage / 'files')
            source_entries = tree_entries(root, skip_transient=True)
            sqlite_paths = {relative for relative, path, mode in source_entries if stat.S_ISREG(mode) and is_sqlite(path)}
            entries = []
            omitted = []
            for relative, source, mode in source_entries:
                if any(relative == db + suffix for db in sqlite_paths for suffix in ('-wal', '-shm', '-journal')):
                    omitted.append(relative)
                    continue
                target = files / relative
                executable = bool(mode & 0o111)
                if stat.S_ISDIR(mode):
                    private_dir(target)
                    entries.append({'path': relative, 'kind': 'directory'})
                    continue
                private_dir(target.parent)
                kind = 'sqlite' if relative in sqlite_paths else 'file'
                if kind == 'sqlite':
                    snapshot_database(source, target)
                    check_database(target)
                else:
                    shutil.copyfile(source, target, follow_symlinks=False)
                target.chmod(0o700 if executable else 0o600)
                entries.append({'path': relative, 'kind': kind, 'executable': executable,
                                'size': target.stat().st_size, 'sha256': digest(target)})
            manifest = {'format': 1, 'createdUtc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                        'namespace': str(root), 'sqliteBackupApi': True,
                        'consistency': 'Offline standalone recovery set under an exclusive namespace lock.',
                        'omittedSqliteSidecars': omitted, 'omittedElectronTransientNames': sorted(TRANSIENT),
                        'entries': entries}
            atomic_json(stage / 'manifest.json', manifest)
            validate_snapshot(stage)
            os.rename(stage, destination)
        finally:
            if stage.exists():
                shutil.rmtree(stage)
    return destination


def restore(root, snapshot):
    root = namespace_root(root)
    snapshot = safe_path(snapshot)
    if root.exists() and not root.is_dir():
        raise ValueError('Standalone namespace root must be a directory')
    if snapshot == root or root in snapshot.parents:
        raise ValueError('Restore snapshot must be outside the namespace')
    with namespace_lock(root):
        assert_offline(root)
        manifest = validate_snapshot(snapshot)
        stage = pathlib.Path(tempfile.mkdtemp(prefix='.' + root.name + '-restore-', dir=root.parent))
        original = None
        try:
            for entry in manifest['entries']:
                target = stage / entry['path']
                if entry['kind'] == 'directory':
                    private_dir(target)
                else:
                    private_dir(target.parent)
                    shutil.copyfile(snapshot / 'files' / entry['path'], target, follow_symlinks=False)
                    target.chmod(0o700 if entry.get('executable') else 0o600)
                    if digest(target) != entry['sha256']:
                        raise ValueError('Staged restore checksum mismatch')
                    if entry['kind'] == 'sqlite':
                        check_database(target)
            assert_offline(root)
            if root.exists():
                tree_entries(root, skip_transient=True)
                stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S-%f')
                original = root.with_name(root.name + '-pre-restore-' + stamp)
                os.rename(root, original)
                original.chmod(0o700)
            try:
                os.rename(stage, root)
            except BaseException:
                if original is not None:
                    os.rename(original, root)
                raise
        finally:
            if stage.exists():
                shutil.rmtree(stage)
    return original


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    create = commands.add_parser('backup')
    create.add_argument('--root', type=pathlib.Path)
    create.add_argument('--destination', type=pathlib.Path)
    check = commands.add_parser('verify')
    check.add_argument('snapshot', type=pathlib.Path)
    recover = commands.add_parser('restore')
    recover.add_argument('snapshot', type=pathlib.Path)
    recover.add_argument('--root', type=pathlib.Path)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        if args.command == 'backup':
            print('Snapshot:', backup(args.root, args.destination))
        elif args.command == 'verify':
            manifest = validate_snapshot(args.snapshot)
            print('Snapshot verified:', len(manifest['entries']), 'entries')
        else:
            original = restore(args.root, args.snapshot)
            print('Restored namespace:', namespace_root(args.root))
            if original is not None:
                print('Previous namespace retained:', original)
    except (OSError, ValueError, sqlite3.Error) as error:
        parser.exit(1, f'{type(error).__name__}: {error}\n')


if __name__ == '__main__':
    main()
