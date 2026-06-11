#!/usr/bin/env python3
"""
Euler Motors VF Dashboard — Server with Google Sheets Backend
Local:   python server.py
Railway: auto-started via Procfile
"""

import json, os, threading, traceback
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# ── CONFIG ────────────────────────────────────────────────────
SHEET_ID   = "1jWmwJJZJzLX0oCSeRm24bCNNQ29pn0jAOl9Y9pUlU-4"
CREDS_FILE = "credentials.json"
PORT       = int(os.environ.get("PORT", 9000))  # Railway sets PORT env var

# ── GOOGLE SHEETS CLIENT ──────────────────────────────────────
_sh   = None
_lock = threading.Lock()

def get_sheet():
    global _sh
    with _lock:
        if _sh is None:
            import gspread
            from google.oauth2.service_account import Credentials
            SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

            # Support credentials from environment variable (Railway) or file (local)
            creds_json = os.environ.get("GOOGLE_CREDENTIALS")
            if creds_json:
                creds_dict = json.loads(creds_json)
                # Railway sometimes double-escapes newlines in private key — fix it
                if 'private_key' in creds_dict:
                    creds_dict['private_key'] = creds_dict['private_key'].replace('\\n', '\n')
                creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
                print("  Using credentials from environment variable")
            else:
                creds = Credentials.from_service_account_file(CREDS_FILE, scopes=SCOPES)
                print("  Using credentials from credentials.json")

            gc  = gspread.authorize(creds)
            _sh = gc.open_by_key(SHEET_ID)
            print(f"  ✅ Connected to Google Sheet: {_sh.title}")
    return _sh

def ws(title):
    return get_sheet().worksheet(title)

def rows_to_dicts(worksheet):
    return worksheet.get_all_records() or []

def upsert_row(worksheet, match_keys, data_dict):
    headers = worksheet.row_values(1)
    all_vals = worksheet.get_all_values()
    row_idx = None
    for i, row in enumerate(all_vals[1:], start=2):
        if all((row[headers.index(k)] if k in headers and headers.index(k) < len(row) else "") == str(v)
               for k, v in match_keys.items()):
            row_idx = i
            break
    row_data = [str(data_dict.get(h, "")) for h in headers]
    if row_idx:
        worksheet.update(f"A{row_idx}", [row_data])
    else:
        worksheet.append_row(row_data)

def delete_row(worksheet, match_keys):
    headers = worksheet.row_values(1)
    all_vals = worksheet.get_all_values()
    for i, row in enumerate(all_vals[1:], start=2):
        if all((row[headers.index(k)] if k in headers and headers.index(k) < len(row) else "") == str(v)
               for k, v in match_keys.items()):
            worksheet.delete_rows(i)
            return True
    return False

# ── API FUNCTIONS ─────────────────────────────────────────────
def api_get(sheet_name):        return rows_to_dicts(ws(sheet_name))
def api_save_fi_master(d):      upsert_row(ws("FI_Master"),      {"name": d["name"]}, d)
def api_delete_fi_master(n):    delete_row(ws("FI_Master"),      {"name": n})
def api_save_dealer_master(d):  upsert_row(ws("Dealer_Master"),  {"dealerName": d["dealerName"], "location": d["location"]}, d)
def api_delete_dealer_master(n, l): delete_row(ws("Dealer_Master"), {"dealerName": n, "location": l})
def api_save_added_dealer(d):   upsert_row(ws("Added_Dealers"),  {"dealer": d["dealer"], "location": d["location"]}, d)
def api_delete_added_dealer(d, l): delete_row(ws("Added_Dealers"), {"dealer": d, "location": l})
def api_save_onboarding(d):     upsert_row(ws("FI_Onboarding"),  {"dealer": d["dealer"], "location": d["location"], "financier": d["financier"]}, d)
def api_delete_onboarding(d, l, f): delete_row(ws("FI_Onboarding"), {"dealer": d, "location": l, "financier": f})
def api_save_fi_policy(d):      upsert_row(ws("FI_Policy"),      {"financier": d["financier"], "productKey": d["productKey"]}, d)
def api_save_dealer_health(d):  upsert_row(ws("Dealer_Health"),  {"dealer": d["dealer"], "location": d["location"]}, d)
def api_get_taif():             return rows_to_dicts(ws("TA_IF_Status")) or []
def api_save_taif(d):           upsert_row(ws("TA_IF_Status"), {"dealerCode": d["dealerCode"], "city": d["city"]}, d)

