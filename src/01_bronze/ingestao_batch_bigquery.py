"""
Ingestão batch da camada Bronze: BigQuery (Base dos Dados) -> Data Lake.

Uso:
    python src/01_bronze/ingestao_batch_bigquery.py            # todas as entidades
    python src/01_bronze/ingestao_batch_bigquery.py alunos uf  # apenas as citadas
"""
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from google.cloud import bigquery

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.utils.data_quality import (
    check_not_empty,
    check_required_columns,
    fail_if_critical,
    save_report,
)
from src.utils.logger import get_logger

load_dotenv()
logger = get_logger("bronze.ingestao_batch")

GCP_PROJECT_ID = os.environ["GCP_PROJECT_ID"]
LAKE_PATH = os.environ.get("LAKE_PATH", "./data")
DATASET = "basedosdados.br_inep_avaliacao_alfabetizacao"

ENTITIES = {
    "alunos": {"required": ["ano", "id_municipio", "proficiencia"], "partition": "ano"},
    "municipio": {"required": ["id_municipio"], "partition": None},
    "uf": {"required": ["sigla_uf"], "partition": None},
    "meta_alfabetizacao_brasil": {"required": ["ano"], "partition": None},
    "meta_alfabetizacao_uf": {"required": ["ano", "sigla_uf"], "partition": None},
    "meta_alfabetizacao_municipio": {"required": ["ano", "id_municipio"], "partition": None},
}


def ingest_table(client: bigquery.Client, entity: str, config: dict, ingestion_ts: str) -> dict:
    source = f"{DATASET}.{entity}"
    logger.info("Iniciando ingestão de %s", source)

    df = client.query(f"SELECT * FROM `{source}`").to_dataframe()
    logger.info("%s: %d linhas x %d colunas lidas", entity, len(df), len(df.columns))

    # Metadados de rastreabilidade; hash calculado antes, só sobre as colunas da fonte
    df["_row_hash"] = pd.util.hash_pandas_object(df, index=False).astype("uint64")
    df["_ingestion_ts"] = ingestion_ts
    df["_source"] = source

    checks = [
        check_not_empty(df, entity),
        check_required_columns(df, entity, config["required"]),
    ]

    output_dir = Path(LAKE_PATH) / "bronze" / "batch" / entity
    output_dir.mkdir(parents=True, exist_ok=True)
    if config["partition"] and config["partition"] in df.columns:
        df.to_parquet(output_dir, partition_cols=[config["partition"]], index=False)
    else:
        df.to_parquet(output_dir / "data.parquet", index=False)

    logger.info("%s: salvo em %s", entity, output_dir)
    return {"entity": entity, "rows": len(df), "checks": checks}


def main() -> None:
    requested = sys.argv[1:] or list(ENTITIES)
    unknown = [e for e in requested if e not in ENTITIES]
    if unknown:
        raise SystemExit(f"Entidades desconhecidas: {unknown}. Válidas: {list(ENTITIES)}")

    client = bigquery.Client(project=GCP_PROJECT_ID)
    ingestion_ts = datetime.now(timezone.utc).isoformat()

    all_checks, total_rows = [], 0
    for entity in requested:
        result = ingest_table(client, entity, ENTITIES[entity], ingestion_ts)
        all_checks.extend(result["checks"])
        total_rows += result["rows"]

    report_path = save_report(all_checks, layer="bronze")
    logger.info("Ingestão concluída: %d entidades, %d registros. DQ: %s",
                len(requested), total_rows, report_path)
    fail_if_critical(all_checks)


if __name__ == "__main__":
    main()
