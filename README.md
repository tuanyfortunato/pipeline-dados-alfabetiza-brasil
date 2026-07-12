# 📊 Pipeline Híbrido para Análise da Alfabetização no Brasil

Projeto do Tech Challenge (Fase 2 - Pós Tech). A ideia é construir um pipeline de dados completo, seguindo a arquitetura Medalhão, para integrar as bases do **Indicador Criança Alfabetizada** e conseguir responder perguntas como: quantas crianças estão de fato alfabetizadas ao final do 2º ano? Quais municípios estão longe da meta?

## 📌 Contexto do problema

O **Compromisso Nacional Criança Alfabetizada** é a política pública que estabelece que, até 2030, toda criança brasileira deve estar alfabetizada ao final do 2º ano do ensino fundamental.

Mas como medir "estar alfabetizada"? Em 2023 o INEP realizou a Pesquisa Alfabetiza Brasil e definiu um corte objetivo: **743 pontos na escala de proficiência do Saeb**. Quem atinge esse patamar é considerado alfabetizado, e o percentual de alunos acima do corte forma o Indicador Criança Alfabetizada.

O desafio de engenharia está no fato de que essas informações vivem em bases separadas: microdados por aluno, metas nacionais, estaduais e municipais, cadastros de território. Este pipeline integra tudo isso em uma camada analítica confiável.

