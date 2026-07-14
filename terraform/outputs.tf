output "bucket_name" {
  description = "Nome do bucket do data lake - vai no LAKE_PATH do .env como s3://<nome>"
  value       = aws_s3_bucket.datalake.bucket
}

output "athena_workgroup" {
  description = "Workgroup para rodar as queries da Gold"
  value       = aws_athena_workgroup.gold.name
}

output "glue_database" {
  description = "Database do catálogo com as três tabelas Gold"
  value       = aws_glue_catalog_database.gold.name
}

output "state_machine_arn" {
  description = "Esteira batch na Step Functions - use no start-execution da demo"
  value       = aws_sfn_state_machine.batch.arn
}

output "kinesis_stream_name" {
  description = "Stream de eventos - use no --stream do producer (modo kinesis)"
  value       = aws_kinesis_stream.eventos.name
}

output "streaming_job_name" {
  description = "Glue Streaming job - use no start-job-run da demo de streaming"
  value       = aws_glue_job.streaming.name
}

output "sns_alertas_arn" {
  description = "Topico de alerta de falha - confirme a inscricao do e-mail apos o apply"
  value       = aws_sns_topic.alertas.arn
}
