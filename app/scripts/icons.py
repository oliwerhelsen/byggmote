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




def tray() -> None:
    """The icons beside the clock while a meeting is recorded, written into the main process's code (the installed app
    carries no loose image files): the wave in black for the Mac's menu bar, which tints it itself, and the app's own
    tile for the notification area on Windows and Linux."""
    import base64
    import io

    def wave(size: int) -> Image.Image:
        s = size * SS
        im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        w = round(s * 0.085)
        for x, h in ((0.2, 0.22), (0.35, 0.5), (0.5, 0.78), (0.65, 0.42), (0.8, 0.22)):
            cx, half = round(s * x), round(s * h / 2)
            d.rounded_rectangle([cx - w // 2, s // 2 - half, cx + w // 2, s // 2 + half], radius=w // 2, fill=(0, 0, 0, 255))
        return im.resize((size, size), Image.LANCZOS)

    def b64(im: Image.Image) -> str:
        out = io.BytesIO()
        im.save(out, "PNG", optimize=True)
        return base64.b64encode(out.getvalue()).decode()

    tile = Image.open(BUILD / "icon.png").convert("RGBA").resize((32, 32), Image.LANCZOS)
    target = BUILD.parent / "src" / "main" / "tray-icons.ts"
    target.write_text(
        "// Written by scripts/icons.py (tray). The Mac's is drawn at twice the size of its 18 points.\n"
        f"export const MAC_TEMPLATE_2X = '{b64(wave(36))}'\n"
        f"export const TILE_32 = '{b64(tile)}'\n",
        encoding="utf8",
    )


if __name__ == "__main__":
    main()
    tray()
