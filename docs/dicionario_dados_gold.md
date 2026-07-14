# Dicionário de dados — camada Gold

A Gold é contrato: quem consome (BI, análise, modelo) não pode ser surpreendido por mudança de esquema. Este documento fixa o grão, as colunas e os tipos das cinco tabelas, e registra os avisos de fonte que qualquer consumidor precisa conhecer antes de tirar conclusão do dado.

Gerado por `src/03_gold/metricas_gold.py` a partir da Silver. Cada tabela é um Parquet único, sobrescrito a cada execução (reprocessar é idempotente). Os números de validação citados aqui vêm do `notebooks/laboratorio_gold.ipynb`.

## Regra de negócio central

`alfabetizado = proficiencia >= 743` (ponto de corte da escala Saeb definido pela Pesquisa Alfabetiza Brasil, 2023). A taxa de alfabetização é a **média ponderada pelo `peso_aluno`** dos presentes com nota — validado contra o gabarito oficial com mediana de diferença de 0,004pp e ~95% dos municípios dentro de 0,05pp.

## Duas coisas que mudam como o dado deve ser lido

**Toda taxa vem com `ic95`, e ele não é decoração.** É a meia-largura do intervalo de confiança de 95%, em pontos percentuais. Um município com 12 alunos avaliados tem margem de ±30pp; a mediana nacional é ±7,9pp e 544 municípios têm menos de 30 alunos avaliados (margem média de ±17,6pp). **Nenhuma comparação entre dois recortes, ou entre um recorte e a meta, significa alguma coisa se a diferença for menor que o `ic95`.** É por isso que `meta_vs_resultado` tem a coluna `situacao_meta` além do `atingiu_meta`.

**Taxa é percentual, e percentual esconde volume.** `criancas_nao_alfabetizadas` é a estimativa populacional (ponderada pelo peso amostral, que expande a amostra) de crianças abaixo do corte. Ela existe porque as duas leituras divergem de forma radical: metade de todas as crianças não alfabetizadas do país está em 195 municípios (3,5% do total), e **a sobreposição entre "os 50 municípios com pior taxa" e "os 50 com mais crianças fora" é zero**. Priorizar por taxa e priorizar por volume apontam para lugares diferentes.

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
| `ic95` | float | margem de erro da taxa, em pp (± em torno dela) |
| `taxa_limite_inferior` | float | taxa se **todos** os faltantes fossem não alfabetizados |
| `taxa_limite_superior` | float | taxa se **todos** os faltantes fossem alfabetizados |
| `proficiencia_media` | float | média ponderada da proficiência dos presentes com nota |
| `criancas_nao_alfabetizadas` | float | estimativa populacional de crianças abaixo do corte |
| `alerta_participacao` | bool | participação abaixo de 80% (395 municípios em 2024) |

`taxa_alfabetizacao` pode ser nula nos raros municípios sem nenhum presente com nota (4 casos na base atual) — é ausência real de medição, não defeito. Nesses casos `ic95` e os limites também são nulos.

Sobre os limites: 12% dos alunos não fizeram a prova e ficam fora do denominador. A ausência **não é aleatória** — falta mais gente onde o desempenho é pior (correlação de +0,29 entre participação e taxa), o que empurra a taxa publicada para cima. No Brasil de 2024, os limites são [51,7% ; 64,4%] em torno dos 59,2% publicados. Não são um intervalo de confiança: são o contorno do que a falta de medição permite afirmar.

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
| `ic95` | float | margem de erro do resultado |
| `meta_ano` | Float64 | meta vigente no ano do resultado; nula quando não há meta pactuada |
| `gap` | Float64 | realizado − meta (negativo = abaixo da meta); nulo sem meta |
| `atingiu_meta` | boolean | `gap >= 0`; nulo sem meta. **Mantido só por compatibilidade — leia `situacao_meta`** |
| `situacao_meta` | str | `atingiu`, `nao_atingiu`, `indistinguivel` ou `sem_meta` |

**`atingiu_meta` mente em quase metade dos casos, e é por isso que `situacao_meta` existe.** O booleano é `gap >= 0` e nada mais: ele não sabe que o indicador tem margem de erro. Em 45% dos municípios com meta pactuada em 2024, o gap é **menor que o próprio `ic95`** — a diferença entre o resultado e a meta não é distinguível de zero, e o booleano está reportando ruído com cara de fato. `situacao_meta` marca esses casos como `indistinguivel`.

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
| `ic95` | float | margem de erro da taxa |
| `proficiencia_media` | float | média ponderada |
| `criancas_nao_alfabetizadas` | float | estimativa populacional abaixo do corte |

