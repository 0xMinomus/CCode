"""Render optional MCP servers as rows of the native Installed servers list.

The pinned page builds that list in `FTn` from the workspace MCP config. This
patch merges the catalog's not-yet-installed entries into the same list, so an
optional server is one native-styled row with an Install button; once the entry
is written to the workspace config the native row (with its on/off switch)
replaces it.
"""
from . import replace_once

# The list renderer head: signature, then the intl hook and the empty-state
# branch. `c2` is what the list renders, `c3` refreshes both the catalog and the
# native store after an install.
LIST_HEAD_ANCHOR = ('function FTn({servers:e,onCreate:t,onEdit:n,onToggle:r,onOpenAuthorization:i,'
                    'emptyTitle:a,emptyDescription:o,hideMetadata:s=!1}){let{intl:c}=q();return e.length===0?')
LIST_HEAD_PATCH = ('function FTn({servers:e,onCreate:t,onEdit:n,onToggle:r,onOpenAuthorization:i,'
                   'emptyTitle:a,emptyDescription:o,hideMetadata:s=!1}){let{intl:c}=q(),'
                   'c0=CCodeMcpCatalog.useEntries(),'
                   'c1=(c0.status===`ready`?c0.items.filter(x=>!x.installed&&!e.some(y=>y.name===x.id)):[]).map(x=>({id:`catalog:`+x.id,name:x.name,catalogEntry:x})),'
                   'c2=[...e,...c1],'
                   'c3=async()=>{await c0.reload()};'
                   'return c2.length===0?')
LIST_ROWS_ANCHOR = ('(0,$.jsx)(U7,{items:e,getKey:e=>e.id,renderItem:e=>(0,$.jsx)(PTn,'
                    '{server:e,onEdit:n,onToggle:r,onOpenAuthorization:i,hideMetadata:s})})')
LIST_ROWS_PATCH = ('(0,$.jsx)(U7,{items:c2,getKey:e=>e.id,renderItem:e=>e.catalogEntry?'
                   '(0,$.jsx)(CCodeMcpCatalogRow,{entry:e.catalogEntry,onInstalled:c3}):'
                   '(0,$.jsx)(PTn,{server:e,onEdit:n,onToggle:r,onOpenAuthorization:i,hideMetadata:s})})')


def patch_renderer(text):
    return replace_once(replace_once(text, LIST_HEAD_ANCHOR, LIST_HEAD_PATCH), LIST_ROWS_ANCHOR, LIST_ROWS_PATCH)


if __name__ == '__main__':
    sample = LIST_HEAD_ANCHOR + 'CARD}):' + LIST_ROWS_ANCHOR
    patched = patch_renderer(sample)
    assert patched.count('CCodeMcpCatalog.useEntries()') == 1
    assert patched.count('CCodeMcpCatalogRow') == 1
    assert 'items:c2' in patched and 'catalogEntry' in patched
    for changed in ('', LIST_HEAD_ANCHOR, LIST_ROWS_ANCHOR, sample * 2):
        try:
            patch_renderer(changed)
        except ValueError:
            pass
        else:
            raise AssertionError('MCP Installed-servers anchors must be unique')
