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
