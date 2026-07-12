# Data lake do pipeline: um bucket S3 com as camadas bronze/silver/gold como prefixos.
# Os prefixos nascem quando o pipeline escrever o primeiro objeto - S3 não tem pasta.
#
# Nota do ambiente: a conta é um Learner Lab (AWS Academy), que bloqueia IAM de
# escrita e Budgets. Por isso não há aqui usuário dedicado do pipeline nem alerta
# de custo - o pipeline usa a credencial da sessão do lab, e o teto de gasto é o
# crédito do próprio lab. Em conta própria, o desenho seria usuário IAM de menor
# privilégio (só este bucket) + aws_budgets_budget.

resource "aws_s3_bucket" "datalake" {
  bucket = var.bucket_name
}

# versões antigas preservadas: dá imutabilidade/rastreabilidade à Bronze
resource "aws_s3_bucket_versioning" "datalake" {
  bucket = aws_s3_bucket.datalake.id

  versioning_configuration {
    status = "Enabled"
  }
}

# dado de aluno não vaza por engano: bloqueio total de acesso público
resource "aws_s3_bucket_public_access_block" "datalake" {
  bucket = aws_s3_bucket.datalake.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# criptografia em repouso sem custo extra (SSE-S3)
resource "aws_s3_bucket_server_side_encryption_configuration" "datalake" {
  bucket = aws_s3_bucket.datalake.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# FinOps: a Bronze é o que mais pesa e o que menos se relê depois de materializada.
# Esfria em 30 dias, congela em 90; versões antigas somem em 90.
resource "aws_s3_bucket_lifecycle_configuration" "datalake" {
  bucket = aws_s3_bucket.datalake.id

  rule {
    id     = "bronze-esfria"
    status = "Enabled"

    filter {
      prefix = "bronze/"
    }

    transition {
      days          = 30
      storage_class = "STANDARD_IA"
    }

    transition {
      days          = 90
      storage_class = "GLACIER"
    }

    noncurrent_version_expiration {
      noncurrent_days = 90
    }
  }
}
