import pandas as pd
import pytest

from tests.conftest import montar_alunos


def test_eh_alfabetizado_boundaries(gold):
    s = pd.Series([742.9, 743.0, 743.1, 578.0, 904.0])
    assert gold.eh_alfabetizado(s).tolist() == [False, True, True, False, True]


def test_nivel_saeb_boundaries(gold):
    # grade de 25 em 25 a partir de 650; right=False -> intervalos [a, b)
    valores = pd.Series([578, 649.9, 650, 674.9, 675, 743, 824.9, 825, 904])
    niveis = gold.nivel_saeb(valores).astype(int).tolist()
    assert niveis == [0, 0, 1, 1, 2, 4, 7, 8, 8]


def test_margem_de_erro_caso_conhecido(gold):
    # 4 alunos peso=1, 2 alfabetizados: p=0.5, soma_peso=4, soma_peso2=4,
    # soma_alfa_peso2=2 -> variancia=1.0 -> margem=1.96*100*sqrt(1)/4=49.0
    resultado = gold.margem_de_erro(
        pd.Series([0.5]), pd.Series([4.0]), pd.Series([4.0]), pd.Series([2.0]))
    assert resultado.iloc[0] == pytest.approx(49.0)


def test_margem_de_erro_zero_quando_sem_variancia(gold):
    # todo mundo alfabetizado (p=1): variancia colapsa em zero
    resultado = gold.margem_de_erro(
        pd.Series([1.0]), pd.Series([4.0]), pd.Series([4.0]), pd.Series([4.0]))
    assert resultado.iloc[0] == 0.0


def test_agregar_indicador_taxa_e_volumetria(gold):
    linhas = [
        {"ano": 2024, "id_municipio": 1, "sigla_uf": "SP", "rede_nome": "municipal",
         "proficiencia": 800.0, "peso_aluno": 1.0, "presente": True},
        {"ano": 2024, "id_municipio": 1, "sigla_uf": "SP", "rede_nome": "municipal",
         "proficiencia": 750.0, "peso_aluno": 1.0, "presente": True},
        {"ano": 2024, "id_municipio": 2, "sigla_uf": "SP", "rede_nome": "municipal",
         "proficiencia": 800.0, "peso_aluno": 1.0, "presente": True},
        {"ano": 2024, "id_municipio": 2, "sigla_uf": "SP", "rede_nome": "municipal",
         "proficiencia": 500.0, "peso_aluno": 1.0, "presente": True},
        {"ano": 2024, "id_municipio": 2, "sigla_uf": "SP", "rede_nome": "municipal",
         "proficiencia": None, "peso_aluno": None, "presente": False},
    ]
    alunos = montar_alunos(linhas, gold.eh_alfabetizado)
    resultado = gold.agregar_indicador(alunos, ["ano", "id_municipio"]).set_index("id_municipio")

    mun1, mun2 = resultado.loc[1], resultado.loc[2]
    assert (mun1.alunos_avaliados, mun1.alunos_presentes, mun1.alunos_com_nota) == (2, 2, 2)
    assert mun1.taxa_participacao == 100.0
    assert mun1.taxa_alfabetizacao == 100.0
    assert mun1.criancas_nao_alfabetizadas == 0.0

    # mun2: 3 avaliados, 2 presentes com nota, 1 dos 2 alfabetizado -> taxa 50%
    assert (mun2.alunos_avaliados, mun2.alunos_presentes, mun2.alunos_com_nota) == (3, 2, 2)
    assert mun2.taxa_participacao == pytest.approx(66.67, abs=0.01)
    assert mun2.taxa_alfabetizacao == 50.0
    assert mun2.criancas_nao_alfabetizadas == 1.0


