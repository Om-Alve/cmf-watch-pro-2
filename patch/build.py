import struct
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = 0x10000000
STOCK_SHA = "30e7978c39d8fb79b825c7ebf69b4377d214e9cc6739a52f06dbb5ff7f13b490"
CAVE = 0x1025A100
APP_LIMIT = 0x34B000
CFLAGS = ["-mcpu=cortex-m4", "-mthumb", "-mfloat-abi=soft", "-Os", "-ffreestanding", "-fno-builtin",
          "-ffunction-sections", "-fdata-sections", "-fno-common", "-nostdlib", "-Wall", "-Werror", "-I" + str(Path(__file__).resolve().parent)]


def sum32(data):
    return sum(struct.unpack(f"<{len(data) // 4}I", data)) & 0xFFFFFFFF


def encode_bl(pc, target):
    off = target - (pc + 4)
    assert -(1 << 24) <= off < (1 << 24) and off % 2 == 0
    s = 1 if off < 0 else 0
    off &= (1 << 25) - 1
    i1, i2 = (off >> 23) & 1, (off >> 22) & 1
    j1, j2 = (1 - i1) ^ s, (1 - i2) ^ s
    hw1 = 0xF000 | (s << 10) | ((off >> 12) & 0x3FF)
    hw2 = 0xD000 | (j1 << 13) | (j2 << 11) | ((off >> 1) & 0x7FF)
    return struct.pack("<HH", hw1, hw2)


def decode_bl(pc, raw):
    hw1, hw2 = struct.unpack("<HH", raw)
    assert (hw1 & 0xF800) == 0xF000 and (hw2 & 0xD000) == 0xD000, f"not a BL at {pc:#x}"
    s = (hw1 >> 10) & 1
    j1, j2 = (hw2 >> 13) & 1, (hw2 >> 11) & 1
    off = (s << 24) | ((1 - (j1 ^ s)) << 23) | ((1 - (j2 ^ s)) << 22) | ((hw1 & 0x3FF) << 12) | ((hw2 & 0x7FF) << 1)
    if s:
        off -= 1 << 25
    return pc + 4 + off


def icon_source(build, icon_path):
    pixels = Path(icon_path).read_bytes()
    assert len(pixels) == ICON_BYTES, f"{icon_path}: expected {ICON_BYTES} bytes of RGB565+A8, got {len(pixels)}"
    rows = ",\n".join(", ".join(f"0x{b:02x}" for b in pixels[i:i + 24]) for i in range(0, len(pixels), 24))
    src = build / "icon_pixels.c"
    src.write_text("#include <stdint.h>\nconst uint8_t remote_icon_pixels[%d] = {\n%s\n};\n" % (len(pixels), rows))
    return [HERE / "icon/applist_icon.c", src]


def compile_cave(build, keep, debug, icon=None):
    build.mkdir(exist_ok=True)
    objs = []
    sources = sorted(HERE.glob("*.c")) + (sorted(HERE.glob("*.S")) if debug else [])
    if icon:
        sources += icon_source(build, icon)
    for src in sources:
        obj = build / (src.name + ".o")
        subprocess.run(["arm-none-eabi-gcc", *CFLAGS, "-c", str(src), "-o", str(obj)], check=True)
        objs.append(str(obj))
    elf = build / "cave.elf"
    subprocess.run(["arm-none-eabi-gcc", *CFLAGS, "-T", str(HERE / "link.ld"), "-L", str(HERE),
                    "-Wl,--gc-sections", "-Wl,-Map=" + str(build / "cave.map"), *[f"-Wl,-u,{k}" for k in keep], *objs, "-o", str(elf)], check=True)
    syms = {}
    for line in subprocess.run(["arm-none-eabi-nm", str(elf)], capture_output=True, text=True, check=True).stdout.splitlines():
        addr, _, name = line.split()
        syms[name] = int(addr, 16)
    for obj in objs:
        sizes = subprocess.run(["arm-none-eabi-size", "-A", obj], capture_output=True, text=True, check=True).stdout
        for line in sizes.splitlines():
            parts = line.split()
            if parts and parts[0].startswith((".data", ".bss")) and len(parts) > 1 and parts[1] != "0":
                raise SystemExit(f"{obj}: writable section {parts[0]} is not allowed in the flash cave")
    blob = build / "cave.bin"
    subprocess.run(["arm-none-eabi-objcopy", "-O", "binary", str(elf), str(blob)], check=True)
    return blob.read_bytes(), syms


