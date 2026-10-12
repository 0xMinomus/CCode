#!/usr/bin/env bash
# Resolve a usable Python ≥3.10 and exec it with the given args.
#
# Claude Code's MCP/hook spawn PATH is thin (often no Homebrew/pyenv). Never
# put bare "python3" in plugin.json / hooks.json — route every Python invoke
# through this script.
#
# MCP-safe: diagnostics go to stderr only; stdout is reserved for the child.
#
# Override (first match, version-gated):
#   EIGHTYEIGHT_PYTHON  fleet-wide
#   PLUGIN_PYTHON       generic
#   SCREEN_PYTHON           this plugin
#
# Also honors VIRTUAL_ENV and a plugin-local .venv.
set -euo pipefail

MIN_MAJOR=3
MIN_MINOR=10

_version_ok() {
  local py="$1"
  [ -n "$py" ] && [ -x "$py" ] || return 1
  "$py" -c "import sys; raise SystemExit(0 if sys.version_info >= (${MIN_MAJOR}, ${MIN_MINOR}) else 1)" 2>/dev/null
}

# REQUIRE_GI gates the first selection pass. PyGObject cannot be pip-installed (no wheel),
# so it exists only in whatever interpreter the distro installed it for — usually
# /usr/bin/python3. A pyenv/conda/`python:3.12-slim` interpreter earlier on PATH will pass
# the version check and then die on `import gi`, which reads to the user as "screen-mcp is
# broken" rather than "wrong interpreter". Verified in a clean container: apt-installed
# python3-gi was invisible to the image's /usr/local python. So: prefer an interpreter that
# can import gi; fall back to any valid one (and warn) only if none can.
REQUIRE_GI=1

# find_spec again: probing several candidates x a real `import gi` (which pulls in
# GObject) dominated startup. Locating the module is the question being asked.
_gi_ok() {
  [ "$REQUIRE_GI" != "1" ] || \
    "$1" -c 'import importlib.util as u,sys; sys.exit(0 if u.find_spec("gi") else 1)' >/dev/null 2>&1
}

# ONE probe per interpreter, answering every question at once, cached.
#
# find_spec (not import) because importing onnxruntime + cv2 costs ~3s of pure startup.
# But the probes themselves were the next bottleneck: version, gi and two dep checks were
# four separate `python -c` spawns, and the launcher was making SIX in total at ~0.3s each
# — ~2s on every single server start. One spawn answers all of it.
#
# Prints three space-separated flags: <gi> <hard> <full>, each 1 or 0.
_PROBE_SRC='
import importlib.util as u, sys
if sys.version_info < (3, 10):
    sys.exit(3)
spec = u.find_spec
gi = 1 if spec("gi") else 0
hard = 1 if all(spec(m) for m in ("numpy", "PIL")) else 0
full = 1 if hard and all(spec(m) for m in ("cv2", "onnxruntime", "rapidocr")) else 0
print(gi, hard, full)
'
_PROBE_CACHE_PY=""
_PROBE_CACHE_OUT=""

_probe() {  # _probe <python> -> echoes "<gi> <hard> <full>"; empty when unusable
  [ -n "$1" ] || { printf ''; return 1; }
  if [ "$1" = "$_PROBE_CACHE_PY" ]; then
    printf '%s' "$_PROBE_CACHE_OUT"
    [ -n "$_PROBE_CACHE_OUT" ] || return 1
    return 0
  fi
  local out
  out="$("$1" -c "$_PROBE_SRC" 2>/dev/null)" || out=""
  _PROBE_CACHE_PY="$1"
  _PROBE_CACHE_OUT="$out"
  printf '%s' "$out"
  [ -n "$out" ] || return 1
}

_flag() {  # _flag <python> <1|2|3>  (gi|hard|full)
  local out; out="$(_probe "$1")" || return 1
  [ "$(printf '%s' "$out" | cut -d" " -f"$2")" = "1" ]
}

_have_hard_deps() { _flag "$1" 2; }
_have_full_deps() { _flag "$1" 3; }

