"""CCode product mark for the pinned upstream bundles.

Every product mark in the bundle is replaced with the glyph from
`ccode-logo.svg`: the onboarding/login mark, the sidebar and title-bar logo, the
draft watermark, and the packaged icon assets. Anchors are pinned to the upstream
artwork, so an upstream change fails the build instead of shipping half a rebrand.

The product *name* is not handled here: `rebrand.py` rewrites every upstream
product token in the shipped assets, which covers labels, environment variables,
IPC channels, storage paths, and identifiers in one consistent pass.
"""
import pathlib
import re
import urllib.parse

from . import replace_once

ROOT = pathlib.Path(__file__).resolve().parents[2]
PRODUCT = 'CCode'
LOGO_SOURCE = ROOT / 'ccode-logo.svg'
ICON_DIR = ROOT / 'assets/icons'
# Packaged resources that carry the product mark, mapped to the generated sizes.
PACKAGED_ICONS = {
    'icon.png': 'ccode-1024.png',
    'icon_512x512.png': 'ccode-512.png',
    'icon_windows.png': 'ccode-1024.png',
}
LOCAL_ICON_SIZES = (16, 24, 32, 48, 64, 128, 256, 512, 1024)
MAIN = 'out/main/index.js'
PRELOAD = 'out/preload/index.cjs'
INDEX = 'out/renderer/index.html'

_TOKEN = re.compile(r'[MLAZ]|-?\d+\.?\d*')
# The draft watermark drew the old mark inside a 400x320 viewBox.
WATERMARK_BOX = (400.0, 320.0)
WATERMARK_FILL = 0.8


# Mark paths of the pinned upstream logo (256x218 viewBox).
LEGACY_MARK_PREFIXES = ('M134.4 0.130152', 'M256 0.130127', 'M121.601 217.732')
LEGACY_VIEW_BOX = '0 0 256 218'
LEGACY_SIZE = ('118', '100')


def _replace_quoted_after(text, marker, replacement):
    """Replace the quoted value that starts with `marker`, whatever quotes it uses."""
    if text.count(marker) != 1:
        raise ValueError(f'Upstream mark changed ({text.count(marker)} matches): {marker}')
    start = text.index(marker)
    opener = None
    index = start - 1
    while index >= 0 and text[index] not in '"\'`':
        index -= 1
    opener = text[index] if index >= 0 else None
    if opener is None:
        raise ValueError(f'Upstream mark is not a quoted value: {marker}')
    return text[:index + 1] + replacement + text[text.index(opener, start):]


def _replace_legacy_mark(text):
    """Swap the pinned upstream mark wherever it is inlined as static SVG.

    Covers the pre-hydration splash in index.html, the animated startup logo in the
    renderer bundle, and the About dialog markup in the main bundle.
    """
    for index, marker in enumerate(LEGACY_MARK_PREFIXES):
        text = _replace_quoted_after(text, marker, glyph_paths()[index])
    box = _view_box(_glyph_box())
    text = text.replace('viewBox="' + LEGACY_VIEW_BOX + '"', 'viewBox="' + box + '"')
    text = text.replace('viewBox:`' + LEGACY_VIEW_BOX + '`', 'viewBox:`' + box + '`')
    text = re.sub(r'width="' + LEGACY_SIZE[0] + r'"(\s+)height="' + LEGACY_SIZE[1] + r'"',
                  r'width="100"\1height="100"', text)
    text = text.replace('width:`' + LEGACY_SIZE[0] + '`,height:`' + LEGACY_SIZE[1] + '`',
                        'width:`100`,height:`100`')
    return text


def _current(archive, replacements, name):
    return replacements[name].decode() if name in replacements else archive.read(name).decode()


def replace_span(text, start, end, replacement):
    """Replace one bounded region between two unique anchors, keeping the end anchor."""
    if text.count(start) != 1 or text.count(end) != 1:
        raise ValueError(f'Branding boundary is not unique: {start!r} / {end!r}')
    first = text.index(start)
    last = text.index(end, first + len(start))
    return replace_once(text, text[first:last], replacement)


