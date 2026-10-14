"""Mount the catalog in the pinned native MCP Settings list, not its editor."""
from . import replace_once

RENDERER_CATALOG_ANCHOR = 'qe?Je?(0,$.jsx)(C7,{label:h.formatMessage({id:`settings.plugin.mcp.searchEmpty`})}):null:(0,$.jsx)(S7,{label:h.formatMessage({id:`common.loading`})}),(0,$.jsxs)(`div`,{className:!qe||Je?`hidden`:`space-y-6`,"data-mcp-list-layout":`grouped`'


def patch_renderer(text):
    catalog = '(0,$.jsx)(CCodeMcpCatalog,{local:!n&&!r&&!a,scope:o,searchQuery:he,onInstalled:async()=>{if(!await ee(v.mcpSyncService,F))throw Error("Installed, but the native server list could not refresh. Use Refresh in Installed servers.");await Fe({trigger:`manual`})}}),'
    return replace_once(text, RENDERER_CATALOG_ANCHOR, catalog + RENDERER_CATALOG_ANCHOR)


if __name__ == '__main__':
    assert patch_renderer(RENDERER_CATALOG_ANCHOR).count('(CCodeMcpCatalog,') == 1
    for changed in ('', RENDERER_CATALOG_ANCHOR * 2):
        try:
            patch_renderer(changed)
        except ValueError:
            pass
        else:
            raise AssertionError('MCP Settings anchor must be unique')
