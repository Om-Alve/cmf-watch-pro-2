#!/usr/bin/env bash
# Usage: sim/run_phone.sh RUN_DIR   (replays RUN_DIR/uart0.log, writes RUN_DIR/faceclaw-gestures.jsonl)
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
run=$(cd "$1" && pwd)
ring=${G2_RING_REMOTE:-$HOME/boat/oss/g2-ring-remote}
jdk=${JAVA_HOME:-/opt/homebrew/opt/openjdk@21}
out=$here/build
mkdir -p "$out"
"$jdk/bin/javac" -nowarn -source 8 -target 8 -Xlint:-options -d "$out" \
  "$ring"/src/io/github/omalve/g2ringremote/{Log,KeyNames,TouchDecoder,Config,Router,FaceclawSender}.java \
  "$here"/io/github/omalve/g2ringremote/PhoneSim.java
token=$(mktemp); trap 'rm -f "$token"; kill $mock 2>/dev/null || true' EXIT
echo "sim-token-$$" > "$token"
port=$(python3 -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1])')
: > "$run/faceclaw-gestures.jsonl"
python3 "$here/mock_faceclaw.py" "$port" "$token" "$run/faceclaw-gestures.jsonl" & mock=$!
sleep 0.5
"$jdk/bin/java" -cp "$out" io.github.omalve.g2ringremote.PhoneSim "$here/watch.conf" "$run/uart0.log" "$port" "$token" "$run/faceclaw-gestures.jsonl"
echo "--- gestures received by mock Faceclaw (and Android key injections):"
cat "$run/faceclaw-gestures.jsonl"
