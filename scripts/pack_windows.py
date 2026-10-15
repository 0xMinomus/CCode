#!/usr/bin/python3
"""Assemble the unsigned Windows M1 hybrid boot candidate, never an installer.

CCode modification: combine verified application resources with the pinned Windows shell.
"""
import argparse
import base64
import hashlib
import io
import json
import pathlib
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile

from asar import Archive

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from local_only import rebrand
STAGED = ROOT / 'runtime/build/resources'
OUTPUT = ROOT / 'runtime/release-windows'
CACHE = ROOT / 'runtime/release-input/windows'
VENDOR_VERSION = '3.14.3'
INSTALLER = rebrand.previous('CCode-3.14.3-win-x64.exe')
VENDOR_URL = 'https://github.com/zai-org/ZCode/releases/download/v3.14.3/' + INSTALLER
VENDOR_SHA256 = '815721ad9888b03da2bba101faba7368896123849a6a82e3bc9e5fe5f3e5048b'
CODEGRAPH_URL = 'https://registry.npmjs.org/@sdsrs/code-graph-win32-x64/-/code-graph-win32-x64-0.169.0.tgz'
CODEGRAPH_INTEGRITY = 'sha512-e+Sa+GFlfpKkdod+Mke4RQRZfhyK6uAAf04JyzIxIjB17I+74spSCzia0y2mzcGOXgOYJCK9BCnGK7vZxVyNxA=='
FUSE_SENTINEL = b'dL7pKGdnNz796PbbjQWNKmHXBZaB9tsX'
LAUNCHER = r'''param([string]$Root = $env:CCODE_STANDALONE_ROOT,
      [Parameter(ValueFromRemainingArguments=$true)][string[]]$AppArgs)
$ErrorActionPreference = 'Stop'
if (!$Root) { $Root = Join-Path $PSScriptRoot 'm1-isolated-root' }
$Root = [IO.Path]::GetFullPath($Root)
if ($Root.TrimEnd('\') -eq [IO.Path]::GetPathRoot($Root).TrimEnd('\') -or
    $Root.TrimEnd('\') -eq $HOME.TrimEnd('\')) { throw 'Unsafe namespace root' }
foreach ($dir in @('data/.ccode/v2', 'data/.ccode/cli/db', 'electron', 'logs')) {
    New-Item -ItemType Directory -Force (Join-Path $Root $dir) | Out-Null
}
$names = @('CCODE_STANDALONE_ROOT','CCODE_LOCAL_ONLY','CCODE_DESKTOP_APPLICATION_NAME',
    'CCODE_DATA_BASE_DIR','CCODE_DESKTOP_HOME_DIR','DESKTOP_HOME_DIR',
    'CCODE_DESKTOP_USER_DATA_DIR','CCODE_STORAGE_DIR','STORAGE_DIR','CCODE_SESSION_DB_PATH')
$previous = @{}
foreach ($name in $names) { $previous[$name] = [Environment]::GetEnvironmentVariable($name, 'Process') }
try {
    $env:CCODE_STANDALONE_ROOT = $Root
    $env:CCODE_LOCAL_ONLY = '1'
    $env:CCODE_DESKTOP_APPLICATION_NAME = 'ccode'
    $env:CCODE_DATA_BASE_DIR = Join-Path $Root 'data'
    $env:CCODE_DESKTOP_HOME_DIR = $env:CCODE_DATA_BASE_DIR
    $env:DESKTOP_HOME_DIR = $env:CCODE_DATA_BASE_DIR
    $env:CCODE_DESKTOP_USER_DATA_DIR = Join-Path $Root 'electron'
    $env:CCODE_STORAGE_DIR = Join-Path $Root 'data/.ccode'
    $env:STORAGE_DIR = $env:CCODE_STORAGE_DIR
    $env:CCODE_SESSION_DB_PATH = Join-Path $env:CCODE_STORAGE_DIR 'cli/db/db.sqlite'
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $exe = Join-Path $PSScriptRoot 'app/CCode.exe'
    @{
        timestamp = $stamp; os = [Environment]::OSVersion.VersionString; root = $Root
        executable_sha256 = (Get-FileHash -Algorithm SHA256 $exe).Hash
        asar_sha256 = (Get-FileHash -Algorithm SHA256 (Join-Path $PSScriptRoot 'app/resources/app.asar')).Hash
    } | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $Root "logs/$stamp-environment.json")
    # Quote each argument using the Windows command-line backslash/quote rules.
    $quoted = foreach ($arg in $AppArgs) {
        '"' + [regex]::Replace([regex]::Replace($arg, '(\\*)"', '$1$1\"'), '(\\+)$', '$1$1') + '"'
    }
    $options = @{
        FilePath = $exe; WorkingDirectory = $PSScriptRoot; PassThru = $true; Wait = $true
        RedirectStandardOutput = (Join-Path $Root "logs/$stamp-stdout.log")
        RedirectStandardError = (Join-Path $Root "logs/$stamp-stderr.log")
    }
    if ($quoted) { $options.ArgumentList = $quoted -join ' ' }
    $process = Start-Process @options
    if ($process.ExitCode -ne 0) { throw "CCode exited $($process.ExitCode); inspect $Root\logs" }
} finally {
    foreach ($name in $names) { [Environment]::SetEnvironmentVariable($name, $previous[$name], 'Process') }
}
'''
INSTRUCTIONS = r'''CCode Windows M1 hybrid boot candidate (NOT a release or installer)

Unsigned. SmartScreen may warn. No Windows runtime validation has been performed here.
Application layer: {application_version}; vendor shell: 3.14.3, Electron 41.0.3.
Extract the ZIP to a writable local directory. Do not run from inside the ZIP.
Verify its SHA256 against the adjacent SHA256SUMS before extraction.

In PowerShell, from the extracted directory:
  powershell -NoProfile -ExecutionPolicy Bypass -File .\CCode.ps1
Or choose a fresh test-only namespace:
  powershell -NoProfile -ExecutionPolicy Bypass -File .\CCode.ps1 -Root "$env:TEMP\CCode-M1-test"
The default namespace is .\m1-isolated-root (NOT your normal CCode data).
Do not set CCODE_* environment variables permanently. The launcher restores its environment.

M1 evidence to record on Windows (no provider/API key needed):
1. Record Windows version, artifact SHA256, and namespace root. Launcher records OS,
   executable/ASAR SHA256 and root under <root>\logs along with stdout/stderr.
2. Confirm CCode name/icon, workspace opens without login, and no Unknown channel,
   No handler registered, ReferenceError or TypeError in logs/DevTools.
3. Open the integrated terminal and run: cmd /c echo CCODE_M1_PTY_OK
   Record the output, shell and screenshot. This is the Windows native PTY gate.
4. Close CCode normally; restart with the same root and confirm task/settings persist.
5. Redact keys and private paths before sharing logs. Report failures; do not call M1
   passed merely because this ZIP assembled on Linux.

M2+ NOT implemented/claimed: optional LSP/Ripgrep launch shims are still POSIX;
model-sync/Task Scheduler, Windows Computer Use, feature parity, NSIS installation,
shortcuts, URL registration, uninstall and signing. Default Codegraph's native payload
is Windows x64, but its runtime behavior remains unverified. No Linux MCP native is shipped.
Vendor legal notices/licenses remain intact; root NOTICE.md describes CCode modifications.
The PE version resource retains the truthful vendor shell version and legal attribution.
Delete extracted files to remove this candidate; isolated data remains until explicitly deleted.
'''