# ── HTTP HANDLER ──────────────────────────────────────────────
class Handler(SimpleHTTPRequestHandler):

    def log_message(self, fmt, *args):
        if args and ('.well-known' in str(args[0]) or 'favicon' in str(args[0])):
            return
        print(f"  {self.address_string()} → {fmt % args}")

    def send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type",   "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin",  "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin",  "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def read_body(self):
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n)) if n else {}

    def do_GET(self):
        path = urlparse(self.path).path
        # ── API routes ──────────────────────────────────────
        if path.startswith("/api/"):
            try:
                if   path == "/api/fi_master":     self.send_json(200, api_get("FI_Master"))
                elif path == "/api/dealer_master":  self.send_json(200, api_get("Dealer_Master"))
                elif path == "/api/added_dealers":  self.send_json(200, api_get("Added_Dealers"))
                elif path == "/api/onboarding":     self.send_json(200, api_get("FI_Onboarding"))
                elif path == "/api/fi_policy":      self.send_json(200, api_get("FI_Policy"))
                elif path == "/api/dealer_health":  self.send_json(200, api_get("Dealer_Health"))
                elif path == "/api/taif":             self.send_json(200, api_get_taif())
                else:                               self.send_json(404, {"error": f"Unknown: {path}"})
            except Exception as e:
                traceback.print_exc()
                self.send_json(500, {"error": str(e)})
        # ── Static files ─────────────────────────────────────
        else:
            super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        if not path.startswith("/api/"):
            self.send_json(404, {"error": "Not found"}); return
        try:
            body = self.read_body()
            if   path == "/api/fi_master":     api_save_fi_master(body)
            elif path == "/api/dealer_master": api_save_dealer_master(body)
            elif path == "/api/added_dealers": api_save_added_dealer(body)
            elif path == "/api/onboarding":    api_save_onboarding(body)
            elif path == "/api/fi_policy":     api_save_fi_policy(body)
            elif path == "/api/dealer_health": api_save_dealer_health(body)
            elif path == "/api/taif":             api_save_taif(body)
            else: self.send_json(404, {"error": f"Unknown: {path}"}); return
            self.send_json(200, {"ok": True})
        except Exception as e:
            traceback.print_exc()
            self.send_json(500, {"error": str(e)})

    def do_DELETE(self):
        path = urlparse(self.path).path
        qs   = parse_qs(urlparse(self.path).query)
        q    = lambda k: qs.get(k, [""])[0]
        try:
            if   path == "/api/fi_master":     api_delete_fi_master(q("name"))
            elif path == "/api/dealer_master": api_delete_dealer_master(q("dealerName"), q("location"))
            elif path == "/api/added_dealers": api_delete_added_dealer(q("dealer"), q("location"))
            elif path == "/api/onboarding":    api_delete_onboarding(q("dealer"), q("location"), q("financier"))
            else: self.send_json(404, {"error": f"Unknown: {path}"}); return
            self.send_json(200, {"ok": True})
        except Exception as e:
            traceback.print_exc()
            self.send_json(500, {"error": str(e)})

# ── MAIN ──────────────────────────────────────────────────────
if __name__ == "__main__":
    import socket

    # Test connection on startup
    print("\n  Testing Google Sheets connection...")
    try:
        get_sheet()
    except Exception as e:
        print(f"\n  ❌ Google Sheets connection FAILED: {e}")
        print("  Check GOOGLE_CREDENTIALS environment variable.")

    print(f"\n  ✅ Server starting on port {PORT}")
    print(f"  Open: http://localhost:{PORT}/euler_vf.html\n")

    server = HTTPServer(("0.0.0.0", PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Server stopped.")
