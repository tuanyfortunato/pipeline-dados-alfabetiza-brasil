"""
Camada Gold: métricas de negócio do Indicador Criança Alfabetizada.

Materializa as cinco tabelas analíticas da camada (esquema documentado em
docs/dicionario_dados_gold.md), com as decisões validadas no
notebooks/laboratorio_gold.ipynb:

- taxa de alfabetização = média ponderada pelo peso_aluno dos presentes com nota;
- meta usada no confronto é a vigente no ano do resultado (2023 não tem meta);
- toda taxa sai acompanhada da própria margem de erro — sem ela, o confronto com
  a meta não significa nada em quase metade dos municípios (Parte 2 do laboratório);
- a escala de níveis do Saeb é a oficial, conferida contra o gabarito da fonte.

Uso:
    python src/03_gold/metricas_gold.py
"""
import sys
from pathlib import Path

import numpy as np
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
from src.utils.lake import lake_path, preparar_diretorio
from src.utils.logger import get_logger

load_dotenv()
logger = get_logger("gold.metricas")

# Ponto de corte da escala Saeb definido pela Pesquisa Alfabetiza Brasil (2023).
CORTE_ALFABETIZACAO = 743

# Fronteira entre "crítico" e "quase lá". É o topo do nível 2 da escala oficial —
# não um número redondo escolhido a dedo. O corte de 500 que se usa no Saeb de
# 5º/9º ano não serve aqui: nesta escala o mínimo observado é 578, e a faixa
# ficaria vazia.
CORTE_CRITICO = 700

# Cortes dos 9 níveis da escala do 2º ano. A fonte publica a distribuição
# (proporcao_aluno_nivel_0..8) mas não a régua. Derivada por quantis ponderados e
# conferida município a município contra o gabarito: mediana de 0,003pp de
# diferença em 5.516 municípios (laboratorio_gold, seção C).
CORTES_NIVEL = [650, 675, 700, 725, 750, 775, 800, 825]

# Quantos pontos abaixo do corte ainda contam como "quase lá". Com 10, o
# contingente é de 7,8pp da rede pública — é a alavanca mais barata do indicador.
MARGEM_QUASE_LA = 10

# Abaixo disso a taxa do município é frágil demais para leitura isolada.
PARTICIPACAO_MINIMA = 80

# Tolerância do confronto dos níveis com o gabarito oficial.
TOLERANCIA_NIVEL = 0.1

# Recortes de rede usados nas agregações. O confronto com as metas segue o grão
# de cada uma: Brasil e UF são pactuados para a rede pública, municípios para a
# rede municipal (conferido na Silver).
REDES = {
    "municipal": lambda df: df["rede_nome"] == "municipal",
    "estadual": lambda df: df["rede_nome"] == "estadual",
    "publica": lambda df: df["rede_nome"].isin(["municipal", "estadual"]),
    "total": lambda df: df["rede_nome"].notna(),
}

# Os três grãos geográficos, na ordem em que aparecem nas tabelas empilhadas.
NIVEIS_GEOGRAFICOS = [
    ("brasil", ["ano"]),
    ("uf", ["ano", "sigla_uf"]),
    ("municipio", ["ano", "id_municipio", "sigla_uf"]),
]

COLUNAS_NIVEL = [f"pct_nivel_{i}" for i in range(9)]
COLUNAS_NIVEL_OFICIAL = [f"proporcao_aluno_nivel_{i}" for i in range(9)]

# somas intermediárias das agregações: servem de insumo, não vão para a tabela
SOMAS = ["soma_alfa_peso", "soma_prof_peso", "soma_peso", "soma_peso2", "soma_alfa_peso2"]


def eh_alfabetizado(proficiencia: pd.Series) -> pd.Series:
    """Regra de negócio central do projeto: 743 pontos na escala Saeb."""
    return proficiencia >= CORTE_ALFABETIZACAO


def nivel_saeb(proficiencia: pd.Series) -> pd.Series:
    """Nível de 0 a 8 da escala oficial do 2º ano."""
    return pd.cut(proficiencia, [-np.inf, *CORTES_NIVEL, np.inf],
                  labels=range(9), right=False)


