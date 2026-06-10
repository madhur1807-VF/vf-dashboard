#!/usr/bin/env python3
"""
Euler Motors VF Dashboard — Server with Google Sheets Backend
Run: python server.py
Open: http://localhost:8080/euler_vf.html
"""

import json, os, threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

import gspread
from google.oauth2.service_account import Credentials

# ── CONFIG ────────────────────────────────────────────────────
SHEET_ID   = "1jWmwJJZJzLX0oCSeRm24bCNNQ29pn0jAOl9Y9pUlU-4"
CREDS_FILE = "credentials.json"
PORT       = 8080
SCOPES     = ["https://www.googleapis.com/auth/spreadsheets"]

# ── GOOGLE SHEETS CLIENT ──────────────────────────────────────
_gc = None
_sh = None
_lock = threading.Lock()

def get_sheet():
    global _gc, _sh
    if _sh is None:
        creds = Credentials.from_service_account_file(CREDS_FILE, scopes=SCOPES)
        _gc   = gspread.authorize(creds)
        _sh   = _gc.open_by_key(SHEET_ID)
    return _sh

def ws(title):
    return get_sheet().worksheet(title)

# ── SHEET HELPERS ─────────────────────────────────────────────
def rows_to_dicts(worksheet):
    """Convert sheet rows to list of dicts using header row."""
    records = worksheet.get_all_records()
    return records

def find_row(worksheet, key_col, key_val, key_col2=None, key_val2=None):
    """Find 1-based row index matching key(s). Returns None if not found."""
    headers = worksheet.row_values(1)
    idx1 = headers.index(key_col) + 1 if key_col in headers else None
    idx2 = (headers.index(key_col2) + 1 if key_col2 and key_col2 in headers else None)
    data  = worksheet.get_all_values()
    for i, row in enumerate(data[1:], start=2):
        val1 = row[idx1-1] if idx1 and idx1 <= len(row) else ""
        if val1 != str(key_val): continue
        if idx2:
            val2 = row[idx2-1] if idx2 <= len(row) else ""
            if val2 != str(key_val2): continue
        return i
    return None

def upsert_row(worksheet, match_keys, data_dict):
    """Insert or update a row. match_keys = {col: val} for finding existing row."""
    headers = worksheet.row_values(1)
    # Find existing row
    row_idx = None
    all_vals = worksheet.get_all_values()
    for i, row in enumerate(all_vals[1:], start=2):
        match = all([
            (row[headers.index(k)] if k in headers and headers.index(k) < len(row) else "") == str(v)
            for k, v in match_keys.items()
        ])
        if match:
            row_idx = i
            break
    row_data = [str(data_dict.get(h, "")) for h in headers]
    if row_idx:
        worksheet.update(f"A{row_idx}", [row_data])
    else:
        worksheet.append_row(row_data)

def delete_row(worksheet, match_keys):
    """Delete a row matching match_keys."""
    headers = worksheet.row_values(1)
    all_vals = worksheet.get_all_values()
    for i, row in enumerate(all_vals[1:], start=2):
        match = all([
            (row[headers.index(k)] if k in headers and headers.index(k) < len(row) else "") == str(v)
            for k, v in match_keys.items()
        ])
        if match:
            worksheet.delete_rows(i)
            return True
    return False

# ── API HANDLERS ──────────────────────────────────────────────

def api_get_fi_master():
    records = rows_to_dicts(ws("FI_Master"))
    return records

def api_save_fi_master(data):
    """Upsert a financier record."""
    upsert_row(ws("FI_Master"), {"name": data["name"]}, data)

def api_delete_fi_master(name):
    delete_row(ws("FI_Master"), {"name": name})

def api_get_dealer_master():
    return rows_to_dicts(ws("Dealer_Master"))

def api_save_dealer_master(data):
    upsert_row(ws("Dealer_Master"), {"dealerName": data["dealerName"], "location": data["location"]}, data)

def api_delete_dealer_master(dealer_name, location):
    delete_row(ws("Dealer_Master"), {"dealerName": dealer_name, "location": location})

def api_get_added_dealers():
    return rows_to_dicts(ws("Added_Dealers"))

def api_save_added_dealer(data):
    upsert_row(ws("Added_Dealers"), {"dealer": data["dealer"], "location": data["location"]}, data)

def api_delete_added_dealer(dealer, location):
    delete_row(ws("Added_Dealers"), {"dealer": dealer, "location": location})

