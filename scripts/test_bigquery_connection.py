"""Smoke test da conexão com o BigQuery (fonte Base dos Dados)."""
import os

from dotenv import load_dotenv
from google.cloud import bigquery

load_dotenv()

QUERY = """
    SELECT *
    FROM `basedosdados.br_inep_avaliacao_alfabetizacao.alunos`
    LIMIT 10
"""


def main() -> None:
    client = bigquery.Client(project=os.environ["GCP_PROJECT_ID"])
    df = client.query(QUERY).to_dataframe()
    print(f"Conexão OK. {len(df)} linhas retornadas.")
    print(df.head())


if __name__ == "__main__":
    main()
