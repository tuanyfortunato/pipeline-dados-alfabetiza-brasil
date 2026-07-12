"""
Consumer de streaming da camada Bronze: landing (JSON) -> Bronze (Parquet).

Spark Structured Streaming. Lê os eventos que o producer deixa na landing e
materializa micro-batches em Parquet, com os mesmos metadados de rastreabilidade
da Bronze batch. Roda no .venv-spark (ver docs/ambiente_spark.md).

Uso:
    python src/01_bronze/ingestao_streaming_consumer.py            # processa o que houver e encerra
    python src/01_bronze/ingestao_streaming_consumer.py --continuo # fica escutando (Ctrl+C para parar)
"""
import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from pyspark.sql import functions as F
from pyspark.sql.types import (
    DoubleType,
    IntegerType,
    LongType,
    StringType,
    StructField,
    StructType,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.utils.data_quality import (
    check_not_empty,
    check_range,
    check_required_columns,
    fail_if_critical,
    save_report,
)
from src.utils.logger import get_logger
from src.utils.spark_session import get_spark_session

load_dotenv()
logger = get_logger("bronze.streaming_consumer")

LAKE_PATH = os.environ.get("LAKE_PATH", "./data")
STREAMING = Path(LAKE_PATH) / "bronze" / "streaming"
LANDING = STREAMING / "landing"
OUTPUT = STREAMING / "eventos_indicador"
CHECKPOINT = STREAMING / "_checkpoint"
SOURCE = "streaming/landing"

# streaming não infere schema: precisa ser explícito
SCHEMA = StructType([
    StructField("id_municipio", LongType()),
    StructField("ano", IntegerType()),
    StructField("proficiencia_media", DoubleType()),
    StructField("tipo_evento", StringType()),
    StructField("event_timestamp", StringType()),
])
COLUNAS_FONTE = [c.name for c in SCHEMA.fields]


def rodar_dq(pdf) -> list[dict]:
    """DQ sobre o que foi materializado, reusando os checks do pipeline."""
    return [
        check_not_empty(pdf, "eventos_indicador"),
        check_required_columns(pdf, "eventos_indicador", COLUNAS_FONTE),
        check_range(pdf, "eventos_indicador", "proficiencia_media", 0, 1000),
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Consumer de streaming da Bronze.")
    parser.add_argument("--continuo", action="store_true",
                        help="fica escutando a landing (default: processa o disponível e encerra)")
    args = parser.parse_args()

    if not LANDING.exists():
        raise SystemExit(f"Landing não encontrada em {LANDING}. Rode o producer antes.")

    spark = get_spark_session("bronze-streaming-consumer")
    spark.sparkContext.setLogLevel("WARN")

    eventos = (
        spark.readStream
        .schema(SCHEMA)
        .json(str(LANDING))
        # mesmos metadados de rastreabilidade da Bronze batch
        .withColumn("_row_hash", F.sha2(F.concat_ws("|", *COLUNAS_FONTE), 256))
        .withColumn("_ingestion_ts", F.current_timestamp())
        .withColumn("_source", F.lit(SOURCE))
    )

    escrita = (
        eventos.writeStream
        .format("parquet")
        .option("path", str(OUTPUT))
        .option("checkpointLocation", str(CHECKPOINT))
        .partitionBy("ano")
    )
    escrita = escrita.trigger(processingTime="10 seconds") if args.continuo \
        else escrita.trigger(availableNow=True)

    logger.info("Consumindo %s -> %s", LANDING, OUTPUT)
    query = escrita.start()
    query.awaitTermination()

    if not OUTPUT.exists():
        logger.info("Nenhum evento materializado (landing vazia?). Nada a validar.")
        spark.stop()
        return

    # volume do streaming é pequeno; uma leitura para pandas serve para contar e validar
    pdf = spark.read.parquet(str(OUTPUT)).toPandas()
    checks = rodar_dq(pdf)
    report_path = save_report(checks, layer="bronze_streaming")
    logger.info("Streaming consumido: %d eventos na Bronze. DQ: %s", len(pdf), report_path)
    spark.stop()
    fail_if_critical(checks)


if __name__ == "__main__":
    main()
