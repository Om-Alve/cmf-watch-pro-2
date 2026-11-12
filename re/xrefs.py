import struct, sys
from functools import lru_cache
BASE = 0x10000000
app = open(sys.argv[1] if len(sys.argv) > 2 else "app_073.bin", "rb").read()

def bl_target(pc, hw1, hw2):
    if (hw1 & 0xF800) != 0xF000 or (hw2 & 0xD000) not in (0xD000, 0xC000):
        return None
    s = (hw1 >> 10) & 1
    imm10 = hw1 & 0x3FF
    j1 = (hw2 >> 13) & 1; j2 = (hw2 >> 11) & 1
    i1 = 1 - (j1 ^ s); i2 = 1 - (j2 ^ s)
    imm11 = hw2 & 0x7FF
    off = (s << 24) | (i1 << 23) | (i2 << 22) | (imm10 << 12) | (imm11 << 1)
    if s: off -= 1 << 25
    t = pc + 4 + off
    if (hw2 & 0xD000) == 0xC000:
        t &= ~3
    return t, (hw2 & 0xD000) == 0xD000

def scan():
    out = []
    for o in range(0x200, len(app) - 4, 2):
        hw1, hw2 = struct.unpack_from("<HH", app, o)
        r = bl_target(BASE + o, hw1, hw2)
        if r and BASE <= r[0] < BASE + len(app):
            out.append((BASE + o, r[0], r[1]))
    return out

if __name__ == "__main__":
    target = int(sys.argv[-1], 16)
    for pc, t, thumb in scan():
        if t == target:
            print(hex(pc), "BL" if thumb else "BLX")
