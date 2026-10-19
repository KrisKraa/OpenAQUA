"""Tiny static file server with CORS + Private-Network-Access headers, so the EasyEDA
web editor (https) can fetch a local board file for testing.  python3 tools/cors_server.py PORT DIR"""
import sys, http.server, functools
class H(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Private-Network', 'true')
        self.send_header('Access-Control-Allow-Headers', '*')
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()
    def do_OPTIONS(self):
        self.send_response(204); self.end_headers()
port, d = int(sys.argv[1]), sys.argv[2]
http.server.ThreadingHTTPServer(('127.0.0.1', port), functools.partial(H, directory=d)).serve_forever()
