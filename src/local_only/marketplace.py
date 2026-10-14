"""Plugin marketplace compatibility for a rebranded standalone build.

The published plugin ecosystem is written against the upstream product name, and
the rebrand renames that spelling everywhere it can. Three of those names belong
to the publishers instead:

* the official marketplace CDN declares its marketplace id as `zcode-plugins-official`,
  and `Tre` rejects any manifest whose name is not the local trusted id;
* plugin zips ship their manifest under `.zcode-plugin/`, and `sct`/`BBs` only look
  for the local, Claude and Codex spellings, so every URL install fails with
  "Plugin manifest not found: <name>@<marketplace>";
* payload manifests address the runtime as `${ZCODE_PLUGIN_ROOT}` and read
  `<PREFIX>_PLUGIN_DATA`-style variables, which the local runtime never expands or
  exports.

Renaming those contracts is what broke the marketplace. This module meets them at
the boundary instead: the runtime table in `src/main/marketplace-compat.cjs` is
generated with the upstream spellings derived from `rebrand.previous()`, so the
upstream name is still written down exactly once, in `rebrand.py`, and the deployed
agent only ever calls into the compat module. The same module also rewrites the
Chinese labels and skill descriptions that published payloads carry without an
English variant, which otherwise surface in the plugin detail panel and in the
skill list the agent reads.
"""

import pathlib

from . import rebrand, replace_once, storage

ROOT = pathlib.Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / 'src/main/marketplace-compat.cjs'
RESOURCE_DIR = 'marketplace'
RESOURCE_FILE = f'{RESOURCE_DIR}/marketplace-compat.cjs'

# Placeholders in the template, and the local spelling each one reverses from.
PLACEHOLDERS = (
    ('__REMOTE_MARKETPLACE_ID__', 'ccode-plugins-official'),
    ('__REMOTE_MANIFEST_DIR__', '.ccode-plugin'),
    ('__REMOTE_ENV_PREFIX__', 'CCODE_'),
    ('__REMOTE_PRODUCT_UPPER__', 'CCODE'),
    ('__REMOTE_PRODUCT_TITLE__', 'CCode'),
    ('__REMOTE_PRODUCT_LOWER__', 'ccode'),
)

# The standalone storage bootstrap writes this line first; the compat module is
# required next to it so every later patch can call into the resource.
AGENT_REQUIRE = (storage.AGENT_BOOTSTRAP,
                 'const ccodePluginCompat=require("../marketplace/marketplace-compat.cjs");\n')

# `Tre` validates the downloaded manifest against the trusted id before merging it.
MARKETPLACE_TRUST_ANCHOR = ('if(e.trustedId===Yp&&o.manifest.name!==Yp)throw new Error('
                            '`Official marketplace source must provide ${Yp}, received ${o.manifest.name}`);')
MARKETPLACE_TRUST_PATCH = ('if(e.trustedId===Yp&&o.manifest.name!==Yp){'
                           'if(!ccodePluginCompat.acceptOfficialName(o.manifest.name))throw new Error('
                           '`Official marketplace source must provide ${Yp}, received ${o.manifest.name}`);'
                           'ccodePluginCompat.adoptOfficialName(o.manifest,Yp);}')

# Manifest discovery inside a plugin directory, a downloaded zip root, and the
# skill adapter that attributes a skill file to its plugin manifest.
MANIFEST_SCAN_ANCHOR = 'function sct(e){for(let t of[o8s,i8s,s8s]){'
MANIFEST_SCAN_PATCH = 'function sct(e){for(let t of ccodePluginCompat.manifestFiles([o8s,i8s,s8s])){'
ZIP_ROOT_ANCHOR = ('function BBs(e){return bw((0,Gy.join)(e,".ccode-plugin","plugin.json"))'
                   '||bw((0,Gy.join)(e,".claude-plugin","plugin.json"))'
                   '||bw((0,Gy.join)(e,".codex-plugin","plugin.json"))')