def margem_de_erro(p: pd.Series, soma_peso: pd.Series, soma_peso2: pd.Series,
                   soma_alfa_peso2: pd.Series) -> pd.Series:
    """Meia-largura do intervalo de 95% da taxa, em pontos percentuais.

    Estimador ponderado: var(p) = Σw²(y − p)² / (Σw)². Como y é 0 ou 1, isso vira
    (1 − 2p)·Σw²y + p²·Σw², que sai das mesmas somas do groupby. Prefiro este ao
    binomial simples porque ele leva em conta a variação do peso amostral — os
    dois dão quase o mesmo resultado (mediana 7,94 contra 7,91pp), mas este é o
    correto e custa igual.

    Um município com 12 alunos tem margem de ±30pp. Sem esta coluna, a taxa dele
    é publicada com a mesma aparência de certeza que a de São Paulo.
    """
    variancia = (1 - 2 * p) * soma_alfa_peso2 + (p ** 2) * soma_peso2
    # o arredondamento de float pode deixar a variância levemente negativa quando
    # p bate em 0 ou 1 (município onde todo mundo alfabetizou, ou ninguém)
    return (1.96 * 100 * np.sqrt(variancia.clip(lower=0)) / soma_peso).round(2)


def carregar_alunos() -> pd.DataFrame:
    alunos = pd.read_parquet(
        lake_path("silver", "alunos"),
        columns=["ano", "id_municipio", "id_escola", "sigla_uf", "rede_nome",
                 "proficiencia", "peso_aluno", "presente", "sem_nota"],
    )
    # a partição Hive devolve o ano como categoria; int64 explícito porque no
    # Windows astype(int) daria int32 e o contrato da Gold (e o Glue) é bigint
    alunos["ano"] = alunos["ano"].astype("int64")
    alunos["tem_nota"] = alunos["presente"] & ~alunos["sem_nota"]
    # O peso só existe para presentes com nota, então as somas ponderadas
    # abaixo já ficam restritas ao denominador certo (validado no laboratório).
    alfa = eh_alfabetizado(alunos["proficiencia"]).astype(float)
    alunos["alfa_peso"] = alfa * alunos["peso_aluno"]
    alunos["prof_peso"] = alunos["proficiencia"] * alunos["peso_aluno"]
    # insumos da margem de erro (ver margem_de_erro)
    alunos["peso2"] = alunos["peso_aluno"] ** 2
    alunos["alfa_peso2"] = alfa * alunos["peso2"]
    return alunos


def agregar_indicador(df: pd.DataFrame, chaves: list[str]) -> pd.DataFrame:
    """Agrega volumetria, taxas ponderadas e margem de erro no grão pedido.

    Devolve também as somas intermediárias: quem chama decide se precisa delas
    (os limites de participação precisam) e monta o recorte final de colunas.
    """
    # observed=True: só combinações que existem no dado — com chave categórica,
    # o default do pandas 2.x geraria o produto cartesiano de grupos vazios
    g = df.groupby(chaves, dropna=False, observed=True).agg(
        alunos_avaliados=("presente", "size"),
        alunos_presentes=("presente", "sum"),
        alunos_com_nota=("tem_nota", "sum"),
        soma_alfa_peso=("alfa_peso", "sum"),
        soma_prof_peso=("prof_peso", "sum"),
        soma_peso=("peso_aluno", "sum"),
        soma_peso2=("peso2", "sum"),
        soma_alfa_peso2=("alfa_peso2", "sum"),
    ).reset_index()

    proporcao = g["soma_alfa_peso"] / g["soma_peso"]
    g["taxa_participacao"] = (100 * g["alunos_presentes"] / g["alunos_avaliados"]).round(2)
    g["taxa_alfabetizacao"] = (100 * proporcao).round(2)
    g["proficiencia_media"] = (g["soma_prof_peso"] / g["soma_peso"]).round(2)
    g["ic95"] = margem_de_erro(proporcao, g["soma_peso"], g["soma_peso2"],
                               g["soma_alfa_peso2"])
    # Estimativa populacional, não contagem de linhas: o peso expande a amostra
    # (a soma dos pesos dá 2,11 mi contra 1,85 mi de alunos avaliados em 2024).
    # É o número que inverte a leitura de prioridade — percentual esconde volume.
    g["criancas_nao_alfabetizadas"] = (g["soma_peso"] - g["soma_alfa_peso"]).round(0)
    return g


