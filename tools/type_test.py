"""Emulator check for the flick typing screen: opens the remote, enters typing with a right-edge
swipe, types every character on both pages, and compares the characters the watch asked to send.

    python3 tools/type_test.py patch/build/app_type.bin runs/flick1
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

# Same tables as patch/remote_view.c: left flick, tap, right flick.
LETTER_FLICKS = [
    ("B", "A", "C"), ("D", "E", "F"), ("G", "H", "I"),
    ("J", "L", "K"), ("M", "N", "O"), ("P", "R", "Q"),
    ("S", "T", "U"), ("V", "W", "X"), ("Z", "Y", "."),
]
NUMBER_FLICKS = [
    (".", "1", ","), ("?", "2", "!"), ("'", "3", '"'),
    (":", "4", ";"), ("-", "5", "_"), ("/", "6", "\\"),
    ("(", "7", ")"), ("@", "8", "#"), ("+", "9", "="),
    (" ", "0", "%"),
]
GRID = [(140 + i % 3 * 93, 144 + i // 3 * 90) for i in range(9)]
TOGGLE = (112, 396)
MIDDLE = (221, 396)
DELETE = (339, 396)
FLICK = 40


class Script:
    def __init__(self, steps, at):
        self.steps, self.at = steps, at

    def add(self, action, dt=0.0):
        self.steps.append([round(self.at, 2), action])
        self.at += dt

    def drag(self, a, b, hold=0.0, shot=None):
        (x0, y0), (x1, y1) = a, b
        for i in range(6):
            x, y = x0 + (x1 - x0) * i // 6, y0 + (y1 - y0) * i // 6
            self.add(f"t 1 {x} {y}", 0.08)
        self.add(f"t 1 {x1} {y1}", 0.2 + hold)
        if shot:
            self.add(f"shot:{shot}", 0.2)
        self.add(f"t 0 {x1} {y1}", 0.9)

    def tap(self, p):
        self.add(f"t 1 {p[0]} {p[1]}", 0.35)
        self.add(f"t 0 {p[0]} {p[1]}", 0.9)


def build():
    opening = [s for s in json.loads((ROOT / "sim/swipes.json").read_text()) if s[0] < 32]
    s = Script(opening, 34.0)
    expected = []
    s.add("shot:00_remote", 0.3)
    s.drag((440, 233), (150, 233))
    s.add("shot:01_letters", 0.8)

    for i, (left, main, right) in enumerate(LETTER_FLICKS):
        s.tap(GRID[i])
        expected.append(main.lower())
        s.drag(GRID[i], (GRID[i][0] - FLICK, GRID[i][1]), shot="02_flick_left" if i == 0 else None)
        expected.append(left.lower())
        s.drag(GRID[i], (GRID[i][0] + FLICK, GRID[i][1]))
        expected.append(right.lower())

    s.tap(MIDDLE)
    expected.append(" ")
    s.tap(TOGGLE)
    s.add("shot:03_numbers", 0.5)

    for i, (left, main, right) in enumerate(NUMBER_FLICKS[:9]):
        s.tap(GRID[i])
        expected.append(main.lower())
        s.drag(GRID[i], (GRID[i][0] - FLICK, GRID[i][1]))
        expected.append(left.lower())
        s.drag(GRID[i], (GRID[i][0] + FLICK, GRID[i][1]))
        expected.append(right.lower())

    s.tap(MIDDLE)
    expected.append("0")
    s.drag(MIDDLE, (MIDDLE[0] - FLICK, MIDDLE[1]))
    expected.append(" ")
    s.drag(MIDDLE, (MIDDLE[0] + FLICK, MIDDLE[1]))
    expected.append("%")

    s.tap(DELETE)
    expected.append("\b")
    s.tap(TOGGLE)
    s.add("shot:04_letters_again", 0.5)

    # Cancels: nothing may be sent.
    s.drag(GRID[0], (GRID[0][0], GRID[0][1] - 70))
    s.drag(GRID[0], (GRID[0][0] + 150, GRID[0][1]))
    s.drag(GRID[0], (GRID[0][0] + 40, GRID[0][1] + 40))
    s.drag(GRID[0], (10, 10))
    s.drag(MIDDLE, (MIDDLE[0], MIDDLE[1] - 56))

    # Hold delete: repeats, then stops on release. The tap marker after it proves no repeat
    # escaped the release.
    hold_at = len(expected)
    s.add(f"t 1 {DELETE[0]} {DELETE[1]}", 2.0)
    s.add(f"t 0 {DELETE[0]} {DELETE[1]}", 1.5)
    s.tap(GRID[0])
    expected.append("a")

    # Hold delete, then drag away: the repeat must stop and the release must not delete.
    s.add(f"t 1 {DELETE[0]} {DELETE[1]}", 0.3)
    s.drag(DELETE, (DELETE[0] + 40, DELETE[1]), hold=0.8)

    s.add("r 80", 0.5)
    s.add("r -80", 0.5)
    s.add("shot:05_typed", 0.3)
    s.add("c 1", 0.3)
    s.add("c 0", 1.0)
    s.add("shot:06_back_to_remote", 0.3)
    s.tap((233, 300))
    s.add("wait", 1.5)
    s.add("shot:07_remote_tap", 0.3)
    return s, expected, hold_at


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("app")
    parser.add_argument("output", type=Path)
    parser.add_argument("--connected", action="store_true", help="fake a connected HID link and verify press/release bytes")
    parser.add_argument("--reconnect", action="store_true", help="also drop the first character through the after-connect path")
    parser.add_argument("--verify-only", action="store_true", help="check an existing run without starting the emulator")
    args = parser.parse_args()
    if args.reconnect and not args.connected:
        parser.error("--reconnect requires --connected")
    app, out = args.app, args.output
    s, expected, hold_at = build()
    table_chars = {c.lower() for page in (LETTER_FLICKS, NUMBER_FLICKS) for row in page for c in row if c}
    tested = {c.lower() for c in expected if c != "\b"}
    assert table_chars == tested, f"untested table characters: {table_chars - tested}"
    script = out.with_suffix(".script.json")
    runner = "hid_force.py" if args.connected else "emu.py"
    command = ["uv", "run", "--project", str(ROOT.parent / "cmf-watch-utils"), "python", str(HERE / runner),
               "--app", app, "--output", str(out), "--script", str(script), "--seconds", str(s.at + 2)]
    if args.reconnect:
        command += ["--after-connect", "2"]  # First call primes the link; second types A.
    if args.verify_only:
        report_log = (out / "test.log").read_text()
    else:
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text(json.dumps(s.steps))
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        report_log = result.stdout + result.stderr
        (out / "test.log").write_text(report_log)
    uart = (out / "uart0.log").read_text(errors="replace")
    typed = [chr(int(h, 16)) for h in re.findall(r"faceclaw-remote: text ([0-9a-f]+)[ \t\r]*$", uart, re.MULTILINE)]
    modes = re.findall(r"faceclaw-remote: mode (\d)", uart)
    keys = re.findall(r"faceclaw-remote: key (\d+)", uart)

    repeats = 0
    while hold_at + repeats < len(typed) and typed[hold_at + repeats] == "\b":
        repeats += 1
    ok = typed[:hold_at] == expected[:hold_at]
    ok &= 3 <= repeats <= 12
    ok &= typed[hold_at + repeats:] == expected[hold_at:]
    ok &= modes == ["1", "0"] and keys == ["3"] and "ZEPHYR FATAL ERROR" not in uart
    if args.connected:
        reports = [(int(conn, 16), int(kind), int(length), int(rid, 16), int(bits, 16))
                   for conn, kind, length, rid, bits in re.findall(
                       r"REPORT conn=(0x[0-9a-f]+) type=(\d+) len=(\d+) bytes=([0-9a-f]+) ([0-9a-f]+)", report_log)]
        delivered = typed[1:] if args.reconnect else typed
        wanted = []
        for bits in [0x80 | ord(ch) for ch in delivered] + [0x08]:
            wanted.extend([(0x77, 1, 2, 2, bits), (0x77, 1, 2, 2, 0)])
        reports_ok = reports == wanted
        print("HID reports", "PASS" if reports_ok else "FAIL", f"({len(reports)} reports)")
        if not reports_ok:
            print("expected reports", wanted)
            print("actual reports  ", reports)
        if args.reconnect:
            reports_ok &= f"text {ord(expected[0]) & 0x7f:x} dropped, link was reconnecting" in uart
        ok &= reports_ok
    print("expected", repr("".join(expected[:hold_at]) + "<hold>" + "".join(expected[hold_at:])))
    print("typed   ", repr("".join(typed[:hold_at]) + "<hold>" + "".join(typed[hold_at:])))
    print("delete hold", repeats, "repeats (want 3..12)")
    print("modes", modes, "(want ['1', '0'])  remote keys", keys, "(want ['3'] = tap after leaving typing)")
    print("PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