Os dados vêm da [Base dos Dados](https://basedosdados.org/dataset/073a39d4-89cf-4068-b1e8-34ed0d9c0b72?table=e1de7a6a-5038-4e81-89f0-a15f2cc12c9b), que publica o dataset no BigQuery (`basedosdados.br_inep_avaliacao_alfabetizacao`). São 6 entidades:

| Entidade | O que tem | Tamanho |
|---|---|---|
| `alunos` | Microdados por aluno (proficiência, rede, localização) | 3,87 mi de linhas |
| `municipio` | Resultados por município | ~24 mil |
| `uf` | Resultados por estado | 145 |
| `meta_alfabetizacao_brasil` | Metas nacionais | 3 |
| `meta_alfabetizacao_uf` | Metas por estado | 81 |
| `meta_alfabetizacao_municipio` | Metas por município | ~10 mil |

## 🏗️ Arquitetura

O pipeline segue a **arquitetura Medalhão**: o dado entra bruto e vai sendo refinado em camadas, sempre preservando as versões anteriores. Se algo aparecer errado lá na ponta, dá para voltar camada por camada e descobrir se o problema veio de uma transformação ou se já estava na fonte.

```
                        ┌──────────────────────────────────────────────────┐
 FONTES                 │              DATA LAKE (LAKE_PATH)               │
┌────────────────────┐  │                                                  │
│ BigQuery           │  │  ┌─────────┐    ┌──────────┐    ┌─────────┐      │
│ (Base dos Dados)   │─>│  │ BRONZE  │──> │  SILVER  │──> │  GOLD   │──────┼─> BI / ML
│ 6 entidades (batch)│  │  │ fiel à  │    │ limpo +  │    │ métricas│      │
└────────────────────┘  │  │ fonte   │    │ integrado│    │ negócio │      │
                        │  └─────────┘    └──────────┘    └─────────┘      │
┌────────────────────┐  │       ▲              │                           │
│ Simulador de       │  │       │              ▼                           │
│ eventos (streaming)│─>│   landing/     ┌──────────────┐                  │
└────────────────────┘  │   (raw JSON)   │ Data Quality │                  │
                        └──────────────────────────────────────────────────┘
```

**🥉 Bronze** - cópia fiel da fonte, sem nenhum filtro de negócio. Salvo em Parquet com três colunas extras de rastreabilidade: `_ingestion_ts` (quando foi ingerido), `_source` (tabela de origem) e `_row_hash` (identificador do conteúdo da linha, útil para detectar mudanças). A tabela `alunos` fica particionada por ano (`ano=2023/`, `ano=2024/`), então quem consulta um ano só não paga o custo de ler os outros.

**🥈 Silver** - limpeza e integração: conversão de tipos (proficiência vira decimal, códigos IBGE viram inteiro), decodificação dos códigos pelo dicionário da fonte, padronização do vocabulário de rede (um rótulo só, do resultado à meta), flags de ausência (`presente`, `sem_nota`), derivação da UF a partir do código do município e o empilhamento das metas numa estrutura única. É aqui que roda a suite formal de qualidade - e onde entra a **quarentena**: registro que reprova (ex.: município órfão da dimensão) é separado em `silver/quarentena/` com o motivo, em vez de sumir num filtro ou derrubar a esteira.

**🥇 Gold** - regra de negócio (`alfabetizado = proficiencia >= 743`, com a taxa ponderada pelo peso amostral - o recálculo fecha com o gabarito oficial com mediana de 0,004pp) e três tabelas prontas para consumo: indicador por município, meta × resultado (com gap e flag de atingimento) e evolução temporal por recorte geográfico e rede. O esquema é rígido e está documentado em `docs/dicionario_dados_gold.md`.

A ingestão é **híbrida**: batch para as cargas históricas do BigQuery e streaming (simulado com eventos JSON caindo numa pasta landing) para atualizações em tempo quase real.

### Status atual

| Etapa | Situação |
|---|---|
| Ingestão batch → Bronze | ✅ pronto |
| Silver (limpeza + integração) | ✅ pronto |
| Gold (métricas de negócio) | ✅ pronto |
| Data quality com relatório | ✅ pronto (em todas as camadas) |
| Streaming | 🚧 em desenvolvimento |
| Promoção do lake para o S3 | 📋 planejado |

## 📂 Estrutura do repositório

```
├── README.md
├── requirements.txt
├── .env.example                     # modelo de configuração (copiar para .env)
├── docs/
│   └── dicionario_dados_gold.md     # contrato das tabelas Gold (esquema + avisos de fonte)
├── scripts/
│   └── test_bigquery_connection.py  # smoke test da credencial
├── src/
│   ├── utils/
│   │   ├── logger.py                # logging padrão dos scripts
│   │   └── data_quality.py          # checks de qualidade reutilizáveis
│   ├── 01_bronze/
│   │   └── ingestao_batch_bigquery.py
│   ├── 02_silver/
│   │   └── tratamento_integracao.py # limpeza, padronização e integração das entidades
│   └── 03_gold/
│       └── metricas_gold.py         # regra dos 743 + as 3 tabelas analíticas
├── notebooks/
│   ├── exploracao_bronze.ipynb      # EDA da Bronze (perfil, nulos, corte 743, chaves)
│   ├── laboratorio_silver.ipynb     # prototipagem das transformações da Silver
│   └── laboratorio_gold.ipynb       # sondagem das decisões da Gold (peso, denominador, metas)
├── data/                            # data lake local (gerado na execução, fora do Git)
└── logs/                            # relatórios de qualidade (gerados na execução)
```

Se você está lendo o código pela primeira vez, sugiro começar pelo `test_bigquery_connection.py` (10 linhas, mostra como falamos com a fonte), depois os utils, e daí seguir os números das pastas: `01_bronze` → `02_silver` → `03_gold`. Os números são a própria ordem de execução do pipeline.

## ▶️ Como executar

### O que você precisa antes

- Python 3.12 ou mais novo
- Um projeto no Google Cloud (o cadastro é gratuito) com a **BigQuery API** habilitada. O dataset é público, mas as consultas rodam por dentro do seu projeto - o free tier de 1 TB/mês cobre com folga
- Uma Service Account com papel `BigQuery User` e a chave JSON baixada

### Passo a passo

1. Clone o repositório e prepare o ambiente:

```powershell
git clone https://github.com/tuanyfortunato/pipeline-dados-alfabetiza-brasil.git
cd pipeline-dados-alfabetiza-brasil
python -m venv .venv
.venv\Scripts\Activate.ps1        # no Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt
```

2. Crie a pasta `credentials/` na raiz e coloque a chave JSON da Service Account dentro dela. Depois copie o `.env.example` para `.env` e preencha:

```ini
GOOGLE_APPLICATION_CREDENTIALS=./credentials/sua-chave.json
GCP_PROJECT_ID=seu-project-id
LAKE_PATH=./data
```

Tanto `credentials/` quanto `.env` estão no `.gitignore` - nada disso sobe para o Git.

3. Teste a conexão:

```powershell
python scripts/test_bigquery_connection.py
```

Se aparecer `Conexão OK. 10 linhas retornadas.` com uma prévia da tabela de alunos, está tudo certo.

4. Rode a ingestão Bronze:

```powershell
# todas as entidades (leva ~1 min)
python src/01_bronze/ingestao_batch_bigquery.py

# ou só algumas
python src/01_bronze/ingestao_batch_bigquery.py uf municipio
```

No final você vai ter os Parquet em `data/bronze/batch/<entidade>/` e um relatório de qualidade em `logs/dq_bronze_<timestamp>.json`, com score e o detalhe de cada check.

Se um check crítico falhar (base vazia, coluna obrigatória faltando), o script para com `DataQualityError`. Isso é proposital: dado ruim não segue adiante em silêncio.

5. Rode o tratamento da Silver:

```powershell
python src/02_silver/tratamento_integracao.py
```

Ele lê a Bronze e grava a camada tratada em `data/silver/` - `alunos/` (particionado por ano), `quarentena/alunos/`, `resultados/municipio` e `resultados/uf`, e `metas/` (as três tabelas empilhadas). No fim sai um relatório em `logs/dq_silver_<timestamp>.json`. Na base atual são 3,87 mi de alunos tratados, 410 linhas em quarentena e score de qualidade de ~91% (o único ponto de atenção fica como *warning*, não derruba o pipeline).

6. Rode as métricas da Gold:

```powershell
python src/03_gold/metricas_gold.py
```

Ele lê a Silver e grava em `data/gold/` as três tabelas analíticas: `indicador_municipio/` (10,4 mil linhas), `meta_vs_resultado/` (com gap e flag de atingimento) e `evolucao_temporal/` (33,4 mil linhas, por recorte geográfico e rede). O relatório sai em `logs/dq_gold_<timestamp>.json` - na base atual, score de ~94% com um único *warning*: o check que confronta o recálculo com o gabarito oficial e acusa 45 municípios divergentes conhecidos (0,4%, quase todos de 2023 - detalhes no dicionário de dados). Uma prova real: a taxa Brasil 2024 recalculada dá **59,2** - exatamente o número oficial.

7. (Opcional) Os notebooks documentam o caminho até aqui: `notebooks/exploracao_bronze.ipynb` traz a EDA da Bronze (perfil das entidades, distribuição da proficiência, chaves), `notebooks/laboratorio_silver.ipynb` prototipa cada transformação da Silver com contagem antes/depois e `notebooks/laboratorio_gold.ipynb` valida as decisões de cálculo da Gold contra o gabarito oficial (ponderação pelo peso amostral, denominador, qual meta vale). Todos estão versionados já executados, dá para ler direto no GitHub.

## ✅ Qualidade de dados

Os checks (em `src/utils/data_quality.py`) cobrem as quatro dimensões clássicas:

- **Completude** - o dado está presente? (base não vazia, nulos em colunas-chave)
- **Validade** - formato e faixa corretos? (ex.: proficiência dentro da escala Saeb)
- **Consistência** - os campos fazem sentido entre si? (ex.: todo `id_municipio` dos alunos existe na dimensão município)
- **Unicidade** - sem duplicatas indevidas nas chaves

Além das quatro dimensões, o módulo valida formato (regex nos códigos IBGE), consistência linha a linha entre campos (ex.: aluno ausente não pode ter nota) e completude contra threshold. Cada check tem um de três desfechos: **pass**, **warning** (fica registrado, não derruba o pipeline - caso dos raros presentes sem nota) ou **fail** (aborta a execução).

Toda execução gera um relatório JSON em `logs/` com o score. Na Silver entra também a estratégia de quarentena: registro reprovado é separado para análise em vez de descartado (ou de travar a esteira inteira).

Por que não usei Great Expectations ou Soda? Para o volume e o número de regras deste projeto, um módulo próprio de ~100 linhas cobre as mesmas dimensões sem adicionar dependência pesada - e me obrigou a entender cada validação em vez de configurar YAML. Num cenário corporativo com dezenas de fontes, migrar para uma dessas ferramentas seria o caminho natural.

## 🛠️ Tecnologias

- **Python + pandas** na ingestão e nas transformações Bronze e Silver - o volume atual (268 MB, 3,87 mi de linhas) cabe tranquilo em memória, então preferi a simplicidade
- **google-cloud-bigquery** para extração direto da fonte, sem download manual de arquivo
- **Parquet** em todas as camadas - colunar, comprimido e com tipagem forte
- **PySpark** reservado para o streaming e para quando o volume exigir escala distribuída (próximas fases)
- **AWS S3 + Athena** como destino do data lake na nuvem (promoção planejada)

## ⚖️ Decisões arquiteturais

Algumas escolhas que fiz e o raciocínio por trás delas:

**Por que AWS, se a fonte está no BigQuery?** Usar GCP para tudo evitaria um hop de extração, é verdade. Mas concentrei o data lake na AWS pelo peso do ecossistema S3/Athena/Glue no mercado e por manter governança e custo num provedor só. O hop custa pouco: a extração roda uma vez por carga e cabe no free tier do BigQuery.

**Desenvolver local primeiro, promover para a nuvem depois.** O `LAKE_PATH` aponta para `./data` durante o desenvolvimento e a estrutura de pastas espelha exatamente o futuro bucket S3. Quando a lógica estiver validada, a promoção é trocar uma variável de ambiente. Ganho velocidade de iteração e não pago nuvem enquanto erro.

**Cadê a camada raw?** Algumas arquiteturas separam raw (formato original) de Bronze (Parquet + metadados). Como a minha fonte é um warehouse, não existe um "arquivo original" para preservar - a Bronze já nasce sendo a cópia fiel, sem filtro de negócio. No streaming a história é outra: lá a pasta `landing/` guarda o JSON exatamente como chegou, fazendo o papel de raw.

**pandas ou Spark?** Os dois, cada um no seu lugar. O volume atual (268 MB, 3,87 mi de linhas) cabe em memória com folga, então Bronze e Silver rodam em pandas - menos setup e iteração bem mais rápida, inclusive nos joins entre as entidades. O Spark fica reservado para onde realmente agrega: o streaming estruturado e o dia em que o volume crescer a ponto de exigir processamento distribuído. A regra que me guia é que trocar de ferramenta não pode mudar o resultado - então, quando a migração vier, ela parte dos números que a Silver em pandas já validou.

**Batch, streaming ou os dois?** Os dois, porque resolvem coisas diferentes. As cargas históricas do INEP - microdados, metas, municípios - são grandes e mudam poucas vezes por ano; aí batch é o natural, roda de tempos em tempos e processa o lote inteiro de uma vez. Já a chegada de novas medições ou revisões de meta é onde compensa reagir rápido, e é onde entra o streaming (simulado com eventos JSON caindo numa pasta landing). Deixei os dois separados desde a Bronze (`bronze/batch/` e `bronze/streaming/`) para não misturar a origem e poder reprocessar um lado sem encostar no outro. Se fosse só batch, perderia o "quase tempo real" que o problema pede; se fosse só streaming, pagaria complexidade à toa nas cargas que são naturalmente periódicas.

**Data lake ou data warehouse?** Cheguei a considerar jogar tudo num data warehouse (Redshift, ou o próprio BigQuery que já é a fonte) e resolver no SQL. Fiquei com data lake em S3 por dois motivos: os microdados de aluno já são 3,87 milhões de linhas e crescem a cada nova onda da pesquisa - storage barato em Parquet pesa mais que a conveniência do SQL - e o formato colunar aberto não me prende a um fornecedor: hoje leio com Spark, amanhã com Athena, DuckDB ou o que vier. O warehouse não sai de cena, só troca de lado: as tabelas Gold ficam expostas via Athena, que me dá a experiência de warehouse (SQL, catálogo, BI) sem manter cluster nenhum ligado. Na prática, lake para armazenar e refinar, "warehouse" serverless só na ponta do consumo.

**Custo ou performance?** Nesse volume dá para ter os dois, então otimizei custo sem sacrificar tempo de resposta perceptível. Parquet particionado faz a consulta ler só a fatia que interessa (menos byte escaneado = menos conta no Athena e menos espera), a Bronze é materializada uma vez e todo o resto parte dela em vez de bater na fonte de novo, e nada fica ligado 24/7 - desenvolvimento local e, na nuvem, S3 e Athena são serverless. Se um dia a base crescer a ponto de a performance apertar, o caminho é subir um cluster Spark (Glue/EMR) sob demanda: aí sim pago mais em troca de paralelismo, mas como escolha consciente para quando o volume justificar, não como padrão.

## 📡 Monitoramento

Todos os scripts logam início/fim e volume processado por entidade, e os relatórios de qualidade ficam persistidos em `logs/`. Em produção na AWS isso evoluiria naturalmente para CloudWatch (métricas de volume, latência e falha de ingestão) com alertas via SNS.

## 💰 FinOps

- Parquet com compressão snappy em todas as camadas: menos storage, menos bytes escaneados
- Particionamento por ano: as consultas leem só o que precisam
- A Bronze é materializada uma vez e todo o resto parte dela - a fonte não é re-consultada a cada experimento
- Nenhum cluster ligado: desenvolvimento local, e na nuvem S3/Athena são serverless
- Lifecycle planejado no S3: Bronze migra para armazenamento frio depois de N dias

A estimativa de custo mensal da arquitetura completa fica na casa de **US$ 0 a 3** (detalho a conta na promoção para a AWS).

### pandas ou Spark quando subir para a AWS?

Essa foi a decisão de custo × performance que mais me fez pensar, então deixo o raciocínio registrado. Pelo volume, não tem muito o que discutir: a maior tabela tem 3,87 mi de linhas e 268 MB - cabe em memória com sobra. O Spark só começa a valer a pena lá pelas dezenas de GB ou centenas de milhões de linhas; abaixo disso, o custo de subir cluster, o shuffle e a JVM costumam deixar o job mais lento e mais caro do que um pandas bem escrito. E mesmo crescendo, cada nova onda da pesquisa soma ~3,9 mi de linhas por ano - levaria muito tempo até o volume pedir processamento distribuído.

Na prática, a escolha na AWS não é cravar uma ferramenta só, é usar o serviço certo em cada etapa:

- **Bronze e Silver (batch)** seguem em pandas, rodando como Glue Python Shell job (ou Lambda nos passos mais leves), lendo e escrevendo direto no S3. É basicamente trocar o `LAKE_PATH` local por um caminho `s3://` - o código quase não muda, e o custo fica na casa de centavos por execução.
- **Streaming** é onde o Spark entra de verdade, com Structured Streaming: aí ele não é enfeite, resolve micro-batches, checkpoint e tolerância a falha. Repara que aqui a escolha não vem do volume, e sim da natureza do problema.
- **Gold** hoje roda em pandas junto com o resto do batch, mas na nuvem pode dispensar os dois: com os dados já em Parquet no S3, as agregações do indicador saem em SQL no Athena - serverless e por uma fração de centavo do que é escaneado.

Guardo o Spark no batch para o dia em que o volume realmente crescer. Quando esse dia chegar, a migração parte dos números que a versão em pandas já validou, porque trocar de ferramenta não pode mudar o resultado.

## 🤖 Aplicação em IA

A Gold foi desenhada pensando em servir modelos, não só dashboards:

- **Predição de alfabetização por município**: cruzando o indicador com features socioeconômicas, dá para prever quais municípios não vão atingir a meta de 2030 e priorizar intervenção
- **Clusters de vulnerabilidade educacional**: agrupar municípios por perfil de desempenho × meta × território
- **Política pública baseada em evidência**: o meta × resultado por recorte geográfico vira um ranking objetivo de onde investir

## 👩‍💻 Autora

**Tuany Fortunato do Carmo** - Tech Challenge Fase 2, Pós Tech.

Vídeo executivo: link será adicionado na entrega final.