def test_limites_de_participacao_colapsa_com_participacao_total(gold):
    linhas = [
        {"ano": 2024, "id_municipio": 1, "sigla_uf": "SP", "rede_nome": "municipal",
         "proficiencia": 800.0, "peso_aluno": 1.0, "presente": True}
        for _ in range(3)
    ]
    alunos = montar_alunos(linhas, gold.eh_alfabetizado)
    g = gold.limites_de_participacao(gold.agregar_indicador(alunos, ["ano", "id_municipio"]))
    linha = g.iloc[0]
    assert linha.taxa_limite_inferior == linha.taxa_alfabetizacao == linha.taxa_limite_superior
    assert linha.alerta_participacao == False  # noqa: E712


def test_limites_de_participacao_abre_intervalo_com_ausentes(gold):
    linhas = [
        {"ano": 2024, "id_municipio": 2, "sigla_uf": "SP", "rede_nome": "municipal",
         "proficiencia": 800.0, "peso_aluno": 1.0, "presente": True},
        {"ano": 2024, "id_municipio": 2, "sigla_uf": "SP", "rede_nome": "municipal",
         "proficiencia": 500.0, "peso_aluno": 1.0, "presente": True},
        {"ano": 2024, "id_municipio": 2, "sigla_uf": "SP", "rede_nome": "municipal",
         "proficiencia": None, "peso_aluno": None, "presente": False},
    ]
    alunos = montar_alunos(linhas, gold.eh_alfabetizado)
    g = gold.limites_de_participacao(gold.agregar_indicador(alunos, ["ano", "id_municipio"]))
    linha = g.iloc[0]
    assert linha.taxa_limite_inferior < linha.taxa_alfabetizacao < linha.taxa_limite_superior
    assert linha.alerta_participacao == True  # noqa: E712 (66,7% < 80%)


def test_metas_vigentes_usa_a_coluna_do_proprio_ano(gold):
    metas = pd.DataFrame({
        "nivel": ["brasil", "brasil"],
        "ano": [2024, 2025],
        "sigla_uf": [None, None],
        "id_municipio": [None, None],
        "meta_alfabetizacao_2024": [59.9, 60.5],
        "meta_alfabetizacao_2025": [63.0, 63.0],
    })
    vigentes = gold.metas_vigentes(metas).set_index("ano")
    assert vigentes.loc[2024].meta_ano == 59.9
    assert vigentes.loc[2025].meta_ano == 63.0


def test_metas_vigentes_ano_sem_coluna_correspondente_fica_nulo(gold):
    metas = pd.DataFrame({
        "nivel": ["brasil"], "ano": [2023], "sigla_uf": [None], "id_municipio": [None],
        "meta_alfabetizacao_2024": [59.9],
    })
    vigentes = gold.metas_vigentes(metas)
    assert pd.isna(vigentes.iloc[0].meta_ano)


def test_montar_meta_vs_resultado_situacao_meta(gold):
    # 5 alunos rede municipal, todos alfabetizados -> taxa 100%, ic95 = 0
    # (variancia zero quando p=1), entao qualquer gap != 0 e conclusivo.
    linhas = [
        {"ano": 2024, "id_municipio": 1, "sigla_uf": "SP", "rede_nome": "municipal",
         "proficiencia": 800.0, "peso_aluno": 1.0, "presente": True}
        for _ in range(5)
    ]
    alunos = montar_alunos(linhas, gold.eh_alfabetizado)
    metas = pd.DataFrame([
        {"nivel": "brasil", "ano": 2024, "sigla_uf": None, "id_municipio": None,
         "meta_alfabetizacao_2024": 90.0},   # gap +10 -> atingiu
        {"nivel": "uf", "ano": 2024, "sigla_uf": "SP", "id_municipio": None,
         "meta_alfabetizacao_2024": 100.5},  # gap -0.5 -> nao_atingiu
        # nivel "municipio" sem meta pactuada -> sem_meta
    ])

    tabela = gold.montar_meta_vs_resultado(alunos, metas)

    brasil = tabela[tabela.nivel == "brasil"].iloc[0]
    assert brasil.situacao_meta == "atingiu"
    assert brasil.atingiu_meta == True  # noqa: E712

    uf = tabela[tabela.nivel == "uf"].iloc[0]
    assert uf.situacao_meta == "nao_atingiu"
    assert uf.atingiu_meta == False  # noqa: E712

    municipio = tabela[tabela.nivel == "municipio"].iloc[0]
    assert municipio.situacao_meta == "sem_meta"
    assert pd.isna(municipio.atingiu_meta)


