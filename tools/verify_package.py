#!/usr/bin/env python3
"""Independently verify a TEMP-only CMF Watch Pro 2 (JX402) update package.

This is the gate between "the packager produced a file" and "the file is worth
handing to a watch". It shares no code with tools/package.py and uses only the
standard library: every container, checksum, manifest field, chunk limit and
build-time app constraint is recomputed here.

What it checks
--------------
outer AOTA     magic, header_size 0x400, header CRC, data CRC, entry CRCs,
               entry bounds/flags/overlap, board name, exactly ota.xml + TEMP.bin
manifest       firmware_version fields match stock 1.0.0.73, TEMP is file id
               254 / storage 2 / type TEMP, sizes and CRC match the stored bytes
AGPS trailer   byte-identical to the trailer of the stock 1.0.0.73 image
size limits    TEMP <= 3,670,016 B, app <= 0x34B000, sdfs <= 65,536 B,
               LZMA chunks <= 1,572,864 B compressed / 2,097,152 B expanded
nested AOTA    same structural checks, no trailer, exactly ota.xml + app.bin
               (id 4) + sdfs.bin (id 5) with the stock storage ids
stock identity sdfs.bin byte-identical to the stock image's sdfs.bin
app ACTH       magic, sum32(header) == 0xFFFFFFFF, sum32(data)+ih_img_chksum ==
               0xFFFFFFFF, ih_img_size inside the app and <= code_max_len,
               ih_hdr_size 0x200, not encrypted, SP in 0x2FF00000..0x30000000,
               Thumb reset vector inside the app equal to ih_load_addr/ih_entry
diff gate      every app byte that differs from --stock-app is reported; with
               --allow-diff-from FILE (JSON list of [start,end) addresses) any
               difference outside those ranges fails the run

Exit status is 0 only when every check passes. A JSON report goes to stdout.

    python3 tools/verify_package.py dist/remote-temp-only.bin \\
        --stock-app re/app_073.bin --allow-diff-from dist/allowed-diff-remote.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import lzma
import struct
import sys
import xml.etree.ElementTree as ET
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STOCK_IMAGE = (ROOT.parent / "cmf-watch-utils/dumps/binaries/firmware"
                       / "JX402_V1.0.0.73.bin")

BASE = 0x10000000
APP_LIMIT = 0x34B000
SDFS_LIMIT = 0x10000
TEMP_LIMIT = 3670016
CODE_MAX_LEN = APP_LIMIT
BOARD = "jx402_01_3089c"
HDR_SIZE = 0x400
TBL_OFF = 0x200
ENTRY = 32
LZMA_IN_MAX = 1572864
LZMA_OUT_MAX = 2097152
SP_MIN, SP_MAX = 0x2FF00000, 0x30000000

OUTER_PARTS = {"TEMP.bin": {"file_id": 254, "storage_id": 2, "type": "TEMP",
                            "name": "fw0_temp"}}
INNER_PARTS = {"app.bin": {"file_id": 4, "storage_id": 0, "type": "SYSTEM",
                           "name": "fw0_sys", "limit": APP_LIMIT},
               "sdfs.bin": {"file_id": 5, "storage_id": 0, "type": "DATA",
                            "name": "fw0_sdfs", "limit": SDFS_LIMIT}}


class Failure(Exception):
    def __init__(self, check: str, message: str):
        super().__init__(message)
        self.check = check
        self.message = message


class Verifier:
    def __init__(self) -> None:
        self.checks: list[dict] = []
        self.failures: list[dict] = []

    def require(self, ok: bool, check: str, detail: str) -> None:
        self.checks.append({"check": check, "ok": bool(ok), "detail": detail})
        if not ok:
            self.failures.append({"check": check, "message": detail})
            raise Failure(check, detail)

    def note(self, check: str, detail: str) -> None:
        self.checks.append({"check": check, "ok": True, "detail": detail})


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def u16(data: bytes, off: int) -> int:
    return struct.unpack_from("<H", data, off)[0]


def u32(data: bytes, off: int) -> int:
    return struct.unpack_from("<I", data, off)[0]


def crc32(data) -> int:
    return zlib.crc32(data) & 0xFFFFFFFF


def sum32(data: bytes) -> int:
    if len(data) % 4:
        raise Failure("app checksum", f"unaligned checksum region ({len(data)} bytes)")
    return sum(struct.unpack(f"<{len(data) // 4}I", data)) & 0xFFFFFFFF


def parse_aota(v: Verifier, data: bytes, label: str, allow_trailer: bool) -> dict:
    v.require(len(data) >= HDR_SIZE and data[:4] == b"AOTA",
              f"{label} magic", f"{len(data)} bytes, magic {data[:4]!r}")
    v.require(u16(data, 0x0A) == HDR_SIZE, f"{label} header size",
              f"header_size {u16(data, 0x0A):#x} (receiver requires {HDR_SIZE:#x})")
    v.require(crc32(data[8:HDR_SIZE]) == u32(data, 4), f"{label} header CRC",
              "crc32(header[8:0x400]) matches header+0x04")
    count = u16(data, 0x0C)
    v.require(1 <= count <= 16, f"{label} entry count",
              f"file_cnt {count} (receiver accepts 1..16)")
    v.require(u16(data, 0x10) == TBL_OFF, f"{label} directory offset",
              f"dir_offset {u16(data, 0x10):#x}")
    start = u16(data, 0x12)
    end = u32(data, 0x14)
    v.require(start == HDR_SIZE, f"{label} data offset",
              f"data_offset {start:#x} (expected {HDR_SIZE:#x})")
    v.require(HDR_SIZE <= start <= end <= len(data), f"{label} data bounds",
              f"data region {start:#x}..{end:#x} inside {len(data):#x}")
    v.require(crc32(data[start:end]) == u32(data, 0x18), f"{label} data CRC",
              f"crc32({start:#x}..{end:#x}) == header+0x18")
    board = data[0x60:0x70].split(b"\0")[0].decode("ascii", "replace")
    v.require(board == BOARD, f"{label} board name", f"board {board!r} == {BOARD!r}")

    entries, consumed = [], []
    for i in range(count):
        raw = data[TBL_OFF + i * ENTRY:TBL_OFF + (i + 1) * ENTRY]
        name = raw[:12].split(b"\0")[0].decode("ascii", "replace")
        off, size, flags, checksum = struct.unpack_from("<4I", raw, 16)
        v.require(bool(name) and name.isprintable(), f"{label} entry {i} name",
                  f"entry {i} name {name!r}")
        v.require(flags == 0, f"{label} entry {name} flags", f"flags {flags:#x}")
        v.require(start <= off < off + size <= end, f"{label} entry {name} bounds",
                  f"{off:#x}+{size:#x} inside data region")
        consumed.append((off, off + size))
        v.require(crc32(data[off:off + size]) == checksum, f"{label} entry {name} CRC",
                  f"crc32 of {size:#x} stored bytes matches table")
        entries.append({"name": name, "offset": off, "size": size,
                        "checksum": checksum, "stored": data[off:off + size]})
    ordered = sorted(consumed)
    for prev, current in zip(ordered, ordered[1:]):
        v.require(prev[1] <= current[0], f"{label} entry overlap",
                  f"{prev[1]:#x} <= {current[0]:#x}")
    trailer = data[end:]
    if allow_trailer:
        v.require(len(trailer) > 0, f"{label} trailer present", f"{len(trailer)} bytes after data")
    else:
        v.require(not trailer, f"{label} no trailer", "nested image ends at the data region")
    return {"header": data[:HDR_SIZE], "start": start, "end": end,
            "entries": entries, "trailer": trailer,
            "xml": next((e["stored"] for e in entries if e["name"] == "ota.xml"), None),
            "files": {e["name"]: e["stored"] for e in entries if e["name"] != "ota.xml"}}


def parse_manifest(v: Verifier, xml: bytes, label: str, files: dict,
                   expected: dict, version_reference: bytes | None) -> dict:
    v.require(xml is not None, f"{label} manifest present", "ota.xml entry exists")
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as error:
        v.require(False, f"{label} manifest parses", f"{error}")
    v.require(root.tag == "ota_firmware", f"{label} manifest root", f"<{root.tag}>")
    nodes = root.findall("./partitions/partition")
    names = [node.findtext("file_name", "") for node in nodes]
    v.require(len(names) == len(set(names)), f"{label} manifest unique names", str(names))
    v.require(set(names) == set(files), f"{label} manifest file set",
              f"declared {sorted(names)} == entries {sorted(files)}")
    declared = int(root.findtext("./partitions/partitionsNum", "0"), 0)
    v.require(declared == len(nodes), f"{label} partitionsNum",
              f"{declared} == {len(nodes)} partition nodes")

    if version_reference is not None:
        reference = ET.fromstring(version_reference)
        for tag in ("version_code", "version_res", "version_name", "board_name"):
            want = reference.findtext(f"./firmware_version/{tag}")
            got = root.findtext(f"./firmware_version/{tag}")
            v.require(got == want, f"{label} manifest {tag}",
                      f"{got!r} == stock {want!r}")

    for node in nodes:
        name = node.findtext("file_name", "")
        payload = files[name]
        want = expected[name]
        for tag, value in (("file_size", len(payload)), ("orig_size", len(payload)),
                           ("checksum", crc32(payload))):
            got = int(node.findtext(tag, ""), 0)
            v.require(got == value, f"{label} manifest {name} {tag}",
                      f"{got:#x} == {value:#x}")
        for tag in ("file_id", "storage_id"):
            got = int(node.findtext(tag, ""), 0)
            v.require(got == want[tag], f"{label} manifest {name} {tag}",
                      f"{got} == {want[tag]}")
        v.require(node.findtext("type") == want["type"],
                  f"{label} manifest {name} type", node.findtext("type"))
        v.require(node.findtext("name") == want["name"],
                  f"{label} manifest {name} name", node.findtext("name"))
        if "limit" in want:
            v.require(len(payload) <= want["limit"], f"{label} {name} size limit",
                      f"{len(payload):#x} <= {want['limit']:#x}")
    return {"names": names, "nodes": {n.findtext("file_name", ""): n for n in nodes}}


def unpack_chunks(v: Verifier, data: bytes, label: str) -> bytes:
    out = bytearray()
    pos = 0
    chunks = 0
    while pos < len(data):
        v.require(pos + 16 <= len(data), f"{label} chunk header",
                  f"chunk at {pos:#x} has a 16-byte header")
        magic, header, packed, raw = struct.unpack_from("<4I", data, pos)
        v.require(magic == 0x414D5A4C and header == 16, f"{label} chunk magic",
                  f"chunk {chunks} at {pos:#x}: magic {magic:#010x}, header {header}")
        v.require(0 < packed + header <= LZMA_IN_MAX, f"{label} chunk input limit",
                  f"chunk {chunks}: {packed:#x}+{header:#x} <= {LZMA_IN_MAX:#x}")
        v.require(0 < raw <= LZMA_OUT_MAX, f"{label} chunk output limit",
                  f"chunk {chunks}: {raw:#x} <= {LZMA_OUT_MAX:#x}")
        v.require(pos + header + packed <= len(data), f"{label} chunk bounds",
                  f"chunk {chunks} ends at {pos + header + packed:#x}")
        decoder = lzma.LZMADecompressor(format=lzma.FORMAT_XZ, memlimit=64 * 1024 * 1024)
        try:
            block = decoder.decompress(data[pos + header:pos + header + packed],
                                       max_length=raw + 1)
        except lzma.LZMAError as error:
            v.require(False, f"{label} chunk {chunks} decodes", f"{error}")
        v.require(decoder.eof and not decoder.unused_data and len(block) == raw,
                  f"{label} chunk {chunks} exact", f"{len(block):#x} == {raw:#x}")
        out += block
        pos += header + packed
        chunks += 1
    v.require(chunks > 0, f"{label} chunk count", f"{chunks} chunks")
    return bytes(out)


def check_app(v: Verifier, app: bytes, label: str) -> dict:
    size = len(app)
    v.require(size <= APP_LIMIT, f"{label} partition limit",
              f"{size:#x} <= {APP_LIMIT:#x}")
    v.require(size >= 0x208, f"{label} minimum size", f"{size:#x} bytes")
    v.require(app[:8] == b"ACTHHTCA", f"{label} ACTH magic", f"{app[:8]!r}")
    header_size = u16(app, 0x24)
    v.require(header_size == 0x200, f"{label} ih_hdr_size", f"{header_size:#x} == 0x200")
    v.require(u32(app, 0x2C) & 0x04 == 0, f"{label} not encrypted",
              f"ih_flags {u32(app, 0x2C):#x}")
    img_size = u32(app, 0x18)
    v.require(img_size > 0 and img_size % 4 == 0, f"{label} ih_img_size aligned",
              f"{img_size:#x}")
    v.require(img_size <= CODE_MAX_LEN, f"{label} ih_img_size within code_max_len",
              f"{img_size:#x} <= {CODE_MAX_LEN:#x}")
    v.require(header_size + img_size <= size, f"{label} payload inside the app",
              f"{header_size:#x}+{img_size:#x} <= {size:#x}")
    v.require(sum32(app[:header_size]) == 0xFFFFFFFF, f"{label} header fix-up",
              f"sum32(header[:{header_size:#x}]) == 0xFFFFFFFF")
    data = app[header_size:header_size + img_size]
    chksum = u32(app, 0x1C)
    total = (sum32(data) + chksum) & 0xFFFFFFFF
    v.require(total == 0xFFFFFFFF, f"{label} data checksum",
              f"sum32(data)+ih_img_chksum = {total:#010x} (want 0xffffffff)")

    sp = u32(app, header_size)
    reset = u32(app, header_size + 4)
    v.require(SP_MIN <= sp < SP_MAX, f"{label} vector SP",
              f"SP {sp:#010x} in {SP_MIN:#x}..{SP_MAX:#x}")
    v.require(reset & 1 == 1, f"{label} reset vector Thumb", f"{reset:#010x}")
    target = reset & ~1
    v.require(BASE <= target < BASE + header_size + img_size,
              f"{label} reset vector inside the app",
              f"{reset:#010x} -> {target:#010x} in {BASE:#x}..{BASE + header_size + img_size:#x}")
    v.require(u32(app, 0x08) == reset and u32(app, 0x14) == reset,
              f"{label} entry fields", f"ih_load_addr/ih_entry == reset vector {reset:#010x}")
    return {"bytes": size, "img_size": img_size, "ih_img_chksum": chksum,
            "header_size": header_size, "sp": sp, "reset": reset,
            "sha256": sha256(app)}


def diff_ranges(a: bytes, b: bytes, base: int) -> list[list[int]]:
    """Every [start,end) address range where the two apps differ."""
    limit = min(len(a), len(b))
    runs: list[list[int]] = []
    block = 4096
    i = 0
    while i < limit:
        step = min(block, limit - i)
        if a[i:i + step] == b[i:i + step]:
            i += step
            continue
        for j in range(i, i + step):
            if a[j] != b[j]:
                if runs and runs[-1][1] == base + j:
                    runs[-1][1] = base + j + 1
                else:
                    runs.append([base + j, base + j + 1])
        i += step
    longer = max(len(a), len(b))
    if longer > limit:
        runs.append([base + limit, base + longer])
    return runs


def uncovered(run: list[int], allowed: list[list[int]]) -> list[list[int]]:
    gaps, cursor = [], run[0]
    for low, high in allowed:
        if high <= cursor:
            continue
        if low >= run[1]:
            break
        if low > cursor:
            gaps.append([cursor, min(low, run[1])])
        cursor = max(cursor, high)
        if cursor >= run[1]:
            return gaps
    if cursor < run[1]:
        gaps.append([cursor, run[1]])
    return gaps


def verify(path: Path, stock_image: Path, stock_app: Path | None,
           allow_path: Path | None) -> dict:
    v = Verifier()
    result: dict = {"package": str(path), "ok": False}
    try:
        image = path.read_bytes()
        result.update(sha256=sha256(image), bytes=len(image))
        stock = stock_image.read_bytes()
        stock_outer = parse_aota(v, stock, "stock", allow_trailer=True)
        stock_temp = stock_outer["files"]["TEMP.bin"]
        stock_inner = parse_aota(v, unpack_chunks(v, stock_temp, "stock TEMP"), "stock TEMP",
                                 allow_trailer=False)
        stock_sdfs = stock_inner["files"]["sdfs.bin"]
        stock_trailer = stock_outer["trailer"]
        result["stock"] = {"image": str(stock_image), "sha256": sha256(stock),
                           "trailer_sha256": sha256(stock_trailer),
                           "sdfs_sha256": sha256(stock_sdfs)}

        outer = parse_aota(v, image, "outer", allow_trailer=True)
        names = [e["name"] for e in outer["entries"]]
        v.require(names == ["ota.xml", "TEMP.bin"], "outer entries",
                  f"{names} == ['ota.xml', 'TEMP.bin']")
        outer_manifest = parse_manifest(v, outer["xml"], "outer", outer["files"],
                                        OUTER_PARTS, stock_outer["xml"])
        temp = outer["files"]["TEMP.bin"]
        v.require(len(temp) <= TEMP_LIMIT, "TEMP size limit",
                  f"{len(temp)} <= {TEMP_LIMIT} (measured watch partition)")
        v.require(outer["trailer"] == stock_trailer, "AGPS trailer",
                  f"{len(outer['trailer'])} bytes, sha256 {sha256(outer['trailer'])} "
                  f"== stock {sha256(stock_trailer)}")

        inner_bytes = unpack_chunks(v, temp, "TEMP")
        inner = parse_aota(v, inner_bytes, "inner", allow_trailer=False)
        inner_names = [e["name"] for e in inner["entries"]]
        v.require(inner_names == ["ota.xml", "app.bin", "sdfs.bin"], "inner entries",
                  f"{inner_names} == ['ota.xml', 'app.bin', 'sdfs.bin']")
        parse_manifest(v, inner["xml"], "inner", inner["files"], INNER_PARTS,
                       stock_inner["xml"])
        sdfs = inner["files"]["sdfs.bin"]
        app = inner["files"]["app.bin"]
        v.require(sdfs == stock_sdfs, "sdfs identity",
                  f"sha256 {sha256(sdfs)} == stock {sha256(stock_sdfs)}")
        app_report = check_app(v, app, "app")

        result["package_report"] = {
            "outer": {"sha256": sha256(image), "bytes": len(image),
                      "ota_xml_bytes": len(outer["xml"]),
                      "temp_offset": outer["entries"][1]["offset"],
                      "temp_bytes": len(temp), "temp_sha256": sha256(temp),
                      "trailer_bytes": len(outer["trailer"]),
                      "trailer_sha256": sha256(outer["trailer"])},
            "inner": {"bytes": len(inner_bytes), "sha256": sha256(inner_bytes),
                      "ota_xml_bytes": len(inner["xml"])},
            "app": app_report,
            "sdfs": {"bytes": len(sdfs), "sha256": sha256(sdfs)},
            "manifest": {"outer": sorted(outer_manifest["names"]),
                         "inner": sorted(inner_manifest_names(inner))},
        }

        if stock_app is not None:
            reference = stock_app.read_bytes()
            runs = diff_ranges(app, reference, BASE)
            allowed: list[list[int]] = []
            if allow_path is not None:
                document = json.loads(allow_path.read_text(encoding="utf-8"))
                allowed = document.get("ranges", document) if isinstance(document, dict) else document
                allowed = [[int(low), int(high)] for low, high in allowed]
            outside: list[list[int]] = []
            for run in runs:
                outside.extend(uncovered(run, allowed))
            common = min(len(app), len(reference))
            differing = sum(1 for i in range(common) if app[i] != reference[i])
            differing += abs(len(app) - len(reference))
            result["diff"] = {
                "stock_app": str(stock_app), "stock_app_sha256": sha256(reference),
                "ranges": runs, "differing_bytes": differing,
                "allowed_ranges": allowed, "outside": outside,
            }
            if allow_path is None:
                v.require(not runs, "diff gate",
                          f"{len(runs)} differing byte ranges but no --allow-diff-from "
                          "list was given (zero differences required)")
            else:
                v.require(not outside, "diff gate",
                          "every difference is inside the allowed ranges"
                          if not outside else
                          "differences outside the allowed ranges: "
                          + ", ".join(f"[{a:#x},{b:#x})" for a, b in outside))
        else:
            v.note("diff gate", "skipped (no --stock-app)")

        result["ok"] = not v.failures
    except Failure as failure:
        result["ok"] = False
        result["failed_check"] = failure.check
    except (OSError, ValueError, KeyError, struct.error, IndexError) as error:
        result["ok"] = False
        result["failed_check"] = "unexpected"
        v.failures.append({"check": "unexpected", "message": f"{type(error).__name__}: {error}"})
    result["checks"] = v.checks
    result["failures"] = v.failures
    result["checks_passed"] = sum(1 for check in v.checks if check["ok"])
    return result


def inner_manifest_names(inner: dict) -> list[str]:
    root = ET.fromstring(inner["xml"])
    return [node.findtext("file_name", "") for node in root.findall("./partitions/partition")]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("package", type=Path)
    parser.add_argument("--stock-app", type=Path,
                        help="stock app.bin for the diff gate (default: no diff gate)")
    parser.add_argument("--allow-diff-from", type=Path,
                        help="JSON list of allowed [start,end) app address ranges")
    parser.add_argument("--stock-image", type=Path, default=DEFAULT_STOCK_IMAGE,
                        help="stock 1.0.0.73 AOTA (trailer, sdfs and manifest reference)")
    parser.add_argument("--report", type=Path, help="also write the JSON report here")
    args = parser.parse_args()

    if args.allow_diff_from is not None and args.stock_app is None:
        parser.error("--allow-diff-from needs --stock-app")
    result = verify(args.package.resolve(), args.stock_image.resolve(),
                    args.stock_app.resolve() if args.stock_app else None,
                    args.allow_diff_from.resolve() if args.allow_diff_from else None)
    text = json.dumps(result, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text, encoding="utf-8")
    sys.stdout.write(text)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
