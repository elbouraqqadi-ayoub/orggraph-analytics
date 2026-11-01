"""Local dashboard operations; accepts no arbitrary commands, paths or Cypher."""
import base64
import hashlib
import json
import os
import re
import tempfile
import urllib.request
from pathlib import Path

from .pipeline import run_pipeline, write_json
from .services import load_neo4j


def original_document(graph: dict, identifier: str, data: Path):
    if not re.fullmatch(r"[0-9a-f]{24}",identifier):
        raise FileNotFoundError("Unknown document.")
    document=next((d for d in graph["documents"] if d["id"]==identifier),None)
    if document is None:raise FileNotFoundError("Unknown document.")
    for path in data.rglob(identifier+".*"):
        if (path.suffix.lower() in {".txt",".html",".htm",".json",".pdf",".docx"}
                and path.is_file() and path.resolve().is_relative_to(data.resolve())):
            content=path.read_bytes()
            if hashlib.sha256(content).hexdigest()==document["sha256"]:
                mime={".pdf":"application/pdf",".docx":"application/vnd.openxmlformats-officedocument.wordprocessingml.document"}.get(path.suffix.lower(),"text/plain")
                return content,mime,document["title"]
    raise FileNotFoundError("The source is not stored locally; use its original URL.")

WEB_ROOT = Path(__file__).parent / "web"
ASSETS = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"),
          "/styles.css": ("styles.css", "text/css")}


def model_status():
    model = os.environ.get("LLM_MODEL", "")
    result = {"configured": bool(model), "ready": False, "model": model or None}
    if not model:
        return result
    headers = {}
    if os.environ.get("LLM_API_KEY"):
        headers["Authorization"] = "Bearer " + os.environ["LLM_API_KEY"]
    try:
        request = urllib.request.Request(os.environ.get("LLM_BASE_URL", "http://localhost:11434/v1").rstrip("/") + "/models", headers=headers)
        with urllib.request.urlopen(request, timeout=3) as response:
            payload = json.load(response)
        result["ready"] = any(m.get("id") in {model, model + ":latest"} for m in payload.get("data", []))
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return result


def upload_document(payload: dict, data: Path, backend: str):
    filename, mode = payload.get("filename"), payload.get("mode", "rules")
    if (not isinstance(filename, str) or not 1 <= len(filename) <= 200
            or any(c in filename for c in ('/', '\\', '\x00', ':'))):
        raise ValueError("Invalid filename.")
    suffix = Path(filename).suffix.lower()
    if suffix not in {".txt", ".html", ".htm", ".json", ".pdf", ".docx"} or not isinstance(mode, str) or mode not in {"fixture", "rules", "llm"}:
        raise ValueError("Unsupported document format or extraction mode.")
    if not isinstance(payload.get("content"), str):
        raise ValueError("Base64 content is required.")
    content = base64.b64decode(payload["content"], validate=True)
    if not 0 < len(content) <= 10 * 1024 * 1024:
        raise ValueError("Documents must contain between 1 byte and 10 MB.")
    incoming = data / "incoming"
    incoming.mkdir(parents=True, exist_ok=True)
    name = hashlib.sha256(content).hexdigest()[:24] + suffix
    target = incoming / name
    target.write_bytes(content)
    write_json(target.with_suffix(suffix + ".meta"), {"title": filename, "source_uri": target.resolve().as_uri()})
    with tempfile.TemporaryDirectory(prefix=".upload-", dir=data) as folder:
        source = Path(folder)
        (source / name).write_bytes(content)
        write_json(source / (name + ".meta"), {"title": filename, "source_uri": target.resolve().as_uri()})
        aliases = Path("config/aliases.json")
        report = run_pipeline(source, data, mode, aliases if aliases.exists() else None, append=True)
    if report["published"] and backend == "neo4j":
        report["snapshot_id"] = load_neo4j(json.loads((data / "graph.json").read_text(encoding="utf-8")))
    return report


def reports(output=Path("output")):
    result = {}
    for key, filename in {"retrieval": "benchmark.json", "comparison": "comparison.json",
                          "services": "services_validation.json", "pipeline": "pipeline_validation.json", "llm": "llm_validation.json",
                          "local":"local_validation.json","gds":"gds.json","extraction_rules":"extraction_rules.json","extraction_llm":"extraction_llm.json"}.items():
        path = output / filename
        if path.exists() and path.stat().st_size <= 4 * 1024 * 1024:
            try:
                result[key] = json.loads(path.read_text(encoding="utf-8"))
            except ValueError:
                continue
    return result