_try() {
  # ONE probe per candidate. This used to spawn _version_ok AND _gi_ok separately for
  # every candidate in a 5-tier search — the launcher was making six `python -c` calls at
  # ~0.3s each before it even exec'd. _probe answers version+gi+deps in a single spawn and
  # caches, so a resolved candidate costs one interpreter start.
  local cand="$1" resolved=""
  [ -n "$cand" ] || return 1
  if [ -x "$cand" ]; then
    resolved="$cand"
  elif command -v "$cand" >/dev/null 2>&1; then
    resolved="$(command -v "$cand")"
  else
    return 1
  fi
  # Capture the probe ONCE and read the flag out of that string. Calling _flag here would
  # re-run _probe in a fresh command substitution — a subshell, where the cache set by the
  # first call is invisible — so every candidate cost two interpreter spawns instead of one.
  local out
  out="$("$resolved" -c "$_PROBE_SRC" 2>/dev/null)" || return 1
  [ -n "$out" ] || return 1                   # empty also covers version < 3.10 (exit 3)
  if [ "$REQUIRE_GI" = "1" ] && [ "${out%% *}" != "1" ]; then
    return 1
  fi
  printf '%s' "$resolved"
  return 0
}

find_python() {
  local c root
  root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

  # Explicit operator overrides win OUTRIGHT — they are documented as "first match,
  # version-gated", so gating them on gi too would silently discard a deliberate choice
  # and fall through to some other interpreter the operator did not ask for.
  local _rg="$REQUIRE_GI"
  REQUIRE_GI=0
  for c in "${EIGHTYEIGHT_PYTHON:-}" "${PLUGIN_PYTHON:-}" "${SCREEN_PYTHON:-}"; do
    if _try "$c"; then REQUIRE_GI="$_rg"; return 0; fi
  done
  REQUIRE_GI="$_rg"

  if [ -n "${VIRTUAL_ENV:-}" ]; then
    for c in "${VIRTUAL_ENV}/bin/python3" "${VIRTUAL_ENV}/bin/python"; do
      _try "$c" && return 0
    done
  fi

  for c in "${root}/.venv/bin/python" "${root}/.venv/bin/python3" \
           "${root}/venv/bin/python" "${root}/venv/bin/python3"; do
    _try "$c" && return 0
  done

  for c in python3 python3.13 python3.12 python3.11 python3.10 python; do
    _try "$c" && return 0
  done

  for c in \
    /opt/homebrew/bin/python3 \
    /usr/local/bin/python3 \
    /usr/bin/python3 \
    "${HOME}/.local/bin/python3" \
    /usr/bin/python
  do
    _try "$c" && return 0
  done

  return 1
}

if ! PY="$(find_python)"; then
  # Nothing with gi. Retry ignoring it so the user gets a precise diagnosis from a running
  # server instead of a dead one — the system-layer hint below names the exact command.
  # `|| true` is load-bearing: under `set -e` a bare failing assignment here aborts the
  # script, making the diagnostic block below unreachable and leaving the user with a
  # silent non-zero exit instead of the install hint.
  REQUIRE_GI=0
  PY="$(find_python || true)"
fi
[ -n "${PY:-}" ] || {
  echo "screen-mcp: no Python >=${MIN_MAJOR}.${MIN_MINOR} found." >&2
  echo "  Set EIGHTYEIGHT_PYTHON=/path/to/python3 (or SCREEN_PYTHON), or install Python 3." >&2
  echo "  Checked: env overrides, VIRTUAL_ENV, plugin .venv, PATH, Homebrew, /usr/bin." >&2
  exit 1
}

# --- auto-provision the pip layer -------------------------------------------------------
# Users should not have to hand-install numpy/Pillow to get a working server. If the
# resolved interpreter cannot import the hard deps, build a plugin-local venv and install
# them, then use it.
#
# `--system-site-packages` is LOAD-BEARING: PyGObject (`gi`), the GStreamer typelibs and
# the PipeWire binding are SYSTEM packages that cannot be pip-installed — they bind to the
# host's introspection typelibs and the running compositor. A plain `python -m venv` hides
# them and the server dies with "No module named 'gi'" (verified). Never drop the flag.
#
# Opt out: MCP_SCREEN_NO_AUTO_DEPS=1. Heavy optional set: MCP_SCREEN_AUTO_DEPS=full.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"


