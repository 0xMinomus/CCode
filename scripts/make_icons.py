#!/usr/bin/python3
"""Rasterize the CCode brand SVG into the icon sizes the launcher and app need.

ImageMagick with the librsvg delegate renders the source SVG; the generated PNGs
are committed so `make build` never depends on that tool being installed.
Run `make icons` after replacing ccode-logo.svg.
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'ccode-logo.svg'
TARGET = ROOT / 'assets/icons'
SIZES = (16, 24, 32, 48, 64, 128, 256, 512, 1024)


def main():
    if not SOURCE.exists():
        raise SystemExit(f'Brand source is missing: {SOURCE}')
    converter = shutil.which('magick') or shutil.which('convert')
    if not converter:
        raise SystemExit('ImageMagick is required to rasterize the brand SVG')
    TARGET.mkdir(parents=True, exist_ok=True)
    written = []
    for size in SIZES:
        destination = TARGET / f'ccode-{size}.png'
        subprocess.run([converter, '-background', 'none', str(SOURCE),
                        '-resize', f'{size}x{size}', str(destination)], check=True)
        written.append(destination)
    for path in written:
        print(f'{path.name}: {path.stat().st_size} bytes')


if __name__ == '__main__':
    sys.exit(main())
