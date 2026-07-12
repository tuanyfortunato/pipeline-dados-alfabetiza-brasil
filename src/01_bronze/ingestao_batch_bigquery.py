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
import pyarrow as pa
import pyarrow.parquet as pq
from dotenv import load_dotenv
from google.api_core import exceptions as gcp_exceptions
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
QUERY_TIMEOUT_S = 300

ENTITIES = {
    "alunos": {"required": ["ano", "id_municipio", "proficiencia"], "partition": "ano"},
    "municipio": {"required": ["id_municipio"], "partition": None},
    "uf": {"required": ["sigla_uf"], "partition": None},
    "meta_alfabetizacao_brasil": {"required": ["ano"], "partition": None},
    "meta_alfabetizacao_uf": {"required": ["ano", "sigla_uf"], "partition": None},
    "meta_alfabetizacao_municipio": {"required": ["ano", "id_municipio"], "partition": None},
    "dicionario": {"required": ["id_tabela", "nome_coluna", "chave"], "partition": None},
}


def ingest_table(client: bigquery.Client, entity: str, config: dict, ingestion_ts: str) -> dict:
    source = f"{DATASET}.{entity}"
    logger.info("Iniciando ingestão de %s", source)

    df = client.query(f"SELECT * FROM `{source}`").result(timeout=QUERY_TIMEOUT_S).to_dataframe()
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
        # escrita via pyarrow sem o metadata do pandas: o Int64 anulável que o
        # BigQuery devolve quebra o read_parquet de dataset particionado
        table = pa.Table.from_pandas(df, preserve_index=False).replace_schema_metadata()
        pq.write_to_dataset(table, str(output_dir), partition_cols=[config["partition"]])
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

    # uma entidade com problema não derruba as demais; falhas são
    # consolidadas no final e o processo sai com erro se houver alguma
    all_checks, total_rows, falhas = [], 0, {}
    for entity in requested:
        try:
            result = ingest_table(client, entity, ENTITIES[entity], ingestion_ts)
        except gcp_exceptions.GoogleAPICallError as exc:
            logger.error("%s: erro na consulta ao BigQuery: %s", entity, exc)
            falhas[entity] = f"bigquery: {exc}"
        except (gcp_exceptions.RetryError, TimeoutError) as exc:
            logger.error("%s: timeout após %ss: %s", entity, QUERY_TIMEOUT_S, exc)
            falhas[entity] = f"timeout: {exc}"
        except OSError as exc:
            logger.error("%s: erro de escrita no lake: %s", entity, exc)
            falhas[entity] = f"escrita: {exc}"
        except Exception as exc:
            logger.exception("%s: erro inesperado", entity)
            falhas[entity] = f"inesperado: {exc}"
        else:
            all_checks.extend(result["checks"])
            total_rows += result["rows"]

    report_path = save_report(all_checks, layer="bronze")
    logger.info("Ingestão finalizada: %d/%d entidades, %d registros. DQ: %s",
                len(requested) - len(falhas), len(requested), total_rows, report_path)
    fail_if_critical(all_checks)
    if falhas:
        raise SystemExit(f"Ingestão incompleta. Entidades com falha: {sorted(falhas)}")


if __name__ == "__main__":
    main()
