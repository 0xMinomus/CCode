'use strict';
// Screenshot geometry and output budget for the Windows Computer Use backend. Pure functions
// so the scaling policy is unit-tested without touching a real desktop: the backend sends
// desktop pixels to the helper and reports view pixels to the model.

const DEFAULT_MAX_EDGE = 1280, DEFAULT_MAX_OUTPUT_KB = 250;

function limits(env = process.env) {
  const positive = (name, fallback) => {
    const value = Number(env[name]);
    return Number.isFinite(value) && value > 0 ? value : fallback;
  };
  return { maxEdge: Math.round(positive('MCP_SCREEN_MAX_EDGE', DEFAULT_MAX_EDGE)),
    maxOutputKb: Math.round(positive('MCP_SCREEN_MAX_OUTPUT_KB', DEFAULT_MAX_OUTPUT_KB)) };
}

// Shrink until the longest edge fits maxEdge. scale is view pixels per desktop pixel, the
// factor the model needs to map image coordinates back to the desktop.
function scaleSize(width, height, maxEdge = DEFAULT_MAX_EDGE) {
  const source = { width: Math.max(1, Math.round(Number(width) || 0)), height: Math.max(1, Math.round(Number(height) || 0)) };
  const longest = Math.max(source.width, source.height);
  if (!(maxEdge > 0) || longest <= maxEdge) return { ...source, scale: 1 };
  const scale = maxEdge / longest;
  return { width: Math.max(1, Math.round(source.width * scale)), height: Math.max(1, Math.round(source.height * scale)), scale };
}

// Region is [x, y, width, height] in desktop pixels. Clamped to the virtual desktop so a model
// that guesses a region for a small text block still gets a usable capture instead of an error.
function clampRegion(region, desktop) {
  if (!Array.isArray(region) || region.length !== 4 || region.some(value => !Number.isFinite(Number(value)))) return null;
  const [x, y, width, height] = region.map(Number);
  if (width <= 0 || height <= 0) return null;
  const rect = { x: Math.round(x), y: Math.round(y), width: Math.round(width), height: Math.round(height) };
  const left = Math.max(rect.x, desktop.x), top = Math.max(rect.y, desktop.y);
  const right = Math.min(rect.x + rect.width, desktop.x + desktop.width);
  const bottom = Math.min(rect.y + rect.height, desktop.y + desktop.height);
  if (right - left < 8 || bottom - top < 8) return null;
  return { x: left, y: top, width: right - left, height: bottom - top };
}

// A capture plan: the desktop rect to grab, the shipped size, and the scale between them.
function planCapture(region, desktop, maxEdge) {
  const rect = region ? clampRegion(region, desktop) : { ...desktop };
  if (!rect) return null;
  return { rect, view: scaleSize(rect.width, rect.height, maxEdge) };
}

// View pixels are the default coordinate space for the model: the screenshot it just read.
// Never let it multiply or divide by the scale itself, so the mapping happens here.
function viewToDesktop(point, view) {
  if (!Number.isFinite(point?.x) || !Number.isFinite(point?.y)) return null;
  const scale = Number(view?.scale) > 0 ? Number(view.scale) : 1;
  const origin = { x: Number(view?.origin?.x) || 0, y: Number(view?.origin?.y) || 0 };
  return { x: Math.round(origin.x + Number(point.x) / scale), y: Math.round(origin.y + Number(point.y) / scale) };
}

// Text results never exceed the byte budget: a runaway element dump is trimmed with a notice
// instead of silently costing the whole context window.
function limitText(text, maxOutputKb = DEFAULT_MAX_OUTPUT_KB) {
  const budget = Math.max(1, Math.round(maxOutputKb * 1024));
  if (Buffer.byteLength(text, 'utf8') <= budget) return text;
  const head = Buffer.from(text, 'utf8').subarray(0, Math.max(0, budget - 256)).toString('utf8');
  const cut = head.lastIndexOf('\n');
  const kept = cut > budget / 2 ? head.slice(0, cut + 1) : head;
  const note = '\n[truncated: ' + Buffer.byteLength(text, 'utf8') + ' bytes exceeds MCP_SCREEN_MAX_OUTPUT_KB (' + maxOutputKb +
    ' KB). Pass contains=<text> to screen_read_text to fetch only the part you need.]';
  return kept + note;
}

module.exports = { DEFAULT_MAX_EDGE, DEFAULT_MAX_OUTPUT_KB, clampRegion, limits, limitText, planCapture, scaleSize, viewToDesktop };