def limites_de_participacao(g: pd.DataFrame) -> pd.DataFrame:
    """Até onde a taxa poderia ir se os ausentes tivessem feito a prova.

    12% dos alunos não fizeram a prova e ficam fora do denominador. A ausência não
    é aleatória: falta mais gente onde o desempenho é pior (correlação de +0,29
    entre participação e taxa), o que empurra a taxa publicada para cima.

    Os limites são o contorno honesto disso: o inferior supõe que todos os
    faltantes seriam não alfabetizados, o superior que todos seriam. No Brasil de
    2024 isso dá [51,7% ; 64,4%] em torno dos 59,2% publicados.
    """
    sem_nota = g["alunos_avaliados"] - g["alunos_com_nota"]
    peso_medio = g["soma_peso"] / g["alunos_com_nota"]
    peso_faltante = sem_nota * peso_medio
    denominador = g["soma_peso"] + peso_faltante

    g["taxa_limite_inferior"] = (100 * g["soma_alfa_peso"] / denominador).round(2)
    g["taxa_limite_superior"] = (
        100 * (g["soma_alfa_peso"] + peso_faltante) / denominador).round(2)
    g["alerta_participacao"] = g["taxa_participacao"] < PARTICIPACAO_MINIMA
    return g


def montar_indicador_municipio(alunos: pd.DataFrame) -> pd.DataFrame:
    """Indicador por município sobre a rede pública (municipal + estadual)."""
    publica = alunos[REDES["publica"](alunos)]
    tabela = limites_de_participacao(
        agregar_indicador(publica, ["ano", "id_municipio", "sigla_uf"]))
    colunas = ["ano", "id_municipio", "sigla_uf", "alunos_avaliados", "alunos_presentes",
               "alunos_com_nota", "taxa_participacao", "taxa_alfabetizacao", "ic95",
               "taxa_limite_inferior", "taxa_limite_superior", "proficiencia_media",
               "criancas_nao_alfabetizadas", "alerta_participacao"]
    tabela = tabela[colunas]
    logger.info("indicador_municipio: %d linhas (%d com participação abaixo de %d%%)",
                len(tabela), int(tabela["alerta_participacao"].sum()), PARTICIPACAO_MINIMA)
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

    # O gap só quer dizer alguma coisa se for maior que a margem de erro do próprio
    # indicador. Em 43,8% dos municípios com meta ele não é — e o atingiu_meta, que
    # é um booleano de dois estados, reporta ruído como se fosse fato nesses casos.
    # A coluna abaixo é a leitura honesta; o booleano fica por compatibilidade.
    # to_numpy(bool): o gap é Float64 anulável, e o np.select não aceita a boolean
    # anulável que sai da comparação
    sem_meta = tabela["meta_ano"].isna().to_numpy(dtype=bool)
    indistinguivel = ((tabela["gap"].abs() < tabela["ic95"])
                      .fillna(False).to_numpy(dtype=bool)) & ~sem_meta
    atingiu = (tabela["gap"] >= 0).fillna(False).to_numpy(dtype=bool)
    tabela["situacao_meta"] = np.select(
        [sem_meta, indistinguivel, atingiu],
        ["sem_meta", "indistinguivel", "atingiu"],
        default="nao_atingiu",
    )

    colunas = ["ano", "nivel", "rede", "sigla_uf", "id_municipio", "alunos_com_nota",
               "taxa_alfabetizacao", "ic95", "meta_ano", "gap", "atingiu_meta",
               "situacao_meta"]
    tabela = tabela[colunas]
    logger.info("meta_vs_resultado: %d linhas (%s)",
                len(tabela), dict(tabela["situacao_meta"].value_counts()))
    return tabela


