#!/usr/bin/env node
'use strict';
// CCode Windows Computer Use backend: a stdio MCP server over the Windows APIs. Runs as plain
// `node main.cjs` in development and as Electron-as-Node in production (ELECTRON_RUN_AS_NODE),
// with no npm dependencies. The tool surface is the ten tools of the Linux ccode-fast profile.
const { HelperHost } = require('./host.cjs');
const { TakeoverGuard } = require('./guard.cjs');
const { Session } = require('./session.cjs');
const { createTools } = require('./tools.cjs');

const PROTOCOL_VERSION = '2025-06-18', SERVER_VERSION = '1.0.0';
const INSTRUCTIONS = `Real Windows desktop control. This IS the configured Computer Use backend.
PERCEPTION, cheapest first:
1. screen_read_text: what is on screen as TEXT plus element ids and desktop coordinates, no image. Use contains=<text> to fetch just the label you need. This is your default probe.
2. screen_click(element=<id>): click the exact element the last read_text or annotate screenshot found. Use it for every labelled target instead of guessing pixels.
3. screen_screenshot: only when you must SEE layout or an unlabelled control. annotate=true adds numbered marks plus element ids. region=[x,y,w,h] takes desktop pixels and zooms on small text without a re-guess.
ACTIONS: prefer keyboard shortcuts for predictable sequences (Ctrl+L then type then Enter). Actions return a screenshot plus a SENSE line by default; if SENSE says nothing changed, the action was a no-op: do not repeat it, observe and choose another target. Pass shot=false when you will verify with screen_read_text next. screen_wait_text waits for a label with a bounded poll; screen_verify and screen_sense report change as text; screen_focus raises a window before you type into it.
Coordinates: x,y you read from a screenshot are view pixels. Never multiply or divide them yourself; the backend maps them to the desktop. Pass view_id=<view#N> when you took the screenshot more than one step ago.
STOPPED means the user is using the machine right now (they kept moving the pointer). Yield to them, stop acting, and say so. Never pass force=true to defeat takeover; use force only when the user asks you to take control back.
A parked pointer is not takeover: the backend ignores stray movement and waits for the pointer to go idle before acting.
Windows limits that are real, not guesses: there is no portal permission dialog because capture runs directly; input to elevated windows (Task Manager, an elevated console, the UAC secure desktop) is blocked by UIPI and cannot be forced; multi-monitor and per-monitor DPI behavior must be verified on the machine, not assumed.
Observe after uncertain transitions and verify the requested result before reporting success.`;

function listen(stream, onLine) {
  let buffer = '';
  stream.setEncoding('utf8');
  stream.on('data', chunk => {
    buffer += chunk;
    for (;;) {
      const index = buffer.indexOf('\n');
      if (index < 0) return;
      const line = buffer.slice(0, index).trim();
      buffer = buffer.slice(index + 1);
      if (line) onLine(line);
    }
  });
}

function write(message) { process.stdout.write(JSON.stringify(message) + '\n'); }

function main() {
  // Only the ccode-fast surface exists on Windows: report a different requested profile instead
  // of silently serving a tool surface the caller did not ask for.
  if (process.env.MCP_SCREEN_PROFILE && process.env.MCP_SCREEN_PROFILE !== 'ccode-fast') {
    process.stderr.write('windows-desktop implements only the ccode-fast profile; ignoring MCP_SCREEN_PROFILE=' + process.env.MCP_SCREEN_PROFILE + '\n');
  }
  const host = new HelperHost({});
  const guard = new TakeoverGuard({ cursor: () => host.request('cursor', { timeout: 4000 }) });
  const session = new Session();
  const server = createTools({ host, guard, session });

  const reply = (id, result) => write({ jsonrpc: '2.0', id, result });
  const fail = (id, code, message) => write({ jsonrpc: '2.0', id, error: { code, message } });

  async function dispatch(message) {
    const notification = message.id === undefined || message.id === null;
    const method = message.method;
    if (method === 'initialize') {
      return reply(message.id, { protocolVersion: typeof message.params?.protocolVersion === 'string' ? message.params.protocolVersion : PROTOCOL_VERSION,
        capabilities: { tools: { listChanged: false } },
        serverInfo: { name: 'windows-desktop', title: 'Windows Desktop (CCode Computer Use)', version: SERVER_VERSION },
        instructions: INSTRUCTIONS });
    }
    if (method === 'notifications/initialized' || method === 'notifications/cancelled') return undefined;
    if (method === 'ping') return notification ? undefined : reply(message.id, {});
    if (method === 'logging/setLevel') return notification ? undefined : reply(message.id, {});
    if (method === 'tools/list') {
      if (notification) return undefined;
      return reply(message.id, { tools: server.tools.map(tool => ({ name: tool.name, title: tool.title, description: tool.description, inputSchema: tool.inputSchema })) });
    }
    if (method === 'tools/call') {
      if (notification) return undefined;
      const name = message.params?.name, args = message.params?.arguments;
      if (typeof name !== 'string') return fail(message.id, -32602, 'tools/call needs a tool name.');
      const result = await server.call(name, args && typeof args === 'object' ? args : {});
      return reply(message.id, { content: result.content, isError: result.isError === true });
    }
    if (notification) return undefined;
    return fail(message.id, -32601, 'Method not found: ' + String(method));
  }

  let queue = Promise.resolve();
  listen(process.stdin, line => {
    let message = null;
    try { message = JSON.parse(line); }
    catch { write({ jsonrpc: '2.0', id: null, error: { code: -32700, message: 'Parse error' } }); return; }
    if (!message || typeof message !== 'object') { write({ jsonrpc: '2.0', id: null, error: { code: -32600, message: 'Invalid request' } }); return; }
    // Serialized: a tool call must never interleave with the next one on the shared helper.
    queue = queue.then(() => dispatch(message)).catch(error => {
      if (message.id !== undefined && message.id !== null) fail(message.id, -32603, 'Internal error: ' + error.message);
    });
  });

  const stop = () => { server.shutdown(); process.exit(0); };
  process.on('SIGTERM', stop);
  process.on('SIGINT', stop);
  process.stdin.on('end', stop);
  process.stdout.on('error', () => {});
}

main();
