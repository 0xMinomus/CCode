import hashlib
import json
import pathlib
import shutil
import struct
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import pack_windows


def asar_header(files):
    """A valid ASAR header; packed entries need an offset relative to the data area."""
    encoded = json.dumps({'files': files}).encode()
    padding = (-len(encoded)) % 4
    size = 4 + len(encoded) + padding
    return struct.pack('<IIII', 4, 4 + size, size, len(encoded)) + encoded + bytes(padding)


def write_asar(path, files=(), payload=b''):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(asar_header(dict(files)) + payload)


def write_text_asar(path, name, text):
    payload = text.encode()
    write_asar(path, ((name, {'offset': '0', 'size': len(payload)}),), payload)


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


class ReleaseNamingTests(unittest.TestCase):
    def test_tree_and_artifacts_carry_the_release_version(self):
        self.assertEqual(pack_windows.release_names('1.0.0'),
                         ('CCode-1.0.0-win-x64', 'CCode-1.0.0-win-x64.zip', 'CCode-1.0.0-win-x64.exe'))

    def test_installer_record_describes_the_per_user_installation(self):
        record = pack_windows.installer_record(4096)
        self.assertEqual(record['generator'], 'NSIS (makensis)')
        self.assertEqual(record['script'], 'build/' + pack_windows.SCRIPT)
        self.assertEqual(record['install_dir'], '%LOCALAPPDATA%\\Programs\\CCode')
        self.assertEqual(record['data_dir'], '%LOCALAPPDATA%\\CCode')
        self.assertEqual(record['url_scheme'], 'ccode://')
        self.assertEqual(record['tasks'], ['CCode Model Sync', 'CCode Model Sync (daily)'])
        self.assertEqual(record['uninstall_key'], 'Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\CCode')
        self.assertEqual(record['publisher'], 'CCode project (fork of Z.AI ZCode)')
        self.assertEqual(record['estimated_size_kb'], 4096)
        self.assertTrue(record['per_user'])
        self.assertTrue(record['unsigned'])

    def test_project_metadata_supplies_the_release_version(self):
        version = json.loads((ROOT / 'project.json').read_text())['windows_release_version']
        self.assertRegex(version, r'^\d+\.\d+\.\d+$')
        self.assertEqual(pack_windows.release_names(version)[0], f'CCode-{version}-win-x64')

    def test_release_notes_are_free_of_upstream_product_labels(self):
        notes = pack_windows.release_notes({'upstream_version': '3.14.5'}, '1.0.0')
        self.assertEqual(pack_windows.rebrand.leftover(notes), [])
        self.assertIn('CCode-1.0.0-win-x64.zip', notes)
        self.assertIn(pack_windows.ONLOGON_TASK, notes)
        self.assertIn('%LOCALAPPDATA%\\Programs\\CCode', notes)


