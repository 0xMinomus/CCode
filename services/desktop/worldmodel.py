"""worldmodel.py — persistent, self-building UI map for mcp-screen (v1.2).

The expensive perception (OCR + OmniParser annotate) is recomputed and thrown away every
call. This is a write-through cache around it: ambiently, on every annotated screenshot, we
persist the element list keyed by a tolerant fingerprint of the screen; on revisit we hand
the cached elements back instead of re-running OCR — turning a ~300ms (12s cold) annotate
into a ~1ms SQLite read. It learns ANY app, with no human labeling and no crawl.

State identity = (app + digit/time-stripped window title) bucket  ×  a dHash of the frame.
dHash keys on layout/structure, so live-updating data (clocks, GPU counts) doesn't change a
screen's identity, but navigating to a different tab/page does. The dHash match threshold is
deliberately tight (HAMMING_MAX default 5/64 bits): a looser threshold lets similar sub-pages
of the same app (settings panes, near-identical dialogs) collide, so recall() would hand back
another screen's coordinates and click the wrong control. Self-heals: a misclick on cached
coords (or a drifted dHash) invalidates the entry so the next visit re-learns.

Mirrors recorder.py: a MAP singleton, one lock, every method no-op-safe and never raising
into the caller — a broken world-model must never break the desktop tools. Imports stdlib +
numpy + Pillow only (no server/capture/input)."""

import os
import re
import json
import time
import threading

import numpy as np
from PIL import Image

DB_PATH = os.path.expanduser("~/.local/share/mcp-screen/world/map.db")
HAMMING_MAX = int(
    os.environ.get("MCP_SCREEN_MAP_HAMMING", "5")
)  # dHash bits; "same screen" (tight: looser confuses sibling sub-pages)
CAP = int(os.environ.get("MCP_SCREEN_MAP_CAP", "800"))  # max states before eviction
MISS_EVICT = 2  # cached-coord misclicks before invalidation

_TS = re.compile(r"\b\d{1,2}:\d{2}(:\d{2})?\b")  # clock-ish
_NUM = re.compile(r"\d+")


def _warn(*a):
    try:
        import sys

        print("worldmodel:", *a, file=sys.stderr, flush=True)
    except Exception:
        pass


def _dhash(pil, hx=9, hy=8):
    """64-bit difference hash (grayscale -> 9x8 -> sign of horizontal neighbour diffs).

    Returns a 16-char hex string. Structural: blind to small content churn, sensitive to
    layout. Returns None on failure."""
    try:
        g = pil.convert("L").resize((hx, hy), Image.Resampling.BILINEAR)
        a = np.asarray(g, dtype=np.int16)
        diff = (a[:, 1:] > a[:, :-1]).flatten()
        bits = 0
        for v in diff:
            bits = (bits << 1) | int(v)
        return "%016x" % bits
    except Exception:
        return None


def _hamming(h1, h2):
    try:
        return bin(int(h1, 16) ^ int(h2, 16)).count("1")
    except Exception:
        return 64


def _context(aware_summary):
    """(app, normalized_title) from awareness.summary() text. Digit/time-stripped so live
    data in the title doesn't fragment a state's identity."""
    app, title = "unknown", ""
    try:
        s = aware_summary or ""
        if s.startswith("focused: "):
            body = s[len("focused: ") :]
            if " — " in body:
                app, title = body.split(" — ", 1)
            else:
                app = body
        else:
            title = s
    except Exception:
        pass
    tnorm = _NUM.sub("#", _TS.sub("#", title)).strip().lower()[:120]
    return app.strip().lower()[:60], tnorm


