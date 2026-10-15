'use strict';
// Pointer-takeover policy for the Windows Computer Use backend. Same contract as
// services/desktop/ccode_fast_profile.py: a parked pointer is not a takeover, sustained
// driving is, and an undecidable window fails open exactly like the vendored guard does
// when it cannot read the pointer. Kept dependency-free so the window logic is unit-tested
// with an injected cursor source.
const DEFAULTS = { idlePx: 8, idleMs: 600, takeoverMs: 1200, pollMs: 100 };

function envNumbers(env = process.env) {
  const read = (name, fallback) => {
    const value = Number(env[name]);
    return Number.isFinite(value) && value >= 0 ? value : fallback;
  };
  return { idlePx: read('CCODE_CUA_IDLE_PX', DEFAULTS.idlePx), idleMs: read('CCODE_CUA_IDLE_MS', DEFAULTS.idleMs),
    takeoverMs: read('CCODE_CUA_TAKEOVER_MS', DEFAULTS.takeoverMs), pollMs: read('CCODE_CUA_POLL_S', DEFAULTS.pollMs / 1000) * 1000 };
}

// Samples are [{t, x, y}] in milliseconds from the first divergence, chronological:
// 'pending' when the window is too short to judge, 'idle' when the pointer stopped moving,
// 'driving' when the user kept moving it for the whole takeover window.
function classifyPointerWindow(samples, options = {}) {
  const idlePx = options.idlePx ?? DEFAULTS.idlePx;
  const idleMs = options.idleMs ?? DEFAULTS.idleMs;
  const takeoverMs = options.takeoverMs ?? DEFAULTS.takeoverMs;
  if (samples.length < 2) return 'pending';
  let lastMove = samples[0].t, moved = false;
  for (let index = 1; index < samples.length; index++) {
    const previous = samples[index - 1], current = samples[index];
    if (Math.abs(current.x - previous.x) > idlePx || Math.abs(current.y - previous.y) > idlePx) {
      lastMove = current.t;
      moved = true;
    }
  }
  const span = samples.at(-1).t - samples[0].t;
  const quietFor = samples.at(-1).t - lastMove;
  if (!moved) return span >= idleMs ? 'idle' : 'pending';
  if (quietFor >= idleMs) return 'idle';
  return span >= takeoverMs ? 'driving' : 'pending';
}

class StoppedError extends Error {
  constructor(detail) {
    super('STOPPED: the user is using the mouse right now (' + detail + '). Yield to them: stop acting, ' +
      'tell the user you stopped, and wait. Never pass force=true to defeat takeover; use force only when ' +
      'the user asks you to take control back.');
    this.name = 'StoppedError';
    this.stopped = true;
  }
}

// Wraps the raw cursor reading with the hysteresis window above. `cursor()` returns a screen
// point or null; `commanded` is where the backend last left the pointer, so a stray nudge or a
// pointer the user parked elsewhere never reads as a takeover.
class TakeoverGuard {
  constructor({ cursor, now = () => Date.now(), sleep = ms => new Promise(resolve => setTimeout(resolve, ms)), limits = envNumbers() } = {}) {
    if (typeof cursor !== 'function') throw Error('Takeover guard needs a cursor source');
    this.cursor = cursor;
    this.now = now;
    this.sleep = sleep;
    this.limits = limits;
    this.commanded = null;
  }

  record(point) {
    if (point && Number.isFinite(point.x) && Number.isFinite(point.y)) this.commanded = { x: point.x, y: point.y };
  }

  async read() {
    try {
      const point = await this.cursor();
      return point && Number.isFinite(point.x) && Number.isFinite(point.y) ? { x: point.x, y: point.y } : null;
    } catch { return null; }
  }

  quiet(point) {
    return this.commanded === null || (Math.abs(point.x - this.commanded.x) <= this.limits.idlePx &&
      Math.abs(point.y - this.commanded.y) <= this.limits.idlePx);
  }

  // Resolves when input may be injected, throws StoppedError when the user is driving the
  // pointer. force bypasses the check without waiting on or fighting the user.
  async check(force = false) {
    if (force) return { verdict: 'forced' };
    const first = await this.read();
    if (first === null || this.quiet(first)) return { verdict: 'quiet' };
    const start = this.now(), samples = [{ t: 0, x: first.x, y: first.y }];
    for (;;) {
      const elapsed = this.now() - start;
      const point = await this.read();
      if (point) samples.push({ t: elapsed, x: point.x, y: point.y });
      const verdict = classifyPointerWindow(samples, this.limits);
      if (verdict === 'idle') return { verdict: 'idle' };
      if (verdict === 'driving') throw new StoppedError('the pointer kept moving for ' + Math.round(elapsed) + ' ms');
      if (elapsed >= this.limits.takeoverMs) return { verdict: 'undecidable' };
      await this.sleep(this.limits.pollMs);
    }
  }
}

module.exports = { DEFAULTS, StoppedError, TakeoverGuard, classifyPointerWindow, envNumbers };