def sha256(path):
    digest = hashlib.sha256()
    with pathlib.Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def download(url, destination):
    if destination.exists():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + '.partial')
    try:
        with urllib.request.urlopen(url, timeout=120) as response, temporary.open('wb') as stream:
            shutil.copyfileobj(response, stream)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def verify_staged(staged):
    project = json.loads((ROOT / 'project.json').read_text())
    proof = json.loads((staged / 'build-manifest.json').read_text())
    if proof.get('application_name') != project['application_name']:
        raise ValueError('Wrong staged application identity')
    hashes = proof.get('sha256', {})
    if not {'app.asar', 'glm/ccode.cjs', 'icon_windows.png', 'mcp/catalog.json'} <= hashes.keys():
        raise ValueError('Incomplete staged build manifest')
    for name, digest in hashes.items():
        path = staged.joinpath(*Archive.parts(name))
        if not path.resolve().is_relative_to(staged.resolve()):
            raise ValueError('Unsafe staged manifest path: ' + name)
        if sha256(path) != digest:
            raise ValueError('Staged build checksum mismatch: ' + name)
        if name.startswith('voice/'):
            raise ValueError('Retired Voice resource in staged build')
    archive = Archive(staged / 'app.asar')
    if json.loads(archive.read('package.json'))['name'] != project['application_name']:
        raise ValueError('Wrong ASAR identity')
    return project, proof


