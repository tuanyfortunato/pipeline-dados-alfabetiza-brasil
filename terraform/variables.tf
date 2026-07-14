variable "aws_region" {
  description = "Região dos recursos. O Learner Lab da AWS Academy restringe a us-east-1."
  type        = string
  default     = "us-east-1"
}

variable "bucket_name" {
  description = "Nome do bucket do data lake (globalmente único). Definir no terraform.tfvars."
  type        = string
}

variable "gcp_project_id" {
  description = "Projeto GCP usado na extração do BigQuery (vai como argumento dos Glue jobs)."
  type        = string
}

variable "alert_email" {
  description = "E-mail que recebe o alarme de falha da esteira/streaming (confirmação por SNS na primeira vez)."
  type        = string
}

variable "tags" {
  description = "Tags aplicadas a todos os recursos."
  type        = map(string)
  default = {
    projeto    = "alfabetiza-brasil"
    gerenciado = "terraform"
  }
}
