"""Loopback-only settings and evidence panel; explicit per-session capability."""
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import threading
from urllib.parse import parse_qs, urlsplit
import webbrowser

import delivery
import notify


def make_server(root, token=None):
    root, token = Path(root), token or secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Do not log the URL capability.

        def setup(self):
            super().setup()
            self.connection.settimeout(5)

        def respond(self, code, body, mime="application/json; charset=utf-8"):
            if not isinstance(body, bytes):
                body = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; media-src blob:; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(body)

        def authorized(self, page=False):
            host = f"127.0.0.1:{self.server.server_port}"
            if self.headers.get("Host") != host:
                return False
            origin = self.headers.get("Origin")
            if origin and origin != "http://" + host:
                return False
            offered = self.headers.get("X-Soft-Notify-Token", "")
            if page:
                offered = parse_qs(urlsplit(self.path).query).get("token", [""])[0]
                # The static shell has no data or secrets. On refresh the
                # browser obtains the capability from its own sessionStorage.
                if not offered:
                    return True
            return hmac.compare_digest(offered, token)

        def do_GET(self):
            path = urlsplit(self.path).path
            if not self.authorized(path == "/"):
                return self.respond(403, {"error": "Open the panel with its private session URL."})
            try:
                if path == "/":
                    return self.respond(200, (root / "assets/panel.html").read_bytes(), "text/html; charset=utf-8")
                if path == "/api/state":
                    return self.respond(200, notify.state_snapshot(root))
                return self.respond(404, {"error": "not found"})
            except Exception:
                self.respond(500, {"error": "Could not read local state; run the status command."})

        def do_POST(self):
            if not self.authorized():
                return self.respond(403, {"error": "invalid session or origin"})
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 8192:
                    return self.respond(413, {"error": "request too large or empty"})
                if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                    return self.respond(415, {"error": "JSON required"})
                value = json.loads(self.rfile.read(size))
                path = urlsplit(self.path).path
                if path == "/api/settings":
                    return self.respond(200, notify.save_settings(root, value))
                if path == "/api/render":
                    event = value["event"]
                    audio = notify.sound_bytes(event, value["volume"], value["tone"], value["design"])
                    return self.respond(200, audio, "audio/wav")
                if path == "/api/preview":
                    delivery.enqueue(root, value["event"], "preview")
                    delivery.spawn_worker(root)
                    return self.respond(200, {"queued": True})
                if path == "/api/trust-check":
                    if value.get("confirmed") is not True:
                        raise ValueError("Confirm your manual /hooks check first.")
                    notify.confirm_trust(root)
                    return self.respond(200, {"recorded": "manual only"})
                if path == "/api/retry":
                    # A retry drains only pending items. Failed/interrupted
                    # audio is not replayed automatically.
                    delivery.spawn_worker(root)
                    return self.respond(200, {"pending_queue_woken": True})
                if path == "/api/shutdown":
                    self.respond(200, {"closed": True})
                    threading.Thread(target=self.server.shutdown, daemon=True).start()
                    return
                self.respond(404, {"error": "not found"})
            except (ValueError, KeyError, TypeError):
                self.respond(400, {"error": "Invalid settings. Check note, volume and timing ranges."})
            except Exception:
                self.respond(500, {"error": "Local operation failed; no approval decision was changed."})

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    return server, f"http://127.0.0.1:{server.server_port}/?token={token}"


def serve(root, open_browser=True):
    server, url = make_server(root)
    print("Local panel:", url, flush=True)
    print("Keep this session URL private. Ctrl+C or Close panel stops the server.", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