class WorldModel:
    """SQLite-backed UI map. observe() learns ambiently; recall() returns cached elements on
    a matching revisit; penalize() self-heals stale coords. No-op-safe, never raises."""

    def __init__(self):
        self._lock = threading.Lock()
        self._db = None
        self._last_id = (
            None  # state id of the most recent observe/recall (for penalize)
        )

    def _conn(self):
        if self._db is not None:
            return self._db
        import sqlite3

        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        db = sqlite3.connect(DB_PATH, check_same_thread=False)
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("""CREATE TABLE IF NOT EXISTS state(
            id INTEGER PRIMARY KEY, app TEXT, title_norm TEXT, dhash TEXT,
            view_ctx TEXT, elements TEXT, scroll_max INTEGER DEFAULT 0,
            visits INTEGER DEFAULT 1, first_seen REAL, last_seen REAL, misses INTEGER DEFAULT 0)""")
        db.execute("CREATE INDEX IF NOT EXISTS idx_lookup ON state(app, title_norm)")
        db.commit()
        self._db = db
        return db

    def _match(self, db, app, tnorm, dh):
        """Best state row in the (app,title) bucket within HAMMING_MAX of dh, or None."""
        best, bestd = None, HAMMING_MAX + 1
        for row in db.execute(
            "SELECT id,dhash,view_ctx,elements,scroll_max,misses FROM state "
            "WHERE app=? AND title_norm=?",
            (app, tnorm),
        ):
            d = _hamming(dh, row[1])
            if d < bestd:
                best, bestd = row, d
        return best if best and bestd <= HAMMING_MAX else None

    def observe(self, pil_img, elements_store, aware_summary, view_ctx):
        """Ambient learn: upsert this screen + its element store. elements_store is the
        server's {id:{x,y,label,role}} dict (desktop coords). Best-effort; never raises."""
        with self._lock:
            try:
                db = self._conn()
                dh = _dhash(pil_img)
                if dh is None:
                    return
                app, tnorm = _context(aware_summary)
                now = time.time()
                row = self._match(db, app, tnorm, dh)
                el_json = json.dumps(elements_store) if elements_store else None
                vc_json = json.dumps(view_ctx) if view_ctx else None
                if row:
                    sid = row[0]
                    # refresh elements only when we actually have them (a plain shot just touches)
                    if el_json:
                        db.execute(
                            "UPDATE state SET dhash=?,view_ctx=?,elements=?,visits=visits+1,"
                            "last_seen=?,misses=0 WHERE id=?",
                            (dh, vc_json, el_json, now, sid),
                        )
                    else:
                        db.execute(
                            "UPDATE state SET visits=visits+1,last_seen=? WHERE id=?",
                            (now, sid),
                        )
                    self._last_id = sid
                else:
                    if not el_json:
                        return  # never create empty states from plain (non-annotated) shots
                    cur = db.execute(
                        "INSERT INTO state(app,title_norm,dhash,view_ctx,elements,first_seen,last_seen) "
                        "VALUES(?,?,?,?,?,?,?)",
                        (app, tnorm, dh, vc_json, el_json, now, now),
                    )
                    self._last_id = cur.lastrowid
                    self._evict(db)
                db.commit()
                return self._last_id
            except Exception as e:
                _warn("observe failed:", e)
        return None

    def recall(self, pil_img, aware_summary, view_ctx):
        """Return {elements, state_id, age_s} for a known matching screen WITH cached elements
        under the SAME geometry, else None. Lets the caller skip OCR/OmniParser.

        Identity here rests on the (app,title) bucket + a tightened dHash + the existing view_ctx
        geometry guard; element-set agreement is intentionally NOT checked because recall runs
        before perception, so there is no current element set to compare against."""
        with self._lock:
            try:
                db = self._conn()
                dh = _dhash(pil_img)
                if dh is None:
                    return None
                app, tnorm = _context(aware_summary)
                row = self._match(db, app, tnorm, dh)
                if not row or not row[3]:  # row[3] = elements json
                    return None
                if view_ctx and row[2]:  # geometry must match for coords to be valid
                    if json.loads(row[2]) != list(view_ctx):
                        return None
                self._last_id = row[0]
                store = {int(k): v for k, v in json.loads(row[3]).items()}
                db.execute(
                    "UPDATE state SET visits=visits+1,last_seen=? WHERE id=?",
                    (time.time(), row[0]),
                )
                db.commit()
                return {"elements": store, "state_id": row[0]}
            except Exception as e:
                _warn("recall failed:", e)
                return None

    def penalize(self, state_id=None):
        """Self-heal: a click on cached coords produced no change. Bump misses; after
        MISS_EVICT, drop the cached elements so the next visit re-annotates fresh."""
        with self._lock:
            try:
                sid = state_id if state_id is not None else self._last_id
                if sid is None:
                    return
                db = self._conn()
                db.execute("UPDATE state SET misses=misses+1 WHERE id=?", (sid,))
                db.execute(
                    "UPDATE state SET elements=NULL WHERE id=? AND misses>=?",
                    (sid, MISS_EVICT),
                )
                db.commit()
            except Exception as e:
                _warn("penalize failed:", e)

    def _evict(self, db):
        try:
            n = db.execute("SELECT COUNT(*) FROM state").fetchone()[0]
            if n <= CAP:
                return
            db.execute(
                "DELETE FROM state WHERE id IN (SELECT id FROM state "
                "ORDER BY visits ASC, last_seen ASC LIMIT ?)",
                (n - CAP,),
            )
        except Exception:
            pass

    def stats(self):
        with self._lock:
            try:
                db = self._conn()
                n = db.execute("SELECT COUNT(*) FROM state").fetchone()[0]
                cached = db.execute(
                    "SELECT COUNT(*) FROM state WHERE elements IS NOT NULL"
                ).fetchone()[0]
                return {
                    "states": n,
                    "with_elements": cached,
                    "db": DB_PATH,
                    "hamming_max": HAMMING_MAX,
                    "last_state": self._last_id,
                }
            except Exception as e:
                return {"error": str(e)}


MAP = WorldModel()
