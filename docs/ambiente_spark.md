# Ambiente Spark (streaming)

O pipeline usa **Python 3.11 nos dois ambientes** virtuais, mas mantém eles separados de
propósito. O PySpark 3.5 suporta oficialmente até o 3.11 (o Python padrão da máquina é o 3.14,
que o Spark não aceita), então o streaming precisa ser 3.11. Para não misturar as dependências
pesadas do Spark com o batch, cada frente tem seu venv: o `.venv` enxuto pro batch (pandas) e o
`.venv-spark` com o PySpark e a ponte com o Java — ambos em 3.11.

| venv | Python | Usado para |
|---|---|---|
| `.venv` | 3.11 | ingestão batch, Silver, Gold, notebooks (pandas), producer |
| `.venv-spark` | 3.11 | consumer de streaming e qualquer execução em PySpark |

## Pré-requisitos (Windows)

- **Python 3.11** instalado (`py -3.11 --version`).
- **JDK 17** — o Spark 3.5 não sobe sem JVM. Instalado com `winget install Microsoft.OpenJDK.17`,
  que já registra `JAVA_HOME` no sistema.
- **winutils.exe + hadoop.dll** — o Spark precisa deles para escrever Parquet no Windows.
  Ficam em `%LOCALAPPDATA%\hadoop\bin`, com `HADOOP_HOME` apontando para `%LOCALAPPDATA%\hadoop`.
  Binários compatíveis com o Hadoop 3.3.x que o PySpark embarca (fonte: repositório
  `cdarlint/winutils`, pasta `hadoop-3.3.6`).

## Como montar do zero

```powershell
py -3.11 -m venv .venv-spark
# pyspark roda o streaming; pyarrow/pandas atendem o producer e o DQ do consumer
.venv-spark\Scripts\python.exe -m pip install pyspark==3.5.3 python-dotenv==1.0.1 pyarrow==17.0.0 pandas==2.2.3

winget install --id Microsoft.OpenJDK.17 --accept-package-agreements --accept-source-agreements

# winutils
$h = "$env:LOCALAPPDATA\hadoop\bin"; New-Item -ItemType Directory -Force $h | Out-Null
$base = "https://raw.githubusercontent.com/cdarlint/winutils/master/hadoop-3.3.6/bin"
Invoke-WebRequest "$base/winutils.exe" -OutFile "$h\winutils.exe"
Invoke-WebRequest "$base/hadoop.dll"   -OutFile "$h\hadoop.dll"
[Environment]::SetEnvironmentVariable("HADOOP_HOME", "$env:LOCALAPPDATA\hadoop", "User")
```

Feche e reabra o terminal depois de instalar o JDK e setar o `HADOOP_HOME` — variáveis de
ambiente novas só valem em sessões novas.

## Detalhe importante do PySpark

Driver e worker precisam do **mesmo** interpretador. Como o `python` do PATH é o 3.14, o worker
subiria na versão errada e quebraria. `src/utils/spark_session.py` resolve isso fixando
`PYSPARK_PYTHON` no interpretador do próprio `.venv-spark` — sempre use esse helper para abrir a
sessão.

## Validação rápida

```powershell
.venv-spark\Scripts\python.exe -c "from pyspark.sql import SparkSession; s=SparkSession.builder.master('local[*]').getOrCreate(); print(s.version); s.stop()"
```

Deve imprimir `3.5.3` sem stack trace.

## Plano B

Se o Spark no Windows virar um poço de tempo, o mesmo código roda no **Google Colab** ou
**Databricks Community** (PySpark pré-instalado). Muda só onde executa.
