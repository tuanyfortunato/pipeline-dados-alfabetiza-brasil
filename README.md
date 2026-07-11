# 📊 Tech Challenge - Fase 2: Pipeline Híbrido para Análise da Alfabetização no Brasil

## 📌 Sobre o Projeto
Este projeto foi desenvolvido como requisito de avaliação do Tech Challenge (Fase 2) e tem como objetivo construir um pipeline de dados robusto e escalável para analisar o cenário da alfabetização infantil no Brasil. 

O pipeline processa os microdados da **Pesquisa Alfabetiza Brasil (INEP)** para calcular o **Indicador Criança Alfabetizada**, aplicando a regra de negócio oficial que estabelece o ponto de corte de **743 pontos** na escala de proficiência do Saeb.

## 🏗️ Arquitetura da Solução
A solução foi desenhada utilizando a **Arquitetura Medalhão**, separando o fluxo de processamento em três camadas principais:

* **🥉 Camada Bronze (Ingestão):** Conexão direta com o repositório da Base dos Dados no BigQuery (`br_inep_avaliacao_alfabetizacao.microdados`). Os dados brutos são extraídos e armazenados no formato `.parquet` para garantir a rastreabilidade (imutabilidade do dado origem).
* **🥈 Camada Silver (Qualidade e Padronização):** Processamento dos dados da camada Bronze, realizando tratamento de valores nulos, conversão de tipos de dados (casting), padronização de strings e aplicação de testes de Qualidade de Dados (Data Quality).
* **🥇 Camada Gold (Regras de Negócio e Agregação):** Transformação final aplicando a lógica de corte (>= 743 pontos). A base resultante entrega métricas prontas para o consumo analítico (BI) e serve como insumo estruturado para futuros modelos preditivos de Inteligência Artificial.

## 🛠️ Tecnologias Utilizadas
* **Linguagem:** Python
* **Processamento Distribuído:** Apache Spark (PySpark)
* **Fonte de Dados:** Google BigQuery (via `spark-bigquery-connector`)
* **Armazenamento:** Parquet

## 📂 Estrutura do Repositório

```text
├── README.md                   # Documentação do projeto
├── .gitignore                  # Arquivos ignorados pelo versionamento (dados locais)
├── src/                        # Códigos-fonte do pipeline
│   ├── 01_bronze/              # Scripts de extração e salvamento bruto
│   ├── 02_silver/              # Scripts de limpeza e tipagem
│   ├── 03_gold/                # Scripts de agregação e regras de negócio
│   └── utils/                  # Scripts de validação de Data Quality
└── notebooks/                  # Notebooks para exploração de dados e testes (Colab/Databricks)