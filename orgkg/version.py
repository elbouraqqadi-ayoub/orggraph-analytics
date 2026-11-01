"""Fingerprint packaged source so acceptance reports can identify the tested build."""
import hashlib
from pathlib import Path


def source_fingerprint():
    root=Path(__file__).parent
    digest=hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix in {".py",".js",".css",".html",".svg"} and "__pycache__" not in path.parts:
            digest.update(path.relative_to(root).as_posix().encode())
            digest.update(path.read_text(encoding="utf-8").replace("\r\n","\n").encode("utf-8"))
    return digest.hexdigest()[:16]