**Não construa ranking de evolução a partir desta tabela.** Com duas ondas, a variação ano a ano é dominada por regressão à média: a correlação entre a taxa de 2023 e o avanço 2023→2024 é de **−0,45**. O quartil de pior desempenho em 2023 "avançou" +8,2pp e o melhor "caiu" −4,3pp — em boa parte, isso é o município que teve medida ruidosa em 2023 voltando para o próprio nível, não política pública funcionando. Um ranking de "quem mais melhorou" seria, em larga medida, um ranking de quem teve mais azar no ano anterior. Compare a variação sempre contra o `ic95` dos dois anos.

## `gold/perfil_escola/`

O indicador no grão da escola. Grão: uma linha por (`ano`, `id_escola`) — 79.264 linhas (36.768 escolas em 2023, 42.497 em 2024).

| Coluna | Tipo | Descrição |
|---|---|---|
| `ano` | int | ano da avaliação |
| `id_escola` | int | identificador da escola **na base** — não é o código INEP (ver avisos) |
| `id_municipio` | int | código IBGE do município da escola |
| `sigla_uf` | str | UF da escola |
| `rede` | str | `municipal` ou `estadual` |
| `alunos_avaliados`, `alunos_presentes`, `alunos_com_nota` | int | volumetria |
| `taxa_participacao` | float | 100 × presentes / avaliados |
| `taxa_alfabetizacao` | float | % ponderada com proficiência ≥ 743 |
| `ic95` | float | margem de erro — grande nas escolas pequenas (mediana de 35 alunos) |
| `proficiencia_media` | float | média ponderada |
| `taxa_municipio` | float | taxa da rede pública do município da escola (de `indicador_municipio`) |
| `residuo` | float | `taxa_alfabetizacao − taxa_municipio` |

**Por que esta tabela existe.** Decompondo a variância da proficiência em 2024: 16% está entre municípios, 9% entre escolas do mesmo município e **75% entre alunos da mesma escola**. O município — grão em que a política pactua meta, compara e cobra — explica um sexto da variação. A escola, que nenhuma tabela olhava, explica mais da metade disso.

O `residuo` é a leitura da tabela: a escola comparada ao **próprio município**, o que controla contexto socioeconômico e gestão. Em 2024, entre as escolas com pelo menos 20 alunos avaliados, **2.083 estão 20pp acima do próprio município** e 2.008 estão 20pp abaixo. As de cima são casos a estudar; as de baixo são onde a intervenção rende mais.

Filtre por `alunos_com_nota` antes de rankear: escola pequena tem `ic95` enorme, e um ranking cru de resíduo devolve as escolas de 5 alunos.

## `gold/distribuicao_proficiencia/`

Distribuição dos alunos nos níveis oficiais e nas faixas de negócio. Grão: uma linha por (`ano`, `nivel`, `rede`, recorte) — 33.392 linhas.

| Coluna | Tipo | Descrição |
|---|---|---|
| `ano`, `nivel`, `rede`, `sigla_uf`, `id_municipio` | — | mesmas chaves de `evolucao_temporal` |
| `alunos_com_nota` | int | base do cálculo |
| `pct_nivel_0` … `pct_nivel_8` | float | % ponderado em cada nível da **escala oficial do INEP** |
| `pct_critico` | float | % com proficiência < 700 (níveis 0 a 2) |
| `pct_atencao` | float | % entre 700 e 742 — abaixo do corte, mas fora da faixa crítica |
| `pct_alfabetizado` | float | % ≥ 743 — bate com `taxa_alfabetizacao` (é check de DQ) |
| `pct_quase_la` | float | % entre 733 e 742: a **10 pontos ou menos** do corte |

**Os cortes dos 9 níveis foram derivados aqui, não copiados da fonte.** As tabelas `municipio` e `uf` publicam a distribuição (`proporcao_aluno_nivel_0..8`), mas o dicionário da Base dos Dados **não publica os pontos de corte**. Derivamos por quantis ponderados e validamos município a município contra as colunas oficiais: mediana de 0,003pp de diferença em 5.516 municípios. A grade é de 25 pontos a partir de 650:

| Nível | Faixa | | Nível | Faixa |
|---|---|---|---|---|
| 0 | < 650 | | 5 | 750–775 |
| 1 | 650–675 | | 6 | 775–800 |
| 2 | 675–700 | | 7 | 800–825 |
| 3 | 700–725 | | 8 | ≥ 825 |
| 4 | 725–750 | | | |

