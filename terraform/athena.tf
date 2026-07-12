# Consumo analítico da Gold via Athena: as três tabelas declaradas aqui, não por
# crawler - o schema versionado é o mesmo contrato do docs/dicionario_dados_gold.md.
# Cada tabela é um Parquet único (sem partição), então não precisa de MSCK/projection.
#
# Tipos: os inteiros do pandas viram int64 no Parquet, então tudo é bigint aqui;
# float vira double. Declarar int quebraria a leitura (HIVE_BAD_DATA).

resource "aws_glue_catalog_database" "gold" {
  name = "alfabetiza_gold"
}

# workgroup com resultado dentro do próprio lake e trava de custo por query
resource "aws_athena_workgroup" "gold" {
  name          = "alfabetiza-gold"
  force_destroy = true

  configuration {
    enforce_workgroup_configuration = true

    # 1 GB por query - a Gold inteira tem poucos MB, isso já é folga enorme
    bytes_scanned_cutoff_per_query = 1073741824

    result_configuration {
      output_location = "s3://${aws_s3_bucket.datalake.bucket}/athena-results/"

      encryption_configuration {
        encryption_option = "SSE_S3"
      }
    }
  }
}

locals {
  # colunas por tabela, na ordem do dicionário de dados
  gold_tables = {
    indicador_municipio = [
      { name = "ano", type = "bigint" },
      { name = "id_municipio", type = "bigint" },
      { name = "sigla_uf", type = "string" },
      { name = "alunos_avaliados", type = "bigint" },
      { name = "alunos_presentes", type = "bigint" },
      { name = "alunos_com_nota", type = "bigint" },
      { name = "taxa_participacao", type = "double" },
      { name = "taxa_alfabetizacao", type = "double" },
      { name = "proficiencia_media", type = "double" },
    ]
    meta_vs_resultado = [
      { name = "ano", type = "bigint" },
      { name = "nivel", type = "string" },
      { name = "rede", type = "string" },
      { name = "sigla_uf", type = "string" },
      { name = "id_municipio", type = "bigint" },
      { name = "alunos_com_nota", type = "bigint" },
      { name = "taxa_alfabetizacao", type = "double" },
      { name = "meta_ano", type = "double" },
      { name = "gap", type = "double" },
      { name = "atingiu_meta", type = "boolean" },
    ]
    evolucao_temporal = [
      { name = "ano", type = "bigint" },
      { name = "nivel", type = "string" },
      { name = "rede", type = "string" },
      { name = "sigla_uf", type = "string" },
      { name = "id_municipio", type = "bigint" },
      { name = "alunos_avaliados", type = "bigint" },
      { name = "alunos_presentes", type = "bigint" },
      { name = "alunos_com_nota", type = "bigint" },
      { name = "taxa_participacao", type = "double" },
      { name = "taxa_alfabetizacao", type = "double" },
      { name = "proficiencia_media", type = "double" },
    ]
  }
}

resource "aws_glue_catalog_table" "gold" {
  for_each = local.gold_tables

  name          = each.key
  database_name = aws_glue_catalog_database.gold.name
  table_type    = "EXTERNAL_TABLE"

  parameters = {
    classification = "parquet"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.datalake.bucket}/gold/${each.key}/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.serde2.parquet.ParquetHiveSerDe"
    }

    dynamic "columns" {
      for_each = each.value
      content {
        name = columns.value.name
        type = columns.value.type
      }
    }
  }
}
