import argparse
import socket
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main():
    p = argparse.ArgumentParser(description="Run the emulator and log every hit of the given code addresses")
    p.add_argument("--app")
    p.add_argument("--output", required=True)
    p.add_argument("--script")
    p.add_argument("--seconds", type=float, default=25)
    p.add_argument("--break", dest="breaks", action="append", default=[],
                   help="ADDR or ADDR:EXPR1,EXPR2 (gdb expressions printed on hit, default r0-r3,lr)")
    p.add_argument("--max-hits", type=int, default=50, help="disable a breakpoint after this many hits")
    a = p.parse_args()
    port = free_port()
    emu = [sys.executable, str(HERE / "emu.py"), "--output", a.output, "--seconds", str(a.seconds),
           "--gdb-port", str(port)]
    if a.app:
        emu += ["--app", a.app]
    if a.script:
        emu += ["--script", a.script]
    proc = subprocess.Popen(emu)
    cmds = ["set pagination off", "set confirm off", "set remotetimeout 10"]
    for i, spec in enumerate(a.breaks, 1):
        addr, _, exprs = spec.partition(":")
        exprs = exprs.split(",") if exprs else ["$r0", "$r1", "$r2", "$r3", "$lr"]
        fmt = "HIT " + addr + " " + " ".join(f"{e}=%#x" for e in exprs) + "\\n"
        cmds += [f"break *{addr}", "commands", "silent", f'printf "{fmt}", {", ".join(exprs)}',
                 f"if $bpnum_hits_{i} >= {a.max_hits}", f"disable {i}", "end",
                 f"set $bpnum_hits_{i} = $bpnum_hits_{i} + 1", "continue", "end"]
        cmds.insert(3, f"set $bpnum_hits_{i} = 0")
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    cmdfile = Path(a.output + ".gdb")
    cmdfile.write_text("\n".join(cmds + [f"target remote 127.0.0.1:{port}", "continue"]) + "\n")
    gdb = subprocess.run(["arm-none-eabi-gdb", "-batch", "-nx", "-x", str(cmdfile)], capture_output=True, text=True)
    proc.wait()
    for line in gdb.stdout.splitlines():
        if line.startswith("HIT "):
            print(line)
    cmdfile.unlink()


if __name__ == "__main__":
    main()
