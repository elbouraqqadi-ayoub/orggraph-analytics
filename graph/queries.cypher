// Active snapshot only; direct edges from older snapshots are excluded.
MATCH (:Catalog {name:'active'})-[:ACTIVE]->(s:Snapshot)-[:HAS_FACT]->(f:FactVersion),
      (f)-[:SUBJECT]->(a:EntityVersion), (f)-[:OBJECT]->(b:EntityVersion)
RETURN a.name AS source, f.type AS relation, b.name AS target;

// Degree centrality on the active graph (facts counted once).
MATCH (:Catalog {name:'active'})-[:ACTIVE]->(:Snapshot)-[:HAS_FACT]->(f:FactVersion),
      (f)-[:SUBJECT|OBJECT]->(e:EntityVersion)
RETURN e.name AS entity, count(DISTINCT f) AS degree
ORDER BY degree DESC, entity;

// Provenance; parameter $fact_id.
MATCH (:Catalog {name:'active'})-[:ACTIVE]->(s:Snapshot)-[:HAS_FACT]->(f:FactVersion {id:$fact_id}),
      (f)-[p:SUPPORTED_BY]->(d:DocumentVersion), (s)-[:HAS_DOCUMENT]->(d)
RETURN d.source_uri AS source, p.chunk_id AS passage, p.evidence AS evidence,
       p.confidence AS confidence;
