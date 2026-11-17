"""Dummy controller endpoint for testing integration/notifier.py. Owner: Member C.

Prints every event POSTed to it and replies 200. Default 127.0.0.1:8081, so it does not compete with
Ryu's own HTTP service (port 8080).   Usage: python3 integration/test_listener.py [--host 127.0.0.1] [--port 8081] [--log events.jsonl]
NOTE: this is only a stand-in. The real controller (controller/trustme.py) does not implement /exam/event yet.
"""
import argparse
from http.server import BaseHTTPRequestHandler, HTTPServer


def make_handler(logfile):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode()
            print("RECEIVED:", self.path, body, flush=True)
            if logfile:
                with open(logfile, "a") as f:
                    f.write(body + "\n")
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args):      # silence the default per-request log line
            pass
    return Handler


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8081)
    ap.add_argument("--log", default=None, help="also append each event to this file")
    a = ap.parse_args()
    print("listening on http://%s:%d (Ctrl+C to stop)" % (a.host, a.port), flush=True)
    HTTPServer((a.host, a.port), make_handler(a.log)).serve_forever()