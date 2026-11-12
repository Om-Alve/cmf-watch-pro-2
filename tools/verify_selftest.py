#!/usr/bin/env python3
"""Prove tools/verify_package.py rejects broken packages and accepts the real ones.

Every corrupted variant is derived from a real package in a temporary directory;
nothing under dist/ is modified. Each corruption is made *structurally valid*
where that is the point of the case, so the verifier has to catch the semantic
problem rather than a broken container CRC:

  outer header CRC     a header byte flipped, header CRC left stale
  outer data CRC       0x18 changed and the header CRC repaired
  app ACTH fix-up      package rebuilt from an app whose 0x20 word is wrong
  app byte outside     package rebuilt from an app edited at 0x10100000 with
                       valid ACTH checksums: only the diff gate can catch it
  AGPS trailer         last trailer byte flipped
  extra partition      outer container rebuilt with a third entry

    python3 tools/verify_selftest.py
"""

from __future__ import annotations

import hashlib
import json
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERIFY = ROOT / "tools/verify_package.py"
PACKAGE = ROOT / "tools/package.py"
STOCK_APP = ROOT / "re/app_073.bin"
REMOTE_APP = ROOT / "patch/build/app_patched.bin"
TOOLKIT = ROOT.parent / "cmf-watch-utils"
STOCK_IMAGE = TOOLKIT / "dumps/binaries/firmware/JX402_V1.0.0.73.bin"
DIST = ROOT / "dist"
ALLOW = DIST / "allowed-diff-remote.json"
BASE = 0x10000000


def fwkit_aota():
    try:
        from fwkit import aota
        return aota
    except ImportError:
        sys.path.insert(0, str(TOOLKIT / "tooling/src"))
        from fwkit import aota
        return aota


def fix_header(image: bytes) -> bytes:
    out = bytearray(image)
    struct.pack_into("<I", out, 0x04, zlib.crc32(memoryview(out)[8:0x400]) & 0xFFFFFFFF)
    return bytes(out)


def build_with_app(app: bytes, out: Path, tmp: Path) -> Path:
    source = tmp / (out.stem + "-app.bin")
    source.write_bytes(app)
    subprocess.run([sys.executable, str(PACKAGE), "--app", str(source), "--out", str(out),
                    "--toolkit", str(TOOLKIT), "--stock-image", str(STOCK_IMAGE)],
                   check=True, capture_output=True)
    return out


def recheck_app(app: bytes) -> bytes:
    """Recompute the ACTH checksums the way patch/build.py does."""
    out = bytearray(app)
    size = struct.unpack_from("<I", out, 0x18)[0]

    def sum32(data):
        return sum(struct.unpack(f"<{len(data) // 4}I", data)) & 0xFFFFFFFF

    struct.pack_into("<I", out, 0x1C, 0)
    struct.pack_into("<I", out, 0x20, 0)
    struct.pack_into("<I", out, 0x1C, (0xFFFFFFFF - sum32(out[0x200:0x200 + size])) & 0xFFFFFFFF)
    struct.pack_into("<I", out, 0x20, (0xFFFFFFFF - sum32(out[:0x200])) & 0xFFFFFFFF)
    return bytes(out)


def add_extra_partition(source: Path, out: Path) -> Path:
    aota = fwkit_aota()
    image = source.read_bytes()
    header, entries = aota.parse(image)
    xml = entries[0].stored(image)
    parts = [(entry.name, entry.stored(image)) for entry in entries if entry.name != "ota.xml"]
    parts.append(("res.bin", b"\0" * 0x201))
    trailer = image[aota.agps_offset(header):]
    rebuilt = bytearray(aota.build(header, xml, parts, trailer))
    start = struct.unpack_from("<H", rebuilt, 0x12)[0]
    end = struct.unpack_from("<I", rebuilt, 0x14)[0]
    struct.pack_into("<I", rebuilt, 0x18, zlib.crc32(memoryview(rebuilt)[start:end]) & 0xFFFFFFFF)
    out.write_bytes(fix_header(rebuilt))
    return out


def run_verifier(package: Path, stock_app: Path | None = None,
                 allow: Path | None = None) -> dict:
    command = [sys.executable, str(VERIFY), str(package)]
    if stock_app is not None:
        command += ["--stock-app", str(stock_app)]
    if allow is not None:
        command += ["--allow-diff-from", str(allow)]
    process = subprocess.run(command, capture_output=True, text=True)
    try:
        report = json.loads(process.stdout)
    except json.JSONDecodeError:
        raise SystemExit(f"verifier produced no JSON for {package}:\n{process.stdout}\n{process.stderr}")
    report["exit"] = process.returncode
    return report


