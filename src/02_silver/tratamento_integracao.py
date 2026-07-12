"""
Camada Silver: limpeza, padronização e integração das entidades da Bronze.

Consolida o que foi validado em notebooks/laboratorio_silver.ipynb. A ordem de
trabalho é sempre a mesma: casting -> decodificação/normalização de texto ->
flags -> UF derivada -> quarentena -> checks formais -> escrita particionada.

Uso:
    python src/02_silver/tratamento_integracao.py
"""
import os
import re
import sys
import unicodedata
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.utils.data_quality import (
    check_completeness,
    check_consistency,
    check_format,
    check_not_null,
    check_range,
    check_referential_integrity,
    check_unique,
    fail_if_critical,
    save_report,
)
from src.utils.logger import get_logger

load_dotenv()
logger = get_logger("silver.tratamento_integracao")

LAKE_PATH = os.environ.get("LAKE_PATH", "./data")
BRONZE = Path(LAKE_PATH) / "bronze" / "batch"
SILVER = Path(LAKE_PATH) / "silver"

# Os dois primeiros dígitos do código IBGE do município são o código da UF.
# É tabela pública e estável desde os anos 70, então mantenho como constante.
UF_POR_CODIGO = {
    11: "RO", 12: "AC", 13: "AM", 14: "RR", 15: "PA", 16: "AP", 17: "TO",
    21: "MA", 22: "PI", 23: "CE", 24: "RN", 25: "PB", 26: "PE", 27: "AL", 28: "SE", 29: "BA",
    31: "MG", 32: "ES", 33: "RJ", 35: "SP",
    41: "PR", 42: "SC", 43: "RS",
    50: "MS", 51: "MT", 52: "GO", 53: "DF",
}

# Vocabulário único de rede. O dicionário da fonte não traz o código 5 (que
# aparece em municipio/uf) e as metas trazem a rede como texto, então padronizo
# tudo aqui para os três vocabulários convergirem — decisão registrada na
# célula 27 do laboratório da Silver.
REDE_RESULTADO = {0: "total", 2: "estadual", 3: "municipal", 5: "publica"}


def normaliza(texto) -> str:
    """Tira acento, baixa a caixa e troca separadores por underscore."""
    s = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


def carregar_bronze(entidade: str) -> pd.DataFrame:
    return pd.read_parquet(BRONZE / entidade)


def mapa_dicionario(dicionario: pd.DataFrame, tabela: str, coluna: str) -> dict:
    """De-para oficial da fonte: (id_tabela, nome_coluna, chave) -> valor."""
    d = dicionario[(dicionario["id_tabela"] == tabela) & (dicionario["nome_coluna"] == coluna)]
    return {int(k): v for k, v in zip(d["chave"], d["valor"])}


def _para_inteiro(df: pd.DataFrame, colunas: list[str]) -> None:
    """Int64 anulável, para conviver com nulos legítimos."""
    for c in colunas:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c]).astype("Int64")


def _para_decimal(df: pd.DataFrame, colunas: list[str]) -> None:
    for c in colunas:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").astype("float64")


