"""Product identity: the upstream spelling of the product name becomes CCode.

`RENAMES` is the only place in this repository where the upstream product name is
written down. Every patched asset runs through `apply()` before the other patch
modules match their anchors, so anchors are written in the shipped spelling and a
single pass keeps every contract (env var, IPC channel, URL scheme, data layout,
identifier) consistent on both sides of each boundary.
"""

import pathlib
import re

RENAMES = (('ZCODE', 'CCODE'), ('ZCode', 'CCode'), ('Zcode', 'Ccode'), ('zcode', 'ccode'))
# Absolute URLs are network contracts, not labels: the upstream asset and API hosts
# only answer to their real spelling, so every `http(s)://…` run is left verbatim.
URL = re.compile(r'https?://[^\s"\'`<>)\]}\\]+')
_MASK = '\x00rebrand-mask-'
_MASK_CLOSE = '\x00'
# The pre-rebrand two-word label collapses to the product name, as it did before
# this module existed; the token pass alone would leave it as `CCode on Steroids`.
LABELS = (('CCode on Steroids', 'CCode'),)
_REPLACEMENTS = dict(RENAMES)
_PATTERN = re.compile('|'.join(re.escape(source) for source, _ in RENAMES))
_LABELS = tuple((re.compile(re.escape(label)), target) for label, target in LABELS)
_MASKED = re.compile(r'\x00rebrand-mask-(\d+)\x00')
# Text assets inside the app archive. Source maps are skipped: their mappings
# describe positions in the original file and renaming inside them corrupts them.
TEXT_SUFFIXES = ('.js', '.cjs', '.mjs', '.json', '.html', '.css', '.txt', '.md', '.yml',
                 '.yaml', '.xml', '.ts', '.py', '.sh', '.ps1', '.tex', '.cmd', '.toml')


def apply(text):
    """Replace every upstream product token, leaving absolute URLs untouched."""
    urls = []

    def mask(match):
        urls.append(match.group(0))
        return f'{_MASK}{len(urls) - 1}' + _MASK_CLOSE

    text = _PATTERN.sub(lambda match: _REPLACEMENTS[match.group(0)], URL.sub(mask, text))
    for pattern, target in _LABELS:
        text = pattern.sub(target, text)
    if not urls:
        return text
    return _MASKED.sub(lambda match: urls[int(match.group(1))], text)


def leftover(text):
    """Upstream tokens still present in `text`, ignoring absolute URLs."""
    return sorted(set(_PATTERN.findall(URL.sub(' ', text))))


_REVERSE_MAP = {target: source for source, target in RENAMES}
_REVERSE = re.compile('|'.join(re.escape(target) for _, target in RENAMES))


def previous(text):
    """The upstream spelling of a renamed contract, for migrating an old install."""
    return _REVERSE.sub(lambda match: _REVERSE_MAP[match.group(0)], text)


def restore_urls(text):
    """Undo the rename inside absolute URLs.

    The identity migration of an existing namespace rewrote stored URLs as if they
    were labels; this reverses that for every `http(s)://…` run.
    """
    return URL.sub(lambda match: previous(match.group(0)), text)


# Spellings of the pre-rebrand installation. The installer reads them to retire the
# old launcher, units, data root, and lock file, which is why this module is the one
# place in the repository where the upstream name is still written down.
PREVIOUS_NAMESPACE = previous('ccode-on-steroids')
PREVIOUS_BACKUPS = previous('ccode-backups')
PREVIOUS_UNIT = previous('ccode-on-steroids-model-sync')
PREVIOUS_LAUNCHER = previous('ccode-on-steroids.desktop')
PREVIOUS_LAUNCHER_FILE = previous('ccode.desktop')
PREVIOUS_APPDATA = previous('.ccode')
PREVIOUS_APPCONFIG = previous('CCode')
PREVIOUS_CONFIG_DIR = previous('CCode on Steroids')
PREVIOUS_LOCK = previous('.ccode-on-steroids.operations.lock')
PREVIOUS_VANSROUTER_UNIT = previous('ccode-vansrouter-model-sync')


def is_text(name):
    return name.endswith(TEXT_SUFFIXES)


def asset(name, data):
    """Rewrite one archive entry; binary entries pass through untouched."""
    if not is_text(name):
        return data
    try:
        text = data.decode('utf-8')
    except UnicodeDecodeError:
        return data
    return apply(text).encode()


def assert_clean(text, name):
    """Fail the build when an upstream token survives in a shipped asset."""
    left = leftover(text)
    if left:
        raise ValueError(f'Unbranded product name left in {name}: ' + ' '.join(left))


def rewrite_tree(root, skip_dirs=('node_modules',)):
    """Rewrite every text file under `root` in place, failing on a survivor."""
    root = pathlib.Path(root)
    for path in sorted(root.rglob('*')):
        if not path.is_file() or any(part in skip_dirs for part in path.parts):
            continue
        if not is_text(path.name):
            continue
        try:
            text = path.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            continue
        rewritten = apply(text)
        assert_clean(rewritten, str(path))
        if rewritten != text:
            path.write_text(rewritten, encoding='utf-8')