class NsisScriptTests(unittest.TestCase):
    def script(self, version='1.0.0'):
        return pack_windows.nsis_script(pathlib.Path('C:\\stage\\CCode-1.0.0-win-x64'), version,
                                        pathlib.Path('C:\\stage\\CCode-1.0.0-win-x64.exe'), 4096,
                                        ROOT / 'assets/icons/ccode.ico')

    def test_setup_is_per_user_and_packs_the_release_tree(self):
        script = self.script()
        self.assertIn('RequestExecutionLevel user', script)
        self.assertIn('InstallDir "$LOCALAPPDATA\\Programs\\CCode"', script)
        self.assertIn('InstallDirRegKey HKCU "' + pack_windows.UNINSTALL_KEY + '" "InstallLocation"', script)
        self.assertIn('File /r "C:\\stage\\CCode-1.0.0-win-x64\\*"', script)
        self.assertIn('OutFile "C:\\stage\\CCode-1.0.0-win-x64.exe"', script)
        self.assertIn('SetCompressor /SOLID lzma', script)
        self.assertIn('VIProductVersion "1.0.0.0"', script)
        self.assertIn('CreateShortCut "$SMPROGRAMS\\CCode.lnk" "$INSTDIR\\app\\CCode.exe"', script)
        self.assertNotIn('@@', script)

    def test_uninstall_entry_registers_the_release_identity(self):
        script = self.script()
        key = pack_windows.UNINSTALL_KEY
        self.assertIn(f'WriteRegStr HKCU "{key}" "DisplayName" "CCode"', script)
        self.assertIn(f'WriteRegStr HKCU "{key}" "DisplayVersion" "1.0.0"', script)
        self.assertIn(f'WriteRegStr HKCU "{key}" "Publisher" "CCode project (fork of Z.AI ZCode)"', script)
        self.assertIn(f'WriteRegStr HKCU "{key}" "UninstallString" \'"$INSTDIR\\Uninstall.exe"\'', script)
        self.assertIn(f'WriteRegStr HKCU "{key}" "DisplayIcon" \'"$INSTDIR\\app\\CCode.exe"\'', script)
        self.assertIn(f'WriteRegDWORD HKCU "{key}" "EstimatedSize" 4096', script)
        self.assertIn(f'WriteRegDWORD HKCU "{key}" "NoModify" 1', script)
        self.assertIn(f'WriteRegDWORD HKCU "{key}" "NoRepair" 1', script)
        self.assertIn(f'DeleteRegKey HKCU "{key}"', script)
        self.assertIn('WriteUninstaller "$INSTDIR\\Uninstall.exe"', script)

    def test_url_scheme_and_model_sync_tasks_are_registered_and_removed(self):
        script = self.script()
        self.assertIn('WriteRegStr HKCU "Software\\Classes\\ccode" "URL Protocol" ""', script)
        self.assertIn('WriteRegStr HKCU "Software\\Classes\\ccode" "shell\\open\\command" \'"$INSTDIR\\app\\CCode.exe" "%1"\'', script)
        self.assertIn('DeleteRegKey HKCU "Software\\Classes\\ccode"', script)
        self.assertIn('schtasks /Create /F /TN "CCode Model Sync" /XML', script)
        self.assertIn('schtasks /Create /F /TN "CCode Model Sync (daily)" /SC DAILY /ST 09:00', script)
        self.assertIn('schtasks /Delete /F /TN "CCode Model Sync"', script)
        self.assertIn('schtasks /Delete /F /TN "CCode Model Sync (daily)"', script)
        self.assertIn('<Arguments>/c "$INSTDIR\\model-sync.cmd"</Arguments>', script)

    def test_logon_task_pins_the_current_user_instead_of_all_users(self):
        script = self.script()
        self.assertIn('FileWriteUTF16LE /BOM', script)
        self.assertIn('<LogonTrigger><Enabled>true</Enabled><UserId>$CCodeTaskUser</UserId></LogonTrigger>', script)
        self.assertIn('<LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel>', script)
        self.assertNotIn('/SC ONLOGON', script)

    def test_running_instance_guard_runs_before_any_section(self):
        script = self.script()
        call = 'nsExec::ExecToStack \'powershell -NoProfile -ExecutionPolicy Bypass -File "$INSTDIR\\guard.ps1"\''
        self.assertEqual(script.count(call), 2)
        self.assertNotIn('Get-Process -Name CCode', script)
        self.assertIn('Get-CimInstance Win32_Process', pack_windows.GUARD_PS1)
        self.assertIn("Join-Path (Split-Path -Parent $PSCommandPath) '@@EXECUTABLE@@'", pack_windows.GUARD_PS1)
        self.assertIn('Function .onInit\n  Call CheckInstalledInstance\nFunctionEnd', script)
        self.assertIn('Function un.onInit\n  Call un.CheckInstalledInstance\nFunctionEnd', script)
        self.assertEqual(script.count('Call CheckInstalledInstance'), 1)
        self.assertEqual(script.count('Call un.CheckInstalledInstance'), 1)
        self.assertIn('${If} $CCodeSafe == "1"\n    SetOutPath "$INSTDIR"\n    File /r', script)
        self.assertIn('${If} $CCodeSafe == "1"\n    nsExec::ExecToLog \'schtasks /Delete /F /TN "CCode Model Sync"\'', script)
        self.assertEqual(script.count('SetErrorLevel 2'), 2)
        self.assertIn('Another CCode instance is running from a different directory', script)
        self.assertIn('"CCode is running from $INSTDIR.', script)
        self.assertNotIn('tasklist', script)
        self.assertEqual(script.count('Var CCodeSafe'), 1)
        self.assertEqual(script.count('StrCpy $CCodeSafe "1"'), 2)
        self.assertEqual(script.count('${If} $CCodeSafe == "1"'), 2)

    def test_uninstaller_keeps_data_unless_the_checkbox_is_ticked(self):
        script = self.script()
        self.assertIn('UninstPage custom un.CCodeDataPage un.CCodeDataPageLeave', script)
        self.assertIn('${NSD_CreateCheckbox} 0 32u 100% 12u "Delete my CCode data', script)
        self.assertIn('${If} $CCodeDeleteData == "1"', script)
        self.assertIn('RMDir /r "$LOCALAPPDATA\\CCode"', script)
        self.assertEqual(script.count('StrCpy $CCodeDeleteData "1"'), 1)
        self.assertIn('RMDir /r "$INSTDIR"', script)

    def test_template_without_a_placeholder_fails_the_build(self):
        without = pack_windows.NSIS.replace('@@DAILY_TASK@@', 'CCode Model Sync (daily)')
        with mock.patch.object(pack_windows, 'NSIS', without):
            with self.assertRaisesRegex(ValueError, 'lost its placeholder: @@DAILY_TASK@@'):
                self.script()


