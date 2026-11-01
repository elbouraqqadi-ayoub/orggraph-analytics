"""Dashboard and bounded JSON API for a local organization knowledge graph."""
import hmac
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, quote

from .core import analytics
from .pipeline import answer, benchmark
from .errors import BackendError, ConfigurationError
from .store import GraphStore
from .dashboard import ASSETS, WEB_ROOT, model_status, reports, upload_document, original_document
from .version import source_fingerprint


def make_handler(data: Path, backend="local"):
    store = GraphStore(data, backend)
    ingestion_lock = threading.Lock()
    counters = {"requests": 0, "errors": 0, "started_at": time.time()}
    metrics_lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(30)

        def send_body(self, status, body, content_type, download_name=None):
            self.send_response(status)
            self.send_header("Content-Type", content_type + "; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-store")
            if download_name is not None:
                self.send_header("Content-Disposition", "attachment; filename*=UTF-8''"+quote(download_name))
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)
            with metrics_lock:
                counters["requests"] += 1
                counters["errors"] += int(status >= 400)

        def send_json(self, status, value):
            self.send_body(status, json.dumps(value, ensure_ascii=False).encode("utf-8"), "application/json")

        def authorized(self):
            token = os.environ.get("API_TOKEN", "")
            actual = self.headers.get("Authorization", "").encode("utf-8")
            if token and not hmac.compare_digest(actual, ("Bearer " + token).encode("utf-8")):
                self.send_json(401, {"error": "Enter the API token to connect."})
                return False
            return True

        def graph(self):
            return store.load()

        def backend_error(self, error):
            self.log_error("Operation failed: %s", type(error).__name__)
            if isinstance(error, ConfigurationError):
                self.send_json(500, {"error": "Server configuration is incomplete. Check the selected backend, model, and graph import."})
            else:
                self.send_json(503, {"error": "The graph or model service is unavailable. Check service logs and try again."})

        def do_GET(self):
            route = urlparse(self.path).path
            if route in ASSETS:
                filename, mime = ASSETS[route]
                self.send_body(200, (WEB_ROOT / filename).read_bytes(), mime)
                return
            if not self.authorized():
                return
            try:
                if route == "/api":
                    self.send_json(200, {"service": "OrgGraph Analytics", "backend": backend,
                                         "routes": ["GET /health", "GET /graph", "GET /analytics", "GET /documents", "GET /reports", "GET /status", "POST /ask", "POST /upload", "POST /benchmark"]})
                elif route == "/health":
                    graph = self.graph()
                    self.send_json(200, {"status": "ok", "backend": backend, "nodes": len(graph["nodes"])})
                elif route in {"/graph", "/analytics", "/documents"}:
                    graph = self.graph()
                    value = graph if route == "/graph" else analytics(graph) if route == "/analytics" else graph["documents"]
                    self.send_json(200, value)
                elif route == "/status":
                    self.send_json(200, {"backend": backend, "llm": model_status(), "max_upload_mb": 10,"source_fingerprint":source_fingerprint()})
                elif route == "/reports":
                    self.send_json(200, reports())
                elif route.startswith("/document/"):
                    try:
                        body,mime,title=original_document(self.graph(),route.removeprefix("/document/"),data)
                        self.send_body(200,body,mime,title)
                    except FileNotFoundError as error:
                        self.send_json(404,{"error":str(error)})
                elif route == "/metrics":
                    with metrics_lock:
                        value = {**counters, "uptime_seconds": time.time() - counters["started_at"]}
                    self.send_json(200, value)
                else:
                    self.send_json(404, {"error": "Unknown route."})
            except (OSError, ValueError, TypeError, KeyError, BackendError, ConfigurationError) as error:
                self.backend_error(error)

        def do_POST(self):
            if not self.authorized():
                return
            route = urlparse(self.path).path
            if route not in {"/ask", "/upload", "/benchmark"}:
                self.send_json(404, {"error": "Unknown route."})
                return
            origin = self.headers.get("Origin")
            if origin and urlparse(origin).netloc != self.headers.get("Host"):
                self.send_json(403, {"error": "Cross-origin writes are not allowed."})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                maximum = 14 * 1024 * 1024 if route == "/upload" else 16384
                if not 0 < length <= maximum:
                    self.send_json(413, {"error": "Request body is empty or exceeds the size limit."})
                    return
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict):
                    raise ValueError("Expected a JSON object.")
                if route == "/ask":
                    question, hops, mode = payload.get("question"), payload.get("hops", 2), payload.get("mode", "extractive")
                    if not isinstance(question, str) or not question.strip() or len(question) > 2000:
                        raise ValueError("Question must contain 1–2000 characters.")
                    if type(hops) is not int or not 1 <= hops <= 3:
                        raise ValueError("Hops must be between 1 and 3.")
                    if not isinstance(mode, str) or mode not in {"extractive", "llm"}:
                        raise ValueError("Unknown answer mode.")
            except (ValueError, TypeError, KeyError):
                self.send_json(400, {"error": "Invalid request. Check the question, mode, hops or JSON payload."})
                return
            try:
                if route == "/ask":
                    self.send_json(200, answer(self.graph(), question, mode, hops))
                elif route == "/upload":
                    with ingestion_lock:
                        report = upload_document(payload, data, backend)
                    self.send_json(200 if report["published"] else 422, report)
                else:
                    self.send_json(200, benchmark(self.graph(), Path("evaluation/questions.json"), Path("output/benchmark.json")))
            except ValueError as error:
                self.send_json(400, {"error": str(error) if route == "/upload" else "Invalid operation."})
            except (OSError, TypeError, KeyError, BackendError, ConfigurationError) as error:
                self.backend_error(error)

    return Handler


def serve(data: Path, port: int = 8080, backend="local", open_browser=False):
    host = os.environ.get("API_BIND", "127.0.0.1")
    server = ThreadingHTTPServer((host, port), make_handler(data, backend))
    print(f"OrgGraph dashboard http://{host}:{port} ({backend})", flush=True)
    if open_browser:
        import webbrowser
        opener=threading.Timer(.5,lambda:webbrowser.open(f"http://127.0.0.1:{port}"))
        opener.daemon=True
        opener.start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
