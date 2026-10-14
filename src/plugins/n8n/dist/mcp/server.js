'use strict';
const fs = require('node:fs'), path = require('node:path');
function configure(env) {
  const apiKey = (env.N8N_API_KEY || '').trim();
  if (!apiKey) throw Error('Set the n8n API key in plugin settings before connecting.');
  let url;
  try { url = new URL((env.N8N_API_URL || '').trim()); }
  catch { throw Error('Set a valid n8n instance URL in plugin settings.'); }
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash)
    throw Error('Use an HTTP or HTTPS n8n instance URL without credentials, query parameters, or fragments.');
  const local = ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname);
  if (url.protocol !== 'https:' && !local)
    throw Error('Use HTTPS for a remote n8n instance to protect the API key.');
  if (!env.CCODE_PLUGIN_DATA || !path.isAbsolute(env.CCODE_PLUGIN_DATA))
    throw Error('The n8n plugin requires its private data directory.');
  const home = env.CCODE_PLUGIN_DATA;
  return {
    N8N_API_URL: url.toString().replace(/\/+$/, ''),
    N8N_API_KEY: apiKey,
    N8N_MCP_ACCESS_TOKEN: (env.N8N_MCP_ACCESS_TOKEN || '').trim(),
    MCP_MODE: 'stdio', LOG_LEVEL: 'error', DISABLE_CONSOLE_OUTPUT: 'true',
    N8N_MCP_TELEMETRY_DISABLED: 'true',
    WEBHOOK_SECURITY_MODE: local ? 'moderate' : 'strict',
    HOME: home, XDG_CONFIG_HOME: path.join(home, '.config'), XDG_CACHE_HOME: path.join(home, '.cache')
  };
}
function main() {
  const env = configure(process.env);
  fs.mkdirSync(env.HOME, { recursive: true, mode: 0o700 });
  Object.assign(process.env, env);
  require(path.join(path.dirname(process.execPath), 'resources/mcp/runtime/node_modules/n8n-mcp/dist/mcp/stdio-wrapper.js'));
}
exports.configure = configure;
exports.main = main;
if (require.main === module) main();
