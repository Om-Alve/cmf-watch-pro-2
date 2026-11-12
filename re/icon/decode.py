import sys
from PIL import Image
def decode(path, out, swap=False):
    d = open(path, "rb").read()
    img = Image.new("RGBA", (96, 96))
    px = []
    for i in range(96 * 96):
        lo, hi, a = d[3*i:3*i+3]
        v = (lo << 8 | hi) if swap else (hi << 8 | lo)
        r, g, b = (v >> 11) << 3, ((v >> 5) & 63) << 2, (v & 31) << 3
        px.append((r, g, b, a))
    img.putdata(px)
    bg = Image.new("RGBA", (96, 96), (0, 0, 0, 255))
    Image.alpha_composite(bg, img).resize((288, 288), Image.NEAREST).save(out)
decode(sys.argv[1], sys.argv[2], len(sys.argv) > 3)
