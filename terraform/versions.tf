terraform {
  required_version = ">= 1.10" # backend S3 com locking nativo (use_lockfile), sem depender de DynamoDB

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Configuração parcial: bucket/key/region vêm de backend.hcl (gitignorado, um por
  # ambiente) via `terraform init -backend-config=backend.hcl`. Sem isso, cada
  # execução (inclusive a do CI, que roda num runner efêmero) começaria com state
  # vazio e tentaria recriar recursos que já existem - foi o que quase aconteceu
  # ao rodar isso manualmente antes deste backend existir.
  backend "s3" {}
}

provider "aws" {
  region = var.aws_region

  # tudo que o projeto criar sai com as mesmas tags
  default_tags {
    tags = var.tags
  }
}
