"""Validated Spark ETL using the same record contract as local ingestion."""
import json
import sys
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from pyspark import StorageLevel
from pyspark.sql import SparkSession, functions as F, types as T

from orgkg.core import entity_id, normalize
from orgkg.validation import validate_aliases, validate_json_line
from orgkg.publication import publish_directory


def record_schema():
    entity = T.StructType([T.StructField("name", T.StringType()), T.StructField("kind", T.StringType())])
    relation = T.StructType([T.StructField(k, T.StringType()) for k in ("source", "target", "type", "evidence")]
                            + [T.StructField("confidence", T.DoubleType())])
    document = T.StructType([T.StructField(k, T.StringType())
                             for k in ("id", "title", "source_uri", "sha256", "raw_path", "collected_at")])
    return T.StructType([
        T.StructField("document", document), T.StructField("chunk_id", T.StringType()),
        T.StructField("text", T.StringType()),
        T.StructField("extraction", T.StructType([
            T.StructField("entities", T.ArrayType(entity)), T.StructField("relations", T.ArrayType(relation))]))])


def transform(spark, input_path, output, alias_path="/app/config/aliases.json"):
    output = output.rstrip("/")
    if not output or urlsplit(output).path in {"", "/", ".", ".."} or output.endswith(("/.", "/..")):
        raise ValueError("Un dossier de sortie dédié est requis.")
    aliases = validate_aliases(json.loads(Path(alias_path).read_text(encoding="utf-8")))
    run_id = uuid.uuid4().hex
    staging = output + "_staging_" + run_id
    audit = output + "_validation/" + run_id
    rows = spark.read.text(input_path).rdd.map(lambda r: r.value).filter(lambda s: bool(s.strip()))
    envelope = spark.createDataFrame(rows.map(validate_json_line),
        T.StructType([T.StructField(k, T.StringType()) for k in ("record_json", "error", "raw")]))
    envelope.persist(StorageLevel.MEMORY_AND_DISK)
    try:
        rejected = envelope.filter(F.col("error").isNotNull()).select("error", "raw")
        rejected_count = rejected.count()
        rejected.write.mode("errorifexists").json(audit + "/rejected")
        if rejected_count:
            raise ValueError(f"{rejected_count} enregistrements invalides ; sortie précédente préservée. Rejets : {audit}")
        if not envelope.count():
            raise ValueError("Entrée Spark vide ; sortie précédente préservée.")
        # Explicit schema supports documents with empty extraction lists.
        records = spark.read.schema(record_schema()).json(envelope.select("record_json").rdd.map(lambda r: r.record_json))
        documents = records.select("document.*").dropDuplicates(["id"])
        versions = records.select("document.id", "document.title", "document.source_uri", "document.sha256").distinct()
        if versions.groupBy("id").count().filter(F.col("count") > 1).limit(1).count():
            raise ValueError("Métadonnées contradictoires pour un même document.")
        if records.select("chunk_id", "text", "extraction").distinct().groupBy("chunk_id").count().filter(F.col("count") > 1).limit(1).count():
            raise ValueError("Plusieurs contenus contradictoires pour un même passage.")
        canonical = F.udf(lambda name: aliases.get(normalize(name), name), T.StringType())
        identifier = F.udf(entity_id, T.StringType())
        mentions = records.select(F.col("document.id").alias("document_id"), "chunk_id",
                                  F.explode("extraction.entities").alias("entity"))
        mentions = mentions.select("document_id", "chunk_id", F.col("entity.name").alias("mention"), "entity.kind")
        mentions = mentions.withColumn("name", canonical("mention")).withColumn("id", identifier("name", "kind"))
        nodes = mentions.groupBy("id", "name", "kind").agg(F.sort_array(F.collect_set("mention")).alias("aliases"))
        relations = records.select(F.col("document.id").alias("document_id"), "chunk_id",
                                   F.explode("extraction.relations").alias("relation"))
        relations = relations.select("document_id", "chunk_id", F.col("relation.source").alias("source_name"),
                                     F.col("relation.target").alias("target_name"), "relation.type", "relation.evidence", "relation.confidence")
        source_lookup = mentions.select("document_id", "chunk_id", F.col("mention").alias("source_name"), F.col("id").alias("source")).distinct()
        target_lookup = mentions.select("document_id", "chunk_id", F.col("mention").alias("target_name"), F.col("id").alias("target")).distinct()
        resolved = relations.join(source_lookup, ["document_id", "chunk_id", "source_name"], "left").join(
            target_lookup, ["document_id", "chunk_id", "target_name"], "left")
        if resolved.filter(F.col("source").isNull() | F.col("target").isNull()).limit(1).count():
            raise ValueError("Une relation référence une entité absente ; aucune publication.")
        resolved = resolved.dropDuplicates(["document_id", "chunk_id", "source", "target", "type", "evidence", "confidence"])
        resolved = resolved.withColumn("id", F.substring(F.sha2(F.concat_ws(":", "source", "type", "target"), 256), 1, 24))
        facts = resolved.groupBy("id", "source", "target", "type").agg(
            F.sort_array(F.collect_set(F.struct("document_id", "chunk_id", "evidence", "confidence"))).alias("supports"))
        # Never overwrite the destination during validation or transformation.
        nodes.select(F.col("id").alias("entity_id"), "name", "kind").write.mode("errorifexists").parquet(staging + "/entities")
        resolved.write.mode("errorifexists").parquet(staging + "/relations")
        nodes.write.mode("errorifexists").json(staging + "/nodes")
        facts.write.mode("errorifexists").json(staging + "/facts")
        documents.write.mode("errorifexists").json(staging + "/documents")
        counts = {"entities": nodes.count(), "facts": facts.count(), "rejected": rejected_count}
        jpath = spark._jvm.org.apache.hadoop.fs.Path
        fs = jpath(output).getFileSystem(spark._jsc.hadoopConfiguration())
        previous = publish_directory(fs, jpath, staging, output, run_id)
        return {**counts, "output": output, "previous_output": previous, "audit": audit, "published": True}
    finally:
        envelope.unpersist()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("Usage: spark-submit transform.py input.jsonl output_directory")
    spark = SparkSession.builder.appName("OrganizationKG-ETL").getOrCreate()
    spark.sparkContext.setLogLevel("WARN")
    try:
        print(json.dumps(transform(spark, sys.argv[1], sys.argv[2])))
    finally:
        spark.stop()