ZIP_ROOT_PATCH = ZIP_ROOT_ANCHOR + '||ccodePluginCompat.manifestAt(e)'
SKILL_SCAN_ANCHOR = ('g3s=[".ccode-plugin/plugin.json",".claude-plugin/plugin.json",'
                     '".codex-plugin/plugin.json",".cursor-plugin/plugin.json"]')
SKILL_SCAN_PATCH = ('g3s=ccodePluginCompat.manifestFiles([".ccode-plugin/plugin.json",'
                    '".claude-plugin/plugin.json",".codex-plugin/plugin.json",".cursor-plugin/plugin.json"])')

# `${...}` expansion for payload manifests, and the environment a plugin process sees.
TEMPLATE_VAR_ANCHOR = 'function AC(e,t,n){return e.replace(Y3s,(o,s)=>{switch(s){'
TEMPLATE_VAR_PATCH = ('function AC(e,t,n){return e.replace(Y3s,(o,s)=>{'
                      'let cc=ccodePluginCompat.resolveRemoteVar(s,t);if(cc!==void 0)return cc;switch(s){')
MCP_ENV_ANCHOR = ('let _=QHr({CLAUDE_PROJECT_DIR:t.workingDirectory,CCODE_PLUGIN_DATA:t.dataPath,'
                  'CCODE_PLUGIN_ROOT:t.loaded.rootPath,CCODE_PROJECT_DIR:t.workingDirectory,'
                  'CLAUDE_PLUGIN_DATA:t.dataPath,CLAUDE_PLUGIN_ROOT:t.loaded.rootPath,')
MCP_ENV_PATCH = ('let _=QHr({...ccodePluginCompat.envAliases({dataPath:t.dataPath,rootPath:t.loaded.rootPath,'
                 'id:t.loaded.id,name:t.loaded.name,workingDirectory:t.workingDirectory}),'
                 'CLAUDE_PROJECT_DIR:t.workingDirectory,CCODE_PLUGIN_DATA:t.dataPath,'
                 'CCODE_PLUGIN_ROOT:t.loaded.rootPath,CCODE_PROJECT_DIR:t.workingDirectory,'
                 'CLAUDE_PLUGIN_DATA:t.dataPath,CLAUDE_PLUGIN_ROOT:t.loaded.rootPath,')
HOOK_ENV_ANCHOR = ('return e?{set:{...o,CLAUDE_PLUGIN_DATA:e.dataPath,CLAUDE_PLUGIN_ROOT:e.rootPath,'
                   'CCODE_PLUGIN_DATA:e.dataPath,CCODE_PLUGIN_ID:e.id,CCODE_PLUGIN_NAME:e.name,'
                   'CCODE_PLUGIN_ROOT:e.rootPath}}:{set:o}')
HOOK_ENV_PATCH = ('return e?{set:{...o,...ccodePluginCompat.envAliases({dataPath:e.dataPath,rootPath:e.rootPath,'
                  'id:e.id,name:e.name,workingDirectory:o.CCODE_PROJECT_DIR}),CLAUDE_PLUGIN_DATA:e.dataPath,'
                  'CLAUDE_PLUGIN_ROOT:e.rootPath,CCODE_PLUGIN_DATA:e.dataPath,CCODE_PLUGIN_ID:e.id,'
                  'CCODE_PLUGIN_NAME:e.name,CCODE_PLUGIN_ROOT:e.rootPath}}:{set:o}')

# Resolved entry trees (describe, validate, install) and marketplace entry lists.
RESOLVE_ANCHOR = 'async function ict(e){nT(e.signal);'
RESOLVE_PATCH = ('async function ict(e){return ccodePluginCompat.localizeResolved(await ictResolved(e));}'
                 'async function ictResolved(e){nT(e.signal);')
ENTRIES_ANCHOR = 'function OJr(e){if(q8s(e))return e;'
ENTRIES_PATCH = 'function OJr(e){if(q8s(e))return e;ccodePluginCompat.localizeManifestEntries(e);'

