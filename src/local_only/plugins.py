"""Bundled plugin payload: local-only agents, CCode identity, no account surface.

The payload is not part of the pinned archive, so `baselines/upstream-3.14.5-original-plugins`
keeps a pristine copy of every file this module rewrites. Its digest is pinned in
`project.json` (`plugins_baseline_sha256`) and checked before staging.
"""

import hashlib
import pathlib
import shutil

from . import rebrand, replace_once

ROOT = pathlib.Path(__file__).resolve().parents[2]
BASELINE = ROOT / 'baselines/upstream-3.14.5-original-plugins'
PACKAGES = 'glm/packages'
# Not payload: the bundled skill pack is staged from src/skills, node_modules is vendor.
SKIP_DIRS = frozenset(('node_modules', 'bundled-skills'))
# Payloads whose only backend is a Z.ai account, with no local replacement.
REMOVALS = ('image-search-plugin',)
# Deployed directory names that carry the upstream product name.
DIR_RENAMES = ((rebrand.previous('ccode-cua-plugin'), 'ccode-cua-plugin'),
               (rebrand.previous('ccode-guide-plugin'), 'ccode-guide-plugin'))
MANIFEST_DIR = (rebrand.previous('.ccode-plugin'), '.ccode-plugin')
# Plugin agents pinned to an account model; the account is gone in this build.
ACCOUNT_PINNED_AGENTS = ('documents-plugin/agents/visual-judge.md', 'pdf-plugin/agents/visual-judge.md',
                         'presentations-plugin/agents/visual-judge.md', 'spreadsheets-plugin/agents/visual-judge.md')
ACCOUNT_MODEL_LINE = 'model: account:bigmodel-individual-coding-plan/GLM-5.3-Flash\n'
ACCOUNT_THOUGHT_LINE = 'thoughtLevel: max\n'
# The deck skill re-ran its whole overflow pass until clean; bound it to one fix pass.
PPTX_SKILL = 'presentations-plugin/skills/pptx/SKILL.md'
PPTX_RERUN = ('then fix the real hits and re-run.',
              'then fix the real hits and re-run once; report anything still flagged in the final message '
              'instead of iterating again.')
# The Computer Use plugin's executor is not part of this payload, so its skill must drive the
# desktop MCP backends instead of the missing nodeRepl runtime it was written for.
CUA_SKILL = 'zcode-cua-plugin/skills/computer-use/SKILL.md'
CUA_DOC = 'zcode-cua-plugin/docs/computer-use.md'
CUA_SKILL_ANCHOR = '## Bootstrap every call'
CUA_SKILL_CONTENT = '''---
name: computer-use
description: "Use when a task needs a native desktop app's own UI or the OS. Drive it with the windows-desktop (Windows) or linux-desktop (Linux) MCP tools. For anything inside a web page, use Browser Use. Main agent only."
---

# Computer Use

Operate the user's desktop through this platform's desktop MCP server: `windows-desktop` on
Windows, `linux-desktop` on Linux. Use the tools that are actually listed in this session.

- Main agent only. Never delegate Computer Use to a subagent.
- Prefer a dedicated connector, API, CLI or skill when one can complete the task.
- Do not use AppleScript, `osascript`, JXA, System Events, shell commands, or
  `mcp__node_repl__js` for desktop control: this plugin's runtime is not installed here. When a
  desktop tool is missing, say so instead of falling back to another automation stack.

## Loop

1. `screen_read_text` first: it returns the foreground window's elements with stable ids and
   desktop coordinates, and it works while the app stays in the background.
2. Act by `element=<id>`; coordinates are the last resort, for canvas, games, and content
   accessibility cannot see. `screen_focus` before `screen_type`/`screen_key` when the target
   is not already focused.
3. Verify with `screen_wait_text` for an expected string, `screen_sense` for the change line,
   or `screen_screenshot` when you need to see layout or color. `screen_verify` warns when an
   action changed nothing.
4. Re-observe after uncertain transitions. Success means the desktop changed, not that a call
   returned.

## Coordinates and views

- Coordinates read from a screenshot are **view pixels**; the backend maps them to the desktop.
  Never rescale them yourself, and pass `view_id=<view#N>` from the screenshot header when the
  shot is older than the previous step.
- `region=[x,y,w,h]` on `screen_screenshot` takes **desktop** pixels: use it to zoom on small
  text instead of guessing.
- `screen_screenshot({ annotate: true })` overlays numbered marks so you can click by id.

## Pointer guard

- Moving the mouse yourself means STOPPED: yield, stop acting, and tell the user. A parked
  pointer is not a takeover and stray nudges are ignored.
- Never pass `force=true` to defeat takeover; use it only after the user hands control back.
- Windows: capture runs directly with no portal dialog; UIPI blocks input to elevated windows
  and the UAC secure desktop, and no mode pierces that. Linux asks the desktop portal for
  screen-sharing and input permission on first use.
- Use a vision model for screenshot work.

## First call

The desktop backend starts on demand and compiles its helper once per session, so the first
action can take a few seconds. Retry once instead of switching tools or giving up.
'''
CUA_DOC_NOTE = ('> CCode ships this plugin without its CUA runtime. Drive the desktop with the '
                '`windows-desktop` (Windows) or `linux-desktop` (Linux) MCP tools; read the '
                '`computer-use` skill for the loop.\n\n')


