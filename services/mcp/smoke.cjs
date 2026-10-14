'use strict';
const fs = require('node:fs'), os = require('node:os'), path = require('node:path');
async function run({ resourcesPath = path.dirname(__dirname), node = process.execPath, includeOptional = false } = {}) {
  resourcesPath = path.resolve(resourcesPath);
  const runtime = require(path.join(resourcesPath, 'mcp/main.cjs'));
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'ccode-mcp-smoke-'));
  const options = { resourcesPath, root, node };
  const results = [];
  try {
    runtime.bootstrap(options);
    for (const entry of runtime.list(options)) {
      if (!entry.default && !includeOptional) continue;
      if (!entry.default) {
        const installed = await runtime.install({ id: entry.id }, options);
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
  run({ resourcesPath, includeOptional: process.argv.includes('--all') }).then(results => {
    console.log(JSON.stringify(results, null, 2));
    if (results.some(result => !result.ok)) process.exitCode = 1;
  }).catch(() => { console.error('MCP smoke setup failed. Check the staged resources path.'); process.exitCode = 1; });
}
