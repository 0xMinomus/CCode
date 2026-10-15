'use strict';
// The Windows Computer Use tool surface: the same ten tools as the Linux ccode-fast profile
// (services/desktop/ccode_fast_profile.py) over Windows APIs. Text-first perception, element-id
// targeting, a hard pointer-takeover guard, and a post-action SENSE line so the model can skip
// a screenshot it does not need.
const { limitText, limits, planCapture, viewToDesktop } = require('./shot.cjs');
const { StoppedError } = require('./guard.cjs');
const { senseText } = require('./session.cjs');

const STOPPED_HINT = 'STOPPED means the user is using the machine right now (they kept moving the pointer). ' +
  'Yield to them, stop acting, and say so. Never pass force=true to defeat takeover; use force only when the ' +
  'user asks you to take control back.';
const POST_SHOT = ['screen_click', 'screen_scroll', 'screen_key', 'screen_type'];
const PLATFORM_NOTES = 'Windows notes: there is no portal permission dialog (capture runs directly), input to ' +
  'elevated windows is blocked by UIPI and cannot be forced, and multi-monitor/DPI behavior must be verified, not assumed.';

function delay(ms) { return new Promise(resolve => setTimeout(resolve, ms)); }

const TOOLS = [
  {
    name: 'screen_sense', title: 'Sense',
    description: 'Return the change signal of the most recent action (changed / opened / modal / no_op / activity) ' +
      'as text. Cheap way to notice a no-op click without a screenshot. Passive: it does not wait for anything new.',
    inputSchema: { type: 'object', properties: {}, additionalProperties: false },
  },
  {
    name: 'screen_read_text', title: 'Read Screen As Text',
    description: 'Read the screen as TEXT plus clickable elements through UI Automation: no image, so it costs a ' +
      'fraction of a screenshot and is the default way to locate a target, read a value, or confirm that something ' +
      'appeared. Returns {origin,size,view,focused,count,elements:[{id,role,text,x,y}]} with desktop coordinates. ' +
      'Pass contains=<text> to return only matching elements. Pass an id straight to screen_click(element=<id>). ' +
      PLATFORM_NOTES,
    inputSchema: { type: 'object', properties: {
      contains: { type: 'string', description: 'Return only elements whose text contains this (case-insensitive).' },
      root: { type: 'string', enum: ['foreground', 'desktop'], description: 'Read the focused window (default) or every top-level window.' },
      use_cache: { type: 'boolean', description: 'Reuse the element ids when the element list is unchanged (default true).' },
    }, additionalProperties: false },
  },
  {
    name: 'screen_click', title: 'Click',
    description: 'Click a target. Prefer element=<id> from the latest screen_read_text or screen_screenshot ' +
      '(annotate=true): the backend resolves the exact desktop point and rejects ids captured under an older view, ' +
      'so you never guess a pixel. Otherwise pass x,y as view pixels with the matching view_id. Omit x,y and ' +
      'element to click in place. button: left|right|middle; double:bool. focus=<app> raises that window first. ' +
      'verify=true adds a warning when nothing on screen changed. force=true bypasses the pointer guard and must ' +
      'only be used when the user asks you to take control back. ' + PLATFORM_NOTES,
    inputSchema: { type: 'object', properties: {
      element: { type: 'string', description: 'Element id (e12) from the latest read_text or annotate screenshot.' },
      x: { type: 'number', description: 'View pixel x.' }, y: { type: 'number', description: 'View pixel y.' },
      view_id: { type: 'string', description: 'The view#N the x,y came from; omit when they come from the newest view.' },
      button: { type: 'string', enum: ['left', 'right', 'middle'] }, double: { type: 'boolean' },
      focus: { type: 'string', description: 'Raise this window (title or process substring) before clicking.' },
      verify: { type: 'boolean' }, force: { type: 'boolean' },
      shot: { type: 'boolean', description: 'Include a post-action screenshot (default true).' },
      settle: { type: 'number', description: 'Milliseconds to wait for a repaint before the post-action capture (default 250).' },
    }, additionalProperties: false },
  },
  {
    name: 'screen_type', title: 'Type Text',
    description: 'Type text into the focused control as Unicode. Pass enter=true to submit in the same call ' +
      'instead of a second round trip. Keyboard input goes to the focused window: call screen_focus first when the ' +
      'target is not already focused. A post-action screenshot and its SENSE line are included by default; if SENSE ' +
      'says nothing changed, treat the action as a no-op. ' + PLATFORM_NOTES,
    inputSchema: { type: 'object', properties: {
      text: { type: 'string' }, enter: { type: 'boolean' }, force: { type: 'boolean' },
      shot: { type: 'boolean' }, settle: { type: 'number' },
    }, required: ['text'], additionalProperties: false },
  },
  {
    name: 'screen_key', title: 'Send Keys',
    description: 'Send a key or chord to the focused window, e.g. keys="Ctrl+L", "Enter", "Alt+F4", "F5", ' +
      '"Ctrl+Shift+S". Modifiers: Ctrl, Shift, Alt, Win. ' + PLATFORM_NOTES,
    inputSchema: { type: 'object', properties: {
      keys: { type: 'string' }, force: { type: 'boolean' }, shot: { type: 'boolean' }, settle: { type: 'number' },
    }, required: ['keys'], additionalProperties: false },
  },
  {
    name: 'screen_scroll', title: 'Scroll',
    description: 'Scroll the window under the pointer. direction: up|down|left|right; amount is in wheel steps ' +
      '(1-50, default 3). Pass x,y as view pixels to place the pointer over the target first. ' + PLATFORM_NOTES,
    inputSchema: { type: 'object', properties: {
      direction: { type: 'string', enum: ['up', 'down', 'left', 'right'] }, amount: { type: 'number' },
      x: { type: 'number' }, y: { type: 'number' }, view_id: { type: 'string' }, force: { type: 'boolean' },
      shot: { type: 'boolean' }, settle: { type: 'number' },
    }, additionalProperties: false },
  },
  {
    name: 'screen_wait_text', title: 'Wait For Text',
    description: 'Wait until text appears (or disappears with absent=true), then return the match. Use this instead ' +
      'of screenshot after screenshot while a page loads or an app starts. Bounded, read-only wait. Windows has no ' +
      'compositor damage event, so this is a bounded poll with a short interval that backs off, not a hybrid ' +
      'damage/poll wait.',
    inputSchema: { type: 'object', properties: {
      text: { type: 'string', description: 'Text to wait for (case-insensitive substring).' },
      absent: { type: 'boolean', description: 'Wait until the text is gone instead.' },
      timeout_ms: { type: 'number', description: 'Upper bound in ms (default 8000, max 60000).' },
      root: { type: 'string', enum: ['foreground', 'desktop'] },
    }, required: ['text'], additionalProperties: false },
  },
  {
    name: 'screen_verify', title: 'Verify Change',
    description: 'Check whether the area around a point (or the watched window) actually changed, and report it as ' +
      'text. Use after an action whose effect you cannot see yet, so you do not have to pull a screenshot just to ' +
      'answer "did that work".',
    inputSchema: { type: 'object', properties: {
      x: { type: 'number', description: 'View pixel x of the region to watch.' },
      y: { type: 'number', description: 'View pixel y of the region to watch.' },
      width: { type: 'number', description: 'View pixel width (default 200).' },
      height: { type: 'number', description: 'View pixel height (default 120).' },
      window: { type: 'boolean', description: 'Watch the whole focused window instead of a region.' },
      view_id: { type: 'string' },
    }, additionalProperties: false },
  },
  {
    name: 'screen_screenshot', title: 'Screenshot',
    description: 'Observe the desktop as an image. Screenshot only when you need to SEE layout, color, or an ' +
      'unlabelled control; screen_read_text answers "what is on screen" as text for far fewer tokens. No args = ' +
      'full virtual desktop. annotate=true overlays numbered marks and returns element ids you can click with ' +
      'screen_click(element=<id>). region=[x,y,w,h] takes DESKTOP pixels, not view pixels: use it to zoom on small ' +
      'text instead of guessing. The header states the shipped size, the captured desktop rect, and the scale; ' +
      'never compute it yourself. Coordinates you read from the image are view pixels: pass them with ' +
      'view_id=<the view#N in the header>. ' + PLATFORM_NOTES,
    inputSchema: { type: 'object', properties: {
      region: { type: 'array', items: { type: 'number' }, description: 'Desktop pixels [x,y,width,height].' },
      annotate: { type: 'boolean', description: 'Overlay numbered marks and return clickable element ids.' },
      use_cache: { type: 'boolean' },
    }, additionalProperties: false },
  },
  {
    name: 'screen_focus', title: 'Focus Window',
    description: 'Raise and keyboard-focus a window by app name, title substring, or window id (e.g. ' +
      'focus(app="notepad")). Keyboard input goes to the focused window, so call this before screen_type/screen_key ' +
      'when the target is not already focused. Reports an error instead of pretending when the focus did not ' +
      'transfer. ' + PLATFORM_NOTES,
    inputSchema: { type: 'object', properties: {
      app: { type: 'string', description: 'Window title or process name substring.' },
      title: { type: 'string', description: 'Window title substring.' },
      window: { type: 'string', description: 'Exact window handle from a previous result.' },
      force: { type: 'boolean' },
    }, additionalProperties: false },
  },
];