# The system layer (PyGObject + GStreamer typelibs + PipeWire) is the ONE part that cannot
# ship with us. Measured 2026-07-25: PyGObject has no wheel — pip builds it from source and
# needs a C toolchain plus libgirepository-dev — and even when built it resolves typelibs and
# a pipewiresrc that must match the RUNNING compositor. So detect it and print the exact
# command for this distro instead of a generic "install the deps" that users cannot action.
_system_layer_hint() {
  if command -v pacman >/dev/null 2>&1; then
    echo "  sudo pacman -S --needed python-gobject gobject-introspection gstreamer \\" >&2
    echo "                 gst-plugins-base gst-plugin-pipewire pipewire \\" >&2
    echo "                 xdg-desktop-portal-gnome wl-clipboard" >&2
  elif command -v apt-get >/dev/null 2>&1; then
    echo "  sudo apt install python3-gi gir1.2-gstreamer-1.0 gstreamer1.0-plugins-base \\" >&2
    echo "                   gstreamer1.0-pipewire pipewire xdg-desktop-portal-gnome \\" >&2
    echo "                   wl-clipboard" >&2
  elif command -v dnf >/dev/null 2>&1; then
    echo "  sudo dnf install python3-gobject gstreamer1-plugins-base \\" >&2
    echo "                   gstreamer1-plugin-pipewire pipewire \\" >&2
    echo "                   xdg-desktop-portal-gnome wl-clipboard" >&2
  else
    echo "  install: PyGObject, GStreamer (+ base plugins + pipewire plugin)," >&2
    echo "           PipeWire, xdg-desktop-portal-gnome, wl-clipboard" >&2
  fi
}

# errexit is disabled for the whole provisioning block. Every command in here is
# best-effort: a failed `pip`, a missing `.venv/bin/python`, an offline box — none of them
# may prevent the final `exec "$PY" "$@"`. Before this, a leftover .venv directory made
# `.venv/bin/python -m pip` run a binary that does not exist and the launcher died 127 with
# no diagnostic, permanently (every relaunch re-entered the same branch).
set +e
# --- uv fast path -----------------------------------------------------------------------
# `uv venv --system-site-packages` + `uv sync` replaces the interpreter hunting, the
# --target fallback, the pip cross-install and the headless-cv2 repair below. It is the
# only uv mode that INHERITS system site-packages, which is mandatory: PyGObject ships
# sdist-only (0 wheels, every version through 3.56.3) because it binds host typelibs, so
# `gi` exists only where the distro installed it. uv run --script / uvx / pipx all build
# ISOLATED envs and therefore cannot see gi at all.
#
# Measured: cold full install (~335MB incl. onnxruntime) 7.1s, warm 0.05s — comfortably
# inside Claude Code's 30s MCP_TIMEOUT, which is why the old background `nohup pip` is gone.
if [ "${MCP_SCREEN_NO_AUTO_DEPS:-0}" != "1" ] && [ "${MCP_SCREEN_NO_UV:-0}" != "1" ] \
   && command -v uv >/dev/null 2>&1 && [ -f "${ROOT}/pyproject.toml" ]; then
  # _have_full_deps, not _satisfied: the latter is defined further down inside the MODE
  # branch, so calling it here silently failed ("command not found" under a non-fatal
  # context) and the uv sync ran on EVERY launch — provisioning a host that needed nothing.
  if ! _have_full_deps "$PY"; then
    echo "screen-mcp: syncing deps with uv ..." >&2
    UV_LINK_MODE=copy uv venv --system-site-packages --python "$PY" "${ROOT}/.venv" >&2 2>/dev/null
    UV_LINK_MODE=copy uv sync --active --project "$ROOT" --extra uinput >&2 2>/dev/null \
      || UV_LINK_MODE=copy uv sync --active --project "$ROOT" >&2 2>/dev/null || true
  fi
  if _have_hard_deps "${ROOT}/.venv/bin/python" 2>/dev/null \
     && { [ "$REQUIRE_GI" != "1" ] || "${ROOT}/.venv/bin/python" -c 'import gi' >/dev/null 2>&1; }; then
    exec "${ROOT}/.venv/bin/python" "$@"
  fi
fi

