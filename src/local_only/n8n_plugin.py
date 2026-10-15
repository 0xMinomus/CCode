"""List the downloadable n8n plugin without seeding its payload or cache."""
import json
import pathlib
from . import replace_once

PLUGIN_ID = 'n8n@ccode-plugins-official'
MANIFEST = pathlib.Path(__file__).resolve().parents[1] / 'plugins/n8n-marketplace.json'
MARKETPLACE_ANCHOR = 'name:Yp,plugins:[...s,...l]}'
MCP_ANCHOR = 'return _[PR]=t.loaded.id,{type:"stdio",command:AC(g,t,{allowSensitive:!1}),'


def patch_agent(text):
    entry = json.loads(MANIFEST.read_text())['plugins'][0]
    # The native partition merger runs for bundled seed and remote refresh alike.
    # A listing has no cachePath: only the native installer downloads the zip.
    listing = json.dumps(entry, separators=(',', ':'))
    text = replace_once(text, MARKETPLACE_ANCHOR,
                        'name:Yp,plugins:[...s.filter(cc=>cc.name!=="n8n"),'
                        '...l.filter(cc=>cc.name!=="n8n"),' + listing + ']}')
    # nodes.db exceeds the native 50 MiB entry limit. Only the exact pinned zip
    # gets 80 MiB; the SHA check precedes extraction and all other limits remain.
    text = replace_once(text, 'archivePath:n,signal:e.signal,targetRoot:o}',
                        'archivePath:n,signal:e.signal,targetRoot:o,maxEntryBytes:l==='
                        + json.dumps(entry['source']['sha256']) + '?80*1024*1024:void 0}')
    text = replace_once(text, 'if(g.uncompressedSize>GGr)',
                        'if(g.uncompressedSize>(e.maxEntryBytes??GGr))')
    text = replace_once(text, 'let T=await zBs(n,g,e.signal);',
                        'let T=await zBs(n,g,e.signal,e.maxEntryBytes);')
    text = replace_once(text, 'function zBs(e,t,n){', 'function zBs(e,t,n,ccMax=GGr){')
    text = replace_once(text, 'if(f+=w.byteLength,f>GGr){', 'if(f+=w.byteLength,f>ccMax){')
    # Downloaded manifests do not pass through the bundled-plugin host rewrite.
    # Reuse its Electron Node host at resolution, leaving credentials in env.
    return replace_once(text, MCP_ANCHOR,
                        'if(t.loaded.id===' + json.dumps(PLUGIN_ID) + '){AEn();'
                        'let cc=k7o({rootPath:t.loaded.rootPath,env:{..._,[PR]:t.loaded.id},'
                        'cwd:typeof e.cwd==="string"?AC(e.cwd,t,{allowSensitive:!1}):void 0,'
                        'timeoutMs:e.timeoutMs});'
                        'if(!cc)throw new Error("The n8n plugin requires the Electron Node host");'
                        'return{...cc,enabled:typeof e.enabled==="boolean"?e.enabled:void 0,source:s}}'
                        + MCP_ANCHOR)