function createTools({ host, guard, session, env = process.env }) {
  const { maxEdge, maxOutputKb } = limits(env);
  const skipUnchangedShot = env.CCODE_CUA_SKIP_UNCHANGED_SHOT !== '0';
  let desktop = null, desktopAt = 0;

  const text = value => ({ type: 'text', text: limitText(String(value), maxOutputKb) });
  const image = data => ({ type: 'image', data, mimeType: 'image/png' });
  const failure = message => ({ content: [{ type: 'text', text: limitText(message, maxOutputKb) }], isError: true });
  const payload = value => ({ type: 'text', text: limitText(JSON.stringify(value), maxOutputKb) });

  async function geometry() {
    if (!desktop || Date.now() - desktopAt > 30000) { desktop = await host.request('desktop'); desktopAt = Date.now(); }
    return desktop;
  }

  async function snapshot(options = {}) {
    const plan = planCapture(options.region || null, await geometry(), maxEdge);
    if (!plan) return null;
    const shot = await host.request('screenshot', { x: plan.rect.x, y: plan.rect.y, width: plan.rect.width, height: plan.rect.height,
      targetWidth: plan.view.width, targetHeight: plan.view.height, encode: options.encode === true, marks: options.marks || null });
    return { hash: shot.sha256, bytes: shot.bytes, png: shot.png || null, topLevel: shot.topLevel, foreground: shot.foreground,
      rect: plan.rect, view: { origin: { x: plan.rect.x, y: plan.rect.y }, width: plan.view.width, height: plan.view.height, scale: plan.view.scale } };
  }

  const elements = options => host.request('elements', { root: options.root || 'foreground', contains: options.contains || null, limit: 400 });

  // Every action shares one shape: guard the pointer, observe, inject, settle, observe, publish
  // a SENSE line, and drop the image when that line says the action changed nothing.
  async function act(name, args, inject) {
    const shot = args.shot === undefined ? POST_SHOT.includes(name) : args.shot === true;
    try { await guard.check(args.force === true); }
    catch (error) {
      return error instanceof StoppedError ? failure(error.message + '\n' + STOPPED_HINT) : failure('The pointer guard failed: ' + error.message);
    }
    const before = shot ? await snapshot() : null;
    const outcome = await inject();
    if (outcome.failure) return failure(outcome.failure);
    const settle = args.settle === undefined ? 250 : Number(args.settle);
    if (settle > 0) await delay(settle);
    const content = [text(outcome.text)];
    if (shot) {
      // The before-shot only needs its hash; the after-shot is the image the model receives.
      const after = await snapshot({ encode: true });
      if (after && before) {
        session.record({ name, before: { hash: before.hash, topLevel: before.topLevel, foreground: before.foreground, elements: null },
          after: { hash: after.hash, topLevel: after.topLevel, foreground: after.foreground, elements: null } });
        const sense = senseText(session.action);
        content.push(text(sense));
        const unchanged = sense.includes('nothing changed');
        if (args.verify === true && unchanged) content.push(text('verify: nothing on screen changed after this action.'));
        if (skipUnchangedShot && unchanged) {
          content.push(text('shot skipped: the screen did not change after this action. Treat it as a no-op and pick ' +
            'another target, or take a screenshot only if you need the pixels.'));
        } else if (after.png) content.push(image(after.png));
      }
    }
    return { content };
  }

  const handlers = {
    async screen_sense() { return { content: [text(senseText(session.action))] }; },

    async screen_read_text(args = {}) {
      const rows = await elements(args);
      const desktop = await geometry();
      // Element coordinates are desktop pixels, so the view is the desktop at scale 1: a model
      // that feeds a returned x,y back in gets the same point instead of a double-counted offset.
      const view = session.openView({ x: desktop.x, y: desktop.y }, { width: desktop.width, height: desktop.height, scale: 1 });
      const items = session.assign(rows.elements);
      const body = { origin: { x: view.origin.x, y: view.origin.y }, size: { width: view.width, height: view.height },
        view: view.id, window: rows.rect || null, focused: rows.focused, count: items.length, elements: items };
      return { content: [payload(body)] };
    },

    async screen_screenshot(args = {}) {
      const region = Array.isArray(args.region) && args.region.length === 4 ? args.region.map(Number) : null;
      let items = null, marks = null;
      if (args.annotate === true) {
        const rows = await elements({ root: 'foreground' });
        items = rows.elements;
        marks = items.map((row, index) => ({ x: row.left, y: row.top, width: row.width, height: row.height, label: String(index + 1) }));
      }
      const shot = await snapshot({ region, encode: true, marks });
      if (!shot) return failure('region ' + JSON.stringify(region) + ' is outside the virtual desktop.');
      const view = session.openView({ x: shot.rect.x, y: shot.rect.y }, shot.view);
      const header = [view.id + ' screenshot ' + shot.view.width + 'x' + shot.view.height + ' (captured desktop rect ' +
        shot.rect.x + ',' + shot.rect.y + ' ' + shot.rect.width + 'x' + shot.rect.height + ', scale ' + shot.view.scale.toFixed(4) + ')',
        'coordinates read from this image are view pixels: pass them with view_id=' + view.id + ' (or omit view_id on this step)',
        'focused: ' + (shot.foreground?.title || '(untitled)') + (shot.foreground?.process ? ' [' + shot.foreground.process + ']' : '')];
      const content = [text(header.join('\n'))];
      if (items) {
        const assigned = session.assign(items);
        header.push('annotate marks 1..' + marks.length + ' match the element ids below (mark 1 = e1); click with ' +
          'screen_click(element=<id>)');
        content[0] = text(header.join('\n'));
        content.push(payload({ view: view.id, count: assigned.length, elements: assigned }));
      }
      content.push(image(shot.png));
      return { content };
    },

    async screen_click(args = {}) {
      let point = null;
      if (args.element !== undefined && args.element !== null && args.element !== '') {
        try { const row = session.resolveElement(args.element); point = { x: row.x, y: row.y }; }
        catch (error) { return failure(error.message); }
      } else if (Number.isFinite(Number(args.x)) && Number.isFinite(Number(args.y))) {
        const view = session.viewFor(args.view_id);
        point = view ? viewToDesktop({ x: Number(args.x), y: Number(args.y) }, view) : null;
        if (!point) return failure('Unknown view_id ' + args.view_id + '. Read the screen again and use its view id.');
      }
      if (args.focus) {
        try { await host.request('focus', { app: String(args.focus) }); }
        catch (error) { return failure(error.message); }
      }
      return act('screen_click', args, async () => {
        const clicked = await host.request('click', { x: point?.x, y: point?.y, button: args.button || 'left', double: args.double === true });
        guard.record({ x: clicked.x, y: clicked.y });
        return { text: 'clicked ' + (point ? 'at desktop ' : 'in place at ') + clicked.x + ',' + clicked.y + ' with the ' +
          clicked.clicked + ' button' + (clicked.count > 1 ? ' (double)' : '') };
      });
    },

    async screen_type(args = {}) {
      if (typeof args.text !== 'string' || !args.text) return failure('text is required.');
      return act('screen_type', args, async () => {
        const typed = await host.request('type', { text: args.text });
        if (args.enter === true) await host.request('key', { keys: 'Enter' });
        return { text: 'typed ' + typed.typed + ' character(s)' + (args.enter === true ? ' and pressed Enter' : '') };
      });
    },

    async screen_key(args = {}) {
      if (typeof args.keys !== 'string' || !args.keys.trim()) return failure('keys is required (for example Ctrl+L).');
      return act('screen_key', args, async () => {
        const pressed = await host.request('key', { keys: args.keys });
        return { text: 'pressed ' + pressed.keys };
      });
    },

    async screen_scroll(args = {}) {
      let point = null;
      if (Number.isFinite(Number(args.x)) && Number.isFinite(Number(args.y))) {
        const view = session.viewFor(args.view_id);
        point = view ? viewToDesktop({ x: Number(args.x), y: Number(args.y) }, view) : null;
        if (!point) return failure('Unknown view_id ' + args.view_id + '. Read the screen again and use its view id.');
      }
      return act('screen_scroll', args, async () => {
        const scrolled = await host.request('scroll', { direction: args.direction || 'down', amount: args.amount || 3, x: point?.x, y: point?.y });
        if (point) guard.record(point);
        return { text: 'scrolled ' + scrolled.direction + ' ' + scrolled.steps + ' step(s)' + (point ? ' at desktop ' + point.x + ',' + point.y : ' at the pointer') };
      });
    },

    async screen_wait_text(args = {}) {
      const wanted = String(args.text ?? '').toLowerCase();
      if (!wanted) return failure('text is required.');
      const timeout = Math.min(Math.max(Number(args.timeout_ms) || 8000, 200), 60000);
      const started = Date.now();
      let interval = 150;
      try {
        while (Date.now() - started < timeout) {
          const rows = await host.request('elements', { root: args.root || 'foreground', contains: args.text, limit: 200 });
          const match = rows.elements.find(row => String(row.text).toLowerCase().includes(wanted)) || null;
          if (args.absent === true ? !match : match) {
            return { content: [payload({ appeared: args.absent !== true, absent: args.absent === true,
              waited_ms: Date.now() - started, focused: rows.focused,
              match: match ? { role: match.role, text: match.text, x: match.x, y: match.y } : null })] };
          }
          await delay(interval);
          interval = Math.min(500, Math.round(interval * 1.5));
        }
      } catch (error) { return failure('screen_wait_text failed: ' + error.message); }
      return failure('screen_wait_text timed out after ' + timeout + ' ms waiting for "' + args.text + '"' +
        (args.absent === true ? ' to disappear' : '') + ' within ' + (args.root || 'foreground') + '. Nothing matched: ' +
        'the window may not be focused, or the text is not exposed through UI Automation. Run screen_read_text ' +
        'without contains to see what is actually there.');
    },

    async screen_verify(args = {}) {
      let region = null;
      if (args.window === true) {
        const info = await host.request('foreground');
        if (!info.rect || info.rect.width < 8 || info.rect.height < 8) return failure('The focused window has no readable rectangle.');
        region = [info.rect.x, info.rect.y, info.rect.width, info.rect.height];
      } else if (Number.isFinite(Number(args.x)) && Number.isFinite(Number(args.y))) {
        const view = session.viewFor(args.view_id);
        const topLeft = view ? viewToDesktop({ x: Number(args.x), y: Number(args.y) }, view) : null;
        if (!topLeft) return failure('Unknown view_id ' + args.view_id + '. Read the screen again and use its view id.');
        const scale = view.scale || 1;
        region = [topLeft.x, topLeft.y, Math.round((Number(args.width) || 200) / scale), Math.round((Number(args.height) || 120) / scale)];
      } else {
        const cursor = await host.request('cursor');
        region = [cursor.x - 100, cursor.y - 60, 200, 120];
      }
      const shot = await snapshot({ region });
      if (!shot) return failure('The verify region is outside the virtual desktop.');
      const key = shot.rect.x + ',' + shot.rect.y + ',' + shot.rect.width + ',' + shot.rect.height;
      const previous = session.baseline(key);
      session.remember(key, shot.hash);
      return { content: [payload({ region: shot.rect, changed: previous ? previous.hash !== shot.hash : null,
        baseline: previous ? 'recorded ' + Math.round((Date.now() - previous.at) / 1000) + 's ago' : 'none (first look at this region)',
        focused: shot.foreground?.title || null })] };
    },

    async screen_focus(args = {}) {
      try { await guard.check(args.force === true); }
      catch (error) {
        return error instanceof StoppedError ? failure(error.message + '\n' + STOPPED_HINT) : failure('The pointer guard failed: ' + error.message);
      }
      try {
        const focused = await host.request('focus', { app: args.app || null, title: args.title || null, window: args.window || null });
        return { content: [payload({ focused: true, hwnd: focused.hwnd, title: focused.title, process: focused.process })] };
      } catch (error) { return failure(error.message); }
    },
  };

  return {
    tools: TOOLS,
    call: async (name, args) => {
      const handler = handlers[name];
      if (!handler) return failure('Unknown tool ' + name + '.');
      try { return await handler(args || {}); }
      catch (error) {
        if (error instanceof StoppedError) return failure(error.message + '\n' + STOPPED_HINT);
        return failure('screen tool ' + name + ' failed: ' + error.message);
      }
    },
    shutdown: () => host.close(),
  };
}

module.exports = { PLATFORM_NOTES, POST_SHOT, TOOLS, createTools };
