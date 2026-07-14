import pandas as pd
import pytest


def test_normaliza_remove_acento_baixa_caixa_e_junta_espacos(silver):
    assert silver.normaliza("Pública") == "publica"
    assert silver.normaliza("Não Informado") == "nao_informado"
    assert silver.normaliza("  Múltiplos   Espaços  ") == "multiplos_espacos"


def test_tratar_resultados_mapeia_todos_os_codigos_de_rede(silver):
    df = pd.DataFrame({
        "id_municipio": [1, 1, 1, 1], "serie": [2, 2, 2, 2], "rede": [0, 2, 3, 5],
        "ano": [2024, 2024, 2024, 2024],
    })
    tratado = silver.tratar_resultados(df, "uf")
    assert tratado["rede_padronizada"].tolist() == ["total", "estadual", "municipal", "publica"]
    assert tratado["ano"].tolist() == [2024, 2024, 2024, 2024]


def test_tratar_metas_empilha_com_nivel_e_normaliza_rede(silver):
    brasil = pd.DataFrame({"id_municipio": [None], "ano": [2024], "rede": ["Pública"],
                           "taxa_alfabetizacao": [59.9], "percentual_participacao": [88.0],
                           "meta_alfabetizacao_2024": [59.9]})
    uf = pd.DataFrame({"id_municipio": [None], "ano": [2024], "rede": ["Pública"],
                       "taxa_alfabetizacao": [60.0], "percentual_participacao": [90.0],
                       "meta_alfabetizacao_2024": [60.0]})
    municipio = pd.DataFrame({"id_municipio": [3550308], "ano": [2024], "rede": ["Municipal"],
                              "taxa_alfabetizacao": [55.0], "percentual_participacao": [85.0],
                              "meta_alfabetizacao_2024": [55.0]})
    tabela = silver.tratar_metas(brasil, uf, municipio)
    assert set(tabela["nivel"]) == {"brasil", "uf", "municipio"}
    linha_municipio = tabela[tabela.nivel == "municipio"].iloc[0]
    assert linha_municipio.rede_padronizada == "municipal"
    assert linha_municipio.id_municipio == 3550308


def test_tratar_alunos_separa_quarentena_por_municipio_orfao(silver):
    dicionario = pd.DataFrame([
        {"id_tabela": "alunos", "nome_coluna": "rede", "chave": 3, "valor": "Municipal"},
        {"id_tabela": "alunos", "nome_coluna": "presenca", "chave": 1, "valor": "Presente"},
    ])
    alunos = pd.DataFrame({
        "ano": [2024, 2024],
        "id_municipio": [3550308, 9999999],  # o segundo não existe na dimensão
        "id_escola": [1, 2],
        "id_aluno": [1, 2],
        "serie": [2, 2],
        "rede": [3, 3],
        "presenca": [1, 1],
        "preenchimento_caderno": [1, 1],
        "alfabetizado": [1, 1],
        "proficiencia": [800.0, 800.0],
        "peso_aluno": [1.0, 1.0],
    })
    municipios_validos = pd.Series([3550308])

    limpos, quarentena = silver.tratar_alunos(alunos, dicionario, municipios_validos)

    assert len(limpos) == 1
    assert limpos.iloc[0].id_municipio == 3550308
    assert limpos.iloc[0].sigla_uf == "SP"  # 3550308 // 100000 == 35
    assert limpos.iloc[0].presente == True  # noqa: E712
    assert limpos.iloc[0].sem_nota == False  # noqa: E712

    assert len(quarentena) == 1
    assert quarentena.iloc[0].id_municipio == 9999999
    assert "motivo" in quarentena.columns


def test_tratar_alunos_ausente_fica_marcado_sem_nota(silver):
    dicionario = pd.DataFrame([
        {"id_tabela": "alunos", "nome_coluna": "rede", "chave": 3, "valor": "Municipal"},
        {"id_tabela": "alunos", "nome_coluna": "presenca", "chave": 2, "valor": "Ausente"},
    ])
    alunos = pd.DataFrame({
        "ano": [2024], "id_municipio": [3550308], "id_escola": [1], "id_aluno": [1],
        "serie": [2], "rede": [3], "presenca": [2], "preenchimento_caderno": [0],
        "alfabetizado": [None], "proficiencia": [None], "peso_aluno": [None],
    })
    limpos, _ = silver.tratar_alunos(alunos, dicionario, pd.Series([3550308]))
    assert limpos.iloc[0].presente == False  # noqa: E712
    assert limpos.iloc[0].sem_nota == True  # noqa: E712


def test_integrar_eventos_streaming_sem_prefixo_nao_faz_nada(silver, monkeypatch, tmp_path):
    monkeypatch.setenv("LAKE_PATH", str(tmp_path))
    municipio = pd.DataFrame({"id_municipio": [3550308]})

    silver.integrar_eventos_streaming(municipio)  # não deve levantar

    assert not (tmp_path / "silver" / "eventos_indicador").exists()


def test_integrar_eventos_streaming_so_com_metadado_nao_quebra(silver, monkeypatch, tmp_path):
    """Regressão: bronze/streaming/eventos_indicador pode "existir" (o Structured
    Streaming grava checkpoint/_spark_metadata antes de qualquer evento real) sem
    ter nenhum dado de verdade. pd.read_parquet() nesse caso volta um DataFrame
    com ZERO colunas (reproduzido abaixo com o layout real do S3) - antes da
    correção isso derrubava o job inteiro com KeyError: 'ano', numa integração
    que é opcional. O batch inteiro já tinha rodado certo até esse ponto."""
    monkeypatch.setenv("LAKE_PATH", str(tmp_path))
    pasta = tmp_path / "bronze" / "streaming" / "eventos_indicador"
    (pasta / "_spark_metadata").mkdir(parents=True)
    (pasta / "_spark_metadata" / "0").write_text('{"v":1}')
    municipio = pd.DataFrame({"id_municipio": [3550308]})

    silver.integrar_eventos_streaming(municipio)  # não deve levantar KeyError

    assert not (tmp_path / "silver" / "eventos_indicador").exists()


def test_integrar_eventos_streaming_com_dado_real_escreve_na_silver(silver, monkeypatch, tmp_path):
    monkeypatch.setenv("LAKE_PATH", str(tmp_path))
    pasta = tmp_path / "bronze" / "streaming" / "eventos_indicador"
    pasta.mkdir(parents=True)
    pd.DataFrame({
        "id_municipio": [3550308], "ano": [2024], "proficiencia_media": [750.0],
    }).to_parquet(pasta / "evento.parquet")
    municipio = pd.DataFrame({"id_municipio": [3550308]})

    silver.integrar_eventos_streaming(municipio)

    saida = pd.read_parquet(tmp_path / "silver" / "eventos_indicador")
    assert len(saida) == 1
    assert saida.iloc[0].sigla_uf == "SP"
    assert saida.iloc[0].origem == "streaming"
