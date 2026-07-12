"""Caminhos do data lake: local em dev, s3:// na nuvem.

pathlib não fala s3://, então quem monta caminho no lake usa lake_path() em vez
de Path(LAKE_PATH) / ... — pandas e pyarrow aceitam a string resultante nos
dois mundos (com s3fs instalado no caso do S3).
"""
import os
from pathlib import Path


def _raiz() -> str:
    return os.environ.get("LAKE_PATH", "./data")


def is_s3() -> bool:
    return _raiz().startswith("s3://")


def lake_path(*partes) -> str:
    """Monta um caminho dentro do lake. Sempre string."""
    if is_s3():
        return "/".join([_raiz().rstrip("/"), *map(str, partes)])
    return str(Path(_raiz()).joinpath(*map(str, partes)))


def preparar_diretorio(caminho: str) -> None:
    """mkdir local. No S3 não existe diretório — o prefixo nasce na escrita."""
    if not is_s3():
        Path(caminho).mkdir(parents=True, exist_ok=True)


def existe(caminho: str) -> bool:
    if is_s3():
        import s3fs

        return s3fs.S3FileSystem().exists(caminho)
    return Path(caminho).exists()