def tratar_alunos(alunos: pd.DataFrame, dicionario: pd.DataFrame,
                  municipios_validos: pd.Series) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Trata os microdados e separa a quarentena (município órfão)."""
    _para_inteiro(alunos, ["id_municipio", "id_escola", "id_aluno", "serie", "rede",
                           "presenca", "preenchimento_caderno", "alfabetizado"])
    _para_decimal(alunos, ["proficiencia", "peso_aluno"])
    alunos["ano"] = alunos["ano"].astype(int)  # vem como categoria da partição Hive

    # Decodificação via dicionário + normalização de texto.
    rede = mapa_dicionario(dicionario, "alunos", "rede")
    presenca = mapa_dicionario(dicionario, "alunos", "presenca")
    alunos["rede_nome"] = alunos["rede"].map(rede).map(normaliza)
    alunos["presenca_nome"] = alunos["presenca"].map(presenca).map(normaliza)

    # Flags: o nulo de proficiência é informação (aluno ausente), não defeito.
    alunos["presente"] = alunos["presenca"] == 1
    alunos["sem_nota"] = alunos["proficiencia"].isna()

    # UF derivada do código IBGE (100% de cobertura, inclusive DF).
    alunos["sigla_uf"] = (alunos["id_municipio"] // 100000).map(UF_POR_CODIGO)

    # Quarentena: linhas cujo município não existe na dimensão. Não somem —
    # ficam com o motivo registrado para auditoria e reprocessamento.
    orfaos = ~alunos["id_municipio"].isin(municipios_validos)
    quarentena = alunos[orfaos].copy()
    quarentena["motivo"] = "id_municipio ausente na dimensão municipio"
    limpos = alunos[~orfaos].copy()

    logger.info("alunos: %d limpos, %d em quarentena (%.4f%%)",
                len(limpos), len(quarentena), 100 * len(quarentena) / len(alunos))
    return limpos, quarentena


def tratar_resultados(df: pd.DataFrame, entidade: str) -> pd.DataFrame:
    """Casting + rede no vocabulário padronizado para municipio/uf."""
    _para_inteiro(df, ["id_municipio", "serie", "rede"])
    df["ano"] = pd.to_numeric(df["ano"]).astype(int)
    proporcoes = [c for c in df.columns if c.startswith("proporcao_aluno_nivel_")]
    _para_decimal(df, ["taxa_alfabetizacao", "media_portugues", *proporcoes])
    df["rede_padronizada"] = df["rede"].map(REDE_RESULTADO)
    logger.info("%s: %d linhas tratadas", entidade, len(df))
    return df


def tratar_metas(brasil: pd.DataFrame, por_uf: pd.DataFrame,
                 por_municipio: pd.DataFrame) -> pd.DataFrame:
    """Empilha as 3 tabelas de metas com a coluna `nivel` indicando o grão."""
    metas = pd.concat(
        [
            brasil.assign(nivel="brasil"),
            por_uf.assign(nivel="uf"),
            por_municipio.assign(nivel="municipio"),
        ],
        ignore_index=True,
    )
    _para_inteiro(metas, ["id_municipio"])
    metas["ano"] = pd.to_numeric(metas["ano"]).astype(int)
    anos_meta = [f"meta_alfabetizacao_{a}" for a in range(2024, 2031)]
    _para_decimal(metas, ["taxa_alfabetizacao", "percentual_participacao", *anos_meta])
    # As metas trazem a rede como texto ("Pública", "Municipal") — normalizar
    # já as coloca no mesmo vocabulário dos resultados.
    metas["rede_padronizada"] = metas["rede"].map(normaliza)
    logger.info("metas: %d linhas (%s)", len(metas), dict(metas.groupby("nivel").size()))
    return metas


def rodar_dq(alunos: pd.DataFrame, municipio: pd.DataFrame) -> list[dict]:
    """Suite de qualidade da Silver, rodada sobre os alunos já sem quarentena."""
    com_nota = alunos[alunos["presente"] & ~alunos["sem_nota"]]
    return [
        check_not_null(alunos, "alunos", ["ano", "id_municipio", "id_aluno"]),
        check_unique(alunos, "alunos", ["id_aluno", "ano"]),
        check_range(alunos, "alunos", "proficiencia", 0, 1000),
        check_range(alunos, "alunos", "peso_aluno", 0.0001, 1000),
        check_format(alunos, "alunos", "id_municipio", r"\d{7}"),
        check_format(alunos, "alunos", "id_escola", r"\d{8}"),
        check_consistency(alunos, "alunos", "ausente implica sem nota",
                          ~(~alunos["presente"] & alunos["proficiencia"].notna())),
        check_consistency(com_nota, "alunos", "alfabetizado bate com a regra dos 743",
                          com_nota["alfabetizado"] == (com_nota["proficiencia"] >= 743).astype(int)),
        check_referential_integrity(alunos, "alunos", "id_municipio", municipio, "id_municipio"),
        check_consistency(alunos, "alunos", "presente implica ter nota",
                          ~(alunos["presente"] & alunos["sem_nota"]), severity="warning"),
        check_completeness(alunos, "alunos", "proficiencia", min_pct=80),
    ]


def escrever_particionado(df: pd.DataFrame, destino: Path, particao: str) -> None:
    destino.mkdir(parents=True, exist_ok=True)
    tabela = pa.Table.from_pandas(df, preserve_index=False).replace_schema_metadata()
    pq.write_to_dataset(tabela, str(destino), partition_cols=[particao])


def escrever_tabela(df: pd.DataFrame, destino: Path) -> None:
    destino.mkdir(parents=True, exist_ok=True)
    df.to_parquet(destino / "data.parquet", index=False)


def main() -> None:
    logger.info("Lendo a Bronze de %s", BRONZE)
    dicionario = carregar_bronze("dicionario")
    municipio = tratar_resultados(carregar_bronze("municipio"), "municipio")
    uf = tratar_resultados(carregar_bronze("uf"), "uf")

    alunos_limpos, quarentena = tratar_alunos(
        carregar_bronze("alunos"), dicionario, municipio["id_municipio"].dropna().unique()
    )

    metas = tratar_metas(
        carregar_bronze("meta_alfabetizacao_brasil"),
        carregar_bronze("meta_alfabetizacao_uf"),
        carregar_bronze("meta_alfabetizacao_municipio"),
    )

    checks = rodar_dq(alunos_limpos, municipio)
    report_path = save_report(checks, layer="silver")
    logger.info("DQ da Silver: %s", report_path)

    logger.info("Escrevendo camada Silver em %s", SILVER)
    escrever_particionado(alunos_limpos, SILVER / "alunos", "ano")
    if len(quarentena):
        escrever_particionado(quarentena, SILVER / "quarentena" / "alunos", "ano")
    escrever_tabela(municipio, SILVER / "resultados" / "municipio")
    escrever_tabela(uf, SILVER / "resultados" / "uf")
    escrever_tabela(metas, SILVER / "metas")

    fail_if_critical(checks)
    logger.info("Silver concluída: %d alunos, %d em quarentena, %d resultados municipais, "
                "%d resultados por UF, %d linhas de metas.",
                len(alunos_limpos), len(quarentena), len(municipio), len(uf), len(metas))


if __name__ == "__main__":
    main()
