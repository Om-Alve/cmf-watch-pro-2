import json
import socketserver
import sys
from pathlib import Path


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        request = json.loads(self.rfile.readline())
        ok = request.get("token") == self.server.token and request.get("action") in ("input", "ping", "type")
        if request.get("action") == "input":
            line = json.dumps({"gesture": request.get("gesture"), "source": request.get("source"), "accepted": ok})
            with open(self.server.log, "a") as log:
                log.write(line + "\n")
        elif request.get("action") == "type":
            line = json.dumps({"type": request.get("text")})
            with open(self.server.log, "a") as log:
                log.write(line + "\n")
        reply = {"ok": True} if ok else {"ok": False, "error": "unauthorized"}
        self.wfile.write((json.dumps(reply) + "\n").encode())


def main():
    port, token_file, log = int(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
    server = socketserver.ThreadingTCPServer(("127.0.0.1", port), Handler)
    server.token = token_file.read_text().strip()
    server.log = log
    server.serve_forever()


if __name__ == "__main__":
    main()
