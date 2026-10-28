"""Explicit URL collection, no recursive crawler and no implicit external calls."""
import hashlib
import urllib.parse
import urllib.request
from pathlib import Path

from .pipeline import write_json


def collect(urls: list[str], destination: Path) -> dict:
    destination.mkdir(parents=True, exist_ok=True)
    results = []
    for url in urls:
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("URL HTTP(S) publique sans identifiants requise.")
        request = urllib.request.Request(url, headers={"User-Agent": "OrganizationKG-Research/0.1"})
        with urllib.request.urlopen(request, timeout=30) as response:
            content_type = response.headers.get_content_type()
            suffix = {"text/html": ".html", "application/pdf": ".pdf", "text/plain": ".txt", "application/json": ".json"}.get(content_type)
            if suffix is None:
                raise ValueError(f"Format distant non pris en charge : {content_type}")
            body = response.read(10 * 1024 * 1024 + 1)
            if len(body) > 10 * 1024 * 1024:
                raise ValueError("Document supérieur à 10 Mo.")
            if suffix != ".pdf":
                body = body.decode(response.headers.get_content_charset() or "utf-8").encode("utf-8")
            final_url = response.url
        filename = hashlib.sha256(url.encode()).hexdigest()[:24] + suffix
        target = destination / filename
        target.write_bytes(body)
        write_json(target.with_suffix(suffix + ".meta"), {"source_uri": final_url, "title": parsed.hostname + parsed.path})
        results.append({"url": url, "path": str(target), "bytes": len(body)})
    return {"documents": results}
