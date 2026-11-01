import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from orgkg.core import analytics, chunks, fixture_extract, retrieve, validate_extraction
from orgkg.pipeline import answer, benchmark, run_pipeline
from orgkg.server import make_handler


class PlatformTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.data = Path(self.temp.name) / "data"
        self.report = run_pipeline(Path("data/samples"), self.data, aliases=Path("config/aliases.json"))
        self.graph = json.loads((self.data / "graph.json").read_text(encoding="utf-8"))

    def tearDown(self):
        self.temp.cleanup()

    def test_pipeline_provenance_and_alias_resolution(self):
        self.assertEqual((self.report["documents"], self.report["entities"], self.report["facts"]), (4, 10, 9))
        partnership = next(f for f in self.graph["facts"] if f["type"] == "PARTNERS_WITH")
        self.assertEqual(len(partnership["supports"]), 2)
        self.assertEqual(analytics(self.graph)["facts"], 9)

    def test_reexecution_does_not_duplicate(self):
        run_pipeline(Path("data/samples"), self.data, aliases=Path("config/aliases.json"))
        graph2 = json.loads((self.data / "graph.json").read_text(encoding="utf-8"))
        self.assertEqual(self.graph["facts"], graph2["facts"])
        self.assertEqual(self.graph["nodes"], graph2["nodes"])

    def test_hallucinated_evidence_is_rejected(self):
        text = "[A] ACQUIRED [B]"
        result = fixture_extract(text)
        result["relations"][0]["evidence"] = "A acquired C"
        with self.assertRaises(ValueError):
            validate_extraction(result, text)

    def test_wrong_relation_endpoint_type_is_rejected(self):
        text = "[A] LOCATED_IN [B]"
        result = fixture_extract(text)
        result["entities"][1]["kind"] = "Organization"
        with self.assertRaises(ValueError):
            validate_extraction(result, text)

    def test_multihop_and_abstention(self):
        self.assertEqual(len(retrieve(self.graph, "Atlas Industries", 1)["facts"]), 3)
        self.assertEqual(len(retrieve(self.graph, "Atlas Industries", 2)["facts"]), 6)
        self.assertEqual(len(retrieve(self.graph, "Quels liens autour d'Atlas Industries?", 1)["facts"]), 3)
        self.assertFalse(retrieve(self.graph, "Atlas IndustriesXYZ", 1)["facts"])
        self.assertFalse(answer(self.graph, "Inconnue SA")["context"])
        with self.assertRaises(ValueError):
            retrieve(self.graph, "Atlas Industries", 9)

    def test_chunks_cover_all_text(self):
        text = "abcdef" * 1000
        passages = list(chunks(text))
        self.assertEqual(passages[0][0], 0)
        self.assertEqual(passages[-1][1], len(text))
        for start, end, passage in passages:
            self.assertEqual(passage, text[start:end])

    def test_benchmark_fixture(self):
        result = benchmark(self.graph, Path("evaluation/questions.json"), Path(self.temp.name) / "benchmark.json")
        self.assertEqual(result["mean_retrieval_f1"], 1)

    def test_llm_path_uses_provider_and_validates_output(self):
        with patch("orgkg.pipeline.extract_llm", side_effect=lambda text: (fixture_extract(text), {"model": "mock"})) as provider:
            result = run_pipeline(Path("data/samples"), self.data, "llm", Path("config/aliases.json"))
        self.assertEqual(provider.call_count, 4)
        self.assertEqual(result["facts"], 9)
        cited_answer = "Réponse sourcée [" + self.graph["facts"][0]["id"] + "]"
        with patch("orgkg.pipeline.llm", return_value=(cited_answer, {"model": "mock"})) as provider:
            response = answer(self.graph, "Atlas Industries", "llm")
        self.assertEqual(response["answer"], cited_answer)
        self.assertIn("fact_id", provider.call_args.args[0][1]["content"])

    def test_api_auth_and_validation(self):
        with patch.dict(os.environ, {"API_TOKEN": "test-token"}):
            server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.data))
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            base = f"http://127.0.0.1:{server.server_port}"
            try:
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    urllib.request.urlopen(base + "/graph")
                self.assertEqual(caught.exception.code, 401)
                caught.exception.close()
                request = urllib.request.Request(base + "/ask", data=json.dumps({"question": "Atlas Industries"}).encode(), headers={"Authorization": "Bearer test-token"})
                with urllib.request.urlopen(request) as response:
                    self.assertEqual(len(json.load(response)["context"]), 6)
                bad = urllib.request.Request(base + "/ask", data=b'{"question":123}', headers={"Authorization": "Bearer test-token"})
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    urllib.request.urlopen(bad)
                self.assertEqual(caught.exception.code, 400)
                caught.exception.close()
            finally:
                server.shutdown()
                server.server_close()
                worker.join()


if __name__ == "__main__":
    unittest.main()