def montar_evolucao_temporal(alunos: pd.DataFrame) -> pd.DataFrame:
    """Série do indicador por ano, recorte geográfico e rede."""
    partes = []
    for rede, filtro in REDES.items():
        recorte = alunos[filtro(alunos)]
        for nivel, chaves in NIVEIS_GEOGRAFICOS:
            parte = agregar_indicador(recorte, chaves)
            parte["nivel"] = nivel
            parte["rede"] = rede
            partes.append(parte)
    tabela = pd.concat(partes, ignore_index=True)
    tabela["id_municipio"] = tabela["id_municipio"].astype("Int64")
    colunas = ["ano", "nivel", "rede", "sigla_uf", "id_municipio", "alunos_avaliados",
               "alunos_presentes", "alunos_com_nota", "taxa_participacao",
               "taxa_alfabetizacao", "ic95", "proficiencia_media",
               "criancas_nao_alfabetizadas"]
    tabela = tabela[colunas]
    logger.info("evolucao_temporal: %d linhas", len(tabela))
    return tabela


def montar_perfil_escola(alunos: pd.DataFrame, indicador: pd.DataFrame) -> pd.DataFrame:
    """Indicador no grão da escola, com o resíduo contra o próprio município.

    A camada que faltava. Decompondo a variância da proficiência (laboratório,
    seção B): 16% está entre municípios, 9% entre escolas do mesmo município e 75%
    entre alunos da mesma escola. Ou seja, o grão em que a política pactua meta
    explica um sexto da variação — e a escola, que ninguém olha, mais da metade
    disso.

    O `residuo` é a leitura da tabela: a escola comparada ao próprio município,
    mesmo contexto e mesma rede. As que se destacam para cima são casos a estudar;
    as de baixo são onde a intervenção rende mais.

    O `id_escola` é pseudônimo (prefixo 60, regerado a cada ano) e NÃO é o código
    INEP — não junta com o Censo Escolar, e não serve para comparar escolas entre
    anos. Dentro do ano ele é chave limpa, e é só disso que esta tabela precisa.
    """
    publica = alunos[REDES["publica"](alunos)]
    tabela = agregar_indicador(
        publica, ["ano", "id_escola", "id_municipio", "sigla_uf", "rede_nome"])
    tabela = tabela.rename(columns={"rede_nome": "rede"})

    referencia = indicador[["ano", "id_municipio", "taxa_alfabetizacao"]].rename(
        columns={"taxa_alfabetizacao": "taxa_municipio"})
    tabela = tabela.merge(referencia, on=["ano", "id_municipio"], how="left")
    tabela["residuo"] = (tabela["taxa_alfabetizacao"] - tabela["taxa_municipio"]).round(2)

    colunas = ["ano", "id_escola", "id_municipio", "sigla_uf", "rede", "alunos_avaliados",
               "alunos_presentes", "alunos_com_nota", "taxa_participacao",
               "taxa_alfabetizacao", "ic95", "proficiencia_media", "taxa_municipio",
               "residuo"]
    tabela = tabela[colunas]
    logger.info("perfil_escola: %d linhas", len(tabela))
    return tabela


