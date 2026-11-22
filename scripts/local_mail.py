"""Loopback-only email capture for manual tests. Never forwards mail."""
import argparse
import socketserver
from pathlib import Path
from uuid import uuid4


class Receiver(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(15)
        self.wfile.write(b"220 CampusFlow local email capture\r\n")
        while line := self.rfile.readline(4096):
            command = line.split(b" ", 1)[0].strip().upper()
            if command in (b"EHLO", b"HELO", b"MAIL", b"RCPT", b"RSET", b"NOOP"):
                self.wfile.write(b"250 OK\r\n")
            elif command == b"DATA":
                self.wfile.write(b"354 End with dot\r\n")
                body = bytearray()
                while (line := self.rfile.readline(4096)) and line != b".\r\n":
                    body.extend(line[1:] if line.startswith(b"..") else line)
                    if len(body) > 65536:
                        self.wfile.write(b"552 Message too large\r\n")
                        return
                if not line:
                    return
                path = self.server.directory / (uuid4().hex + ".eml")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(body)
                print(f"Captured email: {path}", flush=True)
                self.wfile.write(b"250 Captured locally; not delivered externally\r\n")
            elif command == b"QUIT":
                self.wfile.write(b"221 Bye\r\n")
                break
            else:
                self.wfile.write(b"500 Unsupported\r\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=1025)
    parser.add_argument("--directory", type=Path, default=Path("data/mail-capture"))
    args = parser.parse_args()
    args.directory.mkdir(parents=True, exist_ok=True)
    with socketserver.ThreadingTCPServer(("127.0.0.1", args.port), Receiver) as server:
        server.daemon_threads = True
        server.directory = args.directory.resolve()
        print(f"Local SMTP capture listening on 127.0.0.1:{args.port}. Ctrl+C stops it.", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
