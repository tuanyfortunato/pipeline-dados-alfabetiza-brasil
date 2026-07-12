"""
Camada Gold: métricas de negócio do Indicador Criança Alfabetizada.

Materializa as três tabelas analíticas da camada (esquema documentado em
docs/dicionario_dados_gold.md), com as decisões validadas no
notebooks/laboratorio_gold.ipynb:

- taxa de alfabetização = média ponderada pelo peso_aluno dos presentes com nota;
- meta usada no confronto é a vigente no ano do resultado (2023 não tem meta);
- o recálculo é conferido contra o gabarito oficial com tolerância de 1pp.

Uso:
    python src/03_gold/metricas_gold.py
"""
import os
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.utils.data_quality import (
    check_completeness,
    check_consistency,
    check_not_empty,
    check_not_null,
    check_range,
    check_referential_integrity,
    check_unique,
    fail_if_critical,
    save_report,
)
from src.utils.logger import get_logger

load_dotenv()
logger = get_logger("gold.metricas")

LAKE_PATH = os.environ.get("LAKE_PATH", "./data")
SILVER = Path(LAKE_PATH) / "silver"
GOLD = Path(LAKE_PATH) / "gold"

# Ponto de corte da escala Saeb definido pela Pesquisa Alfabetiza Brasil (2023).
CORTE_ALFABETIZACAO = 743

# Recortes de rede usados nas agregações. O confronto com as metas segue o grão
# de cada uma: Brasil e UF são pactuados para a rede pública, municípios para a
# rede municipal (conferido na Silver).
REDES = {
    "municipal": lambda df: df["rede_nome"] == "municipal",
    "estadual": lambda df: df["rede_nome"] == "estadual",
    "publica": lambda df: df["rede_nome"].isin(["municipal", "estadual"]),
    "total": lambda df: df["rede_nome"].notna(),
}


def eh_alfabetizado(proficiencia: pd.Series) -> pd.Series:
    """Regra de negócio central do projeto: 743 pontos na escala Saeb."""
    return proficiencia >= CORTE_ALFABETIZACAO


def carregar_alunos() -> pd.DataFrame:
    alunos = pd.read_parquet(
        SILVER / "alunos",
        columns=["ano", "id_municipio", "sigla_uf", "rede_nome", "proficiencia",
                 "peso_aluno", "presente", "sem_nota"],
    )
    alunos["tem_nota"] = alunos["presente"] & ~alunos["sem_nota"]
    # O peso só existe para presentes com nota, então as somas ponderadas
    # abaixo já ficam restritas ao denominador certo (validado no laboratório).
    alfa = eh_alfabetizado(alunos["proficiencia"]).astype(float)
    alunos["alfa_peso"] = alfa * alunos["peso_aluno"]
    alunos["prof_peso"] = alunos["proficiencia"] * alunos["peso_aluno"]
    return alunos


def agregar_indicador(df: pd.DataFrame, chaves: list[str]) -> pd.DataFrame:
    """Agrega volumetria e taxas ponderadas no grão pedido."""
    g = df.groupby(chaves, dropna=False).agg(
        alunos_avaliados=("presente", "size"),
        alunos_presentes=("presente", "sum"),
        alunos_com_nota=("tem_nota", "sum"),
        soma_alfa_peso=("alfa_peso", "sum"),
        soma_prof_peso=("prof_peso", "sum"),
        soma_peso=("peso_aluno", "sum"),
    ).reset_index()
    g["taxa_participacao"] = (100 * g["alunos_presentes"] / g["alunos_avaliados"]).round(2)
    g["taxa_alfabetizacao"] = (100 * g["soma_alfa_peso"] / g["soma_peso"]).round(2)
    g["proficiencia_media"] = (g["soma_prof_peso"] / g["soma_peso"]).round(2)
    return g.drop(columns=["soma_alfa_peso", "soma_prof_peso", "soma_peso"])


def montar_indicador_municipio(alunos: pd.DataFrame) -> pd.DataFrame:
    """Indicador por município sobre a rede pública (municipal + estadual)."""
    publica = alunos[REDES["publica"](alunos)]
    tabela = agregar_indicador(publica, ["ano", "id_municipio", "sigla_uf"])
    logger.info("indicador_municipio: %d linhas", len(tabela))
    return tabela


