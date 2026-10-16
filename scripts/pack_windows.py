#!/usr/bin/python3
"""Assemble the Windows x64 release: portable ZIP plus a per-user NSIS installer.

CCode modification: combine verified application resources with the pinned Windows shell.
Both artifacts are unsigned and need no administrator. The installer writes under
`%LOCALAPPDATA%\\Programs\\CCode`, keeps the application data (`%LOCALAPPDATA%\\CCode`)
unless the uninstaller checkbox asks otherwise, and refuses to touch a running install
instead of terminating it.
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
import time
import urllib.request
import zipfile

from asar import Archive

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from local_only import rebrand
STAGED = ROOT / 'runtime/build/resources'
OUTPUT = ROOT / 'runtime/release-windows'
BUILD = OUTPUT / 'build'
SCRIPT = 'ccode.nsi'
CACHE = ROOT / 'runtime/release-input/windows'
VENDOR_VERSION = '3.14.3'
ELECTRON_VERSION = '41.0.3'
INSTALLER = rebrand.previous('CCode-3.14.3-win-x64.exe')
VENDOR_URL = 'https://github.com/zai-org/ZCode/releases/download/v3.14.3/' + INSTALLER
VENDOR_SHA256 = '815721ad9888b03da2bba101faba7368896123849a6a82e3bc9e5fe5f3e5048b'
CODEGRAPH_URL = 'https://registry.npmjs.org/@sdsrs/code-graph-win32-x64/-/code-graph-win32-x64-0.169.0.tgz'
CODEGRAPH_INTEGRITY = 'sha512-e+Sa+GFlfpKkdod+Mke4RQRZfhyK6uAAf04JyzIxIjB17I+74spSCzia0y2mzcGOXgOYJCK9BCnGK7vZxVyNxA=='
CODEGRAPH_PACKAGE = '@sdsrs/code-graph-win32-x64'
CODEGRAPH_ENTRY = 'code-graph-mcp.exe'
CODEGRAPH_TARBALL = 'code-graph-win32-x64-0.169.0.tgz'
FUSE_SENTINEL = b'dL7pKGdnNz796PbbjQWNKmHXBZaB9tsX'
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)
TRAY_ICON = ROOT / 'assets/icons/ccode.ico'
EXECUTABLE = 'app\\CCode.exe'
MODEL_SYNC = 'model-sync.cmd'
DATA_DIR = 'CCode'
INSTALL_DIR = 'Programs\\CCode'
URL_SCHEME = 'ccode'
ONLOGON_TASK = 'CCode Model Sync'
DAILY_TASK = ONLOGON_TASK + ' (daily)'
DAILY_TIME = '09:00'
PUBLISHER = 'CCode project (fork of Z.AI ZCode)'
UNINSTALL_KEY = 'Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\CCode'
SCHEME_KEY = 'Software\\Classes\\' + URL_SCHEME
VENDOR_NOTICES = ('LICENSE.electron.txt', 'LICENSES.chromium.html', 'resources/THIRD-PARTY-NOTICES.md')
DOCUMENTS = ('LICENSE', 'NOTICE.md', 'THIRD_PARTY.md')
TOOLS = {'7z': (('7z', '7zz'), r'C:\Program Files\7-Zip\7z.exe'),
         'magick': (('magick',), r'C:\Program Files\ImageMagick-7.1.2-Q16-HDRI\magick.exe'),
         'makensis': (('makensis',), r'C:\Program Files (x86)\NSIS\makensis.exe')}
# Shipped files that must keep the upstream spelling to stay truthful, or because it is a
# remote contract rather than a product label: our attribution, the vendor legal and
# provenance files, and the marketplace compat module. The last one only holds the remote
# contract spellings that `marketplace.render_runtime` derives with `rebrand.previous()`,
# and that module fails the build itself when anything else survives in its runtime.
COMPAT = 'app/resources/marketplace/marketplace-compat.cjs'
PROVENANCE = frozenset((*DOCUMENTS, COMPAT, 'app/LICENSE.electron.txt', 'app/LICENSES.chromium.html',
                        'app/resources/THIRD-PARTY-NOTICES.md', 'app/resources/tools/ripgrep/SOURCES.json',
                        'app/resources/tools/ugrep/SOURCES.json'))
UPSTREAM_TOKENS = tuple(source.encode() for source, _ in rebrand.RENAMES)
LEGACY_VIEW_BOX = b'0 0 256 218'
# Vendor files the CCode build replaces. Excluding them from the copy avoids 300 MB of
# copying plus the deletion of a freshly written file, which Windows indexers and virus
# scanners hold open for a while (deletion fails with a sharing violation until they let go).
VENDOR_REPLACED = frozenset(('resources/app.asar', 'resources/app.asar.unpacked', 'resources/glm', 'resources/config',
                             rebrand.previous('.ccode-install-manifest'), rebrand.previous('CCode.exe')))
RETRY_ATTEMPTS, RETRY_DELAY = 6, 5


def retried(action, *arguments):
    """Filesystem work a scanner may block while it holds a freshly written file open."""
    for attempt in range(RETRY_ATTEMPTS):
        try:
            return action(*arguments)
        except PermissionError:
            if attempt == RETRY_ATTEMPTS - 1:
                raise
            time.sleep(RETRY_DELAY)

LAUNCHER = r'''param([string]$Root = $env:CCODE_STANDALONE_ROOT,
      [Parameter(ValueFromRemainingArguments=$true)][string[]]$AppArgs)
$ErrorActionPreference = 'Stop'
# Without -Root (or an inherited CCODE_STANDALONE_ROOT) nothing is redirected: the app
# uses its own default namespace, %LOCALAPPDATA%\CCode. -Root prepares an isolated
# namespace for testing and records launcher evidence under <root>\logs.
$names = @('CCODE_STANDALONE_ROOT','CCODE_LOCAL_ONLY','CCODE_DESKTOP_APPLICATION_NAME',
    'CCODE_DATA_BASE_DIR','CCODE_DESKTOP_HOME_DIR','DESKTOP_HOME_DIR',
    'CCODE_DESKTOP_USER_DATA_DIR','CCODE_STORAGE_DIR','STORAGE_DIR','CCODE_SESSION_DB_PATH')
$previous = @{}
foreach ($name in $names) { $previous[$name] = [Environment]::GetEnvironmentVariable($name, 'Process') }
try {
    $env:CCODE_LOCAL_ONLY = '1'
    $exe = Join-Path $PSScriptRoot 'app/CCode.exe'
    if ($Root) {
        $Root = [IO.Path]::GetFullPath($Root)
        if ($Root.TrimEnd('\') -eq [IO.Path]::GetPathRoot($Root).TrimEnd('\') -or
            $Root.TrimEnd('\') -eq $HOME.TrimEnd('\')) { throw 'Unsafe namespace root' }
        foreach ($dir in @('data/.ccode/v2', 'data/.ccode/cli/db', 'electron', 'logs')) {
            New-Item -ItemType Directory -Force (Join-Path $Root $dir) | Out-Null
        }
        $env:CCODE_STANDALONE_ROOT = $Root
        $env:CCODE_DESKTOP_APPLICATION_NAME = 'ccode'
        $env:CCODE_DATA_BASE_DIR = Join-Path $Root 'data'
        $env:CCODE_DESKTOP_HOME_DIR = $env:CCODE_DATA_BASE_DIR
        $env:DESKTOP_HOME_DIR = $env:CCODE_DATA_BASE_DIR
        $env:CCODE_DESKTOP_USER_DATA_DIR = Join-Path $Root 'electron'
        $env:CCODE_STORAGE_DIR = Join-Path $Root 'data/.ccode'
        $env:STORAGE_DIR = $env:CCODE_STORAGE_DIR
        $env:CCODE_SESSION_DB_PATH = Join-Path $env:CCODE_STORAGE_DIR 'cli/db/db.sqlite'
        $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
        @{
            timestamp = $stamp; os = [Environment]::OSVersion.VersionString; root = $Root
            executable_sha256 = (Get-FileHash -Algorithm SHA256 $exe).Hash
            asar_sha256 = (Get-FileHash -Algorithm SHA256 (Join-Path $PSScriptRoot 'app/resources/app.asar')).Hash
        } | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $Root "logs/$stamp-environment.json")
    }
    # Quote each argument using the Windows command-line backslash/quote rules.
    $quoted = foreach ($arg in $AppArgs) {
        '"' + [regex]::Replace([regex]::Replace($arg, '(\\*)"', '$1$1\"'), '(\\+)$', '$1$1') + '"'
    }
    $options = @{ FilePath = $exe; WorkingDirectory = $PSScriptRoot; PassThru = $true; Wait = $true }
    if ($Root) {
        $options.RedirectStandardOutput = Join-Path $Root "logs/$stamp-stdout.log"
        $options.RedirectStandardError = Join-Path $Root "logs/$stamp-stderr.log"
    }
    if ($quoted) { $options.ArgumentList = $quoted -join ' ' }
    $process = Start-Process @options
    if ($process.ExitCode -ne 0) { throw "CCode exited $($process.ExitCode)" }
} finally {
    foreach ($name in $names) { [Environment]::SetEnvironmentVariable($name, $previous[$name], 'Process') }
}
'''

MODEL_SYNC_CMD = '''@echo off
rem CCode model sync: run the packaged model-sync payload with the application binary as Node.
setlocal
set ELECTRON_RUN_AS_NODE=1
"%~dp0app\\CCode.exe" "%~dp0app\\resources\\model-sync\\main.cjs" %*
exit /b %ERRORLEVEL%
'''

GUARD = 'guard.ps1'
# The setup and the uninstaller call this with `-File`, so no quoting ever reaches PowerShell.
# `Get-Process ... .Path` comes back empty when the caller is the uninstaller's child, so the
# process list comes from WMI, which the service answers regardless of the caller's token.
GUARD_PS1 = '''# CCode install guard: exit 2 when CCode runs from this directory, 1 for instances from
# other directories, 0 when none run. Used by the setup and the uninstaller only.
$ErrorActionPreference = 'SilentlyContinue'
$target = Join-Path (Split-Path -Parent $PSCommandPath) '@@EXECUTABLE@@'
$all = @(Get-CimInstance Win32_Process -Filter "Name='CCode.exe'" -ErrorAction SilentlyContinue)
$match = @($all | Where-Object { $_.ExecutablePath -and ([IO.Path]::GetFullPath($_.ExecutablePath) -ieq [IO.Path]::GetFullPath($target)) })
if ($match.Count -gt 0) { exit 2 } elseif ($all.Count -gt 0) { exit 1 } else { exit 0 }
'''

RELEASE_NOTES = '''CCode for Windows x64 — release {release_version}

Application layer {application_version} (CCode) on the pinned vendor Windows shell
({vendor_version}, Electron {electron_version}). Unsigned: no certificate is attached, so
SmartScreen will warn. The shell is older than the application layer; the hybrid is
documented in windowsrelease.md and is not a claim of vendor version parity.

Portable ZIP
  Extract CCode-{release_version}-win-x64.zip to a writable local directory and verify its
  SHA256 against SHA256SUMS first. Do not run from inside the ZIP.
    powershell -NoProfile -ExecutionPolicy Bypass -File .\\CCode.ps1
  Without -Root the application uses its own default namespace, %LOCALAPPDATA%\\CCode.
  Use an isolated namespace for testing (evidence lands in <root>\\logs):
    powershell -NoProfile -ExecutionPolicy Bypass -File .\\CCode.ps1 -Root "$env:TEMP\\CCode-test"
  {cmd} runs the packaged model sync through the application binary.

NSIS installer
  Per-user and unsigned; no administrator is required.
    application      %LOCALAPPDATA%\\{install_dir}
    Start Menu       CCode
    URL scheme       {scheme}://
    tasks            "{onlogon}" at logon and "{daily}" daily; each is registered only when
                     the Task Scheduler accepts it for this user, and the installer reports
                     the outcome in its details pane either way
    uninstall        removes the application, the shortcut, both registry areas and both
                     tasks; keeps %LOCALAPPDATA%\\{data_dir} unless the data checkbox is
                     ticked, and a silent uninstall always keeps it; stops with a message
                     while CCode runs from the install directory instead of terminating it
  Silent install and uninstall: pass /S. The uninstaller is <install dir>\\Uninstall.exe.
  An unrelated CCode instance installed elsewhere is left untouched. A refused /S run (CCode
  still running from the install directory, or the check could not answer) changes nothing
  but can still report exit code 0, so verify the filesystem instead of the exit code.
  Path length: Windows stops at 260 characters, and the deepest payload path is about 190
  characters, so the setup needs an install directory with roughly 65 characters of room.
  %LOCALAPPDATA%\\{install_dir} fits; a very long user profile path may not.

This release
  Computer Use retains the local Windows backend with two native Settings rows and a real
  composer shortcut. Small pointer nudges are tolerated; sustained takeover still stops input.
  RTK can be installed from Token savers in one click (pinned official Apache-2.0 OSS binary).
  Managed MCP launcher paths heal after moving the application folder.
  General offers background prewarm at login, enabled by default. It consumes RAM while hidden;
  opening CCode normally shows the already-loaded instance. Disable it to avoid background use.

Limits: Windows UIPI blocks elevated windows and secure desktop input. Multi-monitor/mixed-DPI
behavior is not verified. Linux startup prewarm runtime awaits owner validation. No fixed RAM,
startup-time or provider-billed token savings are promised. No code signing or auto-update.
Vendor legal notices and the attribution in NOTICE.md ship unchanged.
'''

NSIS = r'''!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "nsDialogs.nsh"

Unicode true
Name "CCode"
Caption "CCode @@RELEASE_VERSION@@ setup"
OutFile "@@OUTFILE@@"
InstallDir "$LOCALAPPDATA\@@INSTALL_DIR@@"
InstallDirRegKey HKCU "@@UNINSTALL_KEY@@" "InstallLocation"
RequestExecutionLevel user
SetCompressor /SOLID lzma
ShowInstDetails show
ShowUninstDetails show

VIProductVersion "@@VI_VERSION@@"
VIAddVersionKey /LANG=1033 "ProductName" "CCode"
VIAddVersionKey /LANG=1033 "FileDescription" "CCode @@RELEASE_VERSION@@ per-user installer"
VIAddVersionKey /LANG=1033 "FileVersion" "@@RELEASE_VERSION@@"
VIAddVersionKey /LANG=1033 "LegalCopyright" "Apache-2.0; see NOTICE.md and the vendor notices in the payload"

!define MUI_ABORTWARNING
!define MUI_ICON "@@ICON@@"
!define MUI_UNICON "@@ICON@@"
!define MUI_FINISHPAGE_NOAUTOCLOSE
!define MUI_UNFINISHPAGE_NOAUTOCLOSE
!define MUI_FINISHPAGE_TITLE "CCode is installed"
!define MUI_FINISHPAGE_TEXT "CCode was installed for the current user. Start it from the Start Menu.$\r$\n$\r$\nYour data stays in %LOCALAPPDATA%\@@DATA_DIR@@ and survives an uninstall unless you choose to delete it."
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
UninstPage custom un.CCodeDataPage un.CCodeDataPageLeave
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_UNPAGE_FINISH
!insertmacro MUI_LANGUAGE "English"

Var CCodeDataCheckbox
Var CCodeDeleteData
Var CCodeTaskXml
Var CCodeTaskUser
Var CCodeTaskCode
Var CCodeSafe

Section "CCode"
  SetShellVarContext current
  ; Nothing is written unless the guard confirmed that no installed instance runs:
  ; `Quit` in the guard finishes asynchronously, so the section must not be the only thing
  ; keeping the files safe.
  ${If} $CCodeSafe == "1"
    SetOutPath "$INSTDIR"
    File /r "@@TREE@@\*"
    WriteUninstaller "$INSTDIR\Uninstall.exe"
    CreateShortCut "$SMPROGRAMS\CCode.lnk" "$INSTDIR\@@EXECUTABLE@@" "" "$INSTDIR\@@EXECUTABLE@@" 0
    WriteRegStr HKCU "@@UNINSTALL_KEY@@" "DisplayName" "CCode"
    WriteRegStr HKCU "@@UNINSTALL_KEY@@" "DisplayVersion" "@@RELEASE_VERSION@@"
    WriteRegStr HKCU "@@UNINSTALL_KEY@@" "Publisher" "@@PUBLISHER@@"
    WriteRegStr HKCU "@@UNINSTALL_KEY@@" "InstallLocation" "$INSTDIR"
    WriteRegStr HKCU "@@UNINSTALL_KEY@@" "UninstallString" '"$INSTDIR\Uninstall.exe"'
    WriteRegStr HKCU "@@UNINSTALL_KEY@@" "DisplayIcon" '"$INSTDIR\@@EXECUTABLE@@"'
    WriteRegDWORD HKCU "@@UNINSTALL_KEY@@" "EstimatedSize" @@ESTIMATED_SIZE_KB@@
    WriteRegDWORD HKCU "@@UNINSTALL_KEY@@" "NoModify" 1
    WriteRegDWORD HKCU "@@UNINSTALL_KEY@@" "NoRepair" 1
    WriteRegStr HKCU "@@SCHEME_KEY@@" "" "URL:CCode Protocol"
    WriteRegStr HKCU "@@SCHEME_KEY@@" "URL Protocol" ""
    WriteRegStr HKCU "@@SCHEME_KEY@@" "shell\open\command" '"$INSTDIR\@@EXECUTABLE@@" "%1"'
    Call RegisterModelSyncTasks
  ${EndIf}
SectionEnd

; Only an instance started from $INSTDIR blocks the setup; a CCode running from another
; directory is reported and left alone. The script exits 2 for the installed path, 1 for a
; foreign instance, and 0 when none runs, so no output has to be parsed.
Function CheckInstalledInstance
  nsExec::ExecToStack 'powershell -NoProfile -ExecutionPolicy Bypass -File "$INSTDIR\@@GUARD@@"'
  Pop $0
  Pop $1
  StrCpy $CCodeSafe "1"
  ${If} $0 == "2"
    ${If} ${Silent}
    ${Else}
      MessageBox MB_OK|MB_ICONEXCLAMATION "CCode is running from $INSTDIR.$\r$\n$\r$\nClose it, then run this setup again. Nothing was changed."
    ${EndIf}
    StrCpy $CCodeSafe ""
    SetErrorLevel 2
    Quit
  ${ElseIf} $0 == "1"
    DetailPrint "Another CCode instance is running from a different directory; it is left untouched."
  ${EndIf}
FunctionEnd

; The check runs before any section: `Quit` lets the current section finish, so a guard
; placed inside the section would still let the file copy happen.
Function .onInit
  Call CheckInstalledInstance
FunctionEnd

; A per-user setup may not create the all-user logon trigger that `schtasks` asks for with
; its ONLOGON schedule, so the logon task is registered through the XML form, which pins
; the trigger to the current user like the COM API does.
Function RegisterModelSyncTasks
  ${If} $%USERDOMAIN% == ""
    StrCpy $CCodeTaskUser "$%USERNAME%"
  ${Else}
    StrCpy $CCodeTaskUser "$%USERDOMAIN%\$%USERNAME%"
  ${EndIf}
  FileOpen $CCodeTaskXml "$PLUGINSDIR\ccode-model-sync-logon.xml" w
  FileWriteUTF16LE /BOM $CCodeTaskXml '<?xml version="1.0" encoding="UTF-16"?>$\r$\n'
  FileWriteUTF16LE $CCodeTaskXml '<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">$\r$\n'
  FileWriteUTF16LE $CCodeTaskXml '<RegistrationInfo><Description>CCode model sync at logon</Description></RegistrationInfo>$\r$\n'
  FileWriteUTF16LE $CCodeTaskXml '<Triggers><LogonTrigger><Enabled>true</Enabled><UserId>$CCodeTaskUser</UserId></LogonTrigger></Triggers>$\r$\n'
  FileWriteUTF16LE $CCodeTaskXml '<Principals><Principal id="Author"><UserId>$CCodeTaskUser</UserId><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>$\r$\n'
  FileWriteUTF16LE $CCodeTaskXml '<Settings><MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy><StartWhenAvailable>true</StartWhenAvailable><AllowStartOnDemand>true</AllowStartOnDemand><Enabled>true</Enabled><ExecutionTimeLimit>PT10M</ExecutionTimeLimit></Settings>$\r$\n'
  FileWriteUTF16LE $CCodeTaskXml '<Actions Context="Author"><Exec><Command>cmd</Command><Arguments>/c "$INSTDIR\@@MODEL_SYNC@@"</Arguments></Exec></Actions>$\r$\n'
  FileWriteUTF16LE $CCodeTaskXml '</Task>$\r$\n'
  FileClose $CCodeTaskXml
  nsExec::ExecToLog 'schtasks /Create /F /TN "@@ONLOGON_TASK@@" /XML "$PLUGINSDIR\ccode-model-sync-logon.xml"'
  Pop $CCodeTaskCode
  ${If} $CCodeTaskCode != "0"
    DetailPrint "WARNING: the at-logon model sync task was not registered (schtasks exit $CCodeTaskCode); CCode still refreshes models while it runs."
  ${EndIf}
  nsExec::ExecToLog 'schtasks /Create /F /TN "@@DAILY_TASK@@" /SC DAILY /ST @@DAILY_TIME@@ /TR "cmd /c ""$INSTDIR\@@MODEL_SYNC@@"""'
  Pop $CCodeTaskCode
  ${If} $CCodeTaskCode != "0"
    DetailPrint "WARNING: the daily model sync task was not registered (schtasks exit $CCodeTaskCode)."
  ${EndIf}
  Delete "$PLUGINSDIR\ccode-model-sync-logon.xml"