def test_montar_meta_vs_resultado_indistinguivel_quando_gap_menor_que_ic95(gold):
    # município com resultado misto (2 de 4 alfabetizados) tem margem de erro
    # grande o bastante (49pp, ver test_margem_de_erro) pra engolir um gap de 5pp
    linhas = [
        {"ano": 2024, "id_municipio": 1, "sigla_uf": "SP", "rede_nome": "municipal",
         "proficiencia": p, "peso_aluno": 1.0, "presente": True}
        for p in (800.0, 800.0, 500.0, 500.0)
    ]
    alunos = montar_alunos(linhas, gold.eh_alfabetizado)
    metas = pd.DataFrame([
        {"nivel": "municipio", "ano": 2024, "sigla_uf": "SP", "id_municipio": 1,
         "meta_alfabetizacao_2024": 55.0},  # taxa=50%, gap=-5, ic95=49 -> indistinguivel
    ])

    tabela = gold.montar_meta_vs_resultado(alunos, metas)
    municipio = tabela[tabela.nivel == "municipio"].iloc[0]
    assert municipio.ic95 == pytest.approx(49.0)
    assert municipio.situacao_meta == "indistinguivel"
    # o booleano legado não sabe disso e reporta "não bateu" como fato
    assert municipio.atingiu_meta == False  # noqa: E712


def test_montar_perfil_escola_residuo_contra_o_municipio(gold):
    linhas = [
        {"ano": 2024, "id_municipio": 1, "id_escola": 10, "sigla_uf": "SP",
         "rede_nome": "municipal", "proficiencia": 900.0, "peso_aluno": 1.0, "presente": True},
        {"ano": 2024, "id_municipio": 1, "id_escola": 11, "sigla_uf": "SP",
         "rede_nome": "municipal", "proficiencia": 600.0, "peso_aluno": 1.0, "presente": True},
    ]
    alunos = montar_alunos(linhas, gold.eh_alfabetizado)
    indicador = gold.montar_indicador_municipio(alunos)  # taxa do município: 50% (1 de 2)
    escola = gold.montar_perfil_escola(alunos, indicador).set_index("id_escola")

    # escola 10: 100% de taxa, 50pp acima do município (que é 50%)
    assert escola.loc[10].taxa_alfabetizacao == 100.0
    assert escola.loc[10].residuo == pytest.approx(50.0)
    # escola 11: 0% de taxa, 50pp abaixo
    assert escola.loc[11].taxa_alfabetizacao == 0.0
    assert escola.loc[11].residuo == pytest.approx(-50.0)


def test_montar_distribuicao_proficiencia_faixas_somam_100(gold):
    linhas = [
        {"ano": 2024, "id_municipio": 1, "sigla_uf": "SP", "rede_nome": "municipal",
         "proficiencia": p, "peso_aluno": 1.0, "presente": True}
        for p in (600.0, 720.0, 745.0, 900.0)
    ]
    alunos = montar_alunos(linhas, gold.eh_alfabetizado)
    dist = gold.montar_distribuicao_proficiencia(alunos)
    municipio = dist[(dist.nivel == "municipio") & (dist.rede == "municipal")].iloc[0]

    soma_faixas = municipio.pct_critico + municipio.pct_atencao + municipio.pct_alfabetizado
    assert soma_faixas == pytest.approx(100.0, abs=0.01)
    # os 9 niveis oficiais tambem cobrem toda a populacao
    soma_niveis = sum(municipio[f"pct_nivel_{i}"] for i in range(9))
    assert soma_niveis == pytest.approx(100.0, abs=0.01)
