"""
Script de validação do setup do GCP.

Faz uma consulta simples na tabela pública da Base dos Dados no BigQuery
para confirmar que a Service Account e as credenciais estão funcionando
antes de começarmos a escrever o pipeline de verdade (camada Bronze).

Uso:
    export GOOGLE_APPLICATION_CREDENTIALS="./credentials/service-account.json"  (Linux/Mac)
    $env:GOOGLE_APPLICATION_CREDENTIALS = ".\\credentials\\service-account.json"  (PowerShell)
    python scripts/test_bigquery_connection.py
"""
import os

from google.cloud import bigquery

# Projeto do BigQuery que você mesmo criou no GCP (é ele quem paga/mede o scan,
# mesmo consultando uma tabela pública de outro projeto).
GCP_PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "SEU_PROJECT_ID_AQUI")

QUERY = """
    SELECT *
    FROM `basedosdados.br_inep_avaliacao_alfabetizacao.microdados`
    LIMIT 10
"""


def main() -> None:
    client = bigquery.Client(project=GCP_PROJECT_ID)
    df = client.query(QUERY).to_dataframe()
    print(f"Conexão OK. {len(df)} linhas retornadas.")
    print(df.head())


if __name__ == "__main__":
    main()
