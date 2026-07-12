# Religa a infra do projeto. Como tudo e Terraform, religar = aplicar o codigo:
# ele recria o que o aws_desligar.ps1 removeu (Kinesis) e nao mexe no que ja
# existe (S3, catalogo, jobs). O plan aparece antes e pede confirmacao.
#
# As agendas do EventBridge NAO sao reabilitadas de proposito - agenda ativa em
# conta de lab e job rodando sem ninguem olhando. Para a demo:
#   aws events enable-rule --name <regra>

$ErrorActionPreference = "Stop"
$aws = if (Get-Command aws -ErrorAction SilentlyContinue) { "aws" }
       else { "$env:LOCALAPPDATA\Programs\Amazon\AWSCLIV2\aws.exe" }
$tf = if (Get-Command terraform -ErrorAction SilentlyContinue) { "terraform" }
      else { "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\Hashicorp.Terraform_Microsoft.Winget.Source_8wekyb3d8bbwe\terraform.exe" }

Write-Host "== Conferindo credencial da sessao do lab =="
& $aws sts get-caller-identity --query Arn --output text
if ($LASTEXITCODE -ne 0) {
    Write-Host "Credencial invalida ou expirada. Start Lab -> AWS Details -> recolar em ~/.aws/credentials" -ForegroundColor Red
    exit 1
}

Write-Host "`n== terraform apply (recria o que foi desligado) =="
Push-Location "$PSScriptRoot\..\terraform"
try {
    & $tf apply
} finally {
    Pop-Location
}

Write-Host "`n== Pronto =="
Write-Host "Agendas do EventBridge continuam desabilitadas (decisao de custo)."
Write-Host "Jobs Glue nao precisam 'ligar' - rodam sob demanda pela Step Functions ou manualmente."
