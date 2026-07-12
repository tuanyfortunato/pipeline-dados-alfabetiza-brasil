"""Wrapper que roda uma camada do pipeline (bronze/silver/gold) num Glue Python
Shell job. O código do repositório chega em s3://<lake>/scripts/src.zip (publicado
pelo scripts/deploy_glue_artifacts.ps1) e é importado direto do zip — mesmo código
do desenvolvimento local, sem fork.

Argumentos do job (default_arguments no Terraform):
    --etapa            bronze | silver | gold
    --lake_bucket      nome do bucket do data lake
    --gcp_project_id   projeto GCP da extração (só a bronze usa de fato)
"""
import importlib
import os
import sys
import tempfile
import zipfile

import boto3
from awsglue.utils import getResolvedOptions

MODULOS = {
    "bronze": "src.01_bronze.ingestao_batch_bigquery",
    "silver": "src.02_silver.tratamento_integracao",
    "gold": "src.03_gold.metricas_gold",
}


def main() -> None:
    args = getResolvedOptions(sys.argv, ["etapa", "lake_bucket", "gcp_project_id"])
    if args["etapa"] not in MODULOS:
        raise SystemExit(f"--etapa inválida: {args['etapa']}. Válidas: {list(MODULOS)}")

    # o pipeline lê a configuração do ambiente; aqui o ambiente vem dos args do job
    os.environ["LAKE_PATH"] = f"s3://{args['lake_bucket']}"
    os.environ["GCP_PROJECT_ID"] = args["gcp_project_id"]

    zip_local = os.path.join(tempfile.gettempdir(), "src.zip")
    boto3.client("s3").download_file(args["lake_bucket"], "scripts/src.zip", zip_local)
    # zipimport não enxerga namespace packages (o projeto não usa __init__.py), então
    # extraímos e colocamos o DIRETÓRIO no path — import via filesystem, igual ao local
    destino_src = os.path.join(tempfile.gettempdir(), "src_extraido")
    with zipfile.ZipFile(zip_local) as z:
        z.extractall(destino_src)
    sys.path.insert(0, destino_src)

    # o main da bronze interpreta argv como lista de entidades; some com os args do Glue
    sys.argv = [sys.argv[0]]
    importlib.import_module(MODULOS[args["etapa"]]).main()


if __name__ == "__main__":
    main()
