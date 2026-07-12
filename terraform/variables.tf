variable "aws_region" {
  description = "Região dos recursos. O Learner Lab da AWS Academy restringe a us-east-1."
  type        = string
  default     = "us-east-1"
}

variable "bucket_name" {
  description = "Nome do bucket do data lake (globalmente único). Definir no terraform.tfvars."
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
