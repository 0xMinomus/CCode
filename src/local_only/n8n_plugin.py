"""Register the packaged n8n plugin with the native marketplace and lifecycle."""
import json
from . import replace_once

PLUGIN_ID = 'n8n@ccode-plugins-official'
REGISTRY_ANCHOR = 'G7a=["skills/ccode-configuration-guide/SKILL.md"],u9=['


def patch_agent(text):
    definition = {
        'name': 'n8n', 'version': '1.0.0', 'defaultEnabled': False,
        'rootCandidates': ['../mcp/plugins/n8n'],
        'requiredSeedPaths': ['dist/mcp/server.js', 'skills/using-n8n-mcp-skills/SKILL.md'],
        'listing': {'author': 'CCode', 'category': 'developer-tools', 'displayName': 'n8n'},
    }
    return replace_once(text, REGISTRY_ANCHOR,
                        REGISTRY_ANCHOR + json.dumps(definition, separators=(',', ':')) + ',')
