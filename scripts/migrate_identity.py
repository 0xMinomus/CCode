#!/usr/bin/python3
"""Move the standalone namespace to the CCode identity: names and stored paths.

Run after `make apply` and with the app closed. Renames every path that carries the
upstream token, rewrites the token inside configuration, state, log, and database
records, and leaves the user's workspace files alone. Snapshots first unless
`--no-backup` is given.
"""
import argparse
import datetime
import os
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from local_only import rebrand

from data_backup import DEFAULT_ROOT, assert_offline, namespace_root

SKIP_CONTENT = ('integration-backups', 'migration-backups')
# The workspace holds user files: paths are renamed, contents are never rewritten.
SKIP_CONTENT_PARTS = ('workspace',)
DATABASES = ('data/.ccode/cli/db/db.sqlite', 'data/.ccode/v2/tasks-index.sqlite')
TEXT_SUFFIXES = ('.json', '.jsonl', '.log', '.txt', '.md', '.yaml', '.yml', '.ini', '.cfg', '.conf', '.desktop')
TEXT_NAMES = ('.ccodeignore', 'config', 'settings')


def app_running():
    """True when a running process belongs to the standalone app or its namespace."""
    for proc in pathlib.Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            target = (proc / 'exe').resolve()
        except (OSError, PermissionError):
            continue
        if target.name == 'ccode' and (ROOT / 'app').resolve() in target.parents:
            return proc.name
    return None


def snapshot(namespace, destination):
    """Archive the state this migration rewrites; the workspace stays out of the tar.

    `data_backup.py` can snapshot the whole namespace, but the workspace is the bulk
    of it and the migration only renames one file name there.
    """
    import tarfile

    destination.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(destination, 'w:gz') as archive:
        for path in sorted(namespace.rglob('*')):
            relative = path.relative_to(namespace)
            parts = relative.parts
            if 'workspace' in parts or 'migration-backups' in parts or 'backups' in parts:
                continue
            archive.add(path, arcname=str(relative), recursive=False)
    return destination


def merge_layout(legacy, destination, backup):
    """Move a legacy data layout into the new one, keeping the legacy files on conflict.

    `make install` may already have seeded the new layout; the legacy tree holds the
    real state, so it wins and the replaced file is archived first.
    """
    if not legacy.is_dir():
        return []
    moved = []
    for path in sorted(legacy.rglob('*')):
        relative = path.relative_to(legacy)
        target = destination / relative
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        if target.exists():
            archived = backup / relative
            archived.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(target), str(archived))
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(target))
        moved.append(relative)
    shutil.rmtree(legacy, ignore_errors=True)
    return moved


def rename_paths(root, superseded):
    """Rename every path carrying the upstream token, deepest first.

    When the CCode-named sibling already exists the runtime re-seeded it from the
    patched payload, so the legacy path is a stale copy: keep it in the superseded
    archive instead of refusing the migration.
    """
    renamed = []
    dropped = []
    candidates = [path for path in root.rglob('*') if rebrand.leftover(path.name)]
    for path in sorted(candidates, key=lambda item: len(item.parts), reverse=True):
        target = path.with_name(rebrand.apply(path.name))
        if target.exists():
            archived = superseded / path.relative_to(root)
            archived.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), str(archived))
            dropped.append(path)
            continue
        os.rename(path, target)
        renamed.append((path, target))
    return renamed, dropped


def rewrite_contents(root):
    """Replace the token inside configuration and state files outside the workspace."""
    rewritten = []
    for path in sorted(rebrand_paths(root)):
        if not path.is_file() or path.suffix not in TEXT_SUFFIXES and path.name not in TEXT_NAMES:
            continue
        if any(part in SKIP_CONTENT_PARTS for part in path.parts):
            continue
        try:
            text = path.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            continue
        patched = rebrand.apply(text)
        if patched != text:
            path.write_text(patched, encoding='utf-8')
            rewritten.append(path)
    return rewritten


def rebrand_paths(root):
    return (path for path in root.rglob('*') if not any(part in SKIP_CONTENT for part in path.parts))


def repair_urls(root):
    """Restore stored URLs that an earlier migration pass renamed like a label."""
    repaired = []
    for path in sorted(rebrand_paths(root)):
        if not path.is_file() or path.suffix not in TEXT_SUFFIXES and path.name not in TEXT_NAMES:
            continue
        if any(part in SKIP_CONTENT_PARTS for part in path.parts):
            continue
        try:
            text = path.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            continue
        patched = rebrand.restore_urls(text)
        if patched != text:
            path.write_text(patched, encoding='utf-8')
            repaired.append(path)
    return repaired