def extract_vendor(installer, destination):
    if sha256(installer) != VENDOR_SHA256:
        raise ValueError('Windows installer checksum mismatch; expected ' + VENDOR_SHA256)
    seven = shutil.which('7z') or shutil.which('7zz')
    if not seven:
        raise ValueError('7z or 7zz is required to extract the pinned vendor installer')
    outer = destination / 'installer'
    subprocess.run([seven, 'x', '-y', '-o' + str(outer), str(installer), '$PLUGINSDIR/app-64.7z'], check=True, stdout=subprocess.DEVNULL)
    vendor = destination / 'vendor'
    subprocess.run([seven, 'x', '-y', '-o' + str(vendor), str(outer / '$PLUGINSDIR/app-64.7z')], check=True, stdout=subprocess.DEVNULL)
    for path in vendor.rglob('*'):
        if path.is_symlink():
            raise ValueError('Unexpected symlink in vendor payload: ' + str(path))
    return vendor


def pe_resources(data):
    """Yield PE resource keys, file offset, size and data-entry offset."""
    if data[:2] != b'MZ':
        raise ValueError('Not a PE executable')
    pe = struct.unpack_from('<I', data, 0x3c)[0]
    if data[pe:pe + 4] != b'PE\0\0':
        raise ValueError('Invalid PE signature')
    optional = pe + 24
    if struct.unpack_from('<H', data, optional)[0] != 0x20b:
        raise ValueError('Expected Windows x64 PE32+')
    directories = optional + 112
    sections = optional + struct.unpack_from('<H', data, pe + 20)[0]

    def offset(rva):
        for index in range(struct.unpack_from('<H', data, pe + 6)[0]):
            size, address, raw_size, raw = struct.unpack_from('<IIII', data, sections + index * 40 + 8)
            if address <= rva < address + max(size, raw_size):
                return raw + rva - address
        raise ValueError('Unmapped PE resource address')

    base = offset(struct.unpack_from('<I', data, directories + 16)[0])

    def walk(position=0, keys=()):
        count = sum(struct.unpack_from('<HH', data, base + position + 12))
        for index in range(count):
            key, child = struct.unpack_from('<II', data, base + position + 16 + index * 8)
            if key & 0x80000000:
                start = base + (key & 0x7fffffff)
                length = struct.unpack_from('<H', data, start)[0]
                key = bytes(data[start + 2:start + 2 + length * 2]).decode('utf-16le')
            if child & 0x80000000:
                yield from walk(child & 0x7fffffff, keys + (key,))
            else:
                address, size = struct.unpack_from('<II', data, base + child)
                yield keys + (key,), offset(address), size, base + child

    return directories, optional, list(walk())


