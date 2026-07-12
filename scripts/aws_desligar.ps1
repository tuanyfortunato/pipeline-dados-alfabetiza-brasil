# Para tudo do projeto que gera custo por hora na AWS. Rodar ao fim de cada
# sessão de trabalho (ou demo). O que é serverless em repouso - S3, catálogo
# Glue, Athena sem query - não cobra parado e fica de fora.
#
# Ordem importa: primeiro a orquestração (senão ela relança job), depois os
# jobs, a agenda e por fim o Kinesis (cobra por shard-hora só de existir;
# o aws_ligar.ps1 recria via terraform apply).

$ErrorActionPreference = "Continue"
$aws = if (Get-Command aws -ErrorAction SilentlyContinue) { "aws" }
       else { "$env:LOCALAPPDATA\Programs\Amazon\AWSCLIV2\aws.exe" }
$prefixo = "alfabetiza"

Write-Host "== Conferindo credencial da sessao do lab =="
& $aws sts get-caller-identity --query Arn --output text
if ($LASTEXITCODE -ne 0) {
    Write-Host "Credencial invalida ou expirada. Start Lab -> AWS Details -> recolar em ~/.aws/credentials" -ForegroundColor Red
    exit 1
}

Write-Host "`n== 1/4 Step Functions: parando execucoes em andamento =="
$maquinas = & $aws stepfunctions list-state-machines --query "stateMachines[?starts_with(name, '$prefixo')].stateMachineArn" --output text
if ($maquinas) {
    foreach ($m in $maquinas -split "\s+") {
        $execucoes = & $aws stepfunctions list-executions --state-machine-arn $m --status-filter RUNNING --query "executions[].executionArn" --output text
        if ($execucoes) {
            foreach ($e in $execucoes -split "\s+") {
                & $aws stepfunctions stop-execution --execution-arn $e | Out-Null
                Write-Host "  parada: $e"
            }
        } else { Write-Host "  nenhuma execucao rodando em $m" }
    }
} else { Write-Host "  nenhuma state machine do projeto (ainda)" }

Write-Host "`n== 2/4 Glue: parando job runs em andamento (inclui o streaming) =="
$jobs = & $aws glue list-jobs --query "JobNames[?starts_with(@, '$prefixo')]" --output text
if ($jobs) {
    foreach ($j in $jobs -split "\s+") {
        $runs = & $aws glue get-job-runs --job-name $j --query "JobRuns[?JobRunState=='RUNNING'].Id" --output text
        if ($runs) {
            & $aws glue batch-stop-job-run --job-name $j --job-run-ids ($runs -split "\s+") | Out-Null
            Write-Host "  parado: $j"
        } else { Write-Host "  $j sem run ativo" }
    }
} else { Write-Host "  nenhum job do projeto (ainda)" }

Write-Host "`n== 3/4 EventBridge: desabilitando agendas =="
$regras = & $aws events list-rules --name-prefix $prefixo --query "Rules[?State=='ENABLED'].Name" --output text
if ($regras) {
    foreach ($r in $regras -split "\s+") {
        & $aws events disable-rule --name $r
        Write-Host "  desabilitada: $r"
    }
} else { Write-Host "  nenhuma agenda habilitada" }

Write-Host "`n== 4/4 Kinesis: removendo streams (cobram por hora so de existir) =="
$streams = & $aws kinesis list-streams --query "StreamNames[?starts_with(@, '$prefixo')]" --output text
if ($streams) {
    foreach ($s in $streams -split "\s+") {
        & $aws kinesis delete-stream --stream-name $s
        Write-Host "  removido: $s (o aws_ligar.ps1 recria via terraform)"
    }
} else { Write-Host "  nenhum stream do projeto" }

Write-Host "`n== Pronto =="
Write-Host "Custo residual: so o storage do S3 (centavos/mes) - dado nao se apaga."
Write-Host "Confira tambem o consumo de credito no painel do Learner Lab antes do End Lab."
