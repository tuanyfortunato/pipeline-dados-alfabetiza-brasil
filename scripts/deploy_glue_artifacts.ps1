# Publica os artefatos dos Glue jobs no S3: o src.zip (código do pipeline) e o
# wrapper. Rodar depois de qualquer mudança em src/ ou no wrapper — o job sempre
# baixa a versão que estiver no bucket.

$ErrorActionPreference = "Stop"
$aws = if (Get-Command aws -ErrorAction SilentlyContinue) { "aws" }
       else { "$env:LOCALAPPDATA\Programs\Amazon\AWSCLIV2\aws.exe" }
$raiz = Split-Path $PSScriptRoot -Parent
$bucket = "alfabetiza-brasil-datalake-tc2"

Write-Host "== Conferindo credencial da sessao do lab =="
& $aws sts get-caller-identity --query Arn --output text
if ($LASTEXITCODE -ne 0) { Write-Host "Credencial expirada." -ForegroundColor Red; exit 1 }

Write-Host "`n== Empacotando src/ (sem __pycache__) =="
$zip = Join-Path $env:TEMP "src.zip"
if (Test-Path $zip) { Remove-Item $zip }
# o zip precisa do prefixo src/ para os imports do pipeline resolverem
$staging = Join-Path $env:TEMP "glue_staging"
if (Test-Path $staging) { Remove-Item $staging -Recurse -Force }
New-Item -ItemType Directory "$staging\src" | Out-Null
Copy-Item "$raiz\src\*" "$staging\src" -Recurse -Exclude "__pycache__"
Get-ChildItem $staging -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
Compress-Archive -Path "$staging\src" -DestinationPath $zip
Remove-Item $staging -Recurse -Force

Write-Host "== Publicando no s3://$bucket/scripts/ =="
& $aws s3 cp $zip "s3://$bucket/scripts/src.zip"
& $aws s3 cp "$raiz\scripts\glue_job_batch.py" "s3://$bucket/scripts/glue_job_batch.py"

Write-Host "`n== Pronto =="
