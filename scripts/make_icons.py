#!/usr/bin/python3
"""Rasterize the CCode brand SVG into the icon sizes the launcher, app and setup need.

ImageMagick with the librsvg delegate renders the source SVG; the generated PNGs and the
multi-resolution `ccode.ico` (executable resources, tray icon, NSIS setup icon) are
committed so `make build` never depends on that tool being installed.
Run `make icons` after replacing ccode-logo.svg.
"""
import pathlib
import shutil
import struct
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'ccode-logo.svg'
TARGET = ROOT / 'assets/icons'
SIZES = (16, 24, 32, 48, 64, 128, 256, 512, 1024)
ICO = TARGET / 'ccode.ico'
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)
FALLBACKS = (r'C:\Program Files\ImageMagick-7.1.2-Q16-HDRI\magick.exe',)


def converter():
    """ImageMagick from PATH first, then its standard Windows install location."""
    found = shutil.which('magick')
    if found:
        return found
    for fallback in FALLBACKS:
        if pathlib.Path(fallback).is_file():
            return fallback
    # ImageMagick 6 only ships `convert`, which on Windows is also the system NTFS tool.
    found = shutil.which('convert')
    if found and pathlib.Path(found).parent.name.lower() not in ('system32', 'syswow64'):
        return found
    raise SystemExit('ImageMagick is required to rasterize the brand SVG; install it or put it on PATH '
                     f'({FALLBACKS[0]})')


def ico_frames(path):
    """The frame sizes a multi-resolution ICO declares; 0 encodes the 256 pixel frame."""
    data = path.read_bytes()
    reserved, kind, count = struct.unpack_from('<HHH', data, 0)
    if reserved or kind != 1:
        raise ValueError(f'Not an ICO file: {path}')
    return sorted((data[6 + index * 16] or 256, data[7 + index * 16] or 256) for index in range(count))


def main():
    if not SOURCE.exists():
        raise SystemExit(f'Brand source is missing: {SOURCE}')
    magick = converter()
    TARGET.mkdir(parents=True, exist_ok=True)
    written = []
    for size in SIZES:
        destination = TARGET / f'ccode-{size}.png'
        subprocess.run([magick, '-background', 'none', str(SOURCE),
                        '-resize', f'{size}x{size}', str(destination)], check=True)
        written.append(destination)
    subprocess.run([magick, *[str(TARGET / f'ccode-{size}.png') for size in ICO_SIZES], str(ICO)], check=True)
    written.append(ICO)
    expected = sorted((size, size) for size in ICO_SIZES)
    frames = ico_frames(ICO)
    if frames != expected:
        raise SystemExit(f'{ICO.name} is not multi-resolution: {frames}, expected {expected}')
    for path in written:
        print(f'{path.name}: {path.stat().st_size} bytes')


if __name__ == '__main__':
    sys.exit(main())
