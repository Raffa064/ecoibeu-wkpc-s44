#!/usr/bin/python3
"""Renderiza o ícone do app (SVG) em PNGs nítidos para o AppImage.

Usa librsvg + cairo em vez do renderizador interno do ImageMagick, que
distorce gradientes e cantos arredondados.

Uso:
    /usr/bin/python3 packaging/render-icons.py
"""

import os

import cairo
import gi

gi.require_version("Rsvg", "2.0")
from gi.repository import Rsvg  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SVG = os.path.join(HERE, "ecoibeu-mouse.svg")
OUT_DIR = os.path.join(HERE, "icons")
SIZES = (16, 24, 32, 48, 64, 128, 256)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    handle = Rsvg.Handle.new_from_file(SVG)
    for size in SIZES:
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
        context = cairo.Context(surface)
        viewport = Rsvg.Rectangle()
        viewport.x = 0
        viewport.y = 0
        viewport.width = size
        viewport.height = size
        handle.render_document(context, viewport)
        path = os.path.join(OUT_DIR, f"{size}.png")
        surface.write_to_png(path)
        print(f"{path} ({size}x{size})")


if __name__ == "__main__":
    main()