class IdentityGateTests(unittest.TestCase):
    def tree(self, root):
        write_asar(root / 'app/resources/app.asar')
        for name in (*pack_windows.DOCUMENTS, *('app/' + name for name in pack_windows.VENDOR_NOTICES)):
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('CCode notice\n', encoding='utf-8')
        (root / 'CCode.ps1').write_text('param()\n', encoding='utf-8')
        return root

    def test_clean_tree_passes_and_reports_what_it_checked(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.tree(pathlib.Path(temporary))
            summary = pack_windows.assert_identity(root)
            self.assertEqual(summary['legacy_view_box'], '0 0 256 218')
            self.assertEqual(summary['documents'], list(pack_windows.DOCUMENTS))
            self.assertEqual(summary['vendor_notices'], list(pack_windows.VENDOR_NOTICES))
            shipped = (*pack_windows.DOCUMENTS, *('app/' + name for name in pack_windows.VENDOR_NOTICES), 'CCode.ps1')
            expected = sum(pack_windows.rebrand.is_text(pathlib.Path(name).name) for name in shipped)
            self.assertEqual(summary['text_files'], expected)

    def test_upstream_product_name_in_a_shipped_text_file_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.tree(pathlib.Path(temporary))
            (root / 'app/resources/leak.json').write_text('{"product": "ZCode"}\n', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'upstream product name: ZCode'):
                pack_windows.assert_identity(root)

    def test_absolute_urls_are_network_contracts_not_labels(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.tree(pathlib.Path(temporary))
            (root / 'app/resources/links.json').write_text('{"home": "https://zcode.z.ai/ZCode"}\n', encoding='utf-8')
            pack_windows.assert_identity(root)

    def test_legacy_mark_view_box_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.tree(pathlib.Path(temporary))
            (root / 'app/resources/index.html').write_text('<svg viewBox="0 0 256 218"></svg>\n', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'legacy upstream mark viewBox'):
                pack_windows.assert_identity(root)

    def test_linux_native_payload_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.tree(pathlib.Path(temporary))
            (root / 'app/resources/engine.so').write_bytes(b'\x7fELF' + bytes(60))
            with self.assertRaisesRegex(ValueError, 'Linux native payload'):
                pack_windows.assert_identity(root)

    def test_vendor_notices_must_ship(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.tree(pathlib.Path(temporary))
            (root / 'app/resources/THIRD-PARTY-NOTICES.md').unlink()
            (root / 'THIRD_PARTY.md').unlink()
            with self.assertRaisesRegex(ValueError, 'missing shipped notice'):
                pack_windows.assert_identity(root)

    def test_provenance_documents_may_name_the_upstream_project(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.tree(pathlib.Path(temporary))
            (root / 'NOTICE.md').write_text('CCode is a fork of ZCode <https://github.com/zai-org/ZCode>\n', encoding='utf-8')
            (root / 'app/resources/THIRD-PARTY-NOTICES.md').write_text('ZCode toolchain notices\n', encoding='utf-8')
            pack_windows.assert_identity(root)

    def test_marketplace_compat_is_exempt_as_a_derived_remote_contract(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.tree(pathlib.Path(temporary))
            compat = root / pack_windows.COMPAT
            compat.parent.mkdir(parents=True, exist_ok=True)
            compat.write_text("const REMOTE = ['zcode-plugins-official', '.zcode-plugin', 'ZCODE_', 'ZCode'];\n", encoding='utf-8')
            self.assertIn(pack_windows.COMPAT, pack_windows.PROVENANCE)
            pack_windows.assert_identity(root)
            (root / 'app/resources/other.cjs').write_text("const LOCAL = 'ZCode';\n", encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'upstream product name'):
                pack_windows.assert_identity(root)

    def test_archive_entries_are_checked_too(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.tree(pathlib.Path(temporary))
            write_text_asar(root / 'app/resources/app.asar', 'out/renderer/index.html', '<svg viewBox="0 0 256 218">')
            with self.assertRaisesRegex(ValueError, 'app.asar:out/renderer/index.html'):
                pack_windows.assert_identity(root)


class PayloadStagingTests(unittest.TestCase):
    def test_missing_payloads_are_recorded_instead_of_failing(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            resources = root / 'resources'
            resources.mkdir()
            with mock.patch.object(pack_windows, 'ROOT', root):
                payloads, missing = pack_windows.stage_payloads(root / 'staged', resources)
            self.assertEqual(payloads, {})
            self.assertEqual(missing, ['model-sync/main.cjs', 'desktop-win'])

    def test_available_payloads_are_copied_into_the_resources(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            staged, resources = root / 'staged', root / 'resources'
            (staged / 'model-sync').mkdir(parents=True)
            (staged / 'model-sync/main.cjs').write_text('// ccode model sync\n', encoding='utf-8')
            (staged / 'model-sync/sync.py').write_text('# linux only\n', encoding='utf-8')
            (root / 'services/desktop-win').mkdir(parents=True)
            (root / 'services/desktop-win/helper.ps1').write_text('Write-Output ccode\n', encoding='utf-8')
            (root / 'services/desktop-win/__pycache__').mkdir()
            resources.mkdir()
            with mock.patch.object(pack_windows, 'ROOT', root):
                payloads, missing = pack_windows.stage_payloads(staged, resources)
            self.assertEqual(missing, [])
            self.assertEqual(payloads['model_sync'], {'source': 'staged/model-sync', 'files': ['main.cjs']})
            self.assertEqual(payloads['desktop_win'], {'source': 'services/desktop-win', 'files': ['helper.ps1']})
            self.assertTrue((resources / 'model-sync/main.cjs').is_file())
            self.assertTrue((resources / 'desktop-win/helper.ps1').is_file())


    def test_payloads_already_delivered_by_staging_are_recorded(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            resources = root / 'resources'
            (resources / 'model-sync').mkdir(parents=True)
            (resources / 'model-sync/main.cjs').write_text('// staged\n', encoding='utf-8')
            (resources / 'desktop-win').mkdir()
            (resources / 'desktop-win/helper.ps1').write_text('Write-Output ccode\n', encoding='utf-8')
            with mock.patch.object(pack_windows, 'ROOT', root):
                payloads, missing = pack_windows.stage_payloads(root / 'staged', resources)
            self.assertEqual(missing, [])
            self.assertEqual(payloads['model_sync'], {'source': 'staged resources/model-sync', 'files': ['main.cjs']})
            self.assertEqual(payloads['desktop_win'], {'source': 'staged resources/desktop-win', 'files': ['helper.ps1']})


class ToolResolutionTests(unittest.TestCase):
    def test_path_is_preferred_over_the_standard_location(self):
        with mock.patch.object(pack_windows.shutil, 'which', return_value='C:/tools/magick.exe'):
            self.assertEqual(pack_windows.tool('magick'), 'C:/tools/magick.exe')

    def test_standard_install_location_is_the_fallback(self):
        with tempfile.TemporaryDirectory() as temporary:
            fake = pathlib.Path(temporary) / 'magick.exe'
            fake.write_bytes(b'')
            with mock.patch.object(pack_windows.shutil, 'which', return_value=None):
                with mock.patch.dict(pack_windows.TOOLS, {'magick': (('magick',), str(fake))}):
                    self.assertEqual(pack_windows.tool('magick'), str(fake))

    def test_missing_tool_names_itself_and_the_expected_location(self):
        with mock.patch.object(pack_windows.shutil, 'which', return_value=None):
            with mock.patch.dict(pack_windows.TOOLS, {'makensis': (('makensis',), r'C:\nowhere\makensis.exe')}):
                with self.assertRaises(ValueError) as caught:
                    pack_windows.tool('makensis')
        self.assertIn('makensis is required', str(caught.exception))
        self.assertIn(r'C:\nowhere\makensis.exe', str(caught.exception))


class LauncherContractTests(unittest.TestCase):
    def test_model_sync_wrapper_runs_the_payload_through_the_app_binary(self):
        self.assertIn('set ELECTRON_RUN_AS_NODE=1', pack_windows.MODEL_SYNC_CMD)
        self.assertIn('"%~dp0app\\CCode.exe" "%~dp0app\\resources\\model-sync\\main.cjs" %*', pack_windows.MODEL_SYNC_CMD)

    def test_launcher_redirects_the_namespace_only_for_an_explicit_root(self):
        launcher = pack_windows.LAUNCHER
        self.assertNotIn('m1-isolated-root', launcher)
        self.assertIn('if ($Root) {', launcher)
        self.assertIn('$env:CCODE_STANDALONE_ROOT = $Root', launcher)
        self.assertIn("$env:CCODE_LOCAL_ONLY = '1'", launcher)
        self.assertIn('[Environment]::SetEnvironmentVariable($name, $previous[$name], \'Process\')', launcher)


class PortableArchiveTests(unittest.TestCase):
    def test_archive_prefixes_the_release_tree_with_fixed_timestamps(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary) / 'CCode-1.0.0-win-x64'
            (root / 'app').mkdir(parents=True)
            (root / 'app/CCode.exe').write_bytes(b'MZ')
            (root / 'CCode.ps1').write_text('param()\n', encoding='utf-8')
            first, second = pathlib.Path(temporary) / 'first.zip', pathlib.Path(temporary) / 'second.zip'
            pack_windows.zip_tree(root, first)
            pack_windows.zip_tree(root, second)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            with zipfile.ZipFile(first) as archive:
                self.assertEqual(sorted(archive.namelist()),
                                 ['CCode-1.0.0-win-x64/CCode.ps1', 'CCode-1.0.0-win-x64/app/CCode.exe'])
                self.assertEqual(archive.getinfo('CCode-1.0.0-win-x64/CCode.ps1').date_time, (2026, 1, 1, 0, 0, 0))

    def test_archive_prefix_comes_from_the_release_name_when_the_stage_is_short(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary) / 't'
            (root / 'app').mkdir(parents=True)
            (root / 'app/CCode.exe').write_bytes(b'MZ')
            archive_path = pathlib.Path(temporary) / 'release.zip'
            pack_windows.zip_tree(root, archive_path, 'CCode-1.0.0-win-x64')
            with zipfile.ZipFile(archive_path) as archive:
                self.assertEqual(archive.namelist(), ['CCode-1.0.0-win-x64/app/CCode.exe'])


class WindowsFileLockTests(unittest.TestCase):
    def test_retried_repeats_while_another_process_holds_the_file(self):
        calls = []

        def flaky():
            calls.append(1)
            if len(calls) < 3:
                raise PermissionError(32, 'held by another process')
            return 'done'

        with mock.patch.object(pack_windows.time, 'sleep'):
            self.assertEqual(pack_windows.retried(flaky), 'done')
        self.assertEqual(len(calls), 3)

    def test_retried_gives_up_after_the_last_attempt(self):
        def locked():
            raise PermissionError(32, 'held by another process')

        with mock.patch.object(pack_windows.time, 'sleep'):
            with self.assertRaises(PermissionError):
                pack_windows.retried(locked)

    def test_vendor_copy_skips_the_payload_the_build_replaces(self):
        with tempfile.TemporaryDirectory() as temporary:
            vendor = pathlib.Path(temporary) / 'vendor'
            for relative in ('resources/glm', 'resources/config', 'resources/tools', 'resources/app.asar.unpacked'):
                (vendor / relative).mkdir(parents=True)
            (vendor / 'resources/glm/ccode.cjs').write_text('vendor agent\n', encoding='utf-8')
            (vendor / 'resources/config/settings.json').write_text('{}\n', encoding='utf-8')
            (vendor / 'resources/tools/ripgrep.exe').write_bytes(b'MZ')
            (vendor / 'resources/app.asar').write_bytes(b'vendor archive')
            (vendor / 'resources/app.asar.unpacked/native.node').write_bytes(b'\x00')
            (vendor / 'resources.pak').write_bytes(b'pak')
            (vendor / pack_windows.rebrand.previous('CCode.exe')).write_bytes(b'MZ')
            (vendor / pack_windows.rebrand.previous('.ccode-install-manifest')).write_text('{}\n', encoding='utf-8')
            target = pathlib.Path(temporary) / 'app'
            shutil.copytree(vendor, target, ignore=pack_windows.vendor_ignore(vendor))
            shutil.copyfile(vendor / pack_windows.rebrand.previous('CCode.exe'), target / 'CCode.exe')
            kept = sorted(path.relative_to(target).as_posix() for path in target.rglob('*') if path.is_file())
            self.assertEqual(kept, ['CCode.exe', 'resources.pak', 'resources/tools/ripgrep.exe'])


class CliTests(unittest.TestCase):
    def test_output_stays_inside_the_release_directory(self):
        with mock.patch.object(pack_windows.sys, 'argv', ['pack_windows.py', '--out', str(ROOT / 'runtime' / 'elsewhere')]):
            with self.assertRaisesRegex(ValueError, '--out must be runtime/release-windows'):
                pack_windows.main()


if __name__ == '__main__':
    unittest.main()
