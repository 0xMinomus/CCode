'use strict';
// Session state for one MCP connection: the view the element ids belong to, the change signal
// of the last action, and the watched baselines screen_verify compares against. Ids are only
// valid for the latest view, mirroring the Linux backend's stale-view rejection, but an
// identical element list keeps its ids so a click planned after an earlier read still lands.
class StaleElementError extends Error {
  constructor(detail) {
    super(detail + ' Element and view ids only live for the latest observation; call screen_read_text ' +
      '(or screen_screenshot with annotate=true) again and use an id from that result.');
    this.name = 'StaleElementError';
  }
}

function rowKey(rows) {
  return rows.map(row => [row.role, row.text, row.x, row.y].join('\u0000')).join('\u0001');
}

class Session {
  constructor() {
    this.view = 0;
    this.viewInfo = null;
    this.elements = new Map();
    this.signature = null;
    this.nextElementId = 0;
    this.baselines = new Map();
    this.action = null;
  }

  openView(origin, size) {
    this.view += 1;
    this.viewInfo = { id: 'view#' + this.view, origin: { x: origin.x, y: origin.y }, width: size.width, height: size.height, scale: size.scale };
    return this.viewInfo;
  }

  // Elements arrive from UI Automation without ids; the session assigns the short `e12`
  // handles the model passes to screen_click(element=). An identical list keeps its ids, so a
  // click planned after an earlier read still lands on the same element.
  assign(rows) {
    const signature = rowKey(rows);
    if (signature === this.signature) return [...this.elements.values()];
    this.signature = signature;
    this.nextElementId = 0;
    this.elements = new Map();
    return rows.map(row => this.add(row));
  }

  add(row) {
    const id = 'e' + (++this.nextElementId);
    const entry = { id, role: String(row.role || 'control'), text: String(row.text || '').slice(0, 500),
      x: Math.round(row.x), y: Math.round(row.y), enabled: row.enabled !== false };
    this.elements.set(id, entry);
    return entry;
  }

  resolveElement(id) {
    const key = String(id ?? '').trim();
    const row = this.elements.get(key);
    if (!row) throw new StaleElementError('Unknown element id ' + (key || '(empty)') + '.');
    return row;
  }

  // Passing no view_id means "the newest view"; anything else must match the current view.
  viewFor(id) {
    if (id === undefined || id === null || id === '') return this.viewInfo;
    return this.viewInfo && String(id) === this.viewInfo.id ? this.viewInfo : null;
  }

  remember(key, hash) { this.baselines.set(key, { hash, at: Date.now() }); }

  baseline(key) { return this.baselines.get(key) || null; }

  record(action) { this.action = { ...action, at: Date.now() }; }
}

function classifySense(action) {
  if (!action) return { signal: 'unknown', detail: 'no action has run with a change signal yet' };
  const { before, after } = action;
  if (!before || !after) return { signal: 'unknown', detail: 'the action has no before/after observation' };
  if (before.foreground?.hwnd !== after.foreground?.hwnd) {
    return { signal: 'opened', detail: 'the foreground window changed to ' + (after.foreground?.title || '(untitled)') };
  }
  if (Number(after.topLevel) > Number(before.topLevel)) {
    return { signal: 'modal', detail: 'a new window appeared in front of ' + (after.foreground?.title || '(untitled)') };
  }
  if (before.hash !== after.hash) return { signal: 'changed', detail: 'the watched area changed' };
  if (before.elements != null && after.elements != null && Number(before.elements) !== Number(after.elements)) {
    return { signal: 'activity', detail: 'the screen repainted without a pixel-level change (element count ' +
      before.elements + ' -> ' + after.elements + ')' };
  }
  return { signal: 'no_op', detail: 'nothing changed after this action' };
}

function senseText(action) {
  const { signal, detail } = classifySense(action);
  const payload = { action: action?.name || null, signal, detail };
  const hints = {
    no_op: 'nothing changed - last action may have been a no-op/misclick. Do not repeat it; observe and pick another target.',
    unknown: 'pass shot=true on an action to record a change signal.',
    opened: 'a window opened; read it before typing into it.',
    modal: 'a dialog or new window is in front: read it and answer it explicitly.',
    changed: 'the screen changed; inspect it instead of guessing.',
    activity: 'the screen repainted; read the text to see what changed.',
  };
  return 'SENSE ' + JSON.stringify(payload) + '\nhints: ' + hints[signal];
}

module.exports = { Session, StaleElementError, classifySense, senseText };