def patch_executable(executable, source_asar, candidate_asar, icons):
    data = bytearray(executable.read_bytes())
    if data.count(FUSE_SENTINEL) != 1:
        raise ValueError('Expected one Electron fuse wire')
    fuse = data.index(FUSE_SENTINEL) + len(FUSE_SENTINEL)
    version, length = data[fuse:fuse + 2]
    wire = bytes(data[fuse + 2:fuse + 2 + length])
    if version != 1 or length < 6 or any(value not in b'01r' for value in wire) or wire[0] != ord('1'):
        raise ValueError('Unsupported Electron fuses; RunAsNode must be enabled')
    directories, optional, entries = pe_resources(data)
    records = [entry for entry in entries if entry[0][:2] == ('INTEGRITY', 'ELECTRONASAR')]
    if len(records) != 1:
        raise ValueError('Expected one embedded Electron ASAR integrity resource')
    keys, start, size, pointer = records[0]
    record = json.loads(bytes(data[start:start + size]))

    def header_hash(path):
        with pathlib.Path(path).open('rb') as stream:
            header = stream.read(16)
            return hashlib.sha256(stream.read(struct.unpack_from('<I', header, 12)[0])).hexdigest()

    if len(record) != 1 or record[0].get('file') != 'resources\\app.asar' or record[0].get('alg', '').lower() != 'sha256':
        raise ValueError('Unexpected vendor executable ASAR integrity resource')
    old_value = record[0].get('value', '')
    if len(old_value) != 64 or any(char not in '0123456789abcdef' for char in old_value):
        raise ValueError('Invalid vendor executable ASAR header hash')
    source_hash = header_hash(source_asar)
    source_matches = old_value == source_hash
    if not source_matches:
        if wire[4] != ord('0'):
            raise ValueError('Vendor executable enables validation with a mismatched ASAR header hash')
        print('Vendor ASAR hash is stale with validation disabled; recording discrepancy and replacing candidate hash.')
    old_hash = record[0]['value'].encode()
    data[start:start + size] = bytes(data[start:start + size]).replace(old_hash, header_hash(candidate_asar).encode())
    icon_sizes = {}
    for keys, start, size, pointer in entries:
        if keys[0] == 3:
            if data[start:start + 8] != b'\x89PNG\r\n\x1a\n':
                raise ValueError('Expected PNG executable icon')
            width, height = struct.unpack_from('>II', data, start + 16)
            icon = (icons / (str(width) + '.png')).read_bytes()
            if width != height or len(icon) > size:
                raise ValueError('CCode icon does not fit pinned executable resource')
            data[start:start + size] = icon + bytes(size - len(icon))
            struct.pack_into('<I', data, pointer + 4, len(icon))
            icon_sizes[keys[1]] = len(icon)
        elif keys[0] == 16:
            # Product fields have equal-length names; leave copyright attribution intact.
            block = bytes(data[start:start + size])
            for field in ('CompanyName', 'FileDescription', 'InternalName', 'ProductName'):
                marker = (field + '\0').encode('utf-16le')
                position = block.index(marker) + len(marker)
                while block[position:position + 2] == b'\0\0':
                    position += 2
                if block[position:position + 12] != rebrand.previous('CCode\0').encode('utf-16le'):
                    raise ValueError('Unexpected vendor PE version identity')
                block = block[:position] + 'CCode\0'.encode('utf-16le') + block[position + 12:]
            data[start:start + size] = block
    for keys, start, size, pointer in entries:
        if keys[0] == 14:
            for index in range(struct.unpack_from('<H', data, start + 4)[0]):
                item = start + 6 + 14 * index
                icon_id = struct.unpack_from('<H', data, item + 12)[0]
                struct.pack_into('<I', data, item + 8, icon_sizes[icon_id])
    certificate, certificate_size = struct.unpack_from('<II', data, directories + 32)
    struct.pack_into('<II', data, directories + 32, 0, 0)
    struct.pack_into('<I', data, optional + 64, 0)  # PE checksum, invalidated by edits.
    if certificate and certificate + certificate_size == len(data):
        del data[certificate:]
    executable.write_bytes(data)
    return {'fuse_wire': wire.decode(), 'embedded_asar_validation': wire[4] == ord('1'),
            'asar_header_sha256': header_hash(candidate_asar), 'integrity_resource_updated': True,
            'vendor_embedded_header_sha256': old_value, 'vendor_actual_header_sha256': source_hash,
            'vendor_embedded_header_matches': source_matches,
            'authenticode': 'unsigned; vendor certificate removed'}


