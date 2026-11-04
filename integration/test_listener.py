"""Prints any event POSTed to it. For testing notifier.py. Owner: Member C."""
from http.server import BaseHTTPRequestHandler, HTTPServer

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        print("RECEIVED:", self.path, body.decode())
        self.send_response(200)
        self.end_headers()

HTTPServer(("0.0.0.0", 8080), Handler).serve_forever()