# The plugin adapter (`v7s`) and the MCP manifest reader (`EEn`) resolve manifests
# from their own constants, outside the marketplace module patched above.
ADAPTER_SCAN_ANCHOR = ('function v7s(e){let t=(0,Bk.join)(e,qzs);if(bw(t))return t;'
                       'let n=(0,Bk.join)(e,Wzs);if(bw(n))return n;'
                       'let o=(0,Bk.join)(e,Vzs);return bw(o)?o:null}')
ADAPTER_SCAN_PATCH = ADAPTER_SCAN_ANCHOR.replace(
    'return bw(o)?o:null}', 'return bw(o)?o:ccodePluginCompat.manifestPathIn(e,[qzs,Wzs,Vzs])}')
MANIFEST_READ_ANCHOR = 'let t=(0,Tbe.join)(e.rootPath,".ccode-plugin","plugin.json"),n=(0,S7o.readFileSync)(t,"utf8")'
MANIFEST_READ_PATCH = ('let t=ccodePluginCompat.manifestPathIn(e.rootPath,[])||(0,Tbe.join)(e.rootPath,".ccode-plugin","plugin.json"),'
                       'n=(0,S7o.readFileSync)(t,"utf8")')

PATCHES = (
    (MARKETPLACE_TRUST_ANCHOR, MARKETPLACE_TRUST_PATCH),
    (MANIFEST_SCAN_ANCHOR, MANIFEST_SCAN_PATCH),
    (ZIP_ROOT_ANCHOR, ZIP_ROOT_PATCH),
    (SKILL_SCAN_ANCHOR, SKILL_SCAN_PATCH),
    (ADAPTER_SCAN_ANCHOR, ADAPTER_SCAN_PATCH),
    (MANIFEST_READ_ANCHOR, MANIFEST_READ_PATCH),
    (TEMPLATE_VAR_ANCHOR, TEMPLATE_VAR_PATCH),
    (MCP_ENV_ANCHOR, MCP_ENV_PATCH),
    (HOOK_ENV_ANCHOR, HOOK_ENV_PATCH),
    (RESOLVE_ANCHOR, RESOLVE_PATCH),
    (ENTRIES_ANCHOR, ENTRIES_PATCH),
)


def render_runtime():
    """The runtime resource with every remote contract spelling filled in."""
    text = TEMPLATE.read_text(encoding='utf-8')
    for placeholder, local in PLACEHOLDERS:
        remote = rebrand.previous(local)
        if placeholder not in text:
            raise ValueError(f'Marketplace compat template lost its placeholder: {placeholder}')
        text = replace_once(text, placeholder, remote)
    remaining = [name for name, _ in PLACEHOLDERS if name in text]
    if remaining:
        raise ValueError('Marketplace compat template still holds placeholders: ' + ' '.join(remaining))
    # The guide keeps the build strict: the runtime may hold upstream tokens only
    # inside the derived contract spellings themselves.
    probe = text
    for _, local in PLACEHOLDERS:
        probe = probe.replace(rebrand.previous(local), '')
    found = rebrand.leftover(probe)
    if found:
        raise ValueError('Marketplace compat runtime holds unexpected upstream tokens: ' + ' '.join(found))
    return text


def patch_agent(text):
    """Meet the published contract spellings at the runtime boundary."""
    text = replace_once(text, AGENT_REQUIRE[0], AGENT_REQUIRE[0] + '\n' + AGENT_REQUIRE[1])
    for anchor, patch in PATCHES:
        text = replace_once(text, anchor, patch)
    return text


if __name__ == '__main__':
    runtime = render_runtime()
    assert 'zcode-plugins-official' in runtime and '.zcode-plugin' in runtime and 'ZCODE_' in runtime
    assert runtime.count('__REMOTE_') == 0
    sample = AGENT_REQUIRE[0] + '\n' + '\n'.join(anchor for anchor, _ in PATCHES)
    patched = patch_agent(sample)
    for _, patch in PATCHES:
        assert patch in patched, patch[:60]
    assert patched.count('ccodePluginCompat') == len(PATCHES) + 2
    for changed in (sample * 2,):
        try:
            patch_agent(changed)
        except ValueError:
            pass
        else:
            raise AssertionError('Marketplace compat anchors must be unique')
    print('Marketplace compat patches self-check passed')
