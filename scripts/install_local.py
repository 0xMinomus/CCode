#!/usr/bin/python3
"""Install the CCode standalone integration without touching upstream launchers or data."""
import argparse
import copy
import datetime
import json
import os
import pathlib
import shutil
import subprocess
import sys
import urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'src'))
from local_only import branding, rebrand

from data_backup import (DEFAULT_LEGACY_ROOT, assert_offline, atomic_json, namespace_lock, namespace_root,
                         private_dir, safe_path)

ROOT = pathlib.Path(__file__).resolve().parents[1]
HOME = pathlib.Path.home()
UNIT_NAME = 'ccode-model-sync'
LAUNCHER_NAME = 'ccode.desktop'
LEGACY_UNIT_NAME = rebrand.PREVIOUS_UNIT
LEGACY_LAUNCHER_NAME = rebrand.PREVIOUS_LAUNCHER
LEGACY_LAUNCHERS = (rebrand.PREVIOUS_LAUNCHER_FILE, rebrand.PREVIOUS_LAUNCHER)
LEGACY_UNITS = (rebrand.PREVIOUS_UNIT, rebrand.PREVIOUS_VANSROUTER_UNIT)
LEGACY_APPIMAGE_LAUNCHER = 'appimagekit_*-' + rebrand.PREVIOUS_APPCONFIG + '.desktop*'
WINDOW_CLASS = 'ccode'


def import_personal_provider(path):
    source = json.loads(safe_path(path).read_text())
    if not isinstance(source, dict) or source.get('schemaVersion') != 1:
        raise ValueError('Provider import requires schemaVersion 1')
    config = source.get('config')
    if not isinstance(config, dict):
        raise ValueError('Provider config must be an object')
    provider_config = config.get('providerConfigRules', {})
    if not isinstance(provider_config, dict):
        raise ValueError('Invalid provider rules')
    rules = provider_config.get('providerRules', [])
    if not isinstance(rules, list):
        raise ValueError('Provider rules must be a list')
    selected = []
    identifiers = set()
    for rule in rules:
        if not isinstance(rule, dict) or not isinstance(rule.get('config'), dict):
            raise ValueError('Invalid provider rule')
        personal = rule['config']
        if personal.get('group') != 'standard-personal':
            continue
        identifier = rule.get('providerId')
        if not isinstance(identifier, str) or not identifier.strip() or identifier in identifiers:
            raise ValueError('Invalid or duplicate personal provider ID')
        if identifier.startswith('account:') or (isinstance(personal.get('access'), dict) and personal['access'].get('type') == 'zhipu-account'):
            continue
        if set(rule) - {'providerId', 'providerName', 'enabled', 'config'}:
            raise ValueError('Unrecognized personal provider fields')
        if 'providerName' in rule and not isinstance(rule['providerName'], str):
            raise ValueError('Invalid provider name')
        if 'enabled' in rule and not isinstance(rule['enabled'], bool):
            raise ValueError('Invalid provider enabled flag')
        if set(personal) - {'group', 'api', 'access', 'personalModelIds', 'modelOrder', 'visibility'}:
            raise ValueError('Unrecognized personal provider config fields')
        api = personal.get('api')
        access = personal.get('access')
        if not isinstance(api, dict) or set(api) - {'type', 'baseUrl', 'headers'} or api.get('type') not in ('anthropic-messages', 'openai-chat-completions', 'openai-responses'):
            raise ValueError('Invalid personal provider API')
        headers = api.get('headers')
        if headers is not None and (not isinstance(headers, dict) or not all(isinstance(key, str) and isinstance(value, str) for key, value in headers.items())):
            raise ValueError('Invalid personal provider headers')
        base_url = api.get('baseUrl')
        if not isinstance(base_url, str):
            raise ValueError('Personal provider requires a base URL')
        parsed = urllib.parse.urlsplit(base_url)
        if parsed.scheme not in ('https', 'http') or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('Invalid personal provider base URL')
        if not isinstance(access, dict) or set(access) - {'type', 'apiKey'} or access.get('type') not in ('api-key', 'zhipu-coding-plan-api-key'):
            raise ValueError('Only personal API-key access can be imported')
        if not isinstance(access.get('apiKey'), str) or not access['apiKey'].strip():
            raise ValueError('Personal provider API key is missing')
        for name in ('personalModelIds', 'modelOrder'):
            models = personal.get(name, [])
            if not isinstance(models, list) or not all(isinstance(model, str) and model.strip() for model in models):
                raise ValueError('Invalid personal model list')
        identifiers.add(identifier)
        selected.append(copy.deepcopy(rule))
    if not selected:
        raise ValueError('No standard-personal API-key providers found')
    model_config = config.get('modelConfigRules', {})
    if not isinstance(model_config, dict):
        raise ValueError('Invalid model rules')
    model_rules = {}
    for name in ('providerModelRules', 'manualProviderModelRules'):
        entries = model_config.get(name, [])
        if not isinstance(entries, list):
            raise ValueError('Model rules must be lists')
        model_rules[name] = []
        for rule in entries:
            if not isinstance(rule, dict) or not isinstance(rule.get('providerId'), str):
                raise ValueError('Invalid model provider rule')
            if rule['providerId'] not in identifiers:
                continue
            if set(rule) - {'providerId', 'modelId', 'config'} or not isinstance(rule.get('config'), dict):
                raise ValueError('Invalid personal model rule fields')
            if set(rule['config']) - {'enabled', 'properties', 'optionSpecs'}:
                raise ValueError('Unrecognized personal model configuration fields')
            if not isinstance(rule.get('modelId'), str) or not rule['modelId'].strip():
                raise ValueError('Invalid personal model ID')
            if 'enabled' in rule['config'] and not isinstance(rule['config']['enabled'], bool):
                raise ValueError('Invalid personal model enabled flag')
            for field in ('properties', 'optionSpecs'):
                if field in rule['config'] and not isinstance(rule['config'][field], dict):
                    raise ValueError('Invalid personal model options')
            model_rules[name].append(copy.deepcopy(rule))
    order = config.get('providerOrder', [])
    if not isinstance(order, list) or not all(isinstance(value, str) for value in order):
        raise ValueError('Invalid provider order')
    order = list(dict.fromkeys([value for value in order if value in identifiers] + [rule['providerId'] for rule in selected]))
    result = {'schemaVersion': 1, 'config': {'providerOrder': order,
              'providerConfigRules': {'providerRules': selected}, 'modelConfigRules': model_rules}}
    selection = config.get('defaultModelSelection')
    if selection is not None:
        if not isinstance(selection, dict) or set(selection) - {'providerId', 'modelId', 'options'}:
            raise ValueError('Invalid default model selection')
        if not all(isinstance(selection.get(field), str) and selection[field].strip() for field in ('providerId', 'modelId')):
            raise ValueError('Invalid default model selection IDs')
        options = selection.get('options', {})
        if not isinstance(options, dict) or set(options) - {'reasoningLevel'} or ('reasoningLevel' in options and (not isinstance(options['reasoningLevel'], str) or not options['reasoningLevel'].strip())):
            raise ValueError('Invalid default model reasoning options')
        provider = next((rule for rule in selected if rule['providerId'] == selection['providerId']), None)
        if provider and selection['modelId'] in provider['config'].get('personalModelIds', []):
            result['config']['defaultModelSelection'] = copy.deepcopy(selection)
    return result