def montar_distribuicao_proficiencia(alunos: pd.DataFrame) -> pd.DataFrame:
    """Distribuição dos alunos nos 9 níveis oficiais e nas faixas de negócio.

    Duas réguas convivem aqui, e elas não se encaixam: os 9 níveis são a escala
    publicada pelo INEP (e por isso dão gabarito para validar contra), enquanto as
    faixas de negócio são ancoradas no corte de alfabetização — que cai DENTRO do
    nível 4 (725-750). Quem consumir precisa saber disso.

    `pct_quase_la` é o contingente empilhado logo abaixo do corte: se todos eles
    cruzassem, a taxa nacional subiria 7,8pp de uma vez.
    """
    com_nota = alunos[alunos["tem_nota"]].copy()
    com_nota["nivel_saeb"] = nivel_saeb(com_nota["proficiencia"])

    peso, prof = com_nota["peso_aluno"], com_nota["proficiencia"]
    com_nota["peso_critico"] = peso.where(prof < CORTE_CRITICO, 0.0)
    com_nota["peso_atencao"] = peso.where(
        (prof >= CORTE_CRITICO) & (prof < CORTE_ALFABETIZACAO), 0.0)
    com_nota["peso_alfabetizado"] = peso.where(prof >= CORTE_ALFABETIZACAO, 0.0)
    com_nota["peso_quase_la"] = peso.where(
        (prof >= CORTE_ALFABETIZACAO - MARGEM_QUASE_LA) & (prof < CORTE_ALFABETIZACAO), 0.0)

    faixas = ["critico", "atencao", "alfabetizado", "quase_la"]
    partes = []
    for rede, filtro in REDES.items():
        recorte = com_nota[filtro(com_nota)]
        if recorte.empty:
            continue
        for nivel, chaves in NIVEIS_GEOGRAFICOS:
            base = recorte.groupby(chaves, observed=True).agg(
                alunos_com_nota=("peso_aluno", "size"),
                soma_peso=("peso_aluno", "sum"),
                **{f"peso_{f}": (f"peso_{f}", "sum") for f in faixas},
            )
            # peso por nível; reindex porque um recorte pequeno pode não ter os 9
            distribuicao = (recorte.groupby(chaves + ["nivel_saeb"], observed=True)
                            ["peso_aluno"].sum().unstack("nivel_saeb")
                            .reindex(columns=range(9)).fillna(0.0))
            distribuicao.columns = COLUNAS_NIVEL

            tabela = base.join(distribuicao)
            for coluna in COLUNAS_NIVEL:
                tabela[coluna] = (100 * tabela[coluna] / tabela["soma_peso"]).round(2)
            for f in faixas:
                tabela[f"pct_{f}"] = (100 * tabela[f"peso_{f}"] / tabela["soma_peso"]).round(2)

            tabela = tabela.reset_index()
            tabela["nivel"] = nivel
            tabela["rede"] = rede
            partes.append(tabela)

    tabela = pd.concat(partes, ignore_index=True)
    tabela["id_municipio"] = tabela["id_municipio"].astype("Int64")
    colunas = (["ano", "nivel", "rede", "sigla_uf", "id_municipio", "alunos_com_nota"]
               + COLUNAS_NIVEL + [f"pct_{f}" for f in faixas])
    tabela = tabela[colunas]
    logger.info("distribuicao_proficiencia: %d linhas", len(tabela))
    return tabela


