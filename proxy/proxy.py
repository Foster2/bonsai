#!/usr/bin/env python3
import http.server
import json
import re
import urllib.error
import urllib.request
import sys

BACKEND_HOST = sys.argv[1] if len(sys.argv) > 1 else "llama-server"
BACKEND_PORT = int(sys.argv[2] if len(sys.argv) > 2 else "8081")
LISTEN_PORT = int(sys.argv[3] if len(sys.argv) > 3 else "8080")
BACKEND = f"http://{BACKEND_HOST}:{BACKEND_PORT}"

# Clients (e.g. Open WebUI) send -1 as "apply to all tokens"; the llama.cpp
# schema rejects values < 0. Neutralise these proactively.
NEG_SENTINEL_FIELDS = {
    "dry_penalty_last_n": 0,
    "repeat_last_n": 0,
    "dry_allowed_length": -1,
}

# Backstop: auto-fix any other field the schema rejects, then retry once.
FIELD_ERR_RE = re.compile(r"Field '([^']+)': Value must be between (-?\d+(?:\.\d+)?) <= value <= (-?\d+(?:\.\d+)?)")


def normalize(data):
    """Apply NEG_SENTINEL_FIELDS. Returns True if anything changed."""
    changed = False
    for field, fallback in NEG_SENTINEL_FIELDS.items():
        if isinstance(data.get(field), (int, float)) and data[field] < 0:
            data[field] = fallback
            changed = True
    return changed


def as_json(body, ctype):
    if not body or "application/json" not in ctype:
        return None
    try:
        return json.loads(body)
    except Exception:
        return None


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self): self._proxy()
    def do_POST(self): self._proxy()
    def do_PUT(self): self._proxy()
    def do_PATCH(self): self._proxy()
    def do_DELETE(self): self._proxy()
    def do_OPTIONS(self): self._proxy()

    def _proxy(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        body = raw
        data = as_json(body, self.headers.get("Content-Type", ""))
        if data is not None and normalize(data):
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")

        retried = False
        while True:
            status, resp, errbody = self._send(body)
            if status == 0:
                self._stream(resp)
                break
            error_data = as_json(errbody, "application/json") or {}
            msg = error_data.get("error") or {}
            text = msg.get("message") if isinstance(msg, dict) else str(msg)
            m = FIELD_ERR_RE.search(str(text))
            if not retried and status == 400 and m and data is not None:
                field, lo, _hi = m.groups()
                if isinstance(data.get(field), (int, float)) and data[field] < float(lo):
                    data[field] = float(lo) if "." in lo else int(lo)
                    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
                    retried = True
                    continue
            self._error(status, errbody)
            break

    def _send(self, body):
        headers = {
            k: v
            for k, v in self.headers.items()
            if k.lower() not in ("host", "connection", "content-length", "accept-encoding")
        }
        headers["Connection"] = "close"
        if body:
            headers["Content-Length"] = str(len(body))
        req = urllib.request.Request(f"{BACKEND}{self.path}", data=body if body else None, headers=headers, method=self.command)
        try:
            resp = urllib.request.urlopen(req, timeout=None)
            return 0, resp, None
        except urllib.error.HTTPError as e:
            errbody = e.read()
            return e.code, None, errbody
        except Exception as ex:
            return 502, None, json.dumps({"error": {"message": f"proxy: {ex}"}}).encode()

    def _stream(self, resp):
        try:
            self.send_response(resp.status)
            for k, v in resp.headers.items():
                if k.lower() in ("transfer-encoding", "connection", "content-length", "accept-encoding", "keep-alive"):
                    continue
                self.send_header(k, v)
            self.send_header("Connection", "close")
            self.end_headers()
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    break
        except Exception:
            pass

    def _error(self, status, body):
        try:
            self.send_response(status)
            if body:
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            self.end_headers()
            if body:
                self.wfile.write(body)
        except Exception:
            pass

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    http.server.ThreadingHTTPServer(("0.0.0.0", LISTEN_PORT), Handler).serve_forever()