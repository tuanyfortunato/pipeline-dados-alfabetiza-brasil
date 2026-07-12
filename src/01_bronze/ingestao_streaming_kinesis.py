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

Argumentos do job (default_arguments no Terraform):
    --stream_arn    ARN do Kinesis Data Stream de eventos
    --lake_bucket   nome do bucket do data lake
    --aws_region    região do stream (monta o endpoint do Kinesis)
"""
import sys

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import functions as F

# mesmas colunas de negócio do consumer local; a ordem alimenta o _row_hash
COLUNAS_FONTE = ["id_municipio", "ano", "proficiencia_media", "tipo_evento", "event_timestamp"]
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

    # o Glue decodifica o JSON e infere o schema (classification/inferSchema);
    # o DataFrame de streaming já chega com as colunas de negócio prontas
    kinesis_options = {
        "streamARN": args["stream_arn"],
        "startingPosition": "TRIM_HORIZON",
        "inferSchema": "true",
        "classification": "json",
        "endpointUrl": f"https://kinesis.{args['aws_region']}.amazonaws.com",
    }
    eventos = glue_context.create_data_frame.from_options(
        connection_type="kinesis",
        connection_options=kinesis_options,
    )

    def processar_batch(df, _batch_id) -> None:
        if df.rdd.isEmpty():
            return
        # mesmos metadados de rastreabilidade da Bronze batch e do consumer local
        enriquecido = (
            df
            .withColumn("_row_hash", F.sha2(F.concat_ws("|", *COLUNAS_FONTE), 256))
            .withColumn("_ingestion_ts", F.current_timestamp())
            .withColumn("_source", F.lit(SOURCE))
        )
        (
            enriquecido.write
            .mode("append")
            .partitionBy("ano")
            .parquet(output)
        )

    # windowSize é o gatilho do micro-batch; checkpoint no S3 garante exactly-once
    # e retomada de onde parou se o job cair (ou for parado e religado na demo)
    glue_context.forEachBatch(
        frame=eventos,
        batch_function=processar_batch,
        options={"windowSize": "30 seconds", "checkpointLocation": checkpoint},
    )
    job.commit()


if __name__ == "__main__":
    main()