def _baseline_files():
    """Payload paths in POSIX spelling, ordered by that spelling.

    The digest is pinned in project.json and must be identical on every host, so
    the order must not come from Path comparison: WindowsPath orders case-folded
    with backslashes and produced a different digest there.
    """
    paths = []
    for path in BASELINE.rglob('*'):
        if not path.is_file():
            continue
        relative = path.relative_to(BASELINE).as_posix()
        if any(part in SKIP_DIRS for part in relative.split('/')):
            continue
        paths.append(relative)
    if not paths:
        raise ValueError('Plugin payload baseline is empty: ' + str(BASELINE))
    return sorted(paths)


def _staged_files():
    """Baseline files the deployed tree keeps; removed payloads are dropped."""
    return [relative for relative in _baseline_files() if relative.split('/')[0] not in REMOVALS]


def baseline_digest():
    """Digest of the pristine payload copy, pinned in project.json."""
    digest = hashlib.sha256()
    for relative in _baseline_files():
        digest.update(relative.encode() + b'\0')
        digest.update(hashlib.sha256((BASELINE / relative).read_bytes()).digest())
    return digest.hexdigest()


def verify_baseline(expected):
    actual = baseline_digest()
    if actual != expected:
        raise ValueError(f'Plugin payload baseline mismatch: {actual} != {expected}')


def target_name(relative):
    """Deployed path of one payload file: every segment carries the CCode identity."""
    return '/'.join(rebrand.apply(segment) for segment in relative.split('/'))


def rename_plan():
    """Directory renames to apply in the deployed resources, in application order."""
    plan = list(DIR_RENAMES)
    marker = f'/{MANIFEST_DIR[0]}/'
    manifests = sorted({relative.split(marker)[0] for relative in _staged_files() if marker in relative})
    for owner in manifests:
        plan.append((f'{target_name(owner)}/{MANIFEST_DIR[0]}', f'{target_name(owner)}/{MANIFEST_DIR[1]}'))
    return plan


def _patch(relative, text):
    if relative in ACCOUNT_PINNED_AGENTS:
        text = replace_once(text, ACCOUNT_MODEL_LINE, '')
        text = replace_once(text, ACCOUNT_THOUGHT_LINE, '')
    if relative == PPTX_SKILL:
        text = replace_once(text, *PPTX_RERUN)
    if relative == CUA_SKILL:
        if CUA_SKILL_ANCHOR not in text:
            raise ValueError('Computer Use skill anchor is missing in ' + relative)
        text = CUA_SKILL_CONTENT
    if relative == CUA_DOC:
        text = CUA_DOC_NOTE + text
    text = rebrand.apply(text)
    left = rebrand.leftover(text)
    if left:
        raise ValueError(f'Unbranded product name left in {relative}: ' + ' '.join(left))
    return text


def deployed_name(relative):
    """How the deployed tree spells this path: only the directory renames were applied."""
    parts = relative.split('/')
    for old, new in DIR_RENAMES:
        if parts[0] == old:
            parts[0] = new
    parts = [MANIFEST_DIR[1] if part == MANIFEST_DIR[0] else part for part in parts]
    return '/'.join(parts)


def legacy_paths():
    """Deployed payload paths the current staging replaces; superseded by the new name."""
    return sorted({deployed_name(relative) for relative in _staged_files()
                   if deployed_name(relative) != target_name(relative)})


def stage(output):
    """Write the patched payload into `output/<PACKAGES>` and return the promotion plan."""
    plan = {'files': {}, 'renames': rename_plan(), 'removals': list(REMOVALS),
            'legacy': legacy_paths()}
    for name in REMOVALS:
        shutil.rmtree(output / PACKAGES / name, ignore_errors=True)
    for relative in _staged_files():
        text = _patch(relative, (BASELINE / relative).read_text(encoding='utf-8'))
        staged = f'{PACKAGES}/{target_name(relative)}'
        destination = output / staged
        destination.parent.mkdir(parents=True, exist_ok=True)
        data = text.encode()
        destination.write_bytes(data)
        plan['files'][staged] = hashlib.sha256(data).hexdigest()
    return plan
