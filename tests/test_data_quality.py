import json

import pandas as pd
import pytest

from tests.conftest import import_src

dq = import_src("src.utils.data_quality")


def test_check_not_empty_pass():
    r = dq.check_not_empty(pd.DataFrame({"a": [1]}), "x")
    assert r["status"] == "pass"


def test_check_not_empty_fail():
    r = dq.check_not_empty(pd.DataFrame({"a": []}), "x")
    assert r["status"] == "fail"


def test_check_required_columns_missing():
    r = dq.check_required_columns(pd.DataFrame({"a": [1]}), "x", ["a", "b"])
    assert r["status"] == "fail"
    assert "b" in r["detail"]


def test_check_required_columns_ok():
    r = dq.check_required_columns(pd.DataFrame({"a": [1], "b": [2]}), "x", ["a", "b"])
    assert r["status"] == "pass"


def test_check_not_null_reports_offenders():
    df = pd.DataFrame({"a": [1, None, 3], "b": [1, 2, 3]})
    r = dq.check_not_null(df, "x", ["a", "b"])
    assert r["status"] == "fail"
    assert "a" in r["detail"] and "b" not in r["detail"]


def test_check_completeness_threshold():
    df = pd.DataFrame({"a": [1, None, None, None]})  # 25% preenchido
    ok = dq.check_completeness(df, "x", "a", min_pct=20)
    baixo = dq.check_completeness(df, "x", "a", min_pct=50)
    assert ok["status"] == "pass"
    assert baixo["status"] == "warning"  # severity default é warning


def test_check_unique_detects_duplicates():
    df = pd.DataFrame({"id": [1, 1, 2]})
    r = dq.check_unique(df, "x", ["id"])
    assert r["status"] == "fail"
    assert "1 duplicatas" in r["detail"]


def test_check_range_out_of_bounds():
    df = pd.DataFrame({"nota": [500, 743, 1000, -5]})
    r = dq.check_range(df, "x", "nota", 0, 904)
    assert r["status"] == "fail"
    assert "2 valores" in r["detail"]  # 1000 e -5


def test_check_range_coerces_non_numeric_as_missing():
    # valor não numérico não conta como violação de faixa (vira NaN e é descartado)
    df = pd.DataFrame({"nota": [500, "abc"]})
    r = dq.check_range(df, "x", "nota", 0, 904)
    assert r["status"] == "pass"


def test_check_format_matches_regex():
    df = pd.DataFrame({"cod": ["3550308", "abc", "12"]})
    r = dq.check_format(df, "x", "cod", r"\d{7}")
    assert r["status"] == "fail"
    assert "2 valores" in r["detail"]


def test_check_consistency_counts_violations():
    df = pd.DataFrame({"presente": [True, False, False], "nota": [700.0, None, 800.0]})
    condicao = ~(~df["presente"] & df["nota"].notna())
    r = dq.check_consistency(df, "x", "ausente sem nota", condicao)
    assert r["status"] == "fail"
    assert "1 violações" in r["detail"]


def test_check_referential_integrity_finds_orphans():
    alunos = pd.DataFrame({"id_municipio": [1, 2, 99]})
    municipios = pd.DataFrame({"id_municipio": [1, 2]})
    r = dq.check_referential_integrity(alunos, "x", "id_municipio", municipios, "id_municipio")
    assert r["status"] == "fail"
    assert "1 chaves órfãs" in r["detail"]


def test_severity_warning_never_fails():
    df = pd.DataFrame({"a": []})
    r = dq.check_not_empty(df, "x", severity="warning")
    assert r["status"] == "warning"
    assert r["passed"] is False


def test_fail_if_critical_raises_only_on_fail():
    resultados = [
        dq.check_not_empty(pd.DataFrame({"a": [1]}), "x"),         # pass
        dq.check_not_empty(pd.DataFrame({"a": []}), "y", severity="warning"),  # warning
    ]
    dq.fail_if_critical(resultados)  # não deve levantar


def test_fail_if_critical_raises_with_summary():
    resultados = [dq.check_not_empty(pd.DataFrame({"a": []}), "x")]
    with pytest.raises(dq.DataQualityError, match="x:not_empty"):
        dq.fail_if_critical(resultados)


def test_save_report_local_writes_json_with_score(tmp_path):
    resultados = [
        dq.check_not_empty(pd.DataFrame({"a": [1]}), "x"),
        dq.check_not_empty(pd.DataFrame({"a": []}), "y", severity="warning"),
    ]
    caminho = dq.save_report(resultados, layer="teste", logs_dir=str(tmp_path))
    conteudo = json.loads(open(caminho, encoding="utf-8").read())
    assert conteudo["layer"] == "teste"
    assert conteudo["passed"] == 1
    assert conteudo["warnings"] == 1
    assert conteudo["score"] == 50.0


def test_save_report_empty_results_has_no_score(tmp_path):
    caminho = dq.save_report([], layer="vazio", logs_dir=str(tmp_path))
    conteudo = json.loads(open(caminho, encoding="utf-8").read())
    assert conteudo["score"] is None
    assert conteudo["total_checks"] == 0
