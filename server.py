#!/usr/bin/env python3
"""
Euler Motors VF Dashboard - Local Server
Run: python server.py
Then open: http://localhost:8080
"""

import json
import os
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse

DATA_FILE = "data.json"
PORT = 8080

# ── Initialise data file if missing ──────────────────────────
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# ── Request handler ──────────────────────────────────────────
class Handler(SimpleHTTPRequestHandler):

    def log_message(self, format, *args):
        print(f"  {self.address_string()} → {format % args}")

    def send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)

        # API: load mapping data
        if parsed.path == "/api/data":
            self.send_json(200, load_data())
            return

        # Serve static files (euler_vf.html etc.)
        super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)

        # API: save mapping data
        if parsed.path == "/api/data":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            try:
                data = json.loads(body.decode("utf-8"))
                save_data(data)
                self.send_json(200, {"status": "ok"})
            except Exception as e:
                self.send_json(400, {"status": "error", "message": str(e)})
            return

        self.send_json(404, {"status": "not found"})

# ── Main ─────────────────────────────────────────────────────
if __name__ == "__main__":
    # Make sure data file exists
    if not os.path.exists(DATA_FILE):
        save_data({})
        print(f"  Created {DATA_FILE}")

    server = HTTPServer(("0.0.0.0", PORT), Handler)

    import socket
    local_ip = socket.gethostbyname(socket.gethostname())

    print()
    print("  ┌─────────────────────────────────────────────┐")
    print("  │   Euler Motors VF Dashboard — Local Server  │")
    print("  ├─────────────────────────────────────────────┤")
    print(f"  │   Local:    http://localhost:{PORT}           │")
    print(f"  │   Network:  http://{local_ip}:{PORT}".ljust(47) + "│")
    print("  │                                             │")
    print("  │   Data saved to: data.json                  │")
    print("  │   Press Ctrl+C to stop                      │")
    print("  └─────────────────────────────────────────────┘")
    print()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Server stopped.")