def main() -> int:
    for path in (VERIFY, PACKAGE, STOCK_APP, REMOTE_APP, STOCK_IMAGE,
                 DIST / "stock73-temp-only.bin", DIST / "remote-temp-only.bin", ALLOW):
        if not path.exists():
            raise SystemExit(f"missing {path}; run tools/package.py first")

    tmp = Path(tempfile.mkdtemp(prefix="wp2-verify-selftest-"))
    results = []
    try:
        stock_pkg = DIST / "stock73-temp-only.bin"
        remote_pkg = DIST / "remote-temp-only.bin"

        cases = [
            ("real: stock73-temp-only", stock_pkg, STOCK_APP, None, True, ""),
            ("real: remote-temp-only", remote_pkg, STOCK_APP, ALLOW, True, ""),
            ("real: remote without allowlist", remote_pkg, STOCK_APP, None, False,
             "diff gate"),
        ]

        # 1. a header byte flipped without repairing the header CRC
        bad = bytearray(stock_pkg.read_bytes())
        bad[0x20] ^= 0xFF
        path = tmp / "bad-header-crc.bin"
        path.write_bytes(bad)
        cases.append(("corrupt: outer header CRC", path, STOCK_APP, None, False,
                      "outer header CRC"))

        # 2. data CRC field changed, header CRC repaired -> only the data CRC is wrong
        bad = bytearray(stock_pkg.read_bytes())
        struct.pack_into("<I", bad, 0x18, struct.unpack_from("<I", bad, 0x18)[0] ^ 1)
        path = tmp / "bad-data-crc.bin"
        path.write_bytes(fix_header(bad))
        cases.append(("corrupt: outer data CRC", path, STOCK_APP, None, False,
                      "outer data CRC"))

        # 3. valid container, app whose ACTH header fix-up word is wrong
        app = bytearray(REMOTE_APP.read_bytes())
        struct.pack_into("<I", app, 0x20, struct.unpack_from("<I", app, 0x20)[0] ^ 1)
        path = build_with_app(bytes(app), tmp / "bad-acth-fixup.bin", tmp)
        cases.append(("corrupt: app ACTH header fix-up", path, STOCK_APP, ALLOW, False,
                      "app header fix-up"))

        # 4. valid container and checksums, one code byte changed at 0x10100000
        app = bytearray(REMOTE_APP.read_bytes())
        app[0x100000] ^= 0x01
        path = build_with_app(recheck_app(bytes(app)), tmp / "bad-app-byte.bin", tmp)
        cases.append(("corrupt: app byte outside allowed ranges", path, STOCK_APP, ALLOW,
                      False, "diff gate"))

        # 5. trailer changed
        bad = bytearray(stock_pkg.read_bytes())
        bad[-1] ^= 0xFF
        path = tmp / "bad-agps.bin"
        path.write_bytes(bad)
        cases.append(("corrupt: AGPS trailer", path, STOCK_APP, None, False,
                      "AGPS trailer"))

        # 6. structurally valid container with an extra outer partition
        path = add_extra_partition(stock_pkg, tmp / "bad-extra-part.bin")
        cases.append(("corrupt: extra partition", path, STOCK_APP, None, False,
                      "outer entries"))

        for label, package, stock_app, allow, expect_ok, expect_check in cases:
            report = run_verifier(package, stock_app, allow)
            passed = report["ok"] is expect_ok and report["exit"] == (0 if expect_ok else 1)
            failure = report["failures"][0] if report["failures"] else None
            detail = (failure["check"] + ": " + failure["message"]) if failure else "accepted"
            if not expect_ok:
                passed = passed and failure is not None and expect_check in detail
            results.append({
                "case": label, "package": str(package), "expected_ok": expect_ok,
                "ok": report["ok"], "exit": report["exit"], "expected_check": expect_check,
                "failure": failure, "as_expected": passed,
                "checks_passed": report.get("checks_passed", 0),
            })

        width = max(len(result["case"]) for result in results)
        print(f"{'case'.ljust(width)}  exit  result  detail")
        for result in results:
            detail = "accepted, all checks pass" if result["failure"] is None else \
                f"{result['failure']['check']}: {result['failure']['message']}"
            print(f"{result['case'].ljust(width)}  {result['exit']:4}  "
                  f"{'ok' if result['as_expected'] else 'MISMATCH'}  {detail}")
        summary = {
            "ok": all(result["as_expected"] for result in results),
            "temp_dir": str(tmp),
            "cases": results,
        }
        print(json.dumps({"ok": summary["ok"],
                          "cases": len(results),
                          "as_expected": sum(1 for result in results if result["as_expected"])},
                         indent=2))
        return 0 if summary["ok"] else 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
