#!/usr/bin/python3
"""Export project notes into an Obsidian vault as real notes; no secrets are copied."""
import argparse
import json
import os
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from local_only import rebrand

DEFAULT_VAULT = pathlib.Path.home() / 'orca/chessrpg'
MCP_CONFIG = pathlib.Path.home() / '.omp/agent/mcp.json'
FOLDER = 'CCode'
FILES = ('README.md', 'AGENTS.md')
DOCS = 'docs'


def write_note(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        with os.fdopen(handle, 'w') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def configured_vault():
    """Vault path from the Obsidian MCP server entry in the omp agent config."""
    try:
        servers = json.loads(MCP_CONFIG.read_text()).get('mcpServers', {})
        entry = servers.get('obsidian') or {}
        for value in entry.get('args') or ():
            path = pathlib.Path(str(value)).expanduser()
            if path.is_dir():
                return path
    except (OSError, ValueError, AttributeError):
        return None
    return None


def vault_directory(value=None):
    """Resolve the vault; an explicit path must exist, otherwise detect automatically."""
    explicit = value or os.environ.get('OBSIDIAN_VAULT_PATH')
    if explicit:
        vault = pathlib.Path(explicit).expanduser()
        if not vault.is_dir():
            raise ValueError(f'Obsidian vault directory not found: {explicit}')
        return vault.resolve()
    if (ROOT / '.obsidian').is_dir():
        return ROOT.resolve()
    for candidate in (configured_vault(), DEFAULT_VAULT):
        if candidate and pathlib.Path(candidate).is_dir():
            return pathlib.Path(candidate).resolve()
    raise ValueError('Obsidian vault not found; pass --vault or set OBSIDIAN_VAULT_PATH')


def ensure_folder(path):
    if path.is_symlink():
        raise ValueError(f'Refusing to write into a symlinked folder: {path}')
    path.mkdir(parents=True, exist_ok=True)


def with_frontmatter(relative, content):
    """Tag exported notes so Obsidian's tag pane can filter the project."""
    if content.startswith('---\n'):
        return content
    slug = pathlib.PurePosixPath(relative).stem.lower().replace(' ', '-')
    return f'---\ntags: [ccode, "ccode/{slug}"]\nsource: {relative}\n---\n\n{content}'


def latest_snapshot():
    parent = pathlib.Path.home() / '.local/share'
    candidates = sorted([*parent.glob('ccode-backups/*'), *parent.glob(rebrand.PREVIOUS_BACKUPS + '/*')], reverse=True)
    # Snapshots taken before the rename stay readable; report the directory that holds them.
    return f'{candidates[0].parent.name}/{candidates[0].name}' if candidates else 'belum ada snapshot'


def key_facts(vault, mode):
    refresh = ('Vault ini adalah folder project, jadi tidak ada salinan: catatan `README`, `AGENTS`, dan `docs/` adalah file asli repo.'
               if mode == 'native' else
               'Catatan di folder ini adalah salinan dari repo: setiap file diberi frontmatter `tags` dan `source` agar bisa difilter di tag pane (`#ccode`).')
    return f'''- Repo: `{ROOT}`
- Vault: `{vault}`
- Data aplikasi: `~/.local/share/ccode` (`data/`, `electron/`, `model-sync/`)
- Launcher: `ccode.desktop`; timer: `ccode-model-sync.timer`
- Data lama `~/{rebrand.PREVIOUS_APPDATA}` dan `~/.config/{rebrand.PREVIOUS_APPCONFIG}` tidak disentuh dan tidak diimpor otomatis
- Build: `make build && make test`; promote: `make apply` (aplikasi harus tertutup)
- Backup/restore: `python3 scripts/data_backup.py backup|verify|restore`
- Snapshot terakhir: `~/.local/share/{latest_snapshot()}`
- {refresh}'''


def index_note(vault, mode='mirror'):
    docs = sorted(path.stem for path in (ROOT / DOCS).glob('*.md'))
    if mode == 'native':
        readme, agents = '[[README|README]]', '[[AGENTS|AGENTS]]'
        links = '\n'.join(f'- [[{DOCS}/{name}|{name}]]' for name in docs)
        intro = ('Folder repo ini dibuka langsung sebagai vault Obsidian. Catatan `README.md`, `AGENTS.md`, '
                 'dan `docs/` adalah file asli; `make obsidian` hanya menyegarkan note ini.')
    else:
        readme, agents = f'[[{FOLDER}/README|README]]', f'[[{FOLDER}/AGENTS|AGENTS]]'
        links = '\n'.join(f'- [[{FOLDER}/{DOCS}/{name}|{name}]]' for name in docs)
        intro = ('Catatan di folder ini adalah salinan dari repo. Jalankan `make obsidian` dari root project untuk '
                 'menyegarkan setelah dokumen berubah; `make obsidian-check` melaporkan selisih tanpa menulis. '
                 'Vault terdeteksi otomatis dari konfigurasi MCP omp, atau lewat `OBSIDIAN_VAULT_PATH`/`--vault`.')
    return f'''---
tags: [ccode, fedora, project]
---
# CCode

Branding CCode untuk workspace patch upstream **3.14.5** di Fedora: varian mandiri tanpa akun, Computer Use lewat `linux-desktop`, dan provider model diatur sendiri di Settings.

{intro}

## Dokumen

- {readme} — ringkasan, struktur, perintah harian
- {agents} — aturan kerja agent di repo
{links}

## Fakta kunci

{key_facts(vault, mode)}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vault', default=None,
                        help='Vault path; defaults to OBSIDIAN_VAULT_PATH, the project folder when it has .obsidian/, the omp Obsidian MCP entry, then ~/orca/chessrpg')
    parser.add_argument('--check', action='store_true', help='report drift without writing')
    args = parser.parse_args()
    try:
        vault = vault_directory(args.vault)
        native = vault.resolve() == ROOT.resolve()
        folder = vault if native else vault / FOLDER
        if folder != ROOT and folder.is_symlink():
            raise ValueError(f'{folder} is a symlink; remove it so real notes can be written')
        notes = {}
        if native:
            notes[ROOT / 'Index.md'] = index_note(vault, 'native')
        else:
            for name in FILES:
                notes[folder / name] = with_frontmatter(name, (ROOT / name).read_text())
            for source in sorted((ROOT / DOCS).glob('*.md')):
                notes[folder / DOCS / source.name] = with_frontmatter(f'{DOCS}/{source.name}', source.read_text())
            notes[folder / 'Index.md'] = index_note(vault)
        missing, drift = [], []
        for target, content in notes.items():
            current = target.read_text() if target.is_file() and not target.is_symlink() else None
            if current is None:
                missing.append(target)
            elif current != content:
                drift.append(target)
        if args.check:
            if not missing and not drift:
                print(f'In sync: {folder}')
                return 0
            for label, paths in (('Missing', missing), ('Drift', drift)):
                if paths:
                    print(f'{label} in {vault}:')
                    for path in paths:
                        print('  ', path)
            return 1
        ensure_folder(folder)
        ensure_folder(folder / DOCS)
        updated = []
        for target, content in notes.items():
            current = target.read_text() if target.is_file() and not target.is_symlink() else None
            if current != content:
                write_note(target, content)
                updated.append(target)
        print(f'Vault: {vault}')
        print(f'Notes: {len(notes)} ({len(updated)} updated) -> {folder}')
        for path in updated:
            print('  ', path)
        return 0
    except (OSError, ValueError) as error:
        print(f'{type(error).__name__}: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
