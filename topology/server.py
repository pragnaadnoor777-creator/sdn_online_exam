from http.server import BaseHTTPRequestHandler, HTTPServer

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/exam":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Exam page OK")
        else:
            self.send_response(404)
            self.end_headers()
if __name__ == "__main__":
    server=HTTPServer(("0.0.0.0",8080),Handler)
    server.serve_forever()            


 
