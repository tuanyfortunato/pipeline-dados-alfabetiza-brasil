"""Fixtures compartilhadas entre os testes.

Os pacotes de camada (`01_bronze`, `02_silver`, `03_gold`) começam com dígito,
que não é identificador Python válido — `from src.02_silver import x` é
SyntaxError. Importamos via `importlib`, o mesmo truque que o
`scripts/glue_job_batch.py` já usa em produção para resolver isso.
"""
import importlib

import pandas as pd
import pytest


def import_src(dotted: str):
    return importlib.import_module(dotted)


@pytest.fixture
def gold():
    return import_src("src.03_gold.metricas_gold")


@pytest.fixture
def silver():
    return import_src("src.02_silver.tratamento_integracao")


def montar_alunos(linhas: list[dict], eh_alfabetizado) -> pd.DataFrame:
    """Recria as colunas derivadas que `carregar_alunos()` calcula a partir da
    Silver, sem precisar ler parquet — cada linha aceita ano, id_municipio,
    sigla_uf, rede_nome, id_escola (opcional), proficiencia, peso_aluno,
    presente.

    Alunos sem nota devem vir com peso_aluno=None: na Silver de verdade o peso
    só existe para presentes com nota (comentário em carregar_alunos), e é
    isso que mantém o denominador certo nas somas ponderadas — reproduzir
    esse detalhe aqui é o que faz o teste valer a pena.
    """
    df = pd.DataFrame(linhas)
    if "id_escola" not in df.columns:
        df["id_escola"] = 1
    df["tem_nota"] = df["presente"] & df["proficiencia"].notna()
    df["sem_nota"] = df["proficiencia"].isna()
    alfa = eh_alfabetizado(df["proficiencia"]).astype(float)
    df["alfa_peso"] = alfa * df["peso_aluno"]
    df["prof_peso"] = df["proficiencia"] * df["peso_aluno"]
    df["peso2"] = df["peso_aluno"] ** 2
    df["alfa_peso2"] = alfa * df["peso2"]
    return df