def quote_desktop(value):
    if any(character in str(value) for character in '\n\r\0'):
        raise ValueError('Invalid launcher path')
    text = str(value).replace('%', '%%')
    for character in ('\\', '"', '`', '$'):
        text = text.replace(character, '\\' + character)
    # Desktop entries decode backslashes once before parsing the Exec field.
    return '"' + text.replace('\\', '\\\\') + '"'


def quote_unit(value):
    if any(character in str(value) for character in '\n\r\0'):
        raise ValueError('Invalid systemd path')
    return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%') + '"'


def unit_path(value):
    """systemd accepts WorkingDirectory only unquoted, so the path must be plain."""
    text = str(value)
    if any(character.isspace() for character in text) or any(character in text for character in '\n\r\0"\\'):
        raise ValueError('systemd unit path must not contain whitespace or quotes')
    return text


def backup_integration(path, namespace):
    safe_path(path)
    if not path.exists():
        return
    folder = private_dir(namespace / 'integration-backups' / datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    destination = folder / (path.parent.name + '-' + path.name)
    shutil.copyfile(path, destination, follow_symlinks=False)
    destination.chmod(0o600)


def write_integration(path, text, namespace):
    backup_integration(path, namespace)
    path.parent.mkdir(parents=True, exist_ok=True)
    safe_path(path)
    temporary = path.with_name('.' + path.name + '.new')
    safe_path(temporary)
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as stream:
        stream.write(text)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def install_icons():
    """Install the CCode launcher icon into the user's hicolor theme."""
    theme = HOME / '.local/share/icons/hicolor'
    written = []
    for size in branding.LOCAL_ICON_SIZES:
        destination = theme / f'{size}x{size}/apps/ccode.png'
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(branding.ICON_DIR / f'ccode-{size}.png', destination)
        written.append(destination)
    scalable = theme / 'scalable/apps/ccode.svg'
    scalable.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(branding.LOGO_SOURCE, scalable)
    written.append(scalable)
    # A cache generated before these files existed keeps the shell on its fallback
    # icon, so refresh it here instead of leaving a manual gtk-update-icon-cache step.
    if shutil.which('gtk-update-icon-cache'):
        refreshed = subprocess.run(['gtk-update-icon-cache', '--force', '--ignore-theme-index', str(theme)],
                                   capture_output=True, text=True)
        if refreshed.returncode != 0:
            print('Icon cache not refreshed:', (refreshed.stderr or refreshed.stdout).strip())
    return written


def migrate_namespace(namespace):
    """Move the CCode-era namespace to the CCode path once, before anything is written."""
    legacy = pathlib.Path(DEFAULT_LEGACY_ROOT)
    if pathlib.Path(namespace) != namespace_root() or not legacy.exists() or namespace.exists():
        return None
    assert_offline(legacy)
    os.rename(legacy, namespace)
    return legacy


def remove_legacy_integration(applications, units, namespace):
    """Retire the pre-rebrand launchers and units so nothing keeps using the old namespace."""
    for name in LEGACY_UNITS:
        for suffix in ('.timer', '.path'):
            subprocess.run(['systemctl', '--user', 'disable', '--now', name + suffix], check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    removed = []
    candidates = [units / (name + suffix) for name in LEGACY_UNITS for suffix in ('.service', '.timer', '.path')]
    candidates += [applications / name for name in LEGACY_LAUNCHERS]
    candidates += sorted(applications.glob(LEGACY_APPIMAGE_LAUNCHER))
    for path in candidates:
        if not path.exists():
            continue
        backup_integration(path, namespace)
        path.unlink()
        removed.append(path)
    lock = namespace.parent / rebrand.PREVIOUS_LOCK
    if lock.exists() and lock.is_file() and not lock.stat().st_size:
        lock.unlink()
        removed.append(lock)
    return removed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--root', type=pathlib.Path)
    parser.add_argument('--import-provider-from', type=pathlib.Path,
                        help='Explicitly import only personal provider/model rules; never overwrite an existing provider config')
    args = parser.parse_args()
    os.umask(0o077)
    try:
        namespace = namespace_root(args.root)
        provider = namespace / 'data/.ccode/v2/provider_config.json'
        mcp_resources = ROOT / 'app/resources'
        mcp_main = mcp_resources / 'mcp/main.cjs'
        mcp_node = ROOT / 'app/ccode'
        if not mcp_node.exists():
            mcp_node = ROOT / 'app/ccode'
        config = namespace / 'data/.ccode/cli/config.json'
        imported = import_personal_provider(args.import_provider_from) if args.import_provider_from else None
        if imported is not None and safe_path(provider).exists():
            raise ValueError('Standalone provider config already exists; import refused')
        applications = safe_path(HOME / '.local/share/applications')
        units = safe_path(HOME / '.config/systemd/user')
        launcher = applications / LAUNCHER_NAME
        command = '/usr/bin/env ' + quote_desktop('CCODE_STANDALONE_ROOT=' + str(namespace)) + ' ' + quote_desktop(ROOT / 'scripts/run.sh')
        desktop = '[Desktop Entry]\nName=CCode\nExec=' + command + ' %U\nTerminal=false\nType=Application\nIcon=ccode\nCategories=Development;\nStartupWMClass=' + WINDOW_CLASS + '\n'
        service = '[Unit]\nDescription=Sync standalone personal model metadata\n\n[Service]\nType=oneshot\nUMask=0077\nExecStart=/usr/bin/python3 ' + quote_unit(ROOT / 'services/model-sync/sync.py') + '\nWorkingDirectory=' + unit_path(ROOT / 'services/model-sync') + '\n'
        for name, value in {'CCODE_STANDALONE_ROOT': namespace, 'CCODE_MODEL_SYNC_CONFIG': provider,
                            'CCODE_MODEL_SYNC_STATE': namespace / 'model-sync', 'PYTHONUNBUFFERED': '1'}.items():
            service += 'Environment=' + quote_unit(name + '=' + str(value)) + '\n'
        service += 'TimeoutStartSec=45\n'
        timer = '[Unit]\nDescription=Keep standalone reasoning options current\n\n[Timer]\nOnStartupSec=30s\nOnUnitActiveSec=60s\nAccuracySec=5s\nUnit=' + UNIT_NAME + '.service\n\n[Install]\nWantedBy=timers.target\n'
        # A provider is added (and its API key entered) from the UI, which writes
        # this file: watching it lets discovery fill the model list right away
        # instead of waiting for the next timer tick.
        path_unit = ('[Unit]\nDescription=Discover standalone 9Router models when the provider config changes\n\n'
                     '[Path]\nPathChanged=' + unit_path(provider) + '\nPathModified=' + unit_path(provider) +
                     '\nUnit=' + UNIT_NAME + '.service\n\n[Install]\nWantedBy=paths.target\n')
        print('Project:', ROOT)
        print('Standalone namespace:', namespace)
        print('MCP config:', config)
        print('Desktop launcher:', launcher)
        print('Icon theme:', HOME / '.local/share/icons/hicolor')
        print('Timer:', UNIT_NAME + '.timer')
        print('Path unit:', UNIT_NAME + '.path')
        legacy = pathlib.Path(DEFAULT_LEGACY_ROOT)
        migrating = pathlib.Path(namespace) == namespace_root() and legacy.exists() and not namespace.exists()
        if migrating:
            print('Data migration:', legacy, '->', namespace)
        if args.dry_run:
            return
        if not mcp_main.is_file() or not mcp_node.is_file():
            raise ValueError('Bundled MCP resources are missing; build and apply before installing')
        with namespace_lock(namespace):
            assert_offline(namespace)
            migrated = migrate_namespace(namespace)
            if migrated is not None:
                print('Migrated standalone data:', migrated, '->', namespace)
            retired = remove_legacy_integration(applications, units, namespace)
            if retired:
                print('Retired old integration:', *[str(path) for path in retired], sep='\n  ')
            private_dir(namespace)
            private_dir(namespace / 'electron')
            private_dir(namespace / 'model-sync')
            private_dir(provider.parent)
            data = json.loads(safe_path(config).read_text()) if config.exists() else {}
            if not isinstance(data, dict):
                raise ValueError('Standalone MCP config must be an object')
            mcp = data.setdefault('mcp', {})
            if not isinstance(mcp, dict) or not isinstance(mcp.setdefault('servers', {}), dict):
                raise ValueError('Invalid standalone MCP servers')
            server = mcp['servers'].setdefault('fedora-desktop', {})
            if not isinstance(server, dict) or not isinstance(server.setdefault('env', {}), dict):
                raise ValueError('Invalid standalone desktop MCP server')
            server['command'] = str(ROOT / 'services/desktop/bin/screen-mcp')
            server.setdefault('args', [])
            server['env'].update({'SCREEN_PYTHON': str(ROOT / 'services/desktop/.venv/bin/python'),
                'MCP_SCREEN_NO_AUTO_DEPS': '1', 'MCP_SCREEN_PROFILE': 'ccode-fast', 'MCP_SCREEN_MAX_EDGE': '1280',
                'MCP_SCREEN_MAX_OUTPUT_KB': '250', 'MCP_SCREEN_ATSPI': '1'})
            backup_integration(config, namespace)
            if imported is not None:
                # Link an exclusive private file so concurrent UI writes cannot be overwritten.
                temporary = provider.with_name('.provider-import.json')
                if temporary.exists():
                    raise ValueError('Stale provider import file exists')
                atomic_json(temporary, imported)
                try:
                    os.link(temporary, provider, follow_symlinks=False)
                finally:
                    temporary.unlink()
            atomic_json(config, data)
            subprocess.run([str(mcp_node), str(mcp_main), '--bootstrap', str(namespace), str(mcp_resources)],
                           env={**os.environ, 'ELECTRON_RUN_AS_NODE': '1'}, check=True)
            write_integration(launcher, desktop, namespace)
            write_integration(units / (UNIT_NAME + '.service'), service, namespace)
            write_integration(units / (UNIT_NAME + '.timer'), timer, namespace)
            write_integration(units / (UNIT_NAME + '.path'), path_unit, namespace)
            icons = install_icons()
        subprocess.run(['systemctl', '--user', 'daemon-reload'], check=True)
        subprocess.run(['systemctl', '--user', 'enable', '--now', UNIT_NAME + '.timer'], check=True)
        subprocess.run(['systemctl', '--user', 'enable', '--now', UNIT_NAME + '.path'], check=True)
        if shutil.which('update-desktop-database'):
            subprocess.run(['update-desktop-database', str(applications)], check=True)
        print('Standalone integration installed:', len(icons), 'icon files, launcher, timer, and data root are CCode.')
        print(f'The upstream {rebrand.PREVIOUS_APPCONFIG} launchers and the old ~/{rebrand.PREVIOUS_APPDATA} data were not changed.')
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f'{type(error).__name__}: {error}\n')


if __name__ == '__main__':
    main()
