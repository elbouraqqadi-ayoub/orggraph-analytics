import base64
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from http.server import ThreadingHTTPServer
from orgkg.core import analytics, read_document, rules_extract, validate_extraction
from orgkg.dashboard import upload_document,original_document
from orgkg.evaluation import evaluate_extraction
from orgkg.pipeline import run_pipeline
from orgkg.server import make_handler


class DashboardTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.data = Path(self.temp.name)/"data"
        run_pipeline(Path("data/samples"),self.data,aliases=Path("config/aliases.json"))

    def tearDown(self):
        self.temp.cleanup()

    def test_static_dashboard_is_public_but_data_stays_authenticated(self):
        with patch.dict(os.environ,{"API_TOKEN":"test-token"}):
            server=ThreadingHTTPServer(("127.0.0.1",0),make_handler(self.data))
            thread=threading.Thread(target=server.serve_forever,daemon=True)
            thread.start()
            try:
                base=f"http://127.0.0.1:{server.server_port}"
                for route,mime in [("/","text/html"),("/app.js","text/javascript"),("/styles.css","text/css")]:
                    with urllib.request.urlopen(base+route) as response:
                        self.assertIn(mime,response.headers["Content-Type"])
                        self.assertIn("frame-ancestors 'none'",response.headers["Content-Security-Policy"])
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    urllib.request.urlopen(base+"/graph")
                self.assertEqual(caught.exception.code,401)
                caught.exception.close()
                request=urllib.request.Request(base+"/upload",data=b'{}',headers={"Authorization":"Bearer test-token","Origin":"https://untrusted.example"})
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    urllib.request.urlopen(request)
                self.assertEqual(caught.exception.code,403)
                caught.exception.close()
            finally:
                server.shutdown();server.server_close();thread.join()

    def test_upload_appends_without_duplicate_documents(self):
        content=base64.b64encode(b"Acme acquired Beta.").decode()
        payload={"filename":"acquisition.txt","content":content,"mode":"rules"}
        first=upload_document(payload,self.data,"local")
        second=upload_document(payload,self.data,"local")
        self.assertTrue(first["published"])
        self.assertEqual((first["documents"],first["entities"],first["facts"]),(5,12,10))
        self.assertEqual((second["documents"],second["entities"],second["facts"]),(5,12,10))

    def test_invalid_uploads_leave_graph_unchanged(self):
        original=(self.data/"graph.json").read_bytes()
        for filename,content in [("../bad.txt","YQ=="),("bad.exe","YQ=="),("bad.txt","not-base64")]:
            with self.assertRaises(ValueError):
                upload_document({"filename":filename,"content":content},self.data,"local")
        report=upload_document({"filename":"bad.docx","content":base64.b64encode(b"not a docx").decode()},self.data,"local")
        self.assertFalse(report["published"])
        self.assertEqual((self.data/"graph.json").read_bytes(),original)

    def test_word_document_extraction(self):
        path=Path(self.temp.name)/"input.docx"
        with ZipFile(path,"w") as archive:
            archive.writestr("word/document.xml",'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Acme acquired Beta.</w:t></w:r></w:p></w:body></w:document>')
        self.assertEqual(read_document(path),"Acme acquired Beta.")

    def test_rules_do_not_cross_sentence_boundaries(self):
        text="Acme acquired Beta. Gamma is based in Paris. No association is implied."
        result=validate_extraction(rules_extract(text),text)
        self.assertEqual({(r["source"],r["type"],r["target"]) for r in result["relations"]},
                         {("Acme","ACQUIRED","Beta"),("Gamma","LOCATED_IN","Paris")})
        self.assertFalse(rules_extract("No company relationship is stated here.")["relations"])

    def test_reference_corpus_has_independent_expected_extractions(self):
        report=evaluate_extraction(Path("data/reference"),Path("evaluation/extraction_gold.json"))
        self.assertEqual(report["entity_metrics"]["expected"],4)
        self.assertEqual(report["relation_metrics"]["expected"],2)
        self.assertEqual(report["relation_metrics"]["f1"],1)
        self.assertTrue(all(not c["errors"] for c in report["cases"]))

    def test_pagerank_is_normalized_and_handles_empty_graphs(self):
        graph=json.loads((self.data/"graph.json").read_text(encoding="utf-8"))
        stats=analytics(graph)
        self.assertAlmostEqual(sum(n["score"] for n in stats["pagerank"]),1,places=8)
        self.assertEqual(len(stats["pagerank"]),len(graph["nodes"]))
        self.assertEqual(analytics({"nodes":[],"facts":[],"documents":[]})["pagerank"],[])

    def test_original_download_is_scoped_to_registered_content(self):
        graph=json.loads((self.data/"graph.json").read_text(encoding="utf-8"))
        document=graph["documents"][0]
        body,mime,title=original_document(graph,document["id"],self.data)
        import hashlib
        self.assertEqual(hashlib.sha256(body).hexdigest(),document["sha256"])
        self.assertEqual(title,document["title"])
        with self.assertRaises(FileNotFoundError):
            original_document(graph,"../../.env",self.data)
        for path in (self.data/"raw").glob(document["id"]+".*"):path.write_bytes(b"tampered")
        with self.assertRaises(FileNotFoundError):
            original_document(graph,document["id"],self.data)

    def test_model_schema_retry_counts_both_attempts(self):
        from orgkg.services import extract_llm
        valid={"entities":[{"name":"Acme","kind":"Organization"},{"name":"Beta","kind":"Organization"}],"relations":[{"source":"Acme","target":"Beta","type":"ACQUIRED","evidence":"Acme acquired Beta","confidence":0.9}]}
        metadata={"seconds":1,"usage":{"prompt_tokens":10,"completion_tokens":20},"estimated_cost_usd":0.01}
        with patch("orgkg.services.llm",side_effect=[('not json',metadata),(json.dumps(valid),metadata)]):
            extracted,report=extract_llm("Acme acquired Beta.")
        self.assertEqual(extracted["relations"][0]["type"],"ACQUIRED")
        self.assertEqual(report["attempts"],2)
        self.assertEqual(report["usage"]["prompt_tokens"],20)
        self.assertAlmostEqual(report["estimated_cost_usd"],0.02)

    def test_model_answer_without_valid_citations_falls_back_to_facts(self):
        from orgkg.pipeline import answer
        graph=json.loads((self.data/"graph.json").read_text(encoding="utf-8"))
        for generated in ("Unsupported uncited claim", "Wrong source [000000000000000000000000]"):
            with patch("orgkg.pipeline.llm",return_value=(generated,{})):
                result=answer(graph,"Atlas Industries","llm")
            self.assertIn("fallback",result["metadata"])
            self.assertNotIn(generated,result["answer"])
            self.assertTrue(all("["+row["fact_id"]+"]" in result["answer"] for row in result["context"]))


if __name__=="__main__":unittest.main()
