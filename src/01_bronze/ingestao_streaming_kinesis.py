"""
Consumer de streaming da Bronze rodando na AWS: Kinesis -> Bronze (Parquet no S3).

É o irmão de nuvem do ingestao_streaming_consumer.py. A lógica é a mesma — Spark
Structured Streaming materializando micro-batches em Parquet com os metadados de
rastreabilidade da Bronze — só muda a FONTE (Kinesis, não pasta landing) e ONDE
executa (Glue Streaming job, não .venv-spark local). Os dois convivem no repo de
propósito: duas fontes para o mesmo destino, e a comparação vira seção de README.

Este arquivo é o script de entrada de um Glue Streaming job (glue_version 4.0, que
traz o conector Kinesis nativo). Sobe pro S3 via scripts/deploy_glue_artifacts.ps1
e é referenciado pelo script_location do aws_glue_job.streaming (terraform).

Schema explícito de propósito: não usamos o inferSchema do Glue porque em streaming
ele é frágil (a inferência pode não materializar as colunas a tempo do micro-batch,
entregando um placeholder). Lemos a coluna crua `data` do Kinesis e aplicamos o
mesmo schema do consumer local via from_json.

Argumentos do job (default_arguments no Terraform):
    --stream_arn    ARN do Kinesis Data Stream de eventos
    --lake_bucket   nome do bucket do data lake
    --aws_region    região do stream
"""
import sys

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import functions as F
from pyspark.sql.types import (
    DoubleType,
    IntegerType,
    LongType,
    StringType,
    StructField,
    StructType,
)

# mesmo schema do consumer local; a ordem das colunas alimenta o _row_hash
SCHEMA = StructType([
    StructField("id_municipio", LongType()),
    StructField("ano", IntegerType()),
    StructField("proficiencia_media", DoubleType()),
    StructField("tipo_evento", StringType()),
    StructField("event_timestamp", StringType()),
])
COLUNAS_FONTE = [c.name for c in SCHEMA.fields]
SOURCE = "kinesis/alfabetiza-eventos"


def main() -> None:
    args = getResolvedOptions(sys.argv, ["JOB_NAME", "stream_arn", "lake_bucket", "aws_region"])

    sc = SparkContext.getOrCreate()
    glue_context = GlueContext(sc)
    spark = glue_context.spark_session
    job = Job(glue_context)
    job.init(args["JOB_NAME"], args)
    spark.conf.set("spark.sql.session.timeZone", "UTC")

    output = f"s3://{args['lake_bucket']}/bronze/streaming/eventos_indicador/"
    checkpoint = f"s3://{args['lake_bucket']}/bronze/streaming/_checkpoint_kinesis/"

    # o conector Spark nativo do Glue pede streamName + endpointUrl (o streamARN é
    # da API create_data_frame.from_options); derivamos o nome do próprio ARN
    stream_name = args["stream_arn"].split("/")[-1]
    endpoint = f"https://kinesis.{args['aws_region']}.amazonaws.com"

    # sem classification/inferSchema: o frame chega cru (coluna binária `data` com o
    # payload) e parseamos nós mesmos com from_json, evitando a inferência frágil
    bruto = (
        spark.readStream
        .format("kinesis")
        .option("streamName", stream_name)
        .option("endpointUrl", endpoint)
        .option("startingposition", "TRIM_HORIZON")
        .load()
    )

    eventos = (
        bruto
        .select(F.from_json(F.col("data").cast("string"), SCHEMA).alias("e"))
        .select("e.*")
        # mesmos metadados de rastreabilidade da Bronze batch e do consumer local
        .withColumn("_row_hash", F.sha2(F.concat_ws("|", *COLUNAS_FONTE), 256))
        .withColumn("_ingestion_ts", F.current_timestamp())
        .withColumn("_source", F.lit(SOURCE))
    )

    query = (
        eventos.writeStream
        .format("parquet")
        .option("path", output)
        .option("checkpointLocation", checkpoint)
        .partitionBy("ano")
        .trigger(processingTime="30 seconds")
        .start()
    )
    query.awaitTermination()
    job.commit()


if __name__ == "__main__":
    main()
