"""Generate the Vertigo PWA icon set.

Run from the project root (requires Pillow, a dev-only dependency):

    python scripts/make_icons.py

Writes ``src/vertigo/static/icons/`` with the sizes a PWA needs.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "src" / "vertigo" / "static" / "icons"

START = (37, 99, 235)  # blue-600
END = (6, 182, 212)  # cyan-500


def _gradient(size: int) -> Image.Image:
    y, x = np.mgrid[0:size, 0:size]
    t = ((x + y) / (2 * (size - 1)))[..., None]
    start = np.array(START, dtype=float)
    end = np.array(END, dtype=float)
    rgb = (start * (1 - t) + end * t).astype(np.uint8)
    return Image.fromarray(rgb, "RGB").convert("RGBA")


def _swirl(size: int) -> Image.Image:
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    cx = cy = size / 2
    steps = 900
    for i in range(steps):
        t = i / (steps - 1)
        angle = t * math.pi * 3.6
        radius = size * 0.045 + t * size * 0.40
        x = cx + radius * math.cos(angle)
        y = cy + radius * math.sin(angle)
        dot = size * (0.055 * (1 - t) + 0.005)
        draw.ellipse([x - dot, y - dot, x + dot, y + dot], fill=(255, 255, 255, 255))
    return layer


def _compose(size: int, *, rounded: bool, glyph_scale: float) -> Image.Image:
    icon = _gradient(size)
    if rounded:
        mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            [0, 0, size - 1, size - 1], radius=round(size * 0.22), fill=255
        )
        icon.putalpha(mask)

    glyph_size = max(8, round(size * glyph_scale))
    glyph = _swirl(glyph_size)
    icon.alpha_composite(glyph, ((size - glyph_size) // 2, (size - glyph_size) // 2))
    return icon


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    targets = {
        "icon-192.png": _compose(192, rounded=True, glyph_scale=0.74),
        "icon-512.png": _compose(512, rounded=True, glyph_scale=0.74),
        "icon-maskable-512.png": _compose(512, rounded=False, glyph_scale=0.58),
        "apple-touch-icon.png": _compose(180, rounded=False, glyph_scale=0.74),
    }
    for name, image in targets.items():
        image.save(OUT / name)
        print(f"wrote {OUT / name}")


if __name__ == "__main__":
    main()
