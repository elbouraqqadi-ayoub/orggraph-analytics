import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from orgkg.comparison import compare
from orgkg.collect import collect
from orgkg.core import digest, retrieve
from orgkg.pipeline import run_pipeline
from orgkg.services import cypher, llm, load_neo4j, upload_hdfs
from orgkg.errors import BackendError


class IntegrationContractTest(unittest.TestCase):
    def test_collection_and_webhdfs_redirect(self):
        uploads = []

        class FakeService(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                body = b'<html><body>[A] ACQUIRED [B]</body></html>'
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(body)

            def do_PUT(self):
                if "op=CREATE" in self.path:
                    self.send_response(307)
                    self.send_header("Location", f"http://127.0.0.1:{self.server.server_port}/datanode")
                    self.end_headers()
                else:
                    body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                    if self.path == "/datanode":
                        uploads.append(body)
                    self.send_response(201 if self.path == "/datanode" else 200)
                    self.end_headers()
                    self.wfile.write(b'{"boolean":true}')

        server = ThreadingHTTPServer(("127.0.0.1", 0), FakeService)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            with tempfile.TemporaryDirectory() as temp:
                url = f"http://127.0.0.1:{server.server_port}"
                report = collect([url + "/report"], Path(temp) / "incoming")
                path = Path(report["documents"][0]["path"])
                with patch.dict(os.environ, {"HDFS_URL": url}):
                    upload_hdfs(path, "/orgkg/raw/test.html")
                self.assertEqual(uploads, [path.read_bytes()])
                result = run_pipeline(Path(temp) / "incoming", Path(temp) / "data")
                graph = json.loads((Path(temp) / "data/graph.json").read_text(encoding="utf-8"))
                self.assertEqual(result["facts"], 1)
                self.assertEqual(graph["documents"][0]["source_uri"], url + "/report")
        finally:
            server.shutdown()
            server.server_close()
            worker.join()

    def test_llm_http_contract_and_usage(self):
        fake = {"choices": [{"message": {"content": '{"entities":[],"relations":[]}'}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 50}}
        with patch.dict(os.environ, {"LLM_MODEL": "test", "LLM_BASE_URL": "http://localhost:11434/v1", "LLM_INPUT_USD_PER_MILLION": "2", "LLM_OUTPUT_USD_PER_MILLION": "4"}), patch("orgkg.services.request_json", return_value=fake) as request:
            _, metadata = llm([{"role": "user", "content": "test"}], True)
        self.assertAlmostEqual(metadata["estimated_cost_usd"], 0.0004)
        self.assertTrue(request.call_args.args[0].endswith("/chat/completions"))
        self.assertEqual(request.call_args.args[1]["response_format"], {"type": "json_object"})

    def test_neo4j_errors_are_not_silently_ignored(self):
        with patch.dict(os.environ, {"NEO4J_PASSWORD": "test-password"}), patch("orgkg.services.request_json", return_value={"errors": [{"code": "bad"}]}):
            with self.assertRaises(BackendError):
                cypher("RETURN 1")

    def test_snapshot_is_stable_and_activation_is_last(self):
        with tempfile.TemporaryDirectory() as temp:
            run_pipeline(Path("data/samples"), Path(temp), aliases=Path("config/aliases.json"))
            graph = json.loads((Path(temp) / "graph.json").read_text(encoding="utf-8"))
            with patch("orgkg.services.cypher", return_value=[]) as query:
                first = load_neo4j(graph)
                self.assertIn("Catalog", query.call_args.args[0])
                graph["documents"][0]["collected_at"] = "another-time"
                second = load_neo4j(graph)
                self.assertEqual(first, second)

    def test_comparison_matches_expected_contract(self):
        with tempfile.TemporaryDirectory() as temp:
            run_pipeline(Path("data/samples"), Path(temp), aliases=Path("config/aliases.json"))
            graph = json.loads((Path(temp) / "graph.json").read_text(encoding="utf-8"))
            graph["snapshot_id"] = "snapshot-test"
            nodes = {n["id"]: n["name"] for n in graph["nodes"]}

            def fake_query(query, parameters=None):
                if parameters is None:
                    return [{"data": [{"row": ["snapshot-test"]}]}]
                if not parameters["seeds"]:
                    facts = []
                else:
                    hops = 1 if "*0..0]" in query else 2
                    facts = retrieve(graph, nodes[parameters["seeds"][0]], hops)["facts"]
                return [{"data": [{"row": [f["id"]]} for f in facts]}]

            with patch("orgkg.comparison.read_neo4j", return_value=graph), patch("orgkg.comparison.cypher", side_effect=fake_query):
                report = compare(Path("evaluation/questions.json"), Path(temp) / "comparison.json")
            self.assertEqual(len(report["cases"]), 3)
            self.assertTrue(all(c["cypher"]["f1"] == 1 for c in report["cases"]))


if __name__ == "__main__":
    unittest.main()
