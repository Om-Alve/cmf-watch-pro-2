"""Turn a logo into a 96x96 app-list icon in the stock style (RGB565 + A8, LVGL TRUE_COLOR_ALPHA).

The circle and its anti-aliased edge come from the stock Voice Assistant icon
(re/icon/stock16.bin, dumped from the emulator); only the glyph is replaced.

    uv run --project ../cmf-watch-utils python tools/make_icon.py \
        ../../faceclaw/images/faceclaw-logo.png patch/icon/faceclaw_icon.bin --preview re/icon/faceclaw.png
"""

import argparse
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SIZE = 96
BG = (40, 44, 48)
FG = (240, 240, 240)


def rgb565(r, g, b):
    return (r >> 3) << 11 | (g >> 2) << 5 | (b >> 3)


def glyph_mask(path, threshold):
    """Dark strokes of a black-on-light logo become an L mask (255 = glyph)."""
    gray = Image.open(path).convert("L")
    mask = gray.point(lambda v: 255 if v < threshold else 0)
    return mask.crop(mask.getbbox())


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("logo")
    p.add_argument("out")
    p.add_argument("--stock", default=ROOT / "re/icon/stock16.bin")
    p.add_argument("--height", type=int, default=64, help="glyph height in pixels")
    p.add_argument("--threshold", type=int, default=100)
    p.add_argument("--preview")
    a = p.parse_args()

    stock = Path(a.stock).read_bytes()
    assert len(stock) == SIZE * SIZE * 3
    circle = [stock[3 * i + 2] for i in range(SIZE * SIZE)]

    mask = glyph_mask(a.logo, a.threshold)
    w = max(1, round(mask.width * a.height / mask.height))
    small = mask.resize((w, a.height), Image.LANCZOS)
    glyph = Image.new("L", (SIZE, SIZE), 0)
    glyph.paste(small, ((SIZE - w) // 2, (SIZE - a.height) // 2))
    cover = list(glyph.getdata())

    out = bytearray()
    preview = []
    for i in range(SIZE * SIZE):
        t = cover[i] / 255
        rgb = tuple(round(BG[c] + (FG[c] - BG[c]) * t) for c in range(3))
        alpha = circle[i]
        v = rgb565(*rgb)
        out += bytes([v & 0xFF, v >> 8, alpha])
        preview.append((*rgb, alpha))
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_bytes(out)
    print(f"{a.out}: {len(out)} bytes, glyph {w}x{a.height}")
    if a.preview:
        img = Image.new("RGBA", (SIZE, SIZE))
        img.putdata(preview)
        bg = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 255))
        Image.alpha_composite(bg, img).resize((SIZE * 3, SIZE * 3), Image.NEAREST).save(a.preview)


if __name__ == "__main__":
    main()
