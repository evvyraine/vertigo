"""Build Vertigo's icon set from the master logo.

The logo is AI-generated (see ``assets/brand/logo-source.png``); the master mark
and the PWA/Apple icons are composed deterministically from it, so re-running
this script reproduces the same files.

    uv run python scripts/make_brand.py

Outputs
-------
``src/vertigo/static/brand/logo.png``   trimmed, padded master mark
``src/vertigo/static/icons/*.png``      PWA / Apple touch icons

The README banner (``assets/banner.png``) and social preview
(``assets/social.png``) are hand-made and not touched here.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets" / "brand" / "logo-source.png"
LOGO_OUT = ROOT / "src" / "vertigo" / "static" / "brand" / "logo.png"
ICONS_OUT = ROOT / "src" / "vertigo" / "static" / "icons"

# Palette — mirrors the Streamlit theme in .streamlit/config.toml.
BG_TOP = (250, 251, 253)
BG_BOTTOM = (230, 234, 242)
SHADOW = (26, 30, 40)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _trim(image: Image.Image, threshold: int = 16) -> Image.Image:
    """Crop to the visible mark, ignoring faint anti-aliasing at the edges."""
    alpha = image.getchannel("A").point(lambda v: 255 if v > threshold else 0)
    box = alpha.getbbox()
    return image.crop(box) if box else image


def _squared(image: Image.Image, *, margin: float = 0.06, size: int | None = None) -> Image.Image:
    """Place the mark on a transparent square canvas with a uniform margin."""
    w, h = image.size
    side = max(w, h)
    pad = round(side * margin)
    canvas = round(side + 2 * pad)
    square = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    square.alpha_composite(image, ((canvas - w) // 2, (canvas - h) // 2))
    if size:
        square = square.resize((size, size), Image.LANCZOS)
    return square


def _background(size: tuple[int, int], top: tuple, bottom: tuple) -> np.ndarray:
    """A soft diagonal gradient as a float array."""
    w, h = size
    ys, xs = np.mgrid[0:h, 0:w]
    t = ((xs / max(w - 1, 1)) * 0.35 + (ys / max(h - 1, 1)) * 0.65)[..., None]
    return np.array(top, dtype=float) * (1 - t) + np.array(bottom, dtype=float) * t


def _drop_shadow(logo: Image.Image, blur: int, strength: float) -> Image.Image:
    """A soft neutral drop shadow behind the mark."""
    alpha = logo.getchannel("A").filter(ImageFilter.GaussianBlur(blur))
    shadow = Image.new("RGBA", logo.size, (*SHADOW, 0))
    shadow.putalpha(alpha.point(lambda v: int(v * strength)))
    return shadow


def _rounded(image: Image.Image, radius: int) -> Image.Image:
    mask = Image.new("L", image.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, image.width - 1, image.height - 1], radius=radius, fill=255)
    out = image.copy()
    out.putalpha(mask)
    return out


# --------------------------------------------------------------------------- #
# Assets
# --------------------------------------------------------------------------- #
def build_logo() -> Image.Image:
    mark = _trim(Image.open(SOURCE).convert("RGBA"))
    logo = _squared(mark, margin=0.06, size=1024)
    LOGO_OUT.parent.mkdir(parents=True, exist_ok=True)
    logo.save(LOGO_OUT, optimize=True, compress_level=9)
    return logo


def _icon(logo: Image.Image, size: int, *, rounded: bool, scale: float) -> Image.Image:
    canvas = _background((size, size), BG_TOP, BG_BOTTOM)
    base = Image.fromarray(np.clip(canvas, 0, 255).astype(np.uint8), "RGB").convert("RGBA")

    target = round(size * scale)
    mark = logo.resize((target, target), Image.LANCZOS)
    offset = max(2, round(size * 0.012))
    shadow = _drop_shadow(mark, max(3, round(size * 0.02)), 0.30)
    left = round((size - target) / 2)
    top = round((size - target) / 2)
    base.alpha_composite(shadow, (left, top + offset))
    base.alpha_composite(mark, (left, top))
    return _rounded(base, round(size * 0.22)) if rounded else base


def build_icons(logo: Image.Image) -> None:
    ICONS_OUT.mkdir(parents=True, exist_ok=True)
    targets = {
        "icon-192.png": _icon(logo, 192, rounded=True, scale=0.74),
        "icon-512.png": _icon(logo, 512, rounded=True, scale=0.74),
        "icon-maskable-512.png": _icon(logo, 512, rounded=False, scale=0.60),
        "apple-touch-icon.png": _icon(logo, 180, rounded=False, scale=0.74),
    }
    for name, image in targets.items():
        image.save(ICONS_OUT / name, optimize=True, compress_level=9)


def main() -> None:
    logo = build_logo()
    build_icons(logo)
    for path in (LOGO_OUT, *(ICONS_OUT / n for n in ("icon-192.png", "icon-512.png", "icon-maskable-512.png", "apple-touch-icon.png"))):
        print(f"wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
