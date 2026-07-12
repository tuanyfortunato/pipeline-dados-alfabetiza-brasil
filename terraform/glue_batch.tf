# O batch rodando dentro da AWS: cada camada vira um Glue Python Shell job
# (pandas puro, sem Spark - a decisão local vale na nuvem), a Step Functions
# encadeia bronze -> silver -> gold e o EventBridge agenda a esteira.
#
# Os jobs assumem a LabRole (o Learner Lab não deixa criar role própria; em
# produção seria uma role mínima por job). O código do pipeline não vive aqui:
# sobe como src.zip via scripts/deploy_glue_artifacts.ps1.

data "aws_iam_role" "lab_role" {
  name = "LabRole"
}

# a casca do secret com a service account do BigQuery; o valor vai por CLI
# (aws secretsmanager put-secret-value) para nunca passar pelo state
resource "aws_secretsmanager_secret" "gcp_service_account" {
  name                    = "alfabetiza/gcp-service-account"
  description             = "Service account do BigQuery usada pela ingestão Bronze"
  recovery_window_in_days = 0
}

locals {
  # pinos iguais ao requirements.txt: o job roda com as versões que o pipeline validou
  modulos_python = join(",", [
    "google-cloud-bigquery==3.42.2",
    "google-cloud-bigquery-storage==2.27.0",
    "db-dtypes==1.3.0",
    "pandas==2.2.3",
    "pyarrow==17.0.0",
    "s3fs==2024.9.0",
    "boto3==1.35.36",
    "python-dotenv==1.0.1",
  ])
  etapas = ["bronze", "silver", "gold"]
}

resource "aws_glue_job" "batch" {
  for_each = toset(local.etapas)

  name     = "alfabetiza-batch-${each.key}"
  role_arn = data.aws_iam_role.lab_role.arn

  command {
    name            = "pythonshell"
    python_version  = "3.9"
    script_location = "s3://${aws_s3_bucket.datalake.bucket}/scripts/glue_job_batch.py"
  }

  # 1 DPU inteira: a Silver carrega 3,9 mi de alunos em memória; a fração de
  # 1/16 (1 GB) não segura. Custo: ~US$ 0,44/h só enquanto roda.
  max_capacity = 1.0
  glue_version = "3.0"
  timeout      = 30 # minutos - trava de segurança e de custo

  default_arguments = {
    "--etapa"                     = each.key
    "--lake_bucket"               = aws_s3_bucket.datalake.bucket
    "--gcp_project_id"            = var.gcp_project_id
    "--additional-python-modules" = local.modulos_python
  }
}

# a esteira: bronze -> silver -> gold, cada passo espera o job terminar (.sync);
# se um falhar, a execução falha ali - mesmo espírito do fail_if_critical local
resource "aws_sfn_state_machine" "batch" {
  name     = "alfabetiza-batch-esteira"
  role_arn = data.aws_iam_role.lab_role.arn

  definition = jsonencode({
    Comment = "Esteira batch do pipeline: bronze -> silver -> gold"
    StartAt = "Bronze"
    States = {
      Bronze = {
        Type       = "Task"
        Resource   = "arn:aws:states:::glue:startJobRun.sync"
        Parameters = { JobName = aws_glue_job.batch["bronze"].name }
        Next       = "Silver"
      }
      Silver = {
        Type       = "Task"
        Resource   = "arn:aws:states:::glue:startJobRun.sync"
        Parameters = { JobName = aws_glue_job.batch["silver"].name }
        Next       = "Gold"
      }
      Gold = {
        Type       = "Task"
        Resource   = "arn:aws:states:::glue:startJobRun.sync"
        Parameters = { JobName = aws_glue_job.batch["gold"].name }
        End        = true
      }
    }
  })
}

# agenda semanal, criada DESABILITADA de propósito: agenda ativa em conta de
# lab é job rodando sem ninguém olhando o crédito. Habilitar só na demo:
#   aws events enable-rule --name alfabetiza-batch-agenda
resource "aws_cloudwatch_event_rule" "batch_agenda" {
  name                = "alfabetiza-batch-agenda"
  description         = "Dispara a esteira batch semanalmente (segunda 06:00 UTC)"
  schedule_expression = "cron(0 6 ? * MON *)"
  state               = "DISABLED"
}

resource "aws_cloudwatch_event_target" "batch_agenda" {
  rule     = aws_cloudwatch_event_rule.batch_agenda.name
  arn      = aws_sfn_state_machine.batch.arn
  role_arn = data.aws_iam_role.lab_role.arn
}