def stage_codegraph(resources, cache):
    tarball = cache / 'code-graph-win32-x64-0.169.0.tgz'
    download(CODEGRAPH_URL, tarball)
    content = tarball.read_bytes()
    if base64.b64encode(hashlib.sha512(content).digest()).decode() != CODEGRAPH_INTEGRITY.split('-', 1)[1]:
        raise ValueError('Windows Codegraph npm integrity mismatch')
    modules = resources / 'mcp/runtime/node_modules'
    shutil.rmtree(modules / '@sdsrs/code-graph-linux-x64', ignore_errors=True)
    target = modules / '@sdsrs/code-graph-win32-x64'
    with tarfile.open(fileobj=io.BytesIO(content), mode='r:gz') as archive:
        for member in archive.getmembers():
            parts = Archive.parts(member.name)
            if len(parts) < 2 or parts[0] != 'package' or not member.isfile():
                if member.isdir():
                    continue
                raise ValueError('Unsafe npm native package member')
            path = target.joinpath(*parts[1:])
            path.parent.mkdir(parents=True, exist_ok=True)
            with archive.extractfile(member) as source, path.open('wb') as output:
                shutil.copyfileobj(source, output)
    if not (target / 'code-graph-mcp.exe').is_file():
        raise ValueError('Missing Windows Codegraph executable')
    catalog_path = resources / 'mcp/catalog.json'
    catalog = json.loads(catalog_path.read_text())
    for item in catalog:
        if item['id'] == 'codegraph':
            item.update(nativePackage='@sdsrs/code-graph-win32-x64', entry='code-graph-mcp.exe')
        elif item['id'] == 'ripgrep':
            item['dependencies'] = {'@vscode/ripgrep-win32-x64': '1.18.0'}
    catalog_path.write_text(json.dumps(catalog, indent=2) + '\n')


def assemble(staged, vendor, tree, cache, project, proof, work):
    app = tree / 'app'
    shutil.copytree(vendor, app)
    (app / rebrand.previous('.ccode-install-manifest')).unlink(missing_ok=True)
    (app / rebrand.previous('CCode.exe')).rename(app / 'CCode.exe')
    resources = app / 'resources'
    for path in ('app.asar.unpacked', 'glm', 'config'):
        shutil.rmtree(resources / path)
    (resources / 'app.asar').unlink()
    for name in proof['sha256']:
        if name == 'app.asar':
            continue
        destination = resources.joinpath(*Archive.parts(name))
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(staged / name, destination)
    shutil.copyfile(staged / 'build-manifest.json', tree / 'source-build-manifest.json')
    source = Archive(staged / 'app.asar')
    windows = Archive(vendor / 'resources/app.asar')
    for package in ('node-pty', 'ssh2'):
        name = 'node_modules/' + package + '/package.json'
        if json.loads(source.read(name))['version'] != json.loads(windows.read(name))['version']:
            raise ValueError('Native dependency version mismatch: ' + package)
    native = {}
    vendor_native_metadata = {}
    for name, entry in windows.all_entries():
        if entry.get('unpacked'):
            payload = (vendor / 'resources/app.asar.unpacked').joinpath(*Archive.parts(name)).read_bytes()
            # Vendor signs native PEs after creating its ASAR; the pinned installer is
            # provenance, and the overlay records fresh integrity for the actual bytes.
            actual_hash = hashlib.sha256(payload).hexdigest()
            if len(payload) != entry['size'] or actual_hash != entry['integrity']['hash']:
                vendor_native_metadata[name] = {'archive_size': entry['size'], 'payload_size': len(payload),
                                                'archive_sha256': entry['integrity']['hash'], 'payload_sha256': actual_hash}
            native[name] = payload
    required = {'node_modules/node-pty/prebuilds/win32-x64/' + name for name in ('pty.node', 'conpty.node', 'conpty_console_list.node')}
    if not required <= native.keys():
        raise ValueError('Missing Windows PTY native payload')
    remove = [name for name, entry in source.all_entries() if entry.get('unpacked') and name not in native]
    packed_natives = [name for name, entry in source.entries() if name.endswith(('.node', '.so', '.dll', '.exe'))]
    if packed_natives:
        raise ValueError('Unreviewed packed native dependencies: ' + str(packed_natives))
    source.write(resources / 'app.asar', {}, unpacked=native, remove=remove)
    stage_codegraph(resources, cache)
    icons = work / 'icons'
    icons.mkdir()
    magick = shutil.which('magick')
    if not magick:
        raise ValueError('ImageMagick magick is required for CCode Windows icons')
    for size in (16, 24, 32, 48, 64, 128, 256):
        subprocess.run([magick, str(staged / 'icon_windows.png'), '-resize', f'{size}x{size}', '-colors', '128', '-strip', '-define', 'png:compression-level=9', str(icons / f'{size}.png')], check=True)
    subprocess.run([magick, *[str(icons / f'{size}.png') for size in (16, 24, 32, 48, 64, 128, 256)], str(resources / 'tray_icon.ico')], check=True)
    executable = patch_executable(app / 'CCode.exe', vendor / 'resources/app.asar', resources / 'app.asar', icons)
    for path in tree.rglob('*'):
        if path.is_file():
            with path.open('rb') as stream:
                magic = stream.read(4)
            if magic == b'\x7fELF' or path.suffix == '.so':
                raise ValueError('Linux native file would ship: ' + str(path.relative_to(tree)))
    (tree / 'CCode.ps1').write_text(LAUNCHER, newline='\r\n')
    (tree / 'M1-INSTRUCTIONS.txt').write_text(INSTRUCTIONS.format(application_version=project['upstream_version']), newline='\r\n')
    for name in ('LICENSE', 'NOTICE.md'):
        shutil.copyfile(ROOT / name, tree / name)
    shutil.copyfile(ROOT / 'docs/THIRD_PARTY.md', tree / 'THIRD_PARTY.md')
    manifest = {'milestone': 'M1 boot candidate; Windows runtime NOT verified', 'application_name': 'CCode',
                'application_version': project['upstream_version'], 'vendor_version': VENDOR_VERSION,
                'electron_version': '41.0.3', 'vendor_url': VENDOR_URL, 'vendor_installer_sha256': VENDOR_SHA256,
                'source_build_manifest_sha256': sha256(staged / 'build-manifest.json'), 'executable': executable,
                'codegraph_url': CODEGRAPH_URL, 'codegraph_integrity': CODEGRAPH_INTEGRITY,
                'native_overlay': sorted(native), 'removed_linux_unpacked': remove,
                'vendor_native_metadata_refreshed': vendor_native_metadata,
                'sha256': {path.relative_to(tree).as_posix(): sha256(path) for path in sorted(tree.rglob('*')) if path.is_file()}}
    (tree / 'candidate-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')


