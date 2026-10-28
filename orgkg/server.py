"""Local JSON API. Bounded requests and no endpoint executing arbitrary Cypher."""
import hmac
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .core import analytics
from .pipeline import answer
from .errors import BackendError, ConfigurationError
from .store import GraphStore


def make_handler(data: Path, backend="local"):
    store = GraphStore(data, backend)

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(30)

        def send_json(self, status, value):
            body = json.dumps(value, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def authorized(self):
            token = os.environ.get("API_TOKEN", "")
            if token and not hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + token):
                self.send_json(401, {"error": "Authentification requise"})
                return False
            return True

        def graph(self):
            return store.load()

        def do_GET(self):
            if not self.authorized():
                return
            route = urlparse(self.path).path
            try:
                if route == "/":
                    self.send_json(200, {"service": "Organization KG", "backend": backend,
                                         "routes": ["GET /health", "GET /graph", "GET /analytics", "POST /ask"],
                                         "ask_body": {"question": "Quels liens autour de Atlas Industries ?", "mode": "extractive", "hops": 2}})
                elif route == "/health":
                    graph = self.graph()
                    self.send_json(200, {"status": "ok", "backend": backend, "nodes": len(graph["nodes"])})
                elif route in {"/graph", "/analytics"}:
                    graph = self.graph()
                    self.send_json(200, graph if route == "/graph" else analytics(graph))
                else:
                    self.send_json(404, {"error": "Route inconnue"})
            except ConfigurationError:
                self.send_json(500, {"error": "Configuration du serveur incomplète ou graphe à réimporter."})
            except (OSError, ValueError, TypeError, KeyError, BackendError) as exc:
                self.log_error("Backend unavailable: %s", type(exc).__name__)
                self.send_json(503, {"error": "Graphe indisponible. Vérifier l'ingestion et le backend."})

        def do_POST(self):
            if not self.authorized():
                return
            if urlparse(self.path).path != "/ask":
                self.send_json(404, {"error": "Route inconnue"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 16384:
                    self.send_json(413, {"error": "Corps requis, maximum 16 Ko"})
                    return
                payload = json.loads(self.rfile.read(length))
                if (not isinstance(payload, dict) or not isinstance(payload.get("question"), str)
                        or not payload["question"].strip() or not 1 <= len(payload["question"]) <= 2000):
                    raise ValueError("question doit contenir de 1 à 2000 caractères.")
                hops = payload.get("hops", 2)
                if type(hops) is not int or not 1 <= hops <= 3:
                    raise ValueError("hops doit être un entier entre 1 et 3.")
                mode = payload.get("mode", "extractive")
                if not isinstance(mode, str) or mode not in {"extractive", "llm"}:
                    raise ValueError("Mode inconnu.")
            except (ValueError, TypeError, KeyError):
                self.send_json(400, {"error": "Requête invalide. Vérifier question, mode et hops."})
                return
            try:
                self.send_json(200, answer(self.graph(), payload["question"], mode, hops))
            except ConfigurationError:
                self.send_json(500, {"error": "Configuration du serveur incomplète ou graphe à réimporter."})
            except (OSError, ValueError, TypeError, KeyError, BackendError):
                self.send_json(503, {"error": "Backend ou fournisseur LLM indisponible"})

    return Handler


def serve(data: Path, port: int = 8080, backend="local"):
    # The container explicitly sets API_BIND; the host default remains loopback.
    host = os.environ.get("API_BIND", "127.0.0.1")
    server = ThreadingHTTPServer((host, port), make_handler(data, backend))
    print(f"API http://{host}:{port} ({backend})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
