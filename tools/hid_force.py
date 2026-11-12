import argparse
import socket
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent

GDB = r"""
set pagination off
set confirm off
set $calls = 0
break *0x1015ee8c
commands
silent
set $calls = $calls + 1
if $calls == {camera_call}
  printf "FORCE camera param on call %d (was %#x)\n", $calls, $r0
  set $r0 = 2
end
printf "HIDKEY param=%#x\n", $r0
continue
end
break *0x1015eeb8
commands
silent
set $r0 = 0x77
continue
end
break *0x1015eec0
commands
silent
set $r0 = 0x38000000
continue
end
break *0x1015eec8
commands
silent
set $pc = 0x1015eeca
continue
end
break *0x1015edac
commands
silent
printf "REPORT conn=%#x type=%d len=%d bytes=%02x %02x\n", $r0, $r1, $r3, *(unsigned char*)$r2, *(unsigned char*)($r2+1)
set $r0 = 0
set $pc = $lr
continue
end
break *0x1015eed2
commands
silent
set $pc = 0x1015eee4
continue
end
set $presses = 0
break *{hid_press}
commands
silent
set $presses = $presses + 1
if {redirect_cond}
  printf "REDIRECT press %d param=%#x to after-connect path\n", $presses, $r1
  set $pc = {after_connect}
end
continue
end
target remote 127.0.0.1:{port}
continue
"""


def main():
    p = argparse.ArgumentParser(description="Emulator run that fakes a connected phone HID link and logs every HID report")
    p.add_argument("--app", required=True)
    p.add_argument("--script", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--seconds", type=float, default=50)
    p.add_argument("--camera-call", type=int, default=0, help="replace the Nth HID request with the camera shutter parameter 2")
    p.add_argument("--after-connect", default="", help="comma list of press numbers to run through hid_press_after_connect")
    a = p.parse_args()
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    emu = subprocess.Popen([sys.executable, str(HERE / "emu.py"), "--app", a.app, "--script", a.script,
                            "--output", a.output, "--seconds", str(a.seconds), "--gdb-port", str(port)])
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    cmd = Path(a.output + ".gdb")
    syms = {}
    for line in subprocess.run(["arm-none-eabi-nm", str(HERE.parent / "patch/build/cave.elf")], capture_output=True, text=True).stdout.splitlines():
        parts = line.split()
        if len(parts) == 3:
            syms[parts[2]] = parts[0]
    picks = [n for n in a.after_connect.split(",") if n]
    cond = " || ".join(f"$presses == {n}" for n in picks) or "0"
    script = (GDB.replace("{port}", str(port)).replace("{camera_call}", str(a.camera_call))
              .replace("{hid_press}", "0x" + syms["hid_press"]).replace("{after_connect}", "0x" + syms["hid_press_after_connect"])
              .replace("{redirect_cond}", cond))
    cmd.write_text(script)
    out = subprocess.run(["arm-none-eabi-gdb", "-batch", "-nx", "-x", str(cmd)], capture_output=True, text=True)
    emu.wait()
    cmd.unlink()
    for line in out.stdout.splitlines():
        if line.startswith(("HIDKEY", "REPORT", "FORCE", "REDIRECT")):
            print(line)


if __name__ == "__main__":
    main()