def zip_tree(tree, destination):
    with zipfile.ZipFile(destination, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(tree.rglob('*')):
            if path.is_file():
                entry = zipfile.ZipInfo(tree.name + '/' + path.relative_to(tree).as_posix(), date_time=(2026, 1, 1, 0, 0, 0))
                entry.compress_type = zipfile.ZIP_DEFLATED
                entry.external_attr = 0o100644 << 16
                with path.open('rb') as source, archive.open(entry, 'w', force_zip64=True) as output:
                    shutil.copyfileobj(source, output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--staged', type=pathlib.Path, default=STAGED)
    parser.add_argument('--installer', type=pathlib.Path, help='Pinned vendor installer; downloaded from official release when omitted')
    parser.add_argument('--out', type=pathlib.Path, default=OUTPUT)
    args = parser.parse_args()
    staged, out = args.staged.resolve(), args.out.resolve()
    # Packaging may write only ignored Windows release artifacts, never Linux/deployed trees.
    if not out.is_relative_to(OUTPUT.resolve()):
        raise ValueError('--out must be runtime/release-windows or a child directory')
    project, proof = verify_staged(staged)
    out.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    installer = args.installer.resolve() if args.installer else CACHE / INSTALLER
    if not args.installer:
        download(VENDOR_URL, installer)
    name = 'CCode-' + project['upstream_version'] + '-win-x64-M1'
    with tempfile.TemporaryDirectory(prefix='.assemble-', dir=out) as temporary:
        work = pathlib.Path(temporary)
        vendor = extract_vendor(installer, work)
        tree = work / name
        assemble(staged, vendor, tree, CACHE, project, proof, work)
        archive = work / (name + '.zip')
        zip_tree(tree, archive)
        digest = sha256(archive)
        archive.replace(out / archive.name)
        manifest = tree / 'candidate-manifest.json'
        shutil.copyfile(manifest, out / 'candidate-manifest.json')
        shutil.copyfile(tree / 'M1-INSTRUCTIONS.txt', out / 'M1-INSTRUCTIONS.txt')
        (out / 'SHA256SUMS').write_text(f'{digest}  {archive.name}\n')
    print('M1 candidate:', out / (name + '.zip'))
    print('SHA256:', digest)
    print('Windows runtime NOT verified. Follow M1-INSTRUCTIONS.txt on Windows before M2.')


if __name__ == '__main__':
    main()
