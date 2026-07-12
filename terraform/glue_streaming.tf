# Frente C — o streaming rodando dentro da AWS: um Kinesis Data Stream faz a fila
# de eventos (o padrão de mercado, no lugar da pasta landing local) e um Glue
# Streaming job (Spark Structured Streaming) consome do Kinesis e materializa na
# Bronze do S3. Mesmo destino do consumer local de pasta — são duas fontes para
# o mesmo lugar, e a comparação vira seção de README.
#
# Custo: o Glue Streaming cobra por DPU-hora ENQUANTO RODA (~US$ 0,88/h com 2 DPU).
# Não é serverless em repouso como os jobs batch — por isso o job nasce sob demanda,
# roda a demo cronometrada e é parado (aws_desligar.ps1 já mata runs ativos). O
# Kinesis cobra por shard-hora só de existir, então o aws_desligar.ps1 destrói o
# stream e o aws_ligar.ps1 (terraform apply) o recria.

# a fila de eventos: 1 shard aguenta de sobra o volume do simulador; retenção de
# 24h é o mínimo padrão (evento perdido reprocessa dentro da janela)
resource "aws_kinesis_stream" "eventos" {
  name             = "alfabetiza-eventos"
  shard_count      = 1
  retention_period = 24

  stream_mode_details {
    stream_mode = "PROVISIONED"
  }
}

# o consumer Spark: diferente do batch (pandas em Python Shell), streaming precisa
# de Spark de verdade — command "gluestreaming", Glue 4.0 (conector Kinesis nativo).
# O código sobe como scripts/ingestao_streaming_kinesis.py via deploy_glue_artifacts.ps1.
resource "aws_glue_job" "streaming" {
  name     = "alfabetiza-streaming-kinesis"
  role_arn = data.aws_iam_role.lab_role.arn

  command {
    name            = "gluestreaming"
    python_version  = "3"
    script_location = "s3://${aws_s3_bucket.datalake.bucket}/scripts/ingestao_streaming_kinesis.py"
  }

  glue_version      = "4.0"
  worker_type       = "G.1X"
  number_of_workers = 2
  timeout           = 60 # minutos - rede de segurança contra "esqueci o job ligado"

  default_arguments = {
    "--stream_arn"  = aws_kinesis_stream.eventos.arn
    "--lake_bucket" = aws_s3_bucket.datalake.bucket
    "--aws_region"  = var.aws_region
    # o Glue manda os logs do driver/executors pro CloudWatch sozinho
    "--enable-continuous-cloudwatch-log" = "true"
    "--job-language"                     = "python"
  }
}
