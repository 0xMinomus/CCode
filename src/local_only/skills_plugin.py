"""Bundle the CCode default skills as a built-in app plugin.

The desktop client only lists skills that arrive through a plugin: its bundled
skill pack root (`glm/packages/bundled-skills`) is discovered by the agent but
never shown in Settings -> Skills. A bundled *plugin* is shown, seeded into the
plugin cache, and discovered as `system/plugin` by the agent as well.

The agent resolves bundled plugin roots from a definition list baked into its
bundle; each definition names its `rootCandidates` (for example
`packages/ccode-skills-plugin`) and the seed paths that must exist. This patch
prepends our definition to that list, and `scripts/build.py` stages the plugin
package next to the agent so the app can seed it.

Anchor is version-pinned: `replace_once` fails the build when it stops matching.
"""
from . import replace_once

PLUGIN_NAME = 'ccode-skills'
PLUGIN_DIR = PLUGIN_NAME + '-plugin'
PLUGIN_VERSION = '1.0.0'
CATEGORY = 'productivity'
DESCRIPTION = 'Default CCode agent skills: antislop, GSAP, UI design, and engineering workflow.'
SEED_SKILLS = ('antislop', 'impeccable', 'gsap-core', 'code-review', 'handoff')

ANCHOR = 'u9=[{defaultEnabled:!0,name:Uwt,'
# The agent lists plugin skills for the `glm` provider only when the plugin id is in
# this allowlist of official plugins. Without the entry our skills never reach the
# Skills page, even though the plugin itself is installed and listed.
OFFICIAL_PLUGIN_IDS_ANCHOR = 'new Set(["browser-use@zcode-plugins-official",'
OFFICIAL_MARKETPLACE = 'zcode-plugins-official'


def definition(skills=SEED_SKILLS):
    """The bundled-plugin definition appended to the agent's plugin list."""
    seed_paths = ','.join(f'"skills/{name}/SKILL.md"' for name in skills)
    candidates = ','.join(f'"packages/{PLUGIN_DIR}"' if index == 0 else f'"{"../" * index}{PLUGIN_DIR}"'
                          for index in range(4))
    return (f'{{defaultEnabled:!0,name:"{PLUGIN_NAME}",version:"{PLUGIN_VERSION}",'
            f'requiredSeedPaths:[{seed_paths}],rootCandidates:[{candidates}],'
            'listing:{author:{name:"CCode",url:"https://github.com/0xMinomus/CCode"},'
            f'category:"{CATEGORY}",displayName:"CCode Skills",displayName_i18n:{{"zh-CN":"CCode \u6280\u80fd"}},'
            f'description:"{DESCRIPTION}",'
            'description_i18n:{"zh-CN":"CCode \u9ed8\u8ba4\u6280\u80fd\uff1aantislop\u3001GSAP\u3001\u754c\u9762\u8bbe\u8ba1\u4e0e\u5de5\u7a0b\u6d41\u7a0b\u3002"}}}')


def patch_agent(text):
    """Register the bundled plugin in the agent's plugin list and official-plugin allowlist."""
    text = replace_once(text, ANCHOR, 'u9=[' + definition() + ',' + ANCHOR[len('u9=['):])
    return replace_once(text, OFFICIAL_PLUGIN_IDS_ANCHOR,
                        f'new Set(["{PLUGIN_NAME}@{OFFICIAL_MARKETPLACE}",' + OFFICIAL_PLUGIN_IDS_ANCHOR[len('new Set(['):])


# The renderer keeps its own list of built-in plugin names and package paths to
# decide which plugin skills the Skills page treats as built-in. Our plugin must
# be named there too, or its skills are filtered out of that page.
RENDERER_NAMES_ANCHOR = 'new Set([`android-emulator`,`browser`,`browser-use`,'
RENDERER_PATHS_ANCHOR = '[`/zcode-plugins-official/`,'


def patch_renderer(text):
    """Register the bundled plugin in the renderer's built-in plugin sets."""
    names = replace_once(text, RENDERER_NAMES_ANCHOR,
                         f'new Set([`{PLUGIN_NAME}`,' + RENDERER_NAMES_ANCHOR[len('new Set(['):])
    return replace_once(names, RENDERER_PATHS_ANCHOR,
                        f'[`/{PLUGIN_DIR}/`,' + RENDERER_PATHS_ANCHOR[1:])


def plugin_manifest(description=DESCRIPTION):
    """The manifest the app reads from the staged plugin package."""
    return {
        'name': PLUGIN_NAME,
        'version': PLUGIN_VERSION,
        'description': description,
        'author': {'name': 'CCode'},
        'license': 'see docs/THIRD_PARTY.md',
        'skills': 'skills',
    }