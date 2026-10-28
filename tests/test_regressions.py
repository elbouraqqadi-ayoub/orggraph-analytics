import copy
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

from orgkg.core import fixture_extract
from orgkg.errors import BackendError, ConfigurationError
from orgkg.pipeline import import_spark, run_pipeline, write_json
from orgkg.server import make_handler
from orgkg.services import load_neo4j, read_neo4j
from orgkg.snapshots import prepare_snapshot
from orgkg.store import GraphStore
from orgkg.validation import validate_aliases, validate_graph, validate_json_line
from orgkg.publication import publish_directory


class RegressionTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.data = self.root / "data"
        run_pipeline(Path("data/samples"), self.data, aliases=Path("config/aliases.json"))
        self.graph = json.loads((self.data / "graph.json").read_text(encoding="utf-8"))
        self.record = json.loads((self.data / "processed/extractions.jsonl").read_text(encoding="utf-8").splitlines()[0])

    def tearDown(self):
        self.temp.cleanup()

    def test_mixed_ingestion_failure_preserves_successful_outputs(self):
        original_graph = (self.data / "graph.json").read_bytes()
        original_export = (self.data / "processed/extractions.jsonl").read_bytes()
        original_report = (self.data / "processed/ingestion_report.json").read_bytes()
        source = self.root / "incoming"
        source.mkdir()
        (source / "good.txt").write_text("[New Org] ACQUIRED [Target]", encoding="utf-8")
        (source / "bad.json").write_text('{"wrong":"format"}', encoding="utf-8")
        result = run_pipeline(source, self.data)
        self.assertFalse(result["published"])
        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual((self.data / "graph.json").read_bytes(), original_graph)
        self.assertEqual((self.data / "processed/extractions.jsonl").read_bytes(), original_export)
        self.assertEqual((self.data / "processed/ingestion_report.json").read_bytes(), original_report)
        self.assertFalse(json.loads((self.data / "processed/last_attempt.json").read_text())["published"])

    def test_initial_failed_ingestion_never_creates_a_graph(self):
        source = self.root / "invalid"
        source.mkdir()
        (source / "empty.txt").write_text("", encoding="utf-8")
        result = run_pipeline(source, self.root / "new_data")
        self.assertFalse(result["published"])
        self.assertFalse((self.root / "new_data/graph.json").exists())

    def test_failed_later_chunk_does_not_keep_partial_document(self):
        source = self.root / "long"
        source.mkdir()
        (source / "long.txt").write_text("[A] ACQUIRED [B] " + "x" * 3000, encoding="utf-8")
        with patch("orgkg.pipeline.extract_llm", side_effect=[(fixture_extract("[A] ACQUIRED [B]"), {}), BackendError("provider failure")]):
            report = run_pipeline(source, self.data, "llm")
        self.assertFalse(report["published"])
        self.assertEqual(report["chunks"], 0)
        self.assertEqual(report["documents"], 0)

    def test_invalid_alias_config_preserves_the_graph(self):
        aliases = self.root / "aliases.json"
        aliases.write_text('["bad config"]', encoding="utf-8")
        original = (self.data / "graph.json").read_bytes()
        with self.assertRaises(ValueError):
            run_pipeline(Path("data/samples"), self.data, aliases=aliases)
        self.assertEqual((self.data / "graph.json").read_bytes(), original)
        with self.assertRaises(ValueError):
            validate_aliases({"Café": "One", "Cafe": "Two"})

    def test_atomic_graph_write_failure_keeps_previous_file(self):
        original = (self.data / "graph.json").read_bytes()
        with patch.object(Path, "replace", side_effect=OSError("disk failure")):
            with self.assertRaises(OSError):
                write_json(self.data / "graph.json", {"new": "data"})
        self.assertEqual((self.data / "graph.json").read_bytes(), original)
        self.assertFalse(list(self.data.glob("graph.json.*.tmp")))

    def test_graph_commit_failure_restores_previous_extraction_export(self):
        source = self.root / "replacement"
        source.mkdir()
        (source / "new.txt").write_text("[New] ACQUIRED [Target]", encoding="utf-8")
        previous_graph = (self.data / "graph.json").read_bytes()
        previous_export = (self.data / "processed/extractions.jsonl").read_bytes()
        replace = Path.replace

        def fail_commit(path, target):
            if Path(target) == self.data / "graph.json":
                raise OSError("graph publication failed")
            return replace(path, target)

        with patch.object(Path, "replace", fail_commit):
            with self.assertRaises(OSError):
                run_pipeline(source, self.data)
        self.assertEqual((self.data / "graph.json").read_bytes(), previous_graph)
        self.assertEqual((self.data / "processed/extractions.jsonl").read_bytes(), previous_export)

    def test_spark_directory_publication_preserves_and_restores_previous_export(self):
        target, staging = self.root / "curated", self.root / "staging"
        target.mkdir()
        staging.mkdir()
        (target / "old.txt").write_text("previous data")
        (staging / "new.txt").write_text("new data")

        class LocalFilesystem:
            fail_publish = True

            def exists(self, path):
                return path.exists()

            def rename(self, source, destination):
                if self.fail_publish and source == staging:
                    return False
                source.rename(destination)
                return True

        fs = LocalFilesystem()
        with self.assertRaises(OSError):
            publish_directory(fs, Path, str(staging), str(target), "failed")
        self.assertEqual((target / "old.txt").read_text(), "previous data")
        self.assertTrue((staging / "new.txt").exists())
        fs.fail_publish = False
        backup = publish_directory(fs, Path, str(staging), str(target), "success")
        self.assertEqual((target / "new.txt").read_text(), "new data")
        self.assertEqual((Path(backup) / "old.txt").read_text(), "previous data")

    def test_failed_rollback_keeps_recovery_files(self):
        source = self.root / "new_source"
        source.mkdir()
        (source / "new.txt").write_text("[New] ACQUIRED [Target]", encoding="utf-8")
        previous_graph = (self.data / "graph.json").read_bytes()
        previous_export = (self.data / "processed/extractions.jsonl").read_bytes()
        replace = Path.replace

        def fail_commit_and_rollback(path, target):
            if Path(target) == self.data / "graph.json" or path.name == "previous.jsonl":
                raise OSError("filesystem error")
            return replace(path, target)

        with patch.object(Path, "replace", fail_commit_and_rollback):
            with self.assertRaisesRegex(OSError, "récupération"):
                run_pipeline(source, self.data)
        self.assertEqual((self.data / "graph.json").read_bytes(), previous_graph)
        backups = list(self.data.glob(".ingestion-*/previous.jsonl"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), previous_export)

    def test_conflicting_confidence_for_same_proof_is_rejected(self):
        graph = copy.deepcopy(self.graph)
        duplicate = {**graph["facts"][0]["supports"][0], "confidence": 0.5}
        graph["facts"][0]["supports"].append(duplicate)
        with self.assertRaises(ValueError):
            validate_graph(graph)

    def test_spark_worker_uses_the_complete_validation_contract(self):
        value, error, _ = validate_json_line(json.dumps(self.record))
        self.assertIsNone(error)
        self.assertEqual(json.loads(value)["extraction"], self.record["extraction"])
        invalid = []
        for field, value in [("source", "Missing"), ("source", []), ("type", "INVENTED"),
                             ("evidence", "invented quote"), ("confidence", True), ("confidence", 2)]:
            record = copy.deepcopy(self.record)
            record["extraction"]["relations"][0][field] = value
            invalid.append(record)
        record = copy.deepcopy(self.record)
        record["extraction"]["entities"][0]["kind"] = "Location"
        invalid.append(record)
        record = copy.deepcopy(self.record)
        record["end"] += 1
        invalid.append(record)
        record = copy.deepcopy(self.record)
        record["document"]["id"] = "wrong"
        invalid.append(record)
        for record in invalid:
            with self.subTest(record=record):
                result, error, raw = validate_json_line(json.dumps(record))
                self.assertIsNone(result)
                self.assertTrue(error)
                self.assertIsNotNone(raw)
        self.assertIsNotNone(validate_json_line("not json")[1])

    def test_empty_extraction_is_valid(self):
        record = copy.deepcopy(self.record)
        record["extraction"] = {"entities": [], "relations": []}
        self.assertIsNone(validate_json_line(json.dumps(record))[1])

    def test_import_spark_rejects_dangling_entities_and_documents(self):
        folder = self.root / "curated"
        for key in ("nodes", "facts", "documents"):
            (folder / key).mkdir(parents=True)
        original = (self.data / "graph.json").read_bytes()
        for corrupt in ("entity", "document", "type"):
            graph = copy.deepcopy(self.graph)
            if corrupt == "entity":
                graph["facts"][0]["target"] = "unknown"
            elif corrupt == "document":
                graph["facts"][0]["supports"][0]["document_id"] = "unknown"
            else:
                graph["nodes"][0]["kind"] = "Invalid"
            for key in ("nodes", "facts", "documents"):
                (folder / key / "part-0000.json").write_text("\n".join(json.dumps(row) for row in graph[key]), encoding="utf-8")
            with self.assertRaises(ValueError):
                import_spark(folder, self.data)
            self.assertEqual((self.data / "graph.json").read_bytes(), original)

    def test_import_spark_accepts_a_valid_export(self):
        folder = self.root / "valid_export"
        for key in ("nodes", "facts", "documents"):
            (folder / key).mkdir(parents=True)
            (folder / key / "part-0000.json").write_text("\n".join(json.dumps(row) for row in self.graph[key]), encoding="utf-8")
        self.assertEqual(import_spark(folder, self.root / "imported"), self.graph)

    def test_snapshot_identity_ignores_order_and_collection_time(self):
        previous = prepare_snapshot(self.graph)
        graph = copy.deepcopy(self.graph)
        for key in ("nodes", "facts", "documents"):
            graph[key].reverse()
        for node in graph["nodes"]:
            node["aliases"].reverse()
        for fact in graph["facts"]:
            fact["supports"].reverse()
            for support in fact["supports"]:
                support["confidence"] = int(support["confidence"])
        graph["documents"][0]["collected_at"] = "another-time"
        self.assertEqual(previous, prepare_snapshot(graph))

    def test_snapshot_versions_isolate_aliases_metadata_and_confidence(self):
        original = prepare_snapshot(self.graph)
        graph = copy.deepcopy(self.graph)
        graph["nodes"][0]["aliases"].append("new alias")
        graph["documents"][0]["title"] = "new title"
        graph["facts"][0]["supports"][0]["confidence"] = 0.5
        changed = prepare_snapshot(graph)
        self.assertNotEqual(original["id"], changed["id"])
        for key in ("nodes", "documents", "facts"):
            self.assertFalse({n["key"] for n in original[key]} & {n["key"] for n in changed[key]})
        self.assertFalse({(s["fact_key"], s["document_key"]) for s in original["supports"]}
                         & {(s["fact_key"], s["document_key"]) for s in changed["supports"]})
        self.assertEqual(original, prepare_snapshot(self.graph))

    def test_failed_snapshot_load_never_activates_the_new_snapshot(self):
        calls = []

        def fail_supports(statement, parameters=None):
            calls.append(statement)
            if "SUPPORTED_BY" in statement:
                raise BackendError("write failed")
            return []

        with patch("orgkg.services.cypher", side_effect=fail_supports):
            with self.assertRaises(BackendError):
                load_neo4j(self.graph)
        self.assertFalse(any("SET s.ready=true" in query for query in calls))

    def test_invalid_graph_rejected_before_any_neo4j_write(self):
        graph = copy.deepcopy(self.graph)
        graph["facts"][0]["source"] = "unknown"
        with patch("orgkg.services.cypher") as query:
            with self.assertRaises(ValueError):
                load_neo4j(graph)
            query.assert_not_called()

    def test_neo4j_load_batches_relations_and_preserves_immutable_properties(self):
        with patch("orgkg.services.cypher", return_value=[]) as query:
            load_neo4j(self.graph, batch_size=2)
        fact_batches = []
        for call in query.call_args_list:
            statement = call.args[0]
            if len(call.args) > 1 and "rows" in call.args[1]:
                self.assertLessEqual(len(call.args[1]["rows"]), 2)
                self.assertIn("ON CREATE SET", statement)
            if "MERGE (f:FactVersion" in statement:
                fact_batches.extend(call.args[1]["rows"])
        self.assertEqual(len(fact_batches), len(self.graph["facts"]))
        self.assertIn("SET s.ready=true", query.call_args.args[0])

    def test_legacy_snapshot_requires_an_explicit_reimport(self):
        response = [{"columns": ["nodes", "facts", "documents", "snapshot_id", "schema_version", "ready"],
                     "data": [{"row": [[], [], [], "old", None, None]}]}]
        with patch("orgkg.services.cypher", return_value=response):
            with self.assertRaises(ConfigurationError):
                read_neo4j()

    def test_graph_cache_reloads_only_after_snapshot_change(self):
        first = {**self.graph, "snapshot_id": "first"}
        second = copy.deepcopy(first)
        second["snapshot_id"] = "second"
        second["documents"][0]["title"] = "Updated"
        with patch("orgkg.store.active_snapshot_id", side_effect=["first", "first", "second"]), patch("orgkg.store.read_neo4j", side_effect=[first, second]) as read:
            store = GraphStore(self.data, "neo4j")
            self.assertIs(store.load(), first)
            self.assertIs(store.load(), first)
            self.assertIs(store.load(), second)
            self.assertEqual([c.args[0] for c in read.call_args_list], ["first", "second"])

    def test_local_graph_cache_observes_atomic_replacement(self):
        store = GraphStore(self.data)
        first = store.load()
        self.assertIs(store.load(), first)
        changed = copy.deepcopy(self.graph)
        changed["documents"][0]["title"] = "new title"
        write_json(self.data / "graph.json", changed)
        self.assertEqual(store.load()["documents"][0]["title"], "new title")

    def test_api_distinguishes_request_configuration_and_backend_errors(self):
        with patch.dict(os.environ, {"API_TOKEN": ""}):
            server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.data))
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                url = f"http://127.0.0.1:{server.server_port}/ask"
                for failure, expected in [(ConfigurationError("secret configuration"), 500), (BackendError("private backend details"), 503)]:
                    with patch("orgkg.store.GraphStore.load", side_effect=failure):
                        request = urllib.request.Request(url, data=b'{"question":"Atlas Industries"}')
                        with self.assertRaises(urllib.error.HTTPError) as caught:
                            urllib.request.urlopen(request)
                        self.assertEqual(caught.exception.code, expected)
                        body = caught.exception.read().decode()
                        self.assertNotIn(str(failure), body)
                        caught.exception.close()
                with patch("orgkg.store.GraphStore.load") as load:
                    request = urllib.request.Request(url, data=b'{"question":"Atlas Industries","mode":[]}')
                    with self.assertRaises(urllib.error.HTTPError) as caught:
                        urllib.request.urlopen(request)
                    self.assertEqual(caught.exception.code, 400)
                    caught.exception.close()
                    load.assert_not_called()
            finally:
                server.shutdown()
                server.server_close()
                worker.join()


if __name__ == "__main__":
    unittest.main()
