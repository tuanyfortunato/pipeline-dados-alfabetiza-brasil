# Dicionário de dados — camada Gold

A Gold é contrato: quem consome (BI, análise, modelo) não pode ser surpreendido por mudança de esquema. Este documento fixa o grão, as colunas e os tipos das três tabelas, e registra os avisos de fonte que qualquer consumidor precisa conhecer antes de tirar conclusão do dado.

Gerado por `src/03_gold/metricas_gold.py` a partir da Silver. Cada tabela é um Parquet único, sobrescrito a cada execução (reprocessar é idempotente). Os números de validação citados aqui vêm do `notebooks/laboratorio_gold.ipynb`.

## Regra de negócio central

`alfabetizado = proficiencia >= 743` (ponto de corte da escala Saeb definido pela Pesquisa Alfabetiza Brasil, 2023). A taxa de alfabetização é a **média ponderada pelo `peso_aluno`** dos presentes com nota — validado contra o gabarito oficial com mediana de diferença de 0,004pp e ~95% dos municípios dentro de 0,05pp.

---

## `gold/indicador_municipio/`

O Indicador Criança Alfabetizada por município, calculado sobre a **rede pública** (municipal + estadual). Grão: uma linha por (`ano`, `id_municipio`) — 10.391 linhas na base atual.

| Coluna | Tipo | Descrição |
|---|---|---|
| `ano` | int | ano da avaliação (2023, 2024) |
| `id_municipio` | int | código IBGE de 7 dígitos |
| `sigla_uf` | str | UF derivada do código IBGE — inclui DF |
| `alunos_avaliados` | int | alunos matriculados na avaliação |
| `alunos_presentes` | int | compareceram no dia da prova |
| `alunos_com_nota` | int | presentes com proficiência registrada |
| `taxa_participacao` | float | 100 × presentes / avaliados |
| `taxa_alfabetizacao` | float | % ponderada com proficiência ≥ 743, sobre presentes com nota |
| `proficiencia_media` | float | média ponderada da proficiência dos presentes com nota |

`taxa_alfabetizacao` pode ser nula nos raros municípios sem nenhum presente com nota (4 casos na base atual) — é ausência real de medição, não defeito.

## `gold/meta_vs_resultado/`

Resultado realizado × meta pactuada, nos três níveis do Compromisso Nacional. Grão: uma linha por (`ano`, `nivel`, recorte) — 10.327 linhas.

| Coluna | Tipo | Descrição |
|---|---|---|
| `ano` | int | ano do resultado |
| `nivel` | str | `brasil`, `uf` ou `municipio` |
| `rede` | str | rede do confronto: `publica` (brasil/uf) ou `municipal` (municípios), espelhando o grão pactuado de cada meta |
| `sigla_uf` | str | nulo no nível brasil |
| `id_municipio` | Int64 | nulo fora do nível município |
| `alunos_com_nota` | int | base do cálculo do resultado |
| `taxa_alfabetizacao` | float | resultado realizado (ponderado) |
| `meta_ano` | Float64 | meta vigente no ano do resultado; nula quando não há meta pactuada |
| `gap` | Float64 | realizado − meta (negativo = abaixo da meta); nulo sem meta |
| `atingiu_meta` | boolean | nulo sem meta |

A meta usada é sempre a **vigente no ano do resultado** (linha de metas com o mesmo `ano`). No nível municipal não houve revisão entre os snapshots 2023 e 2024; as revisões da fonte aparecem só no snapshot 2025 (arredondamentos nos níveis Brasil/UF).

## `gold/evolucao_temporal/`

Série do indicador por ano, recorte geográfico e rede — a tabela de dashboard. Grão: uma linha por (`ano`, `nivel`, recorte, `rede`) — 33.411 linhas. Com duas ondas (2023, 2024) a série é curta; a estrutura já acomoda as próximas.

| Coluna | Tipo | Descrição |
|---|---|---|
| `ano` | int | ano da avaliação |
| `nivel` | str | `brasil`, `uf` ou `municipio` |
| `rede` | str | `municipal`, `estadual`, `publica` ou `total` |
| `sigla_uf` | str | nulo no nível brasil |
| `id_municipio` | Int64 | nulo fora do nível município |
| `alunos_avaliados`, `alunos_presentes`, `alunos_com_nota` | int | volumetria |
| `taxa_participacao` | float | 100 × presentes / avaliados |
| `taxa_alfabetizacao` | float | % ponderada com proficiência ≥ 743 |
| `proficiencia_media` | float | média ponderada |

---

## Avisos de fonte (leia antes de consumir)

1. **`publica` = municipal + estadual dos microdados.** A rede federal não aparece nos microdados e a privada é resíduo estatístico (25 alunos) — ela só entra no recorte `total`.
2. **2023 não tem meta pactuada.** As colunas de meta da fonte começam em 2024, então o gap de 2023 é nulo por definição: 2023 é a linha de base da política, não um dado faltante.
3. **220 municípios sem meta em 2024** (e 344 combinações no total sem par nas metas). Ficam visíveis com `meta_ano` nulo — o join é left de propósito. A hipótese é que a meta municipal cobre a rede municipal, deixando de fora municípios avaliados só pela rede estadual.
4. **DF só existe aqui.** A tabela de resultados por UF da fonte não traz o Distrito Federal, mas ele tem meta pactuada. Como os níveis UF/Brasil desta camada são agregados dos microdados (onde o DF existe via código IBGE), o confronto meta × resultado do DF é possível — e este é o único lugar onde ele aparece completo.
5. **45 municípios (0,43%) divergem do gabarito oficial em mais de 1pp**, 32 deles de 2023 — ano da Pesquisa Alfabetiza Brasil, de desenho amostral diferente. O check de qualidade acusa como warning a cada execução; não bloqueia a esteira.
6. **Brasil 2023: o recálculo dá 57,46; o número divulgado é 55,9.** A divergência é da própria fonte: o nosso agregado fecha com as tabelas oficiais de resultado por UF e município (diferença máxima de 0,0008pp), mas o número nacional de 2023 vem da pesquisa amostral. Para série histórica consistente, use a taxa desta camada; para citar o número oficial de 2023, cite a fonte original.
