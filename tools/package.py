#!/usr/bin/env python3
"""Build a TEMP-only outer AOTA update package from a JX402 app.bin.

The stock CMF receiver accepts an outer AOTA that carries only ``ota.xml`` and
``TEMP.bin`` (file id 254, storage id 2) followed by the stock AGPS trailer.
``TEMP.bin`` is itself a chunk-compressed AOTA with ``ota.xml``, a raw
``app.bin`` (file id 4) and the stock ``sdfs.bin`` (file id 5), which the
stock updater installs after it has streamed TEMP into the TEMP partition.

Everything here is offline. Container parsing and building come from fwkit;
this module only decides which parts go in, keeps the stock manifest fields
and writes the report manifest next to each package.

Usage (defaults build the stock, remote and remote-icon packages in dist/):

    python3 tools/package.py
    python3 tools/package.py --app patch/build/app_patched.bin \\
        --out dist/remote-temp-only.bin --allow-ranges dist/allowed-diff-remote.json
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import struct
import sys
import xml.etree.ElementTree as ET
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TOOLKIT = ROOT.parent / "cmf-watch-utils"
DEFAULT_STOCK_IMAGE = DEFAULT_TOOLKIT / "dumps/binaries/firmware/JX402_V1.0.0.73.bin"
DEFAULT_STOCK_APP = ROOT / "re/app_073.bin"

BOARD = "jx402_01_3089c"
STOCK_APP_SHA256 = "30e7978c39d8fb79b825c7ebf69b4377d214e9cc6739a52f06dbb5ff7f13b490"
BASE = 0x10000000
APP_LIMIT = 0x34B000
TEMP_LIMIT = 3670016
CHUNK_TEMP = 0x200000

STOCK_PACKAGE = ROOT / "dist/stock73-temp-only.bin"
REMOTE_PACKAGE = ROOT / "dist/remote-temp-only.bin"
ICON_PACKAGE = ROOT / "dist/remote-icon-temp-only.bin"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_fwkit(toolkit: Path):
    try:
        from fwkit import aota  # noqa: F401
        return aota
    except ImportError:
        pass
    source = toolkit / "tooling/src"
    if not (source / "fwkit/aota.py").is_file():
        raise SystemExit(f"fwkit not importable and {source} is not a fwkit checkout; "
                         "pass --toolkit or run under uv --project cmf-watch-utils")
    sys.path.insert(0, str(source))
    from fwkit import aota
    return aota


class Stock:
    """The stock 1.0.0.73 image and the parts this packager reuses."""

    def __init__(self, aota, path: Path):
        self.aota = aota
        self.path = path
        self.data = path.read_bytes()
        self.header, self.entries = aota.parse(self.data)
        stored = {e.name: e.stored(self.data) for e in self.entries}
        if "ota.xml" not in stored or "TEMP.bin" not in stored:
            raise SystemExit(f"{path}: not a stock CMF image (needs ota.xml and TEMP.bin)")
        self.xml = stored["ota.xml"]
        self.temp = stored["TEMP.bin"]
        self.trailer = self.data[aota.agps_offset(self.header):]
        self.inner = aota.unpack_chunks(self.temp)
        self.inner_header, self.inner_entries = aota.parse(self.inner)
        inner = {e.name: e.stored(self.inner) for e in self.inner_entries}
        if set(inner) != {"ota.xml", "app.bin", "sdfs.bin"}:
            raise SystemExit(f"{path}: unexpected nested parts {sorted(inner)}")
        self.inner_xml = inner["ota.xml"]
        self.app = inner["app.bin"]
        self.sdfs = inner["sdfs.bin"]

        board = self.header[0x60:0x70].split(b"\0")[0].decode("ascii")
        if board != BOARD:
            raise SystemExit(f"{path}: board {board!r}, expected {BOARD!r}")
        if sha256(self.app) != STOCK_APP_SHA256:
            raise SystemExit(f"{path}: nested app.bin is not stock 1.0.0.73 "
                             f"({sha256(self.app)})")
        if self.trailer[:4] != b"AGPS":
            raise SystemExit(f"{path}: AGPS trailer missing at {aota.agps_offset(self.header):#x}")


def fix_data_crc(aota, img: bytes) -> bytes:
    """Set header +0x18 to crc32(data) and refresh the header CRC.

    fwkit preserves +0x18 (it is only validated by the recovery reader), so the
    packager writes the caller-visible data CRC itself, exactly like the outer
    image of the stock firmware.
    """
    out = bytearray(img)
    start = struct.unpack_from("<H", out, 0x12)[0]
    end = struct.unpack_from("<I", out, 0x14)[0]
    struct.pack_into("<I", out, 0x18, zlib.crc32(memoryview(out)[start:end]) & 0xFFFFFFFF)
    header = bytearray(out[:aota.HDR_SIZE])
    aota.fix_header(header)
    out[:aota.HDR_SIZE] = header
    return bytes(out)


def temp_only_xml(aota, stock_xml: bytes, temp: bytes) -> bytes:
    """Stock outer manifest with its TEMP partition as the only entry."""
    text = stock_xml.decode("utf-8")
    part = re.search(r"\t<partition>\r?\n\s*<type>TEMP</type>.*?</partition>\r?\n", text, re.S)
    if part is None:
        raise SystemExit("stock ota.xml has no TEMP partition block")
    body = "\t<partitionsNum>1</partitionsNum>\r\n" + part.group(0)
    text, count = re.subn(r"<partitions>\r?\n.*?</partitions>",
                          lambda _m: "<partitions>\r\n" + body + "\t</partitions>",
                          text, flags=re.S)
    if count != 1:
        raise SystemExit("stock ota.xml partitions block not found exactly once")
    xml = aota.xml_set(text.encode("utf-8"), {"TEMP.bin": {
        "file_size": len(temp), "orig_size": len(temp), "checksum": aota.crc32(temp)}})
    ET.fromstring(xml)  # the receiver is a strstr parser, but a malformed file is still a bug
    return xml


def build_package(aota, stock: Stock, app: bytes, sdfs: bytes) -> dict:
    if len(app) > APP_LIMIT:
        raise SystemExit(f"app.bin {len(app):#x} exceeds the app partition {APP_LIMIT:#x}")
    if app[:8] != b"ACTHHTCA":
        raise SystemExit("app.bin does not start with the ACTH header")

    inner_xml = aota.xml_set(stock.inner_xml, {
        "app.bin": {"file_size": len(app), "orig_size": len(app),
                    "checksum": aota.crc32(app)},
        "sdfs.bin": {"file_size": len(sdfs), "orig_size": len(sdfs),
                     "checksum": aota.crc32(sdfs)},
    })
    inner_header = bytearray(stock.inner_header)
    inner_header[0x200:0x400] = b"\0" * 0x200
    inner = aota.build(inner_header, inner_xml, [("app.bin", app), ("sdfs.bin", sdfs)], b"")
    inner = fix_data_crc(aota, inner)

    temp = aota.pack_chunks(inner, CHUNK_TEMP, preset=6)
    if len(temp) > TEMP_LIMIT:
        raise SystemExit(f"TEMP.bin {len(temp)} exceeds the measured {TEMP_LIMIT} byte partition")

    outer_xml = temp_only_xml(aota, stock.xml, temp)
    outer_header = bytearray(stock.header)
    outer_header[0x200:0x400] = b"\0" * 0x200
    image = aota.build(outer_header, outer_xml, [("TEMP.bin", temp)], stock.trailer)
    image = fix_data_crc(aota, image)
    return {"image": image, "temp": temp, "inner": inner, "xml": outer_xml}


def roundtrip(aota, stock: Stock, built: dict, app: bytes, sdfs: bytes) -> None:
    """Read the new package back the way the receiver does."""
    image = built["image"]
    header, entries = aota.parse(image)
    names = [e.name for e in entries]
    if names != ["ota.xml", "TEMP.bin"]:
        raise SystemExit(f"round trip: unexpected outer entries {names}")
    for entry in entries:
        if not aota.verify_entry(image, entry):
            raise SystemExit(f"round trip: outer CRC mismatch in {entry.name}")
    temp = entries[1].stored(image)
    if image[aota.agps_offset(header):] != stock.trailer:
        raise SystemExit("round trip: AGPS trailer changed")
    inner = aota.unpack_chunks(temp)
    _, inner_entries = aota.parse(inner)
    parts = {e.name: e.stored(inner) for e in inner_entries}
    if parts.get("app.bin") != app:
        raise SystemExit("round trip: app.bin does not read back byte-identically")
    if parts.get("sdfs.bin") != sdfs:
        raise SystemExit("round trip: sdfs.bin does not read back byte-identically")


def allowed_ranges(stock_app_len: int, icon: bool = False) -> list[list[int]]:
    """Every app range patch/build.py can legitimately touch (read-only import)."""
    spec = importlib.util.spec_from_file_location("wp2_patch_build", ROOT / "patch/build.py")
    if spec is None or spec.loader is None:
        raise SystemExit("cannot load patch/build.py for the diff allowlist")
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True  # never write patch/__pycache__
    try:
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous

    ranges = [[BASE + 0x18, BASE + 0x24]]  # ACTH ih_img_size/chksum/hdr_chksum
    for site, _original, _symbol in module.HOOKS + (module.ICON_HOOKS if icon else []):
        ranges.append([site, site + 4])  # 4-byte BL rewrites
    view_entry = module.VIEW_ENTRY_ALIPAY_MAIN + 4
    ranges.append([view_entry, view_entry + 8])
    row = module.APPLIST_ROW_VOICE_ASSISTANT_ACTION
    ranges.append([row, row + 4])
    for address, _old, new in module.DATA_PATCHES:
        ranges.append([address, address + len(new)])
    ranges.append([BASE + stock_app_len, BASE + APP_LIMIT])  # padding + code cave

    merged: list[list[int]] = []
    for start, end in sorted(ranges):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return merged


def emit(aota, stock: Stock, app_path: Path, out_path: Path, manifest_path: Path,
         allow_path: Path | None, icon: bool = False) -> dict:
    app = app_path.read_bytes()
    built = build_package(aota, stock, app, stock.sdfs)
    roundtrip(aota, stock, built, app, stock.sdfs)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(built["image"])
    image = built["image"]

    report = {
        "package": str(out_path.relative_to(ROOT)) if out_path.is_relative_to(ROOT) else str(out_path),
        "sha256": sha256(image),
        "bytes": len(image),
        "app": {"source": str(app_path.relative_to(ROOT)) if app_path.is_relative_to(ROOT)
                else str(app_path), "sha256": sha256(app), "bytes": len(app)},
        "sdfs": {"sha256": sha256(stock.sdfs), "bytes": len(stock.sdfs)},
        "temp": {"sha256": sha256(built["temp"]), "bytes": len(built["temp"]),
                 "limit": TEMP_LIMIT},
        "inner_bytes": len(built["inner"]),
        "ota_xml_bytes": len(built["xml"]),
        "agps_trailer": {"sha256": sha256(stock.trailer), "bytes": len(stock.trailer)},
        "stock_image": {"sha256": sha256(stock.data), "bytes": len(stock.data)},
        "board_name": BOARD,
        "file_ids": {"TEMP.bin": 254, "app.bin": 4, "sdfs.bin": 5},
        "stock_identity": {
            "app_byte_identical": app == stock.app,
            "temp_byte_identical": built["temp"] == stock.temp,
            "inner_byte_identical": built["inner"] == stock.inner,
        },
    }
    if allow_path is not None:
        ranges = allowed_ranges(len(stock.app), icon)
        allow_path.parent.mkdir(parents=True, exist_ok=True)
        allow_path.write_text(json.dumps(ranges, indent=2) + "\n", encoding="utf-8")
        report["allowed_diff_ranges"] = {
            "path": str(allow_path.relative_to(ROOT)) if allow_path.is_relative_to(ROOT)
            else str(allow_path),
            "ranges": ranges,
        }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--app", type=Path,
                        help="app.bin to package (default: build both dist packages)")
    parser.add_argument("--out", type=Path, help="output AOTA path")
    parser.add_argument("--manifest", type=Path, help="report manifest (default: alongside --out)")
    parser.add_argument("--allow-ranges", type=Path,
                        help="write the patch/build.py diff allowlist here")
    parser.add_argument("--icon", action="store_true",
                        help="the app was built with --icon (allow the icon hook sites)")
    parser.add_argument("--stock-image", type=Path, default=DEFAULT_STOCK_IMAGE)
    parser.add_argument("--stock-app", type=Path, default=DEFAULT_STOCK_APP,
                        help="stock app.bin used for the rehearsal package and allowlist")
    parser.add_argument("--toolkit", type=Path, default=DEFAULT_TOOLKIT,
                        help="cmf-watch-utils checkout (for fwkit)")
    args = parser.parse_args()

    aota = load_fwkit(args.toolkit)
    stock_image = args.stock_image.resolve()
    if not stock_image.is_file():
        raise SystemExit(f"stock image not found: {stock_image}")
    stock = Stock(aota, stock_image)
    stock_app = args.stock_app.resolve()
    if sha256(stock_app.read_bytes()) != STOCK_APP_SHA256:
        raise SystemExit(f"{stock_app}: not stock 1.0.0.73 app.bin")

    if args.app is not None:
        if args.out is None:
            raise SystemExit("--out is required with --app")
        out = args.out.resolve()
        manifest = (args.manifest or out.with_suffix(".json")).resolve()
        reports = [emit(aota, stock, args.app.resolve(), out, manifest, args.allow_ranges, args.icon)]
    else:
        if args.out or args.manifest:
            raise SystemExit("--out/--manifest need --app; the default mode builds both packages")
        reports = [
            emit(aota, stock, stock_app, STOCK_PACKAGE,
                 STOCK_PACKAGE.with_suffix(".json"), None),
            emit(aota, stock, (ROOT / "patch/build/app_patched.bin"),
                 REMOTE_PACKAGE, REMOTE_PACKAGE.with_suffix(".json"),
                 ROOT / "dist/allowed-diff-remote.json"),
            emit(aota, stock, (ROOT / "patch/build/app_icon.bin"),
                 ICON_PACKAGE, ICON_PACKAGE.with_suffix(".json"),
                 ROOT / "dist/allowed-diff-remote-icon.json", icon=True),
        ]
    print(json.dumps(reports, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