def _replace_template(text, prefix, value):
    """Replace the template literal assigned to `prefix`, asserting it is unique."""
    marker = prefix + '`'
    if text.count(marker) != 1:
        raise ValueError(f'Branding literal changed ({text.count(marker)} matches): {prefix}')
    first = text.index(marker) + len(marker)
    last = text.index('`', first)
    return text[:first] + value + text[last:]


def _replace_literal_after(text, marker, replacement):
    """Replace the template literal that starts with `marker`, keeping the backtick."""
    if text.count(marker) != 1:
        raise ValueError(f'Branding literal changed ({text.count(marker)} matches): {marker}')
    first = text.index(marker)
    last = text.index('`', first + len(marker))
    return text[:first] + replacement + text[last:]


# --- brand source ---------------------------------------------------------

def _source_svg():
    if not LOGO_SOURCE.exists():
        raise ValueError(f'Brand source is missing: {LOGO_SOURCE}')
    text = LOGO_SOURCE.read_text().strip()
    return re.sub(r'<metadata>.*?</metadata>', '', text, flags=re.S).strip()


def _arc(tokens, index):
    """Arc parameters: rx, ry, x-axis-rotation, large-arc, sweep, x, y."""
    radii = (float(tokens[index + 1]), float(tokens[index + 2]))
    point = (float(tokens[index + 6]), float(tokens[index + 7]))
    return radii, point


def _tokens(path):
    if re.search(r'[mlaz]', path):
        raise ValueError('CCode brand glyph must use absolute path commands')
    tokens = tuple(_TOKEN.findall(path))
    commands = sum(1 for token in tokens if token.isalpha())
    if commands != len(re.findall(r'[MLAZ]', path)):
        raise ValueError('CCode brand glyph has an unparsable path')
    return tokens


def glyph_paths():
    """The mark paths from ccode-logo.svg; the count is pinned to this artwork."""
    block = re.search(r'<g fill="#ffffff">(.*?)</g>', _source_svg(), re.S)
    if not block:
        raise ValueError('CCode brand glyph group is missing from ccode-logo.svg')
    paths = re.findall(r'<path d="([^"]+)"', block.group(1))
    if len(paths) != 3:
        raise ValueError(f'CCode brand glyph changed ({len(paths)} paths); review the artwork before building')
    return paths


def _glyph_box():
    """Square crop of the 1024 canvas that frames the mark with its own padding."""
    points = []
    radii = []
    for path in glyph_paths():
        tokens = _tokens(path)
        index = 0
        while index < len(tokens):
            token = tokens[index]
            if token in 'ML':
                points.append((float(tokens[index + 1]), float(tokens[index + 2])))
                index += 3
            elif token == 'A':
                radii_and_point = _arc(tokens, index)
                radii.extend(radii_and_point[0])
                points.append(radii_and_point[1])
                index += 8
            else:
                index += 1
    left = min(point[0] for point in points)
    right = max(point[0] for point in points)
    top = min(point[1] for point in points)
    bottom = max(point[1] for point in points)
    margin = max(radii) if radii else 0.0
    size = max(right - left, bottom - top) + 2 * margin
    centre = ((left + right) / 2, (top + bottom) / 2)
    return centre[0] - size / 2, centre[1] - size / 2, size, size


def _view_box(box):
    return ' '.join(f'{value:g}' for value in box)


def _mark_svg(fill='currentColor', width=100, height=100):
    """Mark only, for a container that already paints the dark tile."""
    paths = ''.join(f'<path d="{path}" fill="{fill}"/>' for path in glyph_paths())
    return ('<svg xmlns="http://www.w3.org/2000/svg" fill="none" '
            f'width="{width}" height="{height}" viewBox="{_view_box(_glyph_box())}">{paths}</svg>')