if [ "${MCP_SCREEN_NO_AUTO_DEPS:-0}" != "1" ]; then
  VENV="${ROOT}/.venv"
  MODE="${MCP_SCREEN_AUTO_DEPS:-full}"
  # Ship everything in-box by default: a server that starts but silently has no OCR or icon
  # detection reads as a broken tool, not a missing extra. Size is not the constraint.
  if [ "$MODE" = "core" ]; then
    REQ="${ROOT}/requirements-core.txt"
    _satisfied() { _have_hard_deps "$1"; }
  else
    REQ="${ROOT}/requirements-runtime.txt"
    _satisfied() { _have_full_deps "$1"; }
  fi
  STAMP="${ROOT}/.provisioned-${MODE}"

  # `pip install --target` + PYTHONPATH, used when venv is unavailable. Debian/Ubuntu ship
  # the stdlib `venv` module in a SEPARATE python3-venv package, so the distro interpreter
  # — the very one that has gi — often cannot create a venv (measured in a clean container:
  # "apt install python3.13-venv"). --target needs no venv module and layers our pip deps
  # on top of the distro python that already provides gi, which is exactly what we want.
  DEPS="${ROOT}/.deps"
  # Find any interpreter that HAS pip. Debian strips pip AND ensurepip from the distro
  # python, so the gi-capable interpreter frequently cannot install anything itself, while
  # some other python on the box can. pip's `--python` installs FOR a named interpreter with
  # that interpreter's ABI, so a cp312 pip can correctly populate a cp313 target.
  _pip_helper() {
    local c
    for c in "$PY" python3 python /usr/local/bin/python3 /usr/bin/python3; do
      command -v "$c" >/dev/null 2>&1 || [ -x "$c" ] || continue
      "$c" -m pip --version >/dev/null 2>&1 && { printf '%s' "$c"; return 0; }
    done
    return 1
  }

  # True when the --target dir exists AND the hard deps import through it. Restoring this
  # after it was accidentally deleted: both call sites survived, so the launcher printed
  # "_use_target_if_ready: command not found" and silently skipped adopting a perfectly good
  # --target install.
  _use_target_if_ready() {
    [ -d "$DEPS" ] || return 1
    PYTHONPATH="${DEPS}${PYTHONPATH:+:$PYTHONPATH}" "$PY" \
      -c 'import importlib.util as u,sys; sys.exit(0 if all(u.find_spec(m) for m in ("numpy","PIL")) else 1)' \
      >/dev/null 2>&1
  }

  _provision_target() {
    local req="$1" helper
    "$PY" -m pip --version >/dev/null 2>&1 \
      || "$PY" -m ensurepip --default-pip >/dev/null 2>&1 || true
    if "$PY" -m pip --version >/dev/null 2>&1; then
      "$PY" -m pip install --quiet --target "$DEPS" -r "$req" >&2 && return 0
    fi
    helper="$(_pip_helper)" || return 1
    # `--python` MUST come before the subcommand (pip rejects it after).
    "$helper" -m pip --python "$PY" install --quiet --target "$DEPS" -r "$req" >&2
  }

  if ! _satisfied "$PY" && [ ! -f "$STAMP" ] && [ -f "$REQ" ]; then
    echo "screen-mcp: provisioning Python deps ..." >&2
    # --system-site-packages is LOAD-BEARING: gi/GStreamer are system packages a plain
    # venv would hide, and the server dies with "No module named 'gi'" (verified).
    # Only reuse an existing venv if it can still see the system layer. A tree left by an
    # interrupted run — or created without --system-site-packages — otherwise short-circuits
    # creation, gets the stamp written, and permanently locks the server onto an interpreter
    # that cannot import gi.
    # An existing venv that cannot see the system layer is useless to us — but it may be
    # the user's own, so do NOT delete it. Skip it and provision via --target instead.
    _SKIP_VENV=0
    if [ -d "$VENV" ] \
       && ! "${VENV}/bin/python" -c 'import importlib.util as u,sys; sys.exit(0 if u.find_spec("gi") else 1)' >/dev/null 2>&1; then
      echo "screen-mcp: existing ${VENV} cannot import gi (left as-is); using ${DEPS}" >&2
      _SKIP_VENV=1
    fi
    if [ ! -d "$VENV" ]; then _VENV_OURS=1; fi
    if [ "$_SKIP_VENV" = "1" ] \
       || ! { [ -d "$VENV" ] || "$PY" -m venv --system-site-packages "$VENV" >/dev/null 2>&1; }; then
      # A FAILED `venv` still leaves a partial tree behind (it dies at the ensurepip step
      # after writing bin/python). That stub does NOT inherit system site-packages, so it
      # hides gi — and being at $ROOT/.venv it then WINS interpreter selection, turning a
      # recoverable miss into "No module named 'gi'". Remove it. Guarded: exact literal
      # path under ROOT, created by this script, never a variable-built path.
      # Only remove a venv THIS run created. A user's own hand-built .venv must never be
      # deleted without asking — we degrade to --target instead.
      if [ "${_VENV_OURS:-0}" = "1" ] && [ -n "${ROOT:-}" ] && [ "$VENV" = "${ROOT}/.venv" ]; then
        rm -rf "${ROOT}/.venv"
      fi
      # No venv module. Layer deps onto the current (gi-capable) interpreter instead.
      echo "screen-mcp: venv unavailable; installing into ${DEPS} instead ..." >&2
      _provision_target "$REQ" || _provision_target "${ROOT}/requirements-core.txt" || {
        echo "screen-mcp: dep provisioning FAILED (offline, or no pip)." >&2
        echo "  ${PY} -m pip install --target ${DEPS} -r ${REQ}" >&2
      }
      if _use_target_if_ready; then
        : > "$STAMP"
        export PYTHONPATH="${DEPS}${PYTHONPATH:+:$PYTHONPATH}"
        echo "screen-mcp: provisioned ok (--target)." >&2
      fi
    elif true; then
      "${VENV}/bin/python" -m pip install --quiet --upgrade pip >&2 2>/dev/null
      if "${VENV}/bin/python" -m pip install --quiet -r "$REQ" >&2; then
        : > "$STAMP"
        # evdev separately and best-effort: it builds against kernel headers and its
        # failure must never sink the grounding stack (it did — measured). Prefer the
        # prebuilt wheel, fall back to source, shrug if neither works.
        if [ "$MODE" != "core" ] && ! "${VENV}/bin/python" -c 'import evdev' >/dev/null 2>&1; then
          "${VENV}/bin/python" -m pip install --quiet evdev-binary >/dev/null 2>&1 \
            || "${VENV}/bin/python" -m pip install --quiet evdev >/dev/null 2>&1 \
            || echo "screen-mcp: evdev unavailable (uinput backend off; portal input still works)." >&2
        fi
        echo "screen-mcp: provisioned ok." >&2
      elif "${VENV}/bin/python" -m pip install --quiet -r "${ROOT}/requirements-core.txt" >&2; then
        # Degrade rather than die: core gets a working server without grounding.
        echo "screen-mcp: full set failed; core deps installed (no OCR/icon grounding)." >&2
        echo "  retry later: ${VENV}/bin/python -m pip install -r ${REQ}" >&2
      else
        echo "screen-mcp: dep provisioning FAILED (offline?). Install manually:" >&2
        echo "  ${PY} -m pip install -r ${REQ}" >&2
      fi
    fi
  fi

  # Adopt the venv only if it ALSO kept gi — a venv built without --system-site-packages
  # (or a partial one) satisfies numpy while silently losing PyGObject, which is a strictly
  # worse interpreter than the one we already hold.
  if _have_hard_deps "${VENV}/bin/python" 2>/dev/null \
     && { [ "$REQUIRE_GI" != "1" ] || "${VENV}/bin/python" -c 'import gi' >/dev/null 2>&1; }; then
    PY="${VENV}/bin/python"
  elif _use_target_if_ready; then
    # Keep the gi-capable interpreter and bring our deps in via PYTHONPATH.
    export PYTHONPATH="${DEPS}${PYTHONPATH:+:$PYTHONPATH}"
  fi
fi

set -e
# Last gate: the un-shippable system layer. Report it precisely rather than letting the
# server die later on an opaque ImportError deep in capture.py.
if ! "$PY" -c 'import gi' >/dev/null 2>&1; then
  echo "screen-mcp: PyGObject (gi) missing — this is the one layer we cannot bundle" >&2
  echo "  (no PyPI wheel; it binds the host's typelibs and running PipeWire). Install:" >&2
  _system_layer_hint
fi

exec "$PY" "$@"
