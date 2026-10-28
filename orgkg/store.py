"""Cache immutable graphs; pin Neo4j reads to the observed active snapshot."""
import json
import threading
from pathlib import Path

from .services import active_snapshot_id, read_neo4j
from .validation import validate_graph


class GraphStore:
    def __init__(self, data: Path, backend="local"):
        self.path = data / "graph.json"
        self.backend = backend
        self._key = None
        self._graph = None
        self._lock = threading.Lock()

    def load(self):
        if self.backend == "neo4j":
            key = active_snapshot_id()
        else:
            stat = self.path.stat()
            key = (stat.st_ino, stat.st_mtime_ns, stat.st_size)
        with self._lock:
            if key != self._key:
                graph = (read_neo4j(key) if self.backend == "neo4j"
                         else json.loads(self.path.read_text(encoding="utf-8")))
                validate_graph(graph)
                self._graph, self._key = graph, key
            return self._graph
