"""Checks de qualidade de dados reutilizáveis entre as camadas do pipeline.

Todo check retorna um dicionário com status pass/warning/fail. Checks com
severity="warning" nunca derrubam o pipeline — ficam registrados no relatório.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


class DataQualityError(Exception):
    pass


def _resultado(entity: str, dimension: str, check: str, passed: bool, detail: str,
               severity: str = "critical") -> dict:
    status = "pass" if passed else ("warning" if severity == "warning" else "fail")
    return {
        "entity": entity,
        "dimension": dimension,
        "check": check,
        "passed": bool(passed),
        "status": status,
        "severity": severity,
        "detail": detail,
    }


def check_not_empty(df: pd.DataFrame, entity: str, severity: str = "critical") -> dict:
    return _resultado(entity, "completude", "not_empty", len(df) > 0,
                      f"{len(df)} linhas", severity)


def check_required_columns(df: pd.DataFrame, entity: str, required: list[str],
                           severity: str = "critical") -> dict:
    missing = [c for c in required if c not in df.columns]
    return _resultado(entity, "consistencia", "required_columns", not missing,
                      f"faltando: {missing}" if missing else f"{len(required)} colunas presentes",
                      severity)


def check_not_null(df: pd.DataFrame, entity: str, columns: list[str],
                   severity: str = "critical") -> dict:
    nulls = {c: int(df[c].isna().sum()) for c in columns if c in df.columns}
    offenders = {c: n for c, n in nulls.items() if n > 0}
    return _resultado(entity, "completude", "not_null", not offenders,
                      f"nulos: {offenders}" if offenders else f"sem nulos em {columns}",
                      severity)


def check_completeness(df: pd.DataFrame, entity: str, column: str, min_pct: float,
                       severity: str = "warning") -> dict:
    pct = 100 * df[column].notna().mean()
    return _resultado(entity, "completude", f"completeness({column} >= {min_pct}%)",
                      pct >= min_pct, f"{pct:.1f}% preenchido", severity)


def check_unique(df: pd.DataFrame, entity: str, key_columns: list[str],
                 severity: str = "critical") -> dict:
    dups = int(df.duplicated(subset=key_columns).sum())
    return _resultado(entity, "unicidade", f"unique({','.join(key_columns)})", dups == 0,
                      f"{dups} duplicatas", severity)


def check_range(df: pd.DataFrame, entity: str, column: str, min_value: float,
                max_value: float, severity: str = "critical") -> dict:
    serie = pd.to_numeric(df[column], errors="coerce").dropna()
    out = int(((serie < min_value) | (serie > max_value)).sum())
    return _resultado(entity, "validade", f"range({column} em [{min_value}, {max_value}])",
                      out == 0, f"{out} valores fora do intervalo", severity)


def check_format(df: pd.DataFrame, entity: str, column: str, pattern: str,
                 severity: str = "critical") -> dict:
    serie = df[column].dropna().astype(str)
    fora = int((~serie.str.fullmatch(pattern)).sum())
    return _resultado(entity, "validade", f"format({column} ~ /{pattern}/)", fora == 0,
                      f"{fora} valores fora do padrão", severity)


def check_consistency(df: pd.DataFrame, entity: str, rule: str, condition: pd.Series,
                      severity: str = "critical") -> dict:
    violacoes = int((~condition.fillna(False)).sum())
    return _resultado(entity, "consistencia", f"consistency({rule})", violacoes == 0,
                      f"{violacoes} violações", severity)


def check_referential_integrity(df: pd.DataFrame, entity: str, column: str,
                                dim_df: pd.DataFrame, dim_column: str,
                                severity: str = "critical") -> dict:
    orphans = int((~df[column].isin(dim_df[dim_column])).sum())
    return _resultado(entity, "consistencia", f"referential({column} -> {dim_column})",
                      orphans == 0, f"{orphans} chaves órfãs", severity)


def save_report(results: list[dict], layer: str, logs_dir: str = "logs") -> Path:
    contagem = {s: sum(1 for r in results if r["status"] == s)
                for s in ("pass", "warning", "fail")}
    report = {
        "layer": layer,
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "score": round(100 * contagem["pass"] / len(results), 1) if results else None,
        "total_checks": len(results),
        "passed": contagem["pass"],
        "warnings": contagem["warning"],
        "failed": contagem["fail"],
        "results": results,
    }
    Path(logs_dir).mkdir(exist_ok=True)
    path = Path(logs_dir) / f"dq_{layer}_{datetime.now():%Y%m%d_%H%M%S}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def fail_if_critical(results: list[dict]) -> None:
    failed = [r for r in results if r["status"] == "fail"]
    if failed:
        summary = "; ".join(f"{r['entity']}:{r['check']}" for r in failed)
        raise DataQualityError(f"{len(failed)} check(s) críticos falharam: {summary}")
