"""Ownership of the desktop MCP entry inside the standalone MCP config.

The server keeps a distro-neutral name; `fedora-desktop` is the pre-rename spelling and
is only read so an existing install keeps its settings.
"""

SERVER_NAME = 'linux-desktop'
LEGACY_SERVER_NAME = 'fedora-desktop'


def adopt_legacy_name(servers):
    """Move a pre-rename entry to the neutral name; never touch the user's own entries."""
    if SERVER_NAME in servers:
        return False
    legacy = servers.get(LEGACY_SERVER_NAME)
    if not isinstance(legacy, dict):
        return False
    servers[SERVER_NAME] = servers.pop(LEGACY_SERVER_NAME)
    return True


def ensure_server(servers, *, command, args, env):
    adopt_legacy_name(servers)
    server = servers.setdefault(SERVER_NAME, {})
    if not isinstance(server, dict) or not isinstance(server.setdefault('env', {}), dict):
        raise ValueError('Invalid standalone desktop MCP server')
    server['command'] = str(command)
    server.setdefault('args', list(args))
    server['env'].update({name: str(value) for name, value in env.items()})
    return server
