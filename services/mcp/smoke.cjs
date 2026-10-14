'use strict';
const fs = require('node:fs'), os = require('node:os'), path = require('node:path');
async function run({ resourcesPath = path.dirname(__dirname), node = process.execPath, includeOptional = false, configs = {} } = {}) {
  resourcesPath = path.resolve(resourcesPath);
  const runtime = require(path.join(resourcesPath, 'mcp/main.cjs'));
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'ccode-mcp-smoke-'));
  const options = { resourcesPath, root, node };
  const results = [];
  try {
    runtime.bootstrap(options);
    const vaultPath = path.join(root, 'vault'); fs.mkdirSync(vaultPath);
    for (const entry of runtime.list(options)) {
      if (!entry.default && !includeOptional) continue;
      if (!entry.default) {
        const config = entry.id === 'obsidian' ? { vaultPath } : configs[entry.id] || {};
        const missing = entry.configFields.filter(field => field.required && !config[field.key]);
        if (missing.length) { results.push({ id: entry.id, ok: false, error: 'Missing prerequisite: ' + missing.map(field => field.label).join(', ') }); continue; }
        const installed = await runtime.install({ id: entry.id, config }, options);
        if (!installed.ok) { results.push({ id: entry.id, ...installed }); continue; }
      }
      results.push({ id: entry.id, ...await runtime.test({ id: entry.id }, options) });
    }
    return results;
  } finally { fs.rmSync(root, { recursive: true, force: true }); }
}
module.exports = { run };
if (require.main === module) {
  const resourcesPath = process.argv[2] || path.dirname(__dirname);
  const includeOptional = process.argv.includes('--all');
  const configs = {
    github: { token: process.env.CCODE_MCP_GITHUB_TOKEN || '' },
    n8n: { url: process.env.CCODE_MCP_N8N_URL || '', apiKey: process.env.CCODE_MCP_N8N_API_KEY || '' },
  };
  run({ resourcesPath, includeOptional, configs }).then(results => {
    console.log(JSON.stringify(results, null, 2));
    if (results.some(result => !result.ok)) process.exitCode = 1;
  }).catch(() => { console.error('MCP smoke setup failed. Check the staged resources path.'); process.exitCode = 1; });
}