KEEP = {"remote_key", "remote_view_proc"}

VIEW_ENTRY_ALIPAY_MAIN = 0x100004B8 + 24 * 115
APPLIST_ROW_VOICE_ASSISTANT_ACTION = 0x101EB000 + 8

BOOT_HOOK = (0x10054882, 0x10054CF4, "hook_boot")

HOOKS = [
    (0x1015EECE, 0x1015EE30, "hid_press"),
    (0x1015EF88, 0x1015EE30, "hid_press_after_connect"),
    (0x1005EBFE, 0x10184A5C, "applist_load_texts"),
    (0x1005ED18, 0x10184A5C, "applist_load_texts"),
]


# Optional (--icon): rewrite the Voice Assistant row's icon pixels after the stock image loader.
ICON_BYTES = 96 * 96 * 3
ICON_HOOKS = [
    (0x1005E996, 0x101848D4, "applist_load_images"),
    (0x1005ECD0, 0x101848D4, "applist_load_images"),
]

HID_IDLE_STATE_JUMP = 0x1015EF7D

DATA_PATCHES = [
    (HID_IDLE_STATE_JUMP, bytes([0x13]), bytes([0x17])),
]


def apply_data_patches(app, patches):
    for addr, old, new in patches:
        off = addr - BASE
        assert bytes(app[off:off + len(old)]) == old, f"unexpected bytes at {addr:#x}"
        assert len(old) == len(new)
        app[off:off + len(new)] = new


def build(stock_path, out_path, extra_patches=(), debug=False, icon=None):
    import hashlib
    app = bytearray(Path(stock_path).read_bytes())
    assert hashlib.sha256(app).hexdigest() == STOCK_SHA, "expects stock 1.0.0.73 app.bin"
    hooks = HOOKS + ([BOOT_HOOK] if debug else []) + (ICON_HOOKS if icon else [])
    cave, syms = compile_cave(HERE / "build", sorted({h[2] for h in hooks} | KEEP), debug, icon)
    for site, original, symbol in hooks:
        off = site - BASE
        assert decode_bl(site, app[off:off + 4]) == original, f"unexpected call at {site:#x}"
        app[off:off + 4] = encode_bl(site, syms[symbol] & ~1)
    view_proc = syms["remote_view_proc"] | 1
    patches = [
        (VIEW_ENTRY_ALIPAY_MAIN + 4, struct.pack("<II", 0x100B3B1D, 0), struct.pack("<II", 0, view_proc)),
        (APPLIST_ROW_VOICE_ASSISTANT_ACTION, struct.pack("<I", 0xCF), struct.pack("<I", 0x2C)),
    ]
    apply_data_patches(app, patches + list(DATA_PATCHES) + list(extra_patches))
    app = app.ljust(CAVE - BASE, b"\0") + cave
    app = app.ljust((len(app) + 0x1FF) & ~0x1FF, b"\0")
    assert len(app) <= APP_LIMIT
    size = len(app) - 0x200
    struct.pack_into("<I", app, 0x18, size)
    struct.pack_into("<I", app, 0x1C, 0)
    struct.pack_into("<I", app, 0x1C, (0xFFFFFFFF - sum32(app[0x200:0x200 + size])) & 0xFFFFFFFF)
    struct.pack_into("<I", app, 0x20, 0)
    struct.pack_into("<I", app, 0x20, (0xFFFFFFFF - sum32(app[:0x200])) & 0xFFFFFFFF)
    assert sum32(app[:0x200]) == 0xFFFFFFFF
    assert (sum32(app[0x200:0x200 + size]) + struct.unpack_from("<I", app, 0x1C)[0]) & 0xFFFFFFFF == 0xFFFFFFFF
    Path(out_path).write_bytes(app)
    print(f"{out_path}: {len(app)} bytes, cave {len(cave)} bytes at {CAVE:#x}")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Patch stock 1.0.0.73 app.bin with the Faceclaw remote")
    ap.add_argument("stock")
    ap.add_argument("out")
    ap.add_argument("--debug", action="store_true", help="add the boot-time log hook (emulator only, never flash)")
    ap.add_argument("--icon", help="96x96 RGB565+A8 pixels (tools/make_icon.py) for the remote's app-list icon")
    a = ap.parse_args()
    build(a.stock, a.out, debug=a.debug, icon=a.icon)
