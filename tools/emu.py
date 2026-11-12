import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image

CMF = Path(__file__).resolve().parents[2] / "cmf-watch-utils"
RUNTIME = CMF / "runtime"
FIXTURES = CMF / "fixtures"
APP_OFFSET, APP_SIZE = 0x24000, 0x34B000


def stage(output, app, base_nor=None):
    nor = bytearray(Path(base_nor or FIXTURES / "nor.bin").read_bytes())
    if app:
        payload = Path(app).read_bytes()
        assert 0 < len(payload) <= APP_SIZE
        nor[APP_OFFSET:APP_OFFSET + APP_SIZE] = payload.ljust(APP_SIZE, b"\xff")
    else:
        part = bytes(nor[APP_OFFSET:APP_OFFSET + APP_SIZE])
        assert part[:8] == b"ACTHHTCA", "no valid app in NOR"
        end = len(part.rstrip(b"\xff"))
        payload = part[:(end + 0x1FF) & ~0x1FF]
    (output / "nor.bin").write_bytes(nor)
    (output / "app.bin").write_bytes(payload)
    shutil.copyfile(FIXTURES / "nand-id.bin", output / "nand-id.bin")
    (output / "input.txt").touch()


def launch(output, gdb_port=None, awake=True, hci_port=None, qmp_port=None, allow_reboot=False, ota_snapshot=False):
    env = {k: v for k, v in os.environ.items() if not k.startswith("QEMU_WP2_")}
    env.update({
        "QEMU_WP2_NOR": str(output / "nor.bin"),
        "QEMU_WP2_NAND": str(FIXTURES / "nand-defaults.bin"),
        "QEMU_WP2_FRAME": str(output / "frame.ppm"),
        "QEMU_WP2_INPUT": str(output / "input.txt"),
        "QEMU_WP2_UNPLUGGED": "1",
        "QEMU_WP2_HOST_RTC": "1",
        "QEMU_WP2_EXPLORATORY": "0",
        "QEMU_WP2_LIVE_FRAME": "1",
        "QEMU_WP2_LIVE_SENSORS": "1",
        "QEMU_WP2_LIVE_HEALTH": "1",
    })
    if awake:
        env["QEMU_WP2_STOCK_AWAKE"] = "1"
    if ota_snapshot:
        env["QEMU_WP2_OTA_NAND_SNAPSHOT"] = str(output / "nand-staged.bin")
    argv = [str(RUNTIME / "qemu-system-arm"), "-M", "ats3089c-wp2", "-bios", str(RUNTIME / "compat.bin"),
            "-display", "none", "-monitor", "none", "-serial", f"file:{output / 'uart0.log'}",
            "-serial", "null", "-serial", "null", "-icount", "shift=3,align=off",
            "-kernel", str(output / "app.bin")]
    if not allow_reboot:
        argv.append("-no-reboot")
    if hci_port:
        argv += ["-chardev", f"socket,id=wp2-hci,host=127.0.0.1,port={hci_port}"]
    if qmp_port:
        argv += ["-qmp", f"tcp:127.0.0.1:{qmp_port},server=on,wait=off"]
    if gdb_port:
        argv += ["-gdb", f"tcp:127.0.0.1:{gdb_port}"]
    log = (output / "qemu.log").open("wb")
    return subprocess.Popen(argv, env=env, stdout=log, stderr=log)


def snapshot(output, name):
    src = output / "frame.ppm"
    if src.is_file():
        Image.open(src).save(output / f"{name}.png")
        return True
    return False


def main():
    p = argparse.ArgumentParser(description="Scripted Watch Pro 2 emulator run")
    p.add_argument("--app")
    p.add_argument("--output", required=True)
    p.add_argument("--script", help="JSON list of [seconds, 'event'|'shot:NAME'|'wait']")
    p.add_argument("--seconds", type=float, default=20)
    p.add_argument("--gdb-port", type=int)
    p.add_argument("--no-awake", action="store_true")
    p.add_argument("--nor", help="base virtual NOR instead of the stock fixture (e.g. a paired NOR)")
    p.add_argument("--hci-port", type=int, help="connect the guest Bluetooth controller to an H4 socket (netsim)")
    p.add_argument("--qmp-port", type=int)
    p.add_argument("--allow-reboot", action="store_true")
    p.add_argument("--ota-snapshot", action="store_true", help="save virtual NAND when the guest reboots for OTA")
    a = p.parse_args()
    output = Path(a.output)
    output.mkdir(parents=True, exist_ok=False)
    stage(output, a.app, a.nor)
    steps = json.loads(Path(a.script).read_text()) if a.script else []
    proc = launch(output, a.gdb_port, not a.no_awake, a.hci_port, a.qmp_port, a.allow_reboot, a.ota_snapshot)
    start = time.monotonic()
    events = (output / "input.txt").open("a")
    try:
        for at, action in sorted(steps, key=lambda s: s[0]):
            while time.monotonic() - start < at:
                if proc.poll() is not None:
                    raise SystemExit(f"QEMU exited early ({proc.returncode}); see {output}/qemu.log")
                time.sleep(0.05)
            if action.startswith("shot:"):
                snapshot(output, action[5:])
            else:
                events.write(action + "\n")
                events.flush()
        while time.monotonic() - start < a.seconds and proc.poll() is None:
            time.sleep(0.1)
        snapshot(output, "final")
    finally:
        if proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=5)
    uart = (output / "uart0.log").read_text(errors="replace")
    print(json.dumps({"alive": proc.returncode in (None, -15, 0), "boots": uart.count("*** Booting Zephyr OS"),
                      "fatal": "ZEPHYR FATAL ERROR" in uart, "output": str(output)}))


if __name__ == "__main__":
    main()