**As duas réguas não se encaixam, e isso é de propósito.** O corte de alfabetização (743) cai **dentro do nível 4** (725–750). Os 9 níveis são a escala oficial e existem para dar comparabilidade e gabarito; as faixas de negócio (`pct_critico` / `pct_atencao` / `pct_alfabetizado`) são ancoradas no corte de 743 e existem para responder pergunta de política. Não tente converter uma na outra.

`pct_quase_la` é a alavanca do indicador: na rede pública de 2024 ela vale **7,8%** — se todas essas crianças cruzassem o corte, a taxa nacional saltaria de 59,2% para 67,0% de uma vez.

---

## Avisos de fonte (leia antes de consumir)

1. **`id_escola` é pseudônimo, não o código INEP.** Os IDs vão de `60000001` a `60042811`, sequenciais, com prefixo `60` (que não é código de UF válido). A interseção com as 222.589 escolas do Censo Escolar 2023/2024 é **zero**: não dá para juntar com o Censo Escolar, o que fecha a porta para localização urbana/rural e infraestrutura escolar. E o pseudônimo é **regerado a cada ano** — o mesmo `id_escola` em 2023 e 2024 não é a mesma escola. Dentro de um ano ele é chave limpa (nenhuma escola em dois municípios), e é só para isso que `perfil_escola` o usa.
2. **`id_aluno` não é chave de painel.** Também é pseudônimo regerado por ano. Dos `id_aluno` que aparecem nos dois anos, só 0,1% caem na mesma escola — é colisão de identificador, não o mesmo aluno (são coortes diferentes de 2º ano). Qualquer join de aluno entre 2023 e 2024 devolve lixo sem lançar erro.
3. **A escala não começa em zero.** A proficiência do 2º ano vai de **578 a 904** nesta base. O corte de 500 usado como "nível crítico" no Saeb de 5º/9º ano é de outra escala, e classificaria **zero** crianças aqui. É por isso que a faixa crítica desta camada é < 700.
4. **A rede privada não existe nesta base.** São 25 alunos privados em 2024 e zero em 2023 (contra 3,87 milhões de públicos), e as tabelas oficiais de resultado não trazem nenhuma linha de rede privada ou federal. Qualquer comparação "pública × privada" é irrespondível com estas fontes. `publica` = municipal + estadual; a privada só aparece, como resíduo, no recorte `total`.
5. **A distribuição por nível só existe em 2024.** As colunas `proporcao_aluno_nivel_*` da fonte vêm inteiramente nulas em 2023, então o check de DQ dos 9 níveis compara apenas 2024. A `distribuicao_proficiencia` calcula os dois anos (o cálculo não depende da fonte), mas só um deles tem gabarito.
6. **2023 não tem meta pactuada.** As colunas de meta da fonte começam em 2024, então o gap de 2023 é nulo por definição: 2023 é a linha de base da política, não um dado faltante.
7. **220 municípios sem meta em 2024** (e 344 combinações no total sem par nas metas). Ficam visíveis com `meta_ano` nulo — o join é left de propósito. A hipótese é que a meta municipal cobre a rede municipal, deixando de fora municípios avaliados só pela rede estadual.
8. **DF só existe aqui.** A tabela de resultados por UF da fonte não traz o Distrito Federal, mas ele tem meta pactuada. Como os níveis UF/Brasil desta camada são agregados dos microdados (onde o DF existe via código IBGE), o confronto meta × resultado do DF é possível — e este é o único lugar onde ele aparece completo.
9. **45 municípios (0,43%) divergem do gabarito oficial em mais de 1pp**, 32 deles de 2023 — ano da Pesquisa Alfabetiza Brasil, de desenho amostral diferente. O check de qualidade acusa como warning a cada execução; não bloqueia a esteira. O mesmo grupo de municípios pequenos responde pelas ~570 células (1,15%) que estouram a tolerância de 0,1pp no check dos níveis.
10. **Brasil 2023: o recálculo dá 57,46; o número divulgado é 55,9.** A divergência é da própria fonte: o nosso agregado fecha com as tabelas oficiais de resultado por UF e município (diferença máxima de 0,0008pp), mas o número nacional de 2023 vem da pesquisa amostral. Para série histórica consistente, use a taxa desta camada; para citar o número oficial de 2023, cite a fonte original.
