"""The app icon: the logo's wave in white on coral, drawn here so it can be drawn again.

Writes build/icon.png (1024, Linux and the dock in dev), build/icon.icns (Mac) and build/icon.ico (Windows), the names
electron-builder looks for in build/. Run from app/: python3 scripts/icons.py (needs Pillow; iconutil on a Mac).
"""

import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

BUILD = Path(__file__).resolve().parent.parent / "build"
SS = 4  # drawn this many times larger, then scaled down, for smooth edges
TOP, BOTTOM = (0xFF, 0x70, 0x76), (0xC9, 0x3A, 0x42)  # coral-500 to coral-700, as in app.css


def draw(size: int, inset: float) -> Image.Image:
    """The icon on a transparent square. inset is the margin around the tile, as a share of the side."""
    s = size * SS
    m = round(s * inset)
    tile = s - 2 * m
    gradient = Image.new("RGBA", (s, s))
    g = ImageDraw.Draw(gradient)
    for y in range(s):
        t = min(max((y - m) / tile, 0), 1)
        g.line([(0, y), (s, y)], fill=tuple(round(a + (b - a) * t) for a, b in zip(TOP, BOTTOM)) + (255,))
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle([m, m, s - m, s - m], radius=round(tile * 0.225), fill=255)
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    img.paste(gradient, (0, 0), mask)

    # The wave from Icon.svelte (24 grid: bars at x 4..20, heights 4, 12, 18, 10, 4), scaled into the tile.
    d = ImageDraw.Draw(img)
    unit = tile * 0.6 / 18
    cx, cy = s / 2, s / 2
    w = unit * 2.2
    for x, h in ((4, 4), (8, 12), (12, 18), (16, 10), (20, 4)):
        bx = cx + (x - 12) * unit
        d.rounded_rectangle([bx - w / 2, cy - h * unit / 2 - w / 2, bx + w / 2, cy + h * unit / 2 + w / 2], radius=w / 2, fill="white")
    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    BUILD.mkdir(exist_ok=True)
    # The Mac draws an app icon as-is, so it carries Apple's margin (824 of 1024); Windows and Linux fill the square.
    mac = draw(1024, 100 / 1024)
    full = draw(1024, 0.04)
    full.save(BUILD / "icon.png")
    full.save(BUILD / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    if shutil.which("iconutil"):
        with tempfile.TemporaryDirectory() as tmp:
            iconset = Path(tmp) / "icon.iconset"
            iconset.mkdir()
            for base in (16, 32, 128, 256, 512):
                mac.resize((base, base), Image.LANCZOS).save(iconset / f"icon_{base}x{base}.png")
                mac.resize((base * 2, base * 2), Image.LANCZOS).save(iconset / f"icon_{base}x{base}@2x.png")
            subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(BUILD / "icon.icns")], check=True)
    mac.save(BUILD / "icon-mac.png")


if __name__ == "__main__":
    main()