def api_get_onboarding():
    return rows_to_dicts(ws("FI_Onboarding"))

def api_save_onboarding(data):
    upsert_row(ws("FI_Onboarding"), {"dealer": data["dealer"], "location": data["location"], "financier": data["financier"]}, data)

def api_delete_onboarding(dealer, location, financier):
    delete_row(ws("FI_Onboarding"), {"dealer": dealer, "location": location, "financier": financier})

def api_get_fi_policy():
    return rows_to_dicts(ws("FI_Policy"))

def api_save_fi_policy(data):
    upsert_row(ws("FI_Policy"), {"financier": data["financier"], "productKey": data["productKey"]}, data)

def api_get_dealer_health():
    return rows_to_dicts(ws("Dealer_Health"))

def api_save_dealer_health(data):
    upsert_row(ws("Dealer_Health"), {"dealer": data["dealer"], "location": data["location"]}, data)

# ── HTTP HANDLER ──────────────────────────────────────────────
class Handler(SimpleHTTPRequestHandler):

    def log_message(self, fmt, *args):
        print(f"  {self.address_string()} → {fmt % args}")

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
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length).decode("utf-8")) if length else {}

    def do_GET(self):
        path = urlparse(self.path).path
        try:
            if   path == "/api/fi_master":      self.send_json(200, api_get_fi_master())
            elif path == "/api/dealer_master":   self.send_json(200, api_get_dealer_master())
            elif path == "/api/added_dealers":   self.send_json(200, api_get_added_dealers())
            elif path == "/api/onboarding":      self.send_json(200, api_get_onboarding())
            elif path == "/api/fi_policy":       self.send_json(200, api_get_fi_policy())
            elif path == "/api/dealer_health":   self.send_json(200, api_get_dealer_health())
            else: super().do_GET()
        except Exception as e:
            self.send_json(500, {"error": str(e)})

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            body = self.read_body()
            if   path == "/api/fi_master":      api_save_fi_master(body);       self.send_json(200, {"ok": True})
            elif path == "/api/dealer_master":  api_save_dealer_master(body);   self.send_json(200, {"ok": True})
            elif path == "/api/added_dealers":  api_save_added_dealer(body);    self.send_json(200, {"ok": True})
            elif path == "/api/onboarding":     api_save_onboarding(body);      self.send_json(200, {"ok": True})
            elif path == "/api/fi_policy":      api_save_fi_policy(body);       self.send_json(200, {"ok": True})
            elif path == "/api/dealer_health":  api_save_dealer_health(body);   self.send_json(200, {"ok": True})
            else: self.send_json(404, {"error": "Not found"})
        except Exception as e:
            self.send_json(500, {"error": str(e)})

    def do_DELETE(self):
        path = urlparse(self.path).path
        qs = parse_qs(urlparse(self.path).query)
        def q(k): return qs.get(k, [""])[0]
        try:
            if   path == "/api/fi_master":      api_delete_fi_master(q("name"));                              self.send_json(200, {"ok": True})
            elif path == "/api/dealer_master":  api_delete_dealer_master(q("dealerName"), q("location"));     self.send_json(200, {"ok": True})
            elif path == "/api/added_dealers":  api_delete_added_dealer(q("dealer"), q("location"));          self.send_json(200, {"ok": True})
            elif path == "/api/onboarding":     api_delete_onboarding(q("dealer"), q("location"), q("financier")); self.send_json(200, {"ok": True})
            else: self.send_json(404, {"error": "Not found"})
        except Exception as e:
            self.send_json(500, {"error": str(e)})

# ── MAIN ──────────────────────────────────────────────────────
if __name__ == "__main__":
    import socket
    local_ip = socket.gethostbyname(socket.gethostname())

    print()
    print("  ┌─────────────────────────────────────────────┐")
    print("  │   Euler Motors VF Dashboard                 │")
    print("  ├─────────────────────────────────────────────┤")
    print(f"  │   Local:    http://localhost:{PORT}           │")
    print(f"  │   Network:  http://{local_ip}:{PORT}".ljust(47) + "│")
    print("  │   Backend:  Google Sheets                   │")
    print("  │   Press Ctrl+C to stop                      │")
    print("  └─────────────────────────────────────────────┘")
    print()

    server = HTTPServer(("0.0.0.0", PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Server stopped.")