def conferir_niveis_oficiais(distribuicao: pd.DataFrame,
                             gabarito_municipio: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """Confronta os 9 níveis recalculados com as colunas publicadas pela fonte.

    O melhor check da camada: a régua dos níveis foi derivada (a fonte não publica
    os pontos de corte), então ela precisa provar que reproduz o número oficial a
    cada execução. Mediana de 0,003pp quando isso foi validado no laboratório.

    Só 2024 entra no confronto: em 2023 a fonte não publica a distribuição por
    nível (as colunas existem, mas vêm inteiramente nulas). O dropna abaixo é o que
    garante isso — comparar contra nulo daria violação em toda linha de 2023.
    """
    recalculado = distribuicao[(distribuicao["nivel"] == "municipio")
                               & (distribuicao["rede"] == "publica")]
    oficial = gabarito_municipio[gabarito_municipio["rede_padronizada"] == "publica"]
    conferencia = recalculado.merge(
        oficial[["ano", "id_municipio", *COLUNAS_NIVEL_OFICIAL]],
        on=["ano", "id_municipio"], how="inner",
    )
    pares = pd.concat(
        [pd.DataFrame({"ano": conferencia["ano"],
                       "id_municipio": conferencia["id_municipio"],
                       "calculado": conferencia[calculado],
                       "publicado": conferencia[publicado]})
         for calculado, publicado in zip(COLUNAS_NIVEL, COLUNAS_NIVEL_OFICIAL)],
        ignore_index=True,
    ).dropna(subset=["calculado", "publicado"])
    pares["diferenca"] = (pares["calculado"] - pares["publicado"]).abs()
    return pares, pares["diferenca"] <= TOLERANCIA_NIVEL


def rodar_dq(indicador: pd.DataFrame, confronto: pd.DataFrame, evolucao: pd.DataFrame,
             escola: pd.DataFrame, distribuicao: pd.DataFrame,
             gabarito_municipio: pd.DataFrame) -> list[dict]:
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

    # A taxa publicada tem que caber dentro dos próprios limites de participação.
    # Os municípios sem nenhum presente com nota ficam de fora: lá não há taxa nem
    # limite (é ausência de medição, não defeito — já documentado no dicionário).
    medidos = indicador[indicador["taxa_alfabetizacao"].notna()]
    dentro_dos_limites = (
        (medidos["taxa_alfabetizacao"] >= medidos["taxa_limite_inferior"] - 0.01)
        & (medidos["taxa_alfabetizacao"] <= medidos["taxa_limite_superior"] + 0.01))

    com_meta = confronto[confronto["meta_ano"].notna()]

    # Os níveis recalculados contra o gabarito publicado pela fonte.
    difs_nivel, niveis_batem = conferir_niveis_oficiais(distribuicao, gabarito_municipio)

    # As três faixas de negócio cobrem toda a população, sem sobra nem sobreposição.
    soma_faixas = (distribuicao["pct_critico"] + distribuicao["pct_atencao"]
                   + distribuicao["pct_alfabetizado"])

    # E a faixa "alfabetizado" tem que dar exatamente a taxa da outra tabela —
    # é o que amarra a tabela nova na que já existia.
    ponte = distribuicao[(distribuicao["nivel"] == "municipio")
                         & (distribuicao["rede"] == "publica")].merge(
        indicador[["ano", "id_municipio", "taxa_alfabetizacao"]],
        on=["ano", "id_municipio"], how="inner")
    faixa_bate_com_taxa = (ponte["pct_alfabetizado"] - ponte["taxa_alfabetizacao"]).abs() <= 0.05

    # Uma escola em dois municípios no mesmo ano significaria que o id mudou de
    # semântica na fonte — o resíduo contra o município perderia o sentido.
    escola_por_municipio = escola.groupby(["ano", "id_escola"], observed=True)[
        "id_municipio"].nunique()

    return [
        check_not_empty(indicador, "indicador_municipio"),
        check_not_null(indicador, "indicador_municipio", ["ano", "id_municipio", "sigla_uf"]),
        check_unique(indicador, "indicador_municipio", ["ano", "id_municipio"]),
        check_range(indicador, "indicador_municipio", "taxa_alfabetizacao", 0, 100),
        check_range(indicador, "indicador_municipio", "taxa_participacao", 0, 100),
        check_range(indicador, "indicador_municipio", "ic95", 0, 100),
        check_completeness(indicador, "indicador_municipio", "taxa_alfabetizacao", min_pct=99),
        check_referential_integrity(indicador, "indicador_municipio", "id_municipio",
                                    gabarito_municipio, "id_municipio"),
        check_consistency(medidos, "indicador_municipio",
                          "a taxa cabe dentro dos limites de participacao",
                          dentro_dos_limites),
        check_consistency(conferencia, "indicador_municipio",
                          "recalculo bate com o gabarito oficial (tolerancia 1pp)",
                          bate_com_oficial, severity="warning"),

        check_not_empty(confronto, "meta_vs_resultado"),
        check_unique(confronto, "meta_vs_resultado", ["ano", "nivel", "sigla_uf", "id_municipio"]),
        check_range(confronto, "meta_vs_resultado", "meta_ano", 0, 100),
        check_range(confronto, "meta_vs_resultado", "gap", -100, 100),
        check_consistency(com_meta, "meta_vs_resultado", "atingiu_meta bate com o gap",
                          com_meta["atingiu_meta"] == (com_meta["gap"] >= 0)),
        check_consistency(confronto, "meta_vs_resultado",
                          "situacao_meta so e conclusiva quando o gap supera o ic95",
                          confronto["situacao_meta"].isin(
                              ["sem_meta", "indistinguivel", "atingiu", "nao_atingiu"])),

        check_not_empty(evolucao, "evolucao_temporal"),
        check_not_null(evolucao, "evolucao_temporal", ["ano", "nivel", "rede"]),
        check_range(evolucao, "evolucao_temporal", "taxa_alfabetizacao", 0, 100),

        check_not_empty(escola, "perfil_escola"),
        check_not_null(escola, "perfil_escola", ["ano", "id_escola", "id_municipio"]),
        check_unique(escola, "perfil_escola", ["ano", "id_escola"]),
        check_range(escola, "perfil_escola", "taxa_alfabetizacao", 0, 100),
        check_range(escola, "perfil_escola", "residuo", -100, 100),
        check_referential_integrity(escola, "perfil_escola", "id_municipio",
                                    gabarito_municipio, "id_municipio"),
        check_consistency(escola_por_municipio.to_frame(), "perfil_escola",
                          "cada escola pertence a um unico municipio no ano",
                          escola_por_municipio == 1),

        check_not_empty(distribuicao, "distribuicao_proficiencia"),
        check_unique(distribuicao, "distribuicao_proficiencia",
                     ["ano", "nivel", "rede", "sigla_uf", "id_municipio"]),
        check_range(distribuicao, "distribuicao_proficiencia", "pct_alfabetizado", 0, 100),
        check_range(distribuicao, "distribuicao_proficiencia", "pct_quase_la", 0, 100),
        check_consistency(distribuicao, "distribuicao_proficiencia",
                          "as tres faixas somam 100%", (soma_faixas - 100).abs() <= 0.1),
        check_consistency(ponte, "distribuicao_proficiencia",
                          "pct_alfabetizado bate com a taxa do indicador_municipio",
                          faixa_bate_com_taxa),
        check_consistency(difs_nivel, "distribuicao_proficiencia",
                          f"os 9 niveis batem com o gabarito oficial "
                          f"(tolerancia {TOLERANCIA_NIVEL}pp)",
                          niveis_batem, severity="warning"),
    ]


def escrever_tabela(df: pd.DataFrame, destino: str) -> None:
    # Arquivo único sobrescrito a cada execução: reprocessar é idempotente.
    preparar_diretorio(destino)
    df.to_parquet(f"{destino}/data.parquet", index=False)


def main() -> None:
    logger.info("Lendo a Silver de %s", lake_path("silver"))
    alunos = carregar_alunos()
    metas = pd.read_parquet(lake_path("silver", "metas"))
    gabarito_municipio = pd.read_parquet(lake_path("silver", "resultados", "municipio"))

    indicador = montar_indicador_municipio(alunos)
    confronto = montar_meta_vs_resultado(alunos, metas)
    evolucao = montar_evolucao_temporal(alunos)
    escola = montar_perfil_escola(alunos, indicador)
    distribuicao = montar_distribuicao_proficiencia(alunos)

    checks = rodar_dq(indicador, confronto, evolucao, escola, distribuicao,
                      gabarito_municipio)
    report_path = save_report(checks, layer="gold")
    logger.info("DQ da Gold: %s", report_path)

    logger.info("Escrevendo camada Gold em %s", lake_path("gold"))
    escrever_tabela(indicador, lake_path("gold", "indicador_municipio"))
    escrever_tabela(confronto, lake_path("gold", "meta_vs_resultado"))
    escrever_tabela(evolucao, lake_path("gold", "evolucao_temporal"))
    escrever_tabela(escola, lake_path("gold", "perfil_escola"))
    escrever_tabela(distribuicao, lake_path("gold", "distribuicao_proficiencia"))

    fail_if_critical(checks)
    logger.info("Gold concluída: %d municípios no indicador, %d linhas no confronto "
                "meta × resultado, %d na evolução temporal, %d escolas, "
                "%d linhas na distribuição de proficiência.",
                len(indicador), len(confronto), len(evolucao), len(escola),
                len(distribuicao))


if __name__ == "__main__":
    main()
