"""SparkSession local padrão do pipeline (usado pelo streaming)."""
import os
import shutil
import sys

from pyspark.sql import SparkSession


def get_spark_session(app_name: str) -> SparkSession:
    # o worker TEM que subir no mesmo interpretador do driver; senão cai no
    # python do PATH (3.14) e quebra o protocolo. forçamos, não é setdefault:
    # um PYSPARK_PYTHON herdado errado reintroduziria o crash
    os.environ["PYSPARK_PYTHON"] = sys.executable
    os.environ.setdefault("PYSPARK_DRIVER_PYTHON", sys.executable)

    if not os.environ.get("JAVA_HOME") and not shutil.which("java"):
        raise RuntimeError(
            "Java não encontrado. Rode o ambiente Spark num terminal novo "
            "(ver docs/ambiente_spark.md)."
        )

    return (
        SparkSession.builder
        .appName(app_name)
        .master("local[*]")
        .config("spark.sql.session.timeZone", "UTC")
        .getOrCreate()
    )
