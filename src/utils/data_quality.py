"""Checks de qualidade de dados reutilizáveis entre as camadas do pipeline."""
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


class DataQualityError(Exception):
    pass


def check_not_empty(df: pd.DataFrame, entity: str) -> dict:
    ok = len(df) > 0
    return {
        "entity": entity,
        "dimension": "completude",
        "check": "not_empty",
        "passed": bool(ok),
        "detail": f"{len(df)} linhas",
    }


def check_required_columns(df: pd.DataFrame, entity: str, required: list[str]) -> dict:
    missing = [c for c in required if c not in df.columns]
    return {
        "entity": entity,
        "dimension": "consistencia",
        "check": "required_columns",
        "passed": not missing,
        "detail": f"faltando: {missing}" if missing else f"{len(required)} colunas presentes",
    }


def check_not_null(df: pd.DataFrame, entity: str, columns: list[str]) -> dict:
    nulls = {c: int(df[c].isna().sum()) for c in columns if c in df.columns}
    offenders = {c: n for c, n in nulls.items() if n > 0}
    return {
        "entity": entity,
        "dimension": "completude",
        "check": "not_null",
        "passed": not offenders,
        "detail": f"nulos: {offenders}" if offenders else f"sem nulos em {columns}",
    }


def check_unique(df: pd.DataFrame, entity: str, key_columns: list[str]) -> dict:
    dups = int(df.duplicated(subset=key_columns).sum())
    return {
        "entity": entity,
        "dimension": "unicidade",
        "check": f"unique({','.join(key_columns)})",
        "passed": dups == 0,
        "detail": f"{dups} duplicatas",
    }


def check_range(df: pd.DataFrame, entity: str, column: str, min_value: float, max_value: float) -> dict:
    serie = pd.to_numeric(df[column], errors="coerce").dropna()
    out = int(((serie < min_value) | (serie > max_value)).sum())
    return {
        "entity": entity,
        "dimension": "validade",
        "check": f"range({column} em [{min_value}, {max_value}])",
        "passed": out == 0,
        "detail": f"{out} valores fora do intervalo",
    }


def check_referential_integrity(
    df: pd.DataFrame, entity: str, column: str, dim_df: pd.DataFrame, dim_column: str
) -> dict:
    orphans = int((~df[column].isin(dim_df[dim_column])).sum())
    return {
        "entity": entity,
        "dimension": "consistencia",
        "check": f"referential({column} -> {dim_column})",
        "passed": orphans == 0,
        "detail": f"{orphans} chaves órfãs",
    }


def save_report(results: list[dict], layer: str, logs_dir: str = "logs") -> Path:
    passed = sum(1 for r in results if r["passed"])
    report = {
        "layer": layer,
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "score": round(100 * passed / len(results), 1) if results else None,
        "total_checks": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "results": results,
    }
    Path(logs_dir).mkdir(exist_ok=True)
    path = Path(logs_dir) / f"dq_{layer}_{datetime.now():%Y%m%d_%H%M%S}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def fail_if_critical(results: list[dict]) -> None:
    failed = [r for r in results if not r["passed"]]
    if failed:
        summary = "; ".join(f"{r['entity']}:{r['check']}" for r in failed)
        raise DataQualityError(f"{len(failed)} check(s) críticos falharam: {summary}")