def metas_vigentes(metas: pd.DataFrame) -> pd.DataFrame:
    """A meta que vale é a do snapshot do próprio ano (decisão 5 do laboratório).

    2023 fica sem meta por definição: as colunas pactuadas começam em 2024.
    """
    metas = metas.copy()
    metas["meta_ano"] = pd.NA
    for ano in metas["ano"].unique():
        col = f"meta_alfabetizacao_{ano}"
        if col in metas.columns:
            metas.loc[metas["ano"] == ano, "meta_ano"] = metas.loc[metas["ano"] == ano, col]
    metas["meta_ano"] = metas["meta_ano"].astype("Float64")
    return metas[["nivel", "ano", "sigla_uf", "id_municipio", "meta_ano"]]


def montar_meta_vs_resultado(alunos: pd.DataFrame, metas: pd.DataFrame) -> pd.DataFrame:
    """Confronto realizado × meta nos três níveis, espelhando o grão das metas."""
    publica = alunos[REDES["publica"](alunos)]
    municipal = alunos[REDES["municipal"](alunos)]
    vigentes = metas_vigentes(metas)

    niveis = [
        ("brasil", agregar_indicador(publica, ["ano"]), ["ano"], "publica"),
        ("uf", agregar_indicador(publica, ["ano", "sigla_uf"]), ["ano", "sigla_uf"], "publica"),
        ("municipio", agregar_indicador(municipal, ["ano", "id_municipio", "sigla_uf"]),
         ["ano", "id_municipio"], "municipal"),
    ]

    partes = []
    for nivel, resultado, chaves, rede in niveis:
        m = vigentes[vigentes["nivel"] == nivel]
        # Join left: recorte sem meta pactuada fica visível, com meta_ano nulo.
        parte = resultado.merge(m[chaves + ["meta_ano"]], on=chaves, how="left")
        parte["nivel"] = nivel
        parte["rede"] = rede
        partes.append(parte)

    tabela = pd.concat(partes, ignore_index=True)
    # o concat com os níveis brasil/uf (sem município) rebaixaria a chave para
    # float; Int64 anulável mantém o esquema rígido
    tabela["id_municipio"] = tabela["id_municipio"].astype("Int64")
    tabela["gap"] = (tabela["taxa_alfabetizacao"] - tabela["meta_ano"]).round(2)
    tabela["atingiu_meta"] = (tabela["gap"] >= 0).astype("boolean").mask(tabela["meta_ano"].isna())
    colunas = ["ano", "nivel", "rede", "sigla_uf", "id_municipio",
               "alunos_com_nota", "taxa_alfabetizacao", "meta_ano", "gap", "atingiu_meta"]
    tabela = tabela[[c for c in colunas if c in tabela.columns]]
    logger.info("meta_vs_resultado: %d linhas (%s sem meta)",
                len(tabela), int(tabela["meta_ano"].isna().sum()))
    return tabela


def montar_evolucao_temporal(alunos: pd.DataFrame) -> pd.DataFrame:
    """Série do indicador por ano, recorte geográfico e rede."""
    partes = []
    for rede, filtro in REDES.items():
        recorte = alunos[filtro(alunos)]
        for nivel, chaves in [("brasil", ["ano"]),
                              ("uf", ["ano", "sigla_uf"]),
                              ("municipio", ["ano", "id_municipio", "sigla_uf"])]:
            parte = agregar_indicador(recorte, chaves)
            parte["nivel"] = nivel
            parte["rede"] = rede
            partes.append(parte)
    tabela = pd.concat(partes, ignore_index=True)
    tabela["id_municipio"] = tabela["id_municipio"].astype("Int64")
    colunas = ["ano", "nivel", "rede", "sigla_uf", "id_municipio", "alunos_avaliados",
               "alunos_presentes", "alunos_com_nota", "taxa_participacao",
               "taxa_alfabetizacao", "proficiencia_media"]
    tabela = tabela[[c for c in colunas if c in tabela.columns]]
    logger.info("evolucao_temporal: %d linhas", len(tabela))
    return tabela


