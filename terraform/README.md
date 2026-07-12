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

O state fica local (`terraform.tfstate`, gitignorado) - projeto solo não justifica
backend remoto. O código `.tf` é a fonte da verdade; o state é descartável junto com
a conta do lab.

Para desmontar tudo ao final: `terraform destroy`.