FunctionEnd

Section "Uninstall"
  SetShellVarContext current
  ; Same barrier as the setup: nothing is removed unless the guard allowed it.
  ${If} $CCodeSafe == "1"
    nsExec::ExecToLog 'schtasks /Delete /F /TN "@@ONLOGON_TASK@@"'
    Pop $0
    nsExec::ExecToLog 'schtasks /Delete /F /TN "@@DAILY_TASK@@"'
    Pop $0
    ReadRegStr $0 HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "CCodeStartupPrewarm"
    ${If} $0 == '$\"$INSTDIR\app\CCode.exe$\" --hidden'
      DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "CCodeStartupPrewarm"
    ${EndIf}
    Delete "$SMPROGRAMS\CCode.lnk"
    DeleteRegKey HKCU "@@UNINSTALL_KEY@@"
    DeleteRegKey HKCU "@@SCHEME_KEY@@"
    RMDir /r "$INSTDIR"
    ${If} $CCodeDeleteData == "1"
      RMDir /r "$LOCALAPPDATA\@@DATA_DIR@@"
    ${EndIf}
  ${EndIf}
SectionEnd

Function un.CheckInstalledInstance
  nsExec::ExecToStack 'powershell -NoProfile -ExecutionPolicy Bypass -File "$INSTDIR\@@GUARD@@"'
  Pop $0
  Pop $1
  StrCpy $CCodeSafe "1"
  ${If} $0 == "2"
    ${If} ${Silent}
    ${Else}
      MessageBox MB_OK|MB_ICONEXCLAMATION "CCode is running from $INSTDIR.$\r$\n$\r$\nClose it, then run the uninstaller again. Nothing was removed."
    ${EndIf}
    StrCpy $CCodeSafe ""
    SetErrorLevel 2
    Quit
  ${ElseIf} $0 == "1"
    DetailPrint "Another CCode instance is running from a different directory; it is left untouched."
  ${EndIf}