def rodar_dq(indicador: pd.DataFrame, confronto: pd.DataFrame, evolucao: pd.DataFrame,
             gabarito_municipio: pd.DataFrame) -> list[dict]:
    dim_municipios = gabarito_municipio["id_municipio"].dropna().unique()

    # O teste mais importante da camada: o recálculo contra a taxa oficial.
    # Tolerância de 1pp; os 45 outliers conhecidos (0,4%, quase todos de 2023,
    # ano de desenho amostral diferente) ficam como warning documentado.
    gabarito_publica = gabarito_municipio[gabarito_municipio["rede_padronizada"] == "publica"]
    conferencia = indicador.merge(
        gabarito_publica[["ano", "id_municipio", "taxa_alfabetizacao"]],
        on=["ano", "id_municipio"], how="inner", suffixes=("", "_oficial"),
    )
    bate_com_oficial = (conferencia["taxa_alfabetizacao"]
                        - conferencia["taxa_alfabetizacao_oficial"]).abs() <= 1

    com_meta = confronto[confronto["meta_ano"].notna()]
    return [
        check_not_empty(indicador, "indicador_municipio"),
        check_not_null(indicador, "indicador_municipio", ["ano", "id_municipio", "sigla_uf"]),
        check_unique(indicador, "indicador_municipio", ["ano", "id_municipio"]),
        check_range(indicador, "indicador_municipio", "taxa_alfabetizacao", 0, 100),
        check_range(indicador, "indicador_municipio", "taxa_participacao", 0, 100),
        check_completeness(indicador, "indicador_municipio", "taxa_alfabetizacao", min_pct=99),
        check_referential_integrity(indicador, "indicador_municipio", "id_municipio",
                                    gabarito_municipio, "id_municipio"),
        check_consistency(conferencia, "indicador_municipio",
                          "recalculo bate com o gabarito oficial (tolerancia 1pp)",
                          bate_com_oficial, severity="warning"),
        check_not_empty(confronto, "meta_vs_resultado"),
        check_unique(confronto, "meta_vs_resultado", ["ano", "nivel", "sigla_uf", "id_municipio"]),
        check_range(confronto, "meta_vs_resultado", "meta_ano", 0, 100),
        check_range(confronto, "meta_vs_resultado", "gap", -100, 100),
        check_consistency(com_meta, "meta_vs_resultado", "atingiu_meta bate com o gap",
                          com_meta["atingiu_meta"] == (com_meta["gap"] >= 0)),
        check_not_empty(evolucao, "evolucao_temporal"),
        check_not_null(evolucao, "evolucao_temporal", ["ano", "nivel", "rede"]),
        check_range(evolucao, "evolucao_temporal", "taxa_alfabetizacao", 0, 100),
    ]


def escrever_tabela(df: pd.DataFrame, destino: Path) -> None:
    # Arquivo único sobrescrito a cada execução: reprocessar é idempotente.
    destino.mkdir(parents=True, exist_ok=True)
    df.to_parquet(destino / "data.parquet", index=False)


def main() -> None:
    logger.info("Lendo a Silver de %s", SILVER)
    alunos = carregar_alunos()
    metas = pd.read_parquet(SILVER / "metas")
    gabarito_municipio = pd.read_parquet(SILVER / "resultados" / "municipio")

    indicador = montar_indicador_municipio(alunos)
    confronto = montar_meta_vs_resultado(alunos, metas)
    evolucao = montar_evolucao_temporal(alunos)

    checks = rodar_dq(indicador, confronto, evolucao, gabarito_municipio)
    report_path = save_report(checks, layer="gold")
    logger.info("DQ da Gold: %s", report_path)

    logger.info("Escrevendo camada Gold em %s", GOLD)
    escrever_tabela(indicador, GOLD / "indicador_municipio")
    escrever_tabela(confronto, GOLD / "meta_vs_resultado")
    escrever_tabela(evolucao, GOLD / "evolucao_temporal")

    fail_if_critical(checks)
    logger.info("Gold concluída: %d municípios no indicador, %d linhas no confronto "
                "meta × resultado, %d na evolução temporal.",
                len(indicador), len(confronto), len(evolucao))


if __name__ == "__main__":
    main()
