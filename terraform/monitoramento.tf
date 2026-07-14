# Alertas de falha do pipeline via SNS - fecha a lacuna que o README já
# registrava como consciente ("o que não está implementado, e seria o
# próximo passo"). Duas fontes de falha, dois jeitos de pegar cada uma:
#
# - a esteira batch (Step Functions) já publica métrica nativa no
#   CloudWatch (namespace AWS/States) - um alarme simples nisso cobre
#   bronze/silver/gold de uma vez, porque o `.sync` propaga a falha do
#   Glue job pra execução inteira;
# - o Glue Streaming roda fora da state machine (é disparado à parte, sob
#   demanda), então não tem métrica de execução pra amarrar um alarme -
#   a captura é por evento, direto do Glue Job State Change.
#
# As duas fontes mandam pro mesmo tópico SNS, com e-mail como único
# assinante - é o que o escopo do projeto pede. Fora do escopo por
# enquanto: alerta de queda no score de DQ e métrica de latência, porque
# os dois exigiriam publicar métrica customizada de dentro do pipeline em
# pandas (código novo, não só infra) - registrado como próximo passo real.

resource "aws_sns_topic" "alertas" {
  name = "alfabetiza-alertas"
}

resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.alertas.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# Falha na esteira batch (bronze -> silver -> gold): métrica nativa do Step
# Functions, sem precisar de nenhum código novo no pipeline.
resource "aws_cloudwatch_metric_alarm" "esteira_falhou" {
  alarm_name        = "alfabetiza-batch-esteira-falhou"
  alarm_description = "A esteira batch (bronze -> silver -> gold) falhou pelo menos uma vez na janela de 5 min"
  namespace         = "AWS/States"
  metric_name       = "ExecutionsFailed"
  dimensions = {
    StateMachineArn = aws_sfn_state_machine.batch.arn
  }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alertas.arn]
}

resource "aws_cloudwatch_event_rule" "streaming_falhou" {
  name        = "alfabetiza-streaming-falhou"
  description = "Glue Streaming job terminou em FAILED, ERROR ou TIMEOUT"

  event_pattern = jsonencode({
    source      = ["aws.glue"]
    detail-type = ["Glue Job State Change"]
    detail = {
      jobName = [aws_glue_job.streaming.name]
      state   = ["FAILED", "ERROR", "TIMEOUT"]
    }
  })
}

resource "aws_cloudwatch_event_target" "streaming_falhou" {
  rule = aws_cloudwatch_event_rule.streaming_falhou.name
  arn  = aws_sns_topic.alertas.arn
}

# EventBridge precisa de permissão explícita pra publicar no tópico - sem
# isso o evento dispara e a entrega falha em silêncio, sem erro nenhum
# aparente no console.
resource "aws_sns_topic_policy" "permite_eventbridge" {
  arn = aws_sns_topic.alertas.arn

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "PermiteEventBridgePublicar"
      Effect    = "Allow"
      Principal = { Service = "events.amazonaws.com" }
      Action    = "sns:Publish"
      Resource  = aws_sns_topic.alertas.arn
      Condition = {
        ArnEquals = {
          "aws:SourceArn" = aws_cloudwatch_event_rule.streaming_falhou.arn
        }
      }
    }]
  })
}
