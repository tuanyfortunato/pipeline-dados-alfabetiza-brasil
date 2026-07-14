# Infraestrutura como código

Toda a infra AWS do pipeline nasce daqui: o bucket do data lake (com versionamento,
bloqueio de acesso público, criptografia e lifecycle de custo na Bronze) e o consumo
analítico da Gold (database no Glue, workgroup do Athena com trava de scan e as três
tabelas declaradas com o schema do `docs/dicionario_dados_gold.md`).

## Contexto do ambiente

A conta é um **Learner Lab da AWS Academy**, o que muda duas coisas em relação a uma
conta comum:

- a credencial é temporária (~4h) - copie o bloco de "AWS Details" do lab para o
  `~/.aws/credentials` a cada sessão, incluindo o `aws_session_token`;
- IAM de escrita e Budgets são bloqueados - por isso não há aqui usuário dedicado do
  pipeline nem alerta de custo. Em conta própria, entrariam um `aws_iam_user` de menor
  privilégio e um `aws_budgets_budget`; o teto de gasto do lab é o próprio crédito.

Região fixa em `us-east-1` (restrição do lab).

## Como aplicar

```powershell
cd terraform
cp terraform.tfvars.example terraform.tfvars   # ajuste o nome do bucket
terraform init
terraform plan     # leia antes de aplicar
terraform apply
terraform output   # nome do bucket -> LAKE_PATH do .env
```

O state fica no S3 (prefixo `terraform-state/` do próprio bucket do data lake),
com o locking nativo do Terraform (`use_lockfile`, sem precisar de DynamoDB). Era
local no começo do projeto, mas isso quebra assim que existe um segundo lugar
rodando `terraform` - o runner do GitHub Actions (ver `.github/workflows/deploy-aws.yml`)
começa cada execução do zero, sem o histórico de nenhuma máquina. Sem state
compartilhado, o `apply` do CI tentaria recriar bucket, jobs, tudo - foi
literalmente o que quase aconteceu aqui ao notar que a pasta local não tinha
`.tfstate`, mesmo com a infra inteira já no ar.

A configuração do backend é parcial em `versions.tf`; os valores (bucket, key,
região) vêm de `backend.hcl` (gitignorado, copie de `backend.hcl.example`):

```powershell
terraform init -backend-config=backend.hcl
```

Para desmontar tudo ao final: `terraform destroy`.

## CI/CD

O workflow `.github/workflows/deploy-aws.yml` roda `terraform plan`/`apply` e
publica o código novo no S3 (a mesma coisa que `deploy_glue_artifacts.ps1` faz
na mão). Duas coisas mudam em relação a uma conta AWS normal, e as duas vêm do
Learner Lab:

**Gatilho manual, não `push` em `main`.** A credencial da sessão do lab expira
em ~4h e precisa ser recolada nos secrets do repositório
(`AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`/`AWS_SESSION_TOKEN`) antes de cada
uso - automatizar em todo merge geraria execução vermelha sempre que alguém
mergeasse fora de uma sessão ativa. O `workflow_dispatch` deixa escolher o
momento (sessão aberta, credencial fresca), com três opções: só planejar,
aplicar de verdade, e disparar a esteira no final pra validar.

**Sem OIDC.** Numa conta própria, o normal é o GitHub Actions assumir uma role
via OpenID Connect - zero segredo de longa duração armazenado. Aqui não dá:
criar o provider OIDC e a role de confiança é escrita de IAM, que o lab
bloqueia. Por isso os secrets guardam a credencial de sessão mesmo, e alguém
tem que atualizá-los a cada ~4h. Numa conta própria, a mudança seria só trocar
o passo de `configure-aws-credentials` para assumir a role via OIDC e o
gatilho para `push: branches: [main]` - o resto do workflow (plan, apply,
publicação do código) fica igual.

### As opções do `workflow_dispatch`

| Opção | O que faz |
|---|---|
| `apply` | `terraform apply` de verdade. Sem marcar, o job só roda `plan` - não toca em nada na AWS |
| `deploy_code` | publica `src.zip` + os scripts do Glue no S3 (o `deploy_glue_artifacts.ps1` de dentro do CI) |
| `run_pipeline` | dispara a state machine (`bronze -> silver -> gold`), pra validar a carga depois do deploy |
| `ligar_kinesis` | apply restrito a `aws_kinesis_stream.eventos` + `aws_glue_job.streaming` - recria só o que o streaming precisa, sem mexer no resto da infra |
| `desligar_kinesis` | para o Glue Streaming job (se estiver rodando) e destrói o Kinesis - equivalente ao `aws_desligar.ps1`, mas via `terraform destroy -target`, então o state não fica desalinhado da realidade como aconteceria apagando na mão |
| `disparar_streaming` | `start-job-run` no Glue Streaming job - o pipeline volta a consumir o Kinesis e gravar na Bronze |

`ligar_kinesis`, `desligar_kinesis` e `disparar_streaming` são encadeados no
workflow (`needs`) pra nunca rodar em paralelo com o `apply`/`plan` principal -
os dois mexeriam no mesmo state ao mesmo tempo. `desligar_kinesis` e
`disparar_streaming` esperam o `ligar_kinesis` terminar (ou ser pulado, se não
marcado) antes de rodar.
