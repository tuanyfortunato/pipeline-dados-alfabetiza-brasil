from pathlib import Path

from tests.conftest import import_src

lake = import_src("src.utils.lake")


def test_lake_path_local_default(monkeypatch):
    monkeypatch.delenv("LAKE_PATH", raising=False)
    assert lake.lake_path("bronze", "batch", "uf") == str(Path("./data/bronze/batch/uf"))


def test_lake_path_local_custom(monkeypatch, tmp_path):
    monkeypatch.setenv("LAKE_PATH", str(tmp_path))
    assert lake.lake_path("silver", "alunos") == str(tmp_path / "silver" / "alunos")


def test_lake_path_s3(monkeypatch):
    monkeypatch.setenv("LAKE_PATH", "s3://meu-bucket")
    assert lake.lake_path("gold", "indicador_municipio") == "s3://meu-bucket/gold/indicador_municipio"


def test_lake_path_s3_strips_trailing_slash(monkeypatch):
    monkeypatch.setenv("LAKE_PATH", "s3://meu-bucket/")
    assert lake.lake_path("gold") == "s3://meu-bucket/gold"


def test_is_s3_true(monkeypatch):
    monkeypatch.setenv("LAKE_PATH", "s3://meu-bucket")
    assert lake.is_s3() is True


def test_is_s3_false_local(monkeypatch):
    monkeypatch.setenv("LAKE_PATH", "./data")
    assert lake.is_s3() is False


def test_preparar_diretorio_cria_pasta_local(monkeypatch, tmp_path):
    monkeypatch.setenv("LAKE_PATH", str(tmp_path))
    destino = str(tmp_path / "bronze" / "batch" / "uf")
    lake.preparar_diretorio(destino)
    assert Path(destino).is_dir()


def test_preparar_diretorio_nao_faz_nada_no_s3(monkeypatch):
    monkeypatch.setenv("LAKE_PATH", "s3://meu-bucket")
    # não deve levantar nem tentar tocar disco/rede - é isso que evita os
    # marcadores _$folder$ do EMRFS no batch em pandas
    lake.preparar_diretorio("s3://meu-bucket/bronze/batch/uf")


def test_existe_local(monkeypatch, tmp_path):
    monkeypatch.setenv("LAKE_PATH", str(tmp_path))
    alvo = tmp_path / "silver" / "alunos"
    assert lake.existe(str(alvo)) is False
    alvo.mkdir(parents=True)
    assert lake.existe(str(alvo)) is True
