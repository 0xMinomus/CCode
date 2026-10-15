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
