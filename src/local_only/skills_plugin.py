"""Expose the native bundled skill pack without registering a plugin.

The agent already discovers bundled-skills. Settings uses a separate host-side
filesystem scanner, so both catalogs and the renderer need pinned patches.
"""
from . import replace_once

PACK_DIR = 'bundled-skills'
LEGACY_PLUGIN_ID = 'ccode-skills@ccode-plugins-official'

AGENT_DISCOVERY_ANCHOR = 'if(!I||I.source==="official"&&t.config.suppressedBuiltins.includes(I.id))continue;'
AGENT_INSTALLED_ANCHOR = 'f=X7(n),g=new Set(f.map(L=>L.id)),_=[];'
AGENT_AVAILABLE_ANCHOR = 'T=_.flatMap(L=>L.entries.map(U=>{let B=O$a(U,L.summary.id,g);'
AGENT_CATALOG_ANCHOR = 'function LZo(e,t){return{authority:e,skills:t.skills.filter(n=>n.source!=="bundled").map(YXa)}}'


def patch_agent(text):
    """Keep native discovery and exclude only the obsolete official plugin ID."""
    text = replace_once(text, AGENT_DISCOVERY_ANCHOR,
                        f'if(!I||I.id==="{LEGACY_PLUGIN_ID}"||I.source==="official"&&t.config.suppressedBuiltins.includes(I.id))continue;')
    text = replace_once(text, AGENT_INSTALLED_ANCHOR,
                        f'f=X7(n).filter(L=>L.id!=="{LEGACY_PLUGIN_ID}"),g=new Set(f.map(L=>L.id)),_=[];')
    text = replace_once(text, AGENT_AVAILABLE_ANCHOR,
                        f'T=_.flatMap(L=>L.entries.filter(U=>`${{U.name}}@${{L.summary.id}}`!=="{LEGACY_PLUGIN_ID}").map(U=>{{let B=O$a(U,L.summary.id,g);')
    return replace_once(text, AGENT_CATALOG_ANCHOR,
                        'function LZo(e,t){return{authority:e,skills:t.skills.map(YXa)}}')


HOST_PLUGIN_ANCHOR = 'if(c.marketplace===G_&&e.suppressedBuiltins.includes(l)||a.has(l))continue;'
HOST_ROOTS_ANCHOR = 'n.push(...await phe());let r=[],o=[],s=new Set'
HOST_ENTRY_ANCHOR = 'scope:u.scope,enabled:!0,...u.pluginName?{pluginName:u.pluginName}:{}'
HOST_DELETE_ANCHOR = 'if(o.scope==="plugin")throw new Error('
HOST_ENABLED_ANCHOR = 'if(!d)throw new Error(`Skill not found: ${n.skillId}`);let l=await NK();'


def patch_host(text):
    """Feed native system skills into the actual Settings skillsService.list."""
    text = replace_once(text, HOST_PLUGIN_ANCHOR,
                        f'if(l==="{LEGACY_PLUGIN_ID}"||c.marketplace===G_&&e.suppressedBuiltins.includes(l)||a.has(l))continue;')
    text = replace_once(text, HOST_ROOTS_ANCHOR,
                        'n.push(...await phe());n.push({scope:"user",source:"bundled",rootPath:j2e(new URL("../../../glm/packages/bundled-skills/skills",import.meta.url))});let r=[],o=[],s=new Set')
    text = replace_once(text, HOST_ENTRY_ANCHOR,
                        'scope:u.scope,enabled:!0,...u.source==="bundled"?{source:"bundled",readOnly:!0}:{},...u.pluginName?{pluginName:u.pluginName}:{}')
    text = replace_once(text, HOST_ENABLED_ANCHOR,
                        'if(!d)throw new Error(`Skill not found: ${n.skillId}`);if(d.readOnly)throw new Error("Bundled skills are read-only.");let l=await NK();')
    return replace_once(text, HOST_DELETE_ANCHOR,
                        'if(o.readOnly)throw new Error("Bundled skills are read-only.");if(o.scope==="plugin")throw new Error(')


RENDERER_BUILTIN_ANCHOR = 'function L7e(e){if(e.scope!==`plugin`)return!1;'
RENDERER_GROUP_ANCHOR = 'function R4t(e,t){let n=new Set,r=[],i=[];'
RENDERER_GROUP_PUSH_ANCHOR = 'I0(t,[a.name,a.description,a.pluginName])&&(a.scope===`plugin`?i.push(a):r.push(a)))}return{local:r,plugin:i}}'
RENDERER_COUNT_ANCHOR = 'Ce=xe.local.length+xe.plugin.length,we='
RENDERER_DEFAULT_ANCHOR = 'Se.filter(e=>e.id.startsWith(`plugin:`)).map(e=>'
RENDERER_ACTIONS_ANCHOR = 'children:e.scope===`plugin`?null:(0,$.jsxs)($.Fragment,{children:[(0,$.jsx)(Xx,'
RENDERER_DELETE_ANCHOR = 'if(!(!E||e.scope===`plugin`)&&await T({title:p.formatMessage({id:`settings.skills.delete.title`})'
RENDERER_SCOPE_ANCHOR = 'pe=(0,Q.useCallback)(e=>{switch(e.scope){'


def patch_renderer(text):
    """Use the existing skill rows and translated Default label for native skills."""
    text = replace_once(text, RENDERER_BUILTIN_ANCHOR,
                        'function L7e(e){if(e.source===`bundled`)return!0;if(e.scope!==`plugin`)return!1;')
    text = replace_once(text, RENDERER_GROUP_ANCHOR,
                        'function R4t(e,t){let n=new Set,r=[],i=[],o=[];')
    text = replace_once(text, RENDERER_GROUP_PUSH_ANCHOR,
                        'I0(t,[a.name,a.description,a.pluginName])&&(a.source===`bundled`?o.push(a):a.scope===`plugin`?i.push(a):r.push(a)))}return{local:r,plugin:i,builtIn:o}}')
    text = replace_once(text, RENDERER_COUNT_ANCHOR,
                        'Ce=xe.local.length+xe.plugin.length+xe.builtIn.length,we=')
    text = replace_once(text, RENDERER_DEFAULT_ANCHOR,
                        'xe.builtIn.length>0?(0,$.jsxs)(`section`,{"data-skills-group":`default`,className:`space-y-4`,children:[(0,$.jsx)(H7,{count:xe.builtIn.length,title:p.formatMessage({id:`settings.scope.default`})}),Ie(xe.builtIn)]}):null,Se.filter(e=>e.id.startsWith(`plugin:`)).map(e=>')
    text = replace_once(text, RENDERER_ACTIONS_ANCHOR,
                        'children:e.readOnly||e.scope===`plugin`?null:(0,$.jsxs)($.Fragment,{children:[(0,$.jsx)(Xx,')
    text = replace_once(text, RENDERER_DELETE_ANCHOR,
                        'if(!(!E||e.readOnly||e.scope===`plugin`)&&await T({title:p.formatMessage({id:`settings.skills.delete.title`})')
    return replace_once(text, RENDERER_SCOPE_ANCHOR,
                        'pe=(0,Q.useCallback)(e=>{if(e.source===`bundled`)return p.formatMessage({id:`settings.scope.default`});switch(e.scope){')