def _lockup_svg(width=18, height=18):
    """The full lockup (dark tile plus mark) as shipped in ccode-logo.svg."""
    return re.sub(r'width="\d+" height="\d+"', f'width="{width}" height="{height}"', _source_svg(), count=1)


def data_uri(svg):
    return 'data:image/svg+xml,' + urllib.parse.quote(svg, safe="'=:/_.- ")


def mark_component():
    """Replacement for the bundled mark component: same props, CCode glyph."""
    paths = ''.join(f'(0,$.jsx)(`path`,{{fill:`currentColor`,d:`{path}`}}),' for path in glyph_paths())
    view = _view_box(_glyph_box())
    return ('function tkn({className:e}){return(0,$.jsxs)(`svg`,{xmlns:`http://www.w3.org/2000/svg`,'
            f'width:`100`,height:`100`,fill:`none`,viewBox:`{view}`,'
            'className:Z(`shrink-0 text-current`,e),"aria-hidden":`true`,focusable:`false`,children:['
            + paths + ']})}')


def scaled_path(path, scale, dx, dy):
    """Scale an M/L/A/Z path into another viewBox."""
    output = []
    tokens = _tokens(path)
    index = 0

    def point(values):
        return ' '.join(f'{value * scale + (dx if position % 2 == 0 else dy):g}'
                        for position, value in enumerate(values))

    while index < len(tokens):
        token = tokens[index]
        if token in 'ML':
            output.append(token + point([float(value) for value in tokens[index + 1:index + 3]]))
            index += 3
        elif token == 'A':
            radii, end = _arc(tokens, index)
            output.append('A' + ' '.join(f'{radius * scale:g}' for radius in radii) + ' '
                          + ' '.join(tokens[index + 3:index + 6]) + ' ' + point(list(end)))
            index += 8
        else:
            output.append(token)
            index += 1
    return ''.join(output)


# --- archive --------------------------------------------------------------

def _patch_marks(text):
    # Title bar and sidebar logo: the shell passes this data URI down as appLogoUrl.
    text = _replace_template(text, 'IS=', data_uri(_lockup_svg()))
    # Onboarding and login mark inside the dark rounded tile.
    text = replace_span(text, 'function tkn({className:e})', 'function nkn()', mark_component())
    # Draft watermark: light variant is an inline path, dark variant a data URI.
    box = _glyph_box()
    scale = WATERMARK_FILL * min(WATERMARK_BOX[0] / box[2], WATERMARK_BOX[1] / box[3])
    dx = (WATERMARK_BOX[0] - box[2] * scale) / 2 - box[0] * scale
    dy = (WATERMARK_BOX[1] - box[3] * scale) / 2 - box[1] * scale
    path = scaled_path(glyph_paths()[0], scale, dx, dy)
    text = _replace_literal_after(text, ',{d:`M398.97 0.5L147.576', ',{fill:`currentColor`,d:`' + path)
    return _replace_template(text, 'var Kgt=', data_uri(_mark_svg(fill='#ffffff', width=400, height=320)))


def guard(text, name):
    """Fail when the upstream mark survives in a shipped asset."""
    for marker in LEGACY_MARK_PREFIXES:
        if marker in text:
            raise ValueError(f'Upstream product mark left in {name}: ' + marker)
    if LEGACY_VIEW_BOX in text:
        raise ValueError(f'Upstream mark viewBox left in {name}')


def patch_archive(archive, replacements, assets):
    """Apply the CCode mark; `assets` names the pinned bundle paths."""
    renderer, icon = assets['renderer'], assets['icon']

    replacements[renderer] = _replace_legacy_mark(_patch_marks(_current(archive, replacements, renderer))).encode()
    replacements[icon] = (ICON_DIR / 'ccode-1024.png').read_bytes()
    replacements[MAIN] = _replace_legacy_mark(_current(archive, replacements, MAIN)).encode()
    replacements[INDEX] = _replace_legacy_mark(_current(archive, replacements, INDEX)).encode()

    for name in (renderer, MAIN, INDEX):
        guard(replacements[name].decode(), name)
