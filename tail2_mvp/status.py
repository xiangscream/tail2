"""Loopback-only read-only state viewer. No device calls and no arbitrary file route."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .events import read_events, read_state


class StatusServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, directory: Path, port: int = 0, *, preview=None, overlay=None):
        self.directory = directory.resolve()
        self.preview = preview
        self.overlay = overlay
        super().__init__(("127.0.0.1", port), Handler)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _allowed(self) -> bool:
        port = self.server.server_port
        allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if self.headers.get("Host") not in allowed_hosts:
            return False
        origin = self.headers.get("Origin")
        return origin is None or origin in {f"http://{host}" for host in allowed_hosts}

    def _send(self, status: int, data: bytes, kind: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'none'; img-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if not self._allowed():
            self._send(403, b"loopback origin required", "text/plain"); return
        path = urlsplit(self.path).path
        if path == "/":
            self._send(200, Path(__file__).with_name("status.html").read_bytes(), "text/html; charset=utf-8")
        elif path == "/api/state":
            data = read_state(self.server.directory)
            self._send(200, json.dumps(data, ensure_ascii=False).encode(), "application/json; charset=utf-8")
        elif path == "/api/events":
            data = read_events(self.server.directory)
            self._send(200, json.dumps(data, ensure_ascii=False).encode(), "application/json; charset=utf-8")
        elif path == "/api/preview.jpg":
            if self.server.preview is None:
                self._send(404, b"no preview source", "text/plain"); return
            try:
                data = self.server.preview()
            except Exception as exc:
                self._send(503, f"preview unavailable: {exc}".encode(), "text/plain"); return
            self._send(200, data, "image/jpeg")
        elif path == "/api/overlay":
            if self.server.overlay is None:
                self._send(404, b"no overlay source", "text/plain"); return
            try:
                data = json.dumps(self.server.overlay(), ensure_ascii=False).encode()
            except Exception as exc:
                self._send(503, f"overlay unavailable: {exc}".encode(), "text/plain"); return
            self._send(200, data, "application/json; charset=utf-8")
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self) -> None:
        self._send(405, b"read-only observer", "text/plain")

    do_PUT = do_POST
    do_DELETE = do_POST
    do_PATCH = do_POST


def serve(directory: Path, port: int = 0) -> None:
    with StatusServer(directory, port) as server:
        print(f"Read-only observer: http://127.0.0.1:{server.server_port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