def rewrite_database(path):
    """Replace the token in every text column; SQLite has no regex, so nest replaces."""
    import sqlite3

    if not path.is_file():
        return 0
    connection = sqlite3.connect(path)
    try:
        tables = [row[0] for row in connection.execute(
            "select name from sqlite_master where type='table' and name not like 'sqlite_%'")]
        changed = 0
        for table in tables:
            columns = [row[1] for row in connection.execute(f'pragma table_info("{table}")')]
            for column in columns:
                value = f'"{column}"'
                for source, target in rebrand.RENAMES:
                    value = f"replace({value}, '{source}', '{target}')"
                where = ' or '.join(f"\"{column}\" like '%{source}%'" for source, _ in rebrand.RENAMES)
                cursor = connection.execute(f'update "{table}" set "{column}" = {value} where {where}')
                changed += cursor.rowcount if cursor.rowcount > 0 else 0
        connection.commit()
        return changed
    finally:
        connection.close()


def repair_database_urls(path):
    """Restore renamed URLs inside text columns of a database."""
    import sqlite3

    if not path.is_file():
        return 0
    connection = sqlite3.connect(path)
    try:
        tables = [row[0] for row in connection.execute(
            "select name from sqlite_master where type='table' and name not like 'sqlite_%'")]
        repaired = 0
        for table in tables:
            columns = [row[1] for row in connection.execute(f'pragma table_info("{table}")')]
            for column in columns:
                try:
                    rows = connection.execute(
                        f'select rowid, "{column}" from "{table}" where "{column}" like \'%ccode%\''
                        f' or "{column}" like \'%CCode%\' or "{column}" like \'%CCODE%\'').fetchall()
                except sqlite3.OperationalError:
                    continue
                for rowid, value in rows:
                    if not isinstance(value, str):
                        continue
                    patched = rebrand.restore_urls(value)
                    if patched != value:
                        connection.execute(f'update "{table}" set "{column}" = ? where rowid = ?', (patched, rowid))
                        repaired += 1
        connection.commit()
        return repaired
    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default=str(DEFAULT_ROOT), help='standalone namespace')
    parser.add_argument('--no-backup', action='store_true', help='skip the pre-migration snapshot')
    parser.add_argument('--dry-run', action='store_true', help='report what would change')
    args = parser.parse_args()

    namespace = namespace_root(args.root)
    if not namespace.is_dir():
        parser.exit(1, f'Namespace not found: {namespace}\n')
    running = app_running()
    if running:
        parser.exit(1, f'Close CCode before migrating the namespace. Current app PID: {running}\n')
    assert_offline(namespace)

    layout = namespace / 'data' / '.ccode'
    legacy_layout = namespace / 'data' / rebrand.previous('.ccode')
    if not layout.is_dir() and not legacy_layout.is_dir():
        parser.exit(1, f'Standalone data layout not found under: {namespace}\n')
    if args.dry_run:
        stale = sorted(str(path.relative_to(namespace)) for path in namespace.rglob('*') if rebrand.leftover(path.name))
        print(f'Would rename {len(stale)} paths and rewrite recorded paths under {namespace}')
        for name in stale[:40]:
            print('  ', name)
        return

    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    if not args.no_backup:
        archived = snapshot(namespace, namespace / 'migration-backups' / f'{stamp}-pre.tar.gz')
        print(f'Pre-migration snapshot: {archived}')
    replaced = merge_layout(legacy_layout, layout, namespace / 'migration-backups' / stamp)
    renamed, dropped = rename_paths(namespace, namespace / 'migration-backups' / f'{stamp}-superseded')
    rewritten = rewrite_contents(namespace)
    repaired_files = repair_urls(namespace)
    records = 0
    repaired_records = 0
    for relative in DATABASES:
        records += rewrite_database(namespace / relative)
        repaired_records += repair_database_urls(namespace / relative)
    print(f'Namespace migrated: {namespace}')
    print(f'  merged legacy entries: {len(replaced)}')
    print(f'  renamed paths: {len(renamed)}')
    print(f'  superseded legacy paths: {len(dropped)}')
    print(f'  rewritten files: {len(rewritten)}')
    print(f'  rewritten records: {records}')
    print(f'  restored URLs: {len(repaired_files)} files, {repaired_records} records')


if __name__ == '__main__':
    main()