FunctionEnd

; Same reason as the installer: the check must finish before the uninstall section starts.
Function un.onInit
  Call un.CheckInstalledInstance
FunctionEnd

Function un.CCodeDataPage
  !insertmacro MUI_HEADER_TEXT "CCode data" "Keep or delete your CCode data"
  nsDialogs::Create 1018
  Pop $0
  ${If} $0 == error
    Abort
  ${EndIf}
  ${NSD_CreateLabel} 0 0 100% 28u "CCode keeps tasks, settings, and provider credentials in $LOCALAPPDATA\@@DATA_DIR@@. Removing CCode keeps that folder by default."
  Pop $0
  ${NSD_CreateCheckbox} 0 32u 100% 12u "Delete my CCode data (tasks, settings, provider credentials)"
  Pop $CCodeDataCheckbox
  nsDialogs::Show
FunctionEnd

Function un.CCodeDataPageLeave
  ${NSD_GetState} $CCodeDataCheckbox $0
  ${If} $0 == ${BST_CHECKED}
    StrCpy $CCodeDeleteData "1"
  ${EndIf}
FunctionEnd
'''


def tool(name):
    """Resolve a packaging tool from PATH first, then from its standard Windows location."""
    commands, fallback = TOOLS[name]
    for command in commands:
        found = shutil.which(command)
        if found:
            return found
    if pathlib.Path(fallback).is_file():
        return fallback
    raise ValueError(f'{name} is required to package Windows; install it or put it on PATH ({fallback})')


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
    if not project.get('windows_release_version'):
        raise ValueError('project.json needs windows_release_version for the release names')
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


def extract_vendor(installer, destination, seven):
    if sha256(installer) != VENDOR_SHA256:
        raise ValueError('Windows installer checksum mismatch; expected ' + VENDOR_SHA256)
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
    retried(executable.write_bytes, data)
    return {'fuse_wire': wire.decode(), 'embedded_asar_validation': wire[4] == ord('1'),
            'asar_header_sha256': header_hash(candidate_asar), 'integrity_resource_updated': True,
            'vendor_embedded_header_sha256': old_value, 'vendor_actual_header_sha256': source_hash,
            'vendor_embedded_header_matches': source_matches,
            'authenticode': 'unsigned; vendor certificate removed'}


def stage_codegraph(resources, cache):
    """Pin the Windows Codegraph payload, reusing the staged one when the build staged it."""
    target = resources / 'mcp/runtime/node_modules' / CODEGRAPH_PACKAGE
    catalog_path = resources / 'mcp/catalog.json'
    catalog = json.loads(catalog_path.read_text())
    entry = next((item for item in catalog if item.get('id') == 'codegraph'), {})
    if entry.get('nativePackage') == CODEGRAPH_PACKAGE and entry.get('entry') == CODEGRAPH_ENTRY and (target / CODEGRAPH_ENTRY).is_file():
        source = 'staged'
    else:
        tarball = cache / CODEGRAPH_TARBALL
        download(CODEGRAPH_URL, tarball)
        content = tarball.read_bytes()
        if base64.b64encode(hashlib.sha512(content).digest()).decode() != CODEGRAPH_INTEGRITY.split('-', 1)[1]:
            raise ValueError('Windows Codegraph npm integrity mismatch')
        source = 'npm'
        shutil.rmtree(target, ignore_errors=True)
        with tarfile.open(fileobj=io.BytesIO(content), mode='r:gz') as archive:
            for member in archive.getmembers():
                parts = Archive.parts(member.name)
                if len(parts) < 2 or parts[0] != 'package' or not member.isfile():
                    if member.isdir():
                        continue
                    raise ValueError('Unsafe npm native package member')
                path = target.joinpath(*parts[1:])
                path.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(member) as stream, path.open('wb') as output:
                    shutil.copyfileobj(stream, output)
    if not (target / CODEGRAPH_ENTRY).is_file():
        raise ValueError('Missing Windows Codegraph executable')
    shutil.rmtree(resources / 'mcp/runtime/node_modules/@sdsrs/code-graph-linux-x64', ignore_errors=True)
    for item in catalog:
        if item['id'] == 'codegraph':
            item.update(nativePackage=CODEGRAPH_PACKAGE, entry=CODEGRAPH_ENTRY)
        elif item['id'] == 'ripgrep':
            item['dependencies'] = {'@vscode/ripgrep-win32-x64': '1.18.0'}
    catalog_path.write_text(json.dumps(catalog, indent=2) + '\n')
    print('Windows Codegraph payload:', source)
    return {'source': source, 'package': CODEGRAPH_PACKAGE, 'entry': CODEGRAPH_ENTRY,
            'url': CODEGRAPH_URL, 'integrity': CODEGRAPH_INTEGRITY}


def files_of(root):
    return sorted(path.relative_to(root).as_posix() for path in root.rglob('*') if path.is_file())


# Linux-only helpers and local state never belong to the packaged payloads.
PAYLOAD_IGNORE = shutil.ignore_patterns('__pycache__', '*.pyc', '.git', '*.py',
                                        'state.json', 'catalog.json', 'sync.lock', 'backups')


def stage_payloads(staged, resources):
    """Include the model-sync and Windows desktop payloads when present; never fail when absent."""
    payloads, missing = {}, []
    model_sync = resources / 'model-sync'
    if (model_sync / 'main.cjs').is_file():
        payloads['model_sync'] = {'source': 'staged resources/model-sync', 'files': files_of(model_sync)}
    else:
        source = next((path for path in (staged / 'model-sync', ROOT / 'services/model-sync')
                       if (path / 'main.cjs').is_file()), None)
        if source is None:
            missing.append('model-sync/main.cjs')
            print('WARNING: the model-sync payload is unavailable; packaging without it.')
        else:
            shutil.copytree(source, model_sync, dirs_exist_ok=True, ignore=PAYLOAD_IGNORE)
            payloads['model_sync'] = {'source': source.relative_to(ROOT).as_posix(), 'files': files_of(model_sync)}
    if 'model_sync' in payloads:
        print('Model-sync payload:', payloads['model_sync']['source'], len(payloads['model_sync']['files']), 'files')
    desktop = resources / 'desktop-win'
    if desktop.is_dir():
        payloads['desktop_win'] = {'source': 'staged resources/desktop-win', 'files': files_of(desktop)}
    elif (ROOT / 'services/desktop-win').is_dir():
        shutil.copytree(ROOT / 'services/desktop-win', desktop, ignore=PAYLOAD_IGNORE)
        payloads['desktop_win'] = {'source': 'services/desktop-win', 'files': files_of(desktop)}
    else:
        missing.append('desktop-win')
        print('WARNING: services/desktop-win is unavailable; packaging without it.')
    if 'desktop_win' in payloads:
        print('Windows desktop payload:', payloads['desktop_win']['source'], len(payloads['desktop_win']['files']), 'files')
    return payloads, missing


def leftover_tokens(data):
    """Upstream product tokens in a byte run, ignoring absolute URLs like `rebrand.leftover`."""
    if not any(token in data for token in UPSTREAM_TOKENS):
        return []
    return rebrand.leftover(data.decode('utf-8', 'replace'))


def inspect_bytes(data, relative, text):
    """Identity violations in one shipped file: upstream tokens, legacy mark, Linux natives."""
    found = []
    if data[:4] == b'\x7fELF' or relative.endswith('.so'):
        found.append('Linux native payload')
    if text and relative not in PROVENANCE:
        left = leftover_tokens(data)
        if left:
            found.append('upstream product name: ' + ' '.join(left))
        if LEGACY_VIEW_BOX in data:
            found.append('legacy upstream mark viewBox')
    return found


def inspect_archive(path):
    """Upstream identity left inside the packaged ASAR, which is not a text file itself."""
    archive = Archive(path)
    data = path.read_bytes()
    violations = {}
    for name, entry in archive.entries():
        if not rebrand.is_text(name):
            continue
        start = archive.start + int(entry['offset'])
        found = inspect_bytes(data[start:start + int(entry['size'])], name, True)
        if found:
            violations['app/resources/app.asar:' + name] = found
    return violations, len(archive.index)


def assert_identity(tree):
    """Fail the build when the packaged tree still carries upstream product identity."""
    violations, text_files = {}, 0
    for path in sorted(tree.rglob('*')):
        if not path.is_file():
            continue
        relative = path.relative_to(tree).as_posix()
        text = rebrand.is_text(path.name)
        text_files += text
        found = inspect_bytes(path.read_bytes(), relative, text)
        if found:
            violations[relative] = found
    archive, entries = inspect_archive(tree / 'app/resources/app.asar')
    violations.update(archive)
    shipped = (*DOCUMENTS, *('app/' + name for name in VENDOR_NOTICES))
    missing = [name for name in shipped if not (tree / name).is_file()]
    if missing:
        violations['notices'] = ['missing shipped notice: ' + ' '.join(missing)]
    if violations:
        raise ValueError('CCode identity gate failed: ' + json.dumps(violations, sort_keys=True))
    print(f'Identity gate: {text_files} text files, {entries} ASAR entries, no upstream identity.')
    return {'text_files': text_files, 'asar_entries': entries, 'documents': list(DOCUMENTS),
            'vendor_notices': list(VENDOR_NOTICES), 'provenance_exempt': sorted(PROVENANCE),
            'legacy_view_box': LEGACY_VIEW_BOX.decode()}


def release_notes(project, version):
    return RELEASE_NOTES.format(release_version=version, application_version=project['upstream_version'],
                                vendor_version=VENDOR_VERSION, electron_version=ELECTRON_VERSION,
                                cmd=MODEL_SYNC, scheme=URL_SCHEME, install_dir=INSTALL_DIR, data_dir=DATA_DIR,
                                onlogon=ONLOGON_TASK, daily=DAILY_TASK)


def vendor_ignore(vendor):
    """Skip the vendor payload the CCode build replaces instead of copying and deleting it."""
    def ignore(directory, names):
        relative = pathlib.Path(directory).relative_to(vendor)
        prefix = '' if str(relative) == '.' else relative.as_posix() + '/'
        return {name for name in names if prefix + name in VENDOR_REPLACED}
    return ignore


def assemble(staged, vendor, tree, cache, project, proof, work, magick, version):
    app = tree / 'app'
    executable = rebrand.previous('CCode.exe')
    shutil.copytree(vendor, app, ignore=vendor_ignore(vendor))
    shutil.copyfile(vendor / executable, app / 'CCode.exe')
    resources = app / 'resources'
    for name in proof['sha256']:
        if name == 'app.asar':
            continue
        destination = resources.joinpath(*Archive.parts(name))
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(staged / name, destination)
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
    codegraph = stage_codegraph(resources, cache)
    payloads, missing = stage_payloads(staged, resources)
    icons = work / 'icons'
    icons.mkdir(exist_ok=True)
    for size in ICO_SIZES:
        subprocess.run([magick, str(staged / 'icon_windows.png'), '-resize', f'{size}x{size}', '-colors', '128',
                        '-strip', '-define', 'png:compression-level=9', str(icons / f'{size}.png')], check=True)
    if not TRAY_ICON.is_file():
        raise ValueError('CCode mark is missing; run `make icons` to generate ' + str(TRAY_ICON))
    shutil.copyfile(TRAY_ICON, resources / 'tray_icon.ico')
    executable = patch_executable(app / 'CCode.exe', vendor / 'resources/app.asar', resources / 'app.asar', icons)
    (tree / 'CCode.ps1').write_text(LAUNCHER, newline='\r\n')
    (tree / MODEL_SYNC).write_text(MODEL_SYNC_CMD, newline='\r\n')
    (tree / GUARD).write_text(GUARD_PS1.replace('@@EXECUTABLE@@', EXECUTABLE), newline='\r\n')
    (tree / 'RELEASE-NOTES.txt').write_text(release_notes(project, version), newline='\r\n')
    shutil.copyfile(ROOT / 'LICENSE', tree / 'LICENSE')
    shutil.copyfile(ROOT / 'NOTICE.md', tree / 'NOTICE.md')
    shutil.copyfile(ROOT / 'docs/THIRD_PARTY.md', tree / 'THIRD_PARTY.md')
    identity = assert_identity(tree)
    shutil.copyfile(staged / 'build-manifest.json', tree / 'source-build-manifest.json')
    return {'milestone': 'M4 release packaging (portable tree and per-user installer)',
            'application_name': 'CCode', 'application_version': project['upstream_version'],
            'release_version': version, 'vendor_version': VENDOR_VERSION,
            'electron_version': ELECTRON_VERSION, 'vendor_url': VENDOR_URL, 'vendor_installer': INSTALLER,
            'vendor_installer_sha256': VENDOR_SHA256,
            'source_build_manifest_sha256': sha256(staged / 'build-manifest.json'), 'executable': executable,
            'codegraph': codegraph, 'native_overlay': sorted(native), 'removed_linux_unpacked': remove,
            'vendor_native_metadata_refreshed': vendor_native_metadata, 'identity_gate': identity,
            'payloads': payloads, 'missing_payloads': missing,
            'sha256': {path.relative_to(tree).as_posix(): sha256(path) for path in sorted(tree.rglob('*')) if path.is_file()}}


def nsis_script(tree, version, destination, size_kb, icon):
    """The per-user installer script; every path is absolute so makensis needs no context."""
    parts = version.split('-', 1)[0].split('.')
    numeric = '.'.join((parts + ['0', '0', '0'])[:4]) if all(part.isdigit() for part in parts) else '1.0.0.0'
    script = NSIS
    for token, value in (('@@OUTFILE@@', str(destination)), ('@@TREE@@', str(tree)), ('@@ICON@@', str(icon)),
                         ('@@RELEASE_VERSION@@', version), ('@@VI_VERSION@@', numeric),
                         ('@@INSTALL_DIR@@', INSTALL_DIR), ('@@DATA_DIR@@', DATA_DIR),
                         ('@@EXECUTABLE@@', EXECUTABLE), ('@@MODEL_SYNC@@', MODEL_SYNC), ('@@GUARD@@', GUARD),
                         ('@@UNINSTALL_KEY@@', UNINSTALL_KEY), ('@@SCHEME_KEY@@', SCHEME_KEY),
                         ('@@PUBLISHER@@', PUBLISHER), ('@@ONLOGON_TASK@@', ONLOGON_TASK),
                         ('@@DAILY_TASK@@', DAILY_TASK), ('@@DAILY_TIME@@', DAILY_TIME),
                         ('@@ESTIMATED_SIZE_KB@@', str(size_kb))):
        if token not in script:
            raise ValueError('NSIS template lost its placeholder: ' + token)
        script = script.replace(token, value)
    if '@@' in script:
        raise ValueError('NSIS template holds an unsubstituted placeholder: ' + script[script.index('@@'):][:40])
    return script


def compile_installer(script, makensis):
    subprocess.run([makensis, '/V2', str(script)], check=True)


def zip_tree(tree, destination, prefix=None):
    """Archive a staged tree; the entry prefix is the release tree name, not the stage name."""
    prefix = prefix or tree.name
    with zipfile.ZipFile(destination, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(tree.rglob('*')):
            if path.is_file():
                entry = zipfile.ZipInfo(prefix + '/' + path.relative_to(tree).as_posix(), date_time=(2026, 1, 1, 0, 0, 0))
                entry.compress_type = zipfile.ZIP_DEFLATED
                entry.external_attr = 0o100644 << 16
                with path.open('rb') as source, archive.open(entry, 'w', force_zip64=True) as output:
                    shutil.copyfileobj(source, output)


def release_names(version):
    """Tree, portable archive and installer names for one release version."""
    tree = 'CCode-' + version + '-win-x64'
    return tree, tree + '.zip', tree + '.exe'


def installer_record(size_kb):
    """What the per-user NSIS setup creates; recorded in the package manifest."""
    return {'generator': 'NSIS (makensis)', 'script': 'build/' + SCRIPT, 'install_dir': '%LOCALAPPDATA%\\' + INSTALL_DIR,
            'data_dir': '%LOCALAPPDATA%\\' + DATA_DIR, 'url_scheme': URL_SCHEME + '://', 'tasks': [ONLOGON_TASK, DAILY_TASK],
            'uninstall_key': UNINSTALL_KEY, 'publisher': PUBLISHER, 'per_user': True, 'unsigned': True,
            'estimated_size_kb': size_kb}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--staged', type=pathlib.Path, default=STAGED)
    parser.add_argument('--installer', type=pathlib.Path, help='Pinned vendor installer; downloaded from the official release when omitted')
    parser.add_argument('--out', type=pathlib.Path, default=OUTPUT)
    parser.add_argument('--version', help='Release version; defaults to windows_release_version in project.json')
    parser.add_argument('--zip-only', action='store_true', help='Portable ZIP only; skip the NSIS installer')
    args = parser.parse_args()
    staged, out = args.staged.resolve(), args.out.resolve()
    # Packaging may write only ignored Windows release artifacts, never Linux/deployed trees.
    if not out.is_relative_to(OUTPUT.resolve()):
        raise ValueError('--out must be runtime/release-windows or a child directory')
    project, proof = verify_staged(staged)
    version = args.version or project['windows_release_version']
    name, portable, payload = release_names(version)
    out.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    BUILD.mkdir(parents=True, exist_ok=True)
    seven, magick = tool('7z'), tool('magick')
    installer = args.installer.resolve() if args.installer else CACHE / INSTALLER
    if not args.installer:
        download(VENDOR_URL, installer)
    # NSIS cannot open build-time paths longer than MAX_PATH and the MCP payload nests about
    # 190 characters deep, so the release tree is staged in a short system-temp directory.
    with tempfile.TemporaryDirectory(prefix='p', ignore_cleanup_errors=True) as temporary:
        try:
            scratch = pathlib.Path(temporary)
            vendor = extract_vendor(installer, scratch, seven)
            tree = scratch / 't'
            manifest = assemble(staged, vendor, tree, CACHE, project, proof, BUILD, magick, version)
            artifacts = {}
            archive = out / portable
            zip_tree(tree, archive, name)
            artifacts[archive.name] = sha256(archive)
            if args.zip_only:
                manifest['installer'] = None
            else:
                size_kb = sum(path.stat().st_size for path in tree.rglob('*') if path.is_file()) // 1024
                script = BUILD / SCRIPT
                script.write_text(nsis_script(tree, version, BUILD / payload, size_kb, TRAY_ICON), encoding='utf-8-sig')
                compile_installer(script, tool('makensis'))
                retried(shutil.move, BUILD / payload, out / payload)
                artifacts[payload] = sha256(out / payload)
                manifest['installer'] = installer_record(size_kb)
            manifest['artifacts'] = dict(sorted(artifacts.items()))
            (out / 'package-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
            shutil.copyfile(tree / 'RELEASE-NOTES.txt', out / 'RELEASE-NOTES.txt')
            (out / 'SHA256SUMS').write_text(''.join(f'{digest}  {file}\n' for file, digest in sorted(artifacts.items())))
        except BaseException:
            # Keep a failed stage for inspection; the next run only fails on the same defect.
            print(f'Stage kept for inspection: {temporary}')
            raise
    if pathlib.Path(temporary).exists():
        try:
            retried(shutil.rmtree, temporary)
        except PermissionError as error:
            print(f'WARNING: {temporary} is still held by another process ({error}); delete it later.')
    for file, digest in sorted(artifacts.items()):
        print(f'{file}  {digest}')
    print('Windows release artifacts written to', out, '(unsigned; verify with SHA256SUMS)')


if __name__ == '__main__':
    main()
