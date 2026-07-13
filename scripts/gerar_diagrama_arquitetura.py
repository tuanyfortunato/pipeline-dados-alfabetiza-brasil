"""Gera docs/arquitetura.png — o diagrama da pipeline.

O diagrama fica versionado como código, e não como imagem solta: quando a
arquitetura mudar, é este arquivo que muda, e o PNG sai de novo.

Uso:
    python scripts/gerar_diagrama_arquitetura.py
"""
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

matplotlib.use("Agg")

SAIDA = Path(__file__).resolve().parents[1] / "docs" / "arquitetura.png"

# mesma paleta dos gráficos do laboratório
AZUL, AQUA = "#2a78d6", "#1baf7a"
BRONZE, PRATA, OURO = "#b0763a", "#8e9298", "#eda100"
TINTA, TINTA_2, MUDO = "#0b0b0b", "#52514e", "#898781"
FUNDO, TRILHO, BORDA = "#fcfcfb", "#f2f1ec", "#d8d7d0"
DQ_FUNDO, DQ_BORDA, DQ_TINTA = "#fdecec", "#e8b4b4", "#a33333"
ORQ_FUNDO, ORQ_BORDA, ORQ_TINTA = "#eef4fd", "#c3d9f5", "#1b4f8f"


def caixa(ax, x, y, w, h, titulo, subtitulo="", detalhe="",
          cor=AZUL, texto_claro=True, fonte=10):
    """Caixa com até três níveis de texto — o detalhe fica dentro dela, e não
    solto embaixo, senão os textos de caixas vizinhas colidem."""
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.12",
        facecolor=cor, edgecolor="none", zorder=3))
    tinta = "white" if texto_claro else TINTA
    cx, meio = x + w / 2, y + h / 2

    linhas = [(titulo, fonte, "bold", 1.0)]
    if subtitulo:
        linhas.append((subtitulo, fonte - 2.0, "normal", 0.93))
    if detalhe:
        linhas.append((detalhe, fonte - 3.2, "normal", 0.80))

    alturas = {1: [0.0], 2: [0.20, -0.24], 3: [0.62, 0.10, -0.52]}[len(linhas)]
    for (texto, tam, peso, alfa), dy in zip(linhas, alturas):
        ax.text(cx, meio + dy, texto, ha="center", va="center", color=tinta,
                fontsize=tam, fontweight=peso, alpha=alfa, zorder=4,
                linespacing=1.35)


def trilho(ax, x, y, w, h, rotulo):
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.15",
        facecolor=TRILHO, edgecolor=BORDA, linewidth=1, zorder=1))
    ax.text(x + w / 2, y + h - 0.3, rotulo, ha="center", va="center",
            color=MUDO, fontsize=9, fontweight="bold", zorder=2)


def seta(ax, de, para, cor=TINTA_2, estilo="-", rotulo=""):
    ax.add_patch(FancyArrowPatch(
        de, para, arrowstyle="-|>", mutation_scale=14, linewidth=1.6,
        color=cor, linestyle=estilo, zorder=5, shrinkA=2, shrinkB=2))
    if rotulo:
        ax.text((de[0] + para[0]) / 2, (de[1] + para[1]) / 2 + 0.22, rotulo,
                ha="center", va="bottom", color=cor, fontsize=8.5,
                fontweight="bold", zorder=6,
                bbox=dict(facecolor=FUNDO, edgecolor="none", pad=1.5))


fig, ax = plt.subplots(figsize=(15, 8.6))
fig.patch.set_facecolor(FUNDO)
ax.set_xlim(0, 30)
ax.set_ylim(0, 17)
ax.axis("off")

ax.text(0.3, 16.4, "Pipeline Híbrido — Indicador Criança Alfabetizada",
        fontsize=16, fontweight="bold", color=TINTA)
ax.text(0.3, 15.75, "Arquitetura Medalhão em AWS  ·  ingestão batch + streaming  ·  "
                    "qualidade de dados em todas as camadas",
        fontsize=10.5, color=TINTA_2)

# ───────────────────────────────────────────────────────────── trilhos
trilho(ax, 0.3, 5.6, 5.2, 8.9, "FONTES")
trilho(ax, 6.1, 5.6, 5.6, 8.9, "INGESTÃO")
trilho(ax, 12.3, 5.6, 11.8, 8.9, "DATA LAKE  ·  S3 (nuvem)  /  ./data (local)")
trilho(ax, 24.7, 5.6, 5.0, 8.9, "CONSUMO")

# ───────────────────────────────────────────────────────────── fontes
caixa(ax, 0.8, 11.7, 4.2, 1.7, "BigQuery", "Base dos Dados", "7 entidades · 3,87 mi de linhas", AZUL)
caixa(ax, 0.8, 6.4, 4.2, 1.7, "Producer", "simula sistema externo", "novas medições do indicador", AQUA)

# ───────────────────────────────────────────────────────────── ingestão
caixa(ax, 6.6, 11.7, 4.6, 1.7, "Glue Python Shell", "pandas — o mesmo código", "que roda local", AZUL)
caixa(ax, 6.6, 8.9, 4.6, 1.7, "Glue Streaming", "Spark Structured", "Streaming", AQUA)
caixa(ax, 6.6, 6.4, 4.6, 1.7, "Kinesis Data Stream", "log de eventos", "reprocessável", AQUA)

seta(ax, (5.0, 12.55), (6.6, 12.55), AZUL, rotulo="batch")
seta(ax, (5.0, 7.25), (6.6, 7.25), AQUA, rotulo="streaming")
seta(ax, (8.9, 8.1), (8.9, 8.9), AQUA)          # Kinesis -> Glue Streaming

# ───────────────────────────────────────────────────────────── camadas
caixa(ax, 12.8, 10.6, 3.4, 2.9, "BRONZE", "cópia fiel da fonte",
      "particionado por ano\n_ingestion_ts · _row_hash", BRONZE, fonte=11)
caixa(ax, 16.6, 10.6, 3.4, 2.9, "SILVER", "limpo e integrado",
      "quarentena: o reprovado\né separado, não sumido", PRATA, fonte=11)
caixa(ax, 20.4, 10.6, 3.4, 2.9, "GOLD", "5 tabelas de negócio",
      "proficiência ≥ 743\ntaxa + margem de erro", OURO, texto_claro=False, fonte=11)

seta(ax, (11.2, 12.55), (12.8, 12.4), AZUL)     # batch    -> Bronze
seta(ax, (11.2, 9.75), (12.8, 11.0), AQUA)      # streaming -> Bronze
seta(ax, (16.2, 12.05), (16.6, 12.05))
seta(ax, (20.0, 12.05), (20.4, 12.05))

# ───────────────────────────────────────────────────────────── consumo
caixa(ax, 25.2, 11.8, 4.0, 1.6, "Athena", "SQL sobre o lake", "", AZUL)
caixa(ax, 25.2, 9.4, 4.0, 1.6, "BI / Dashboard", "", "", AZUL, fonte=9.5)
caixa(ax, 25.2, 7.0, 4.0, 1.6, "ML / Feature Store", "", "", AZUL, fonte=9.5)

seta(ax, (23.8, 12.05), (25.2, 12.6))
seta(ax, (23.8, 12.05), (25.2, 10.2))
seta(ax, (23.8, 12.05), (25.2, 7.8))

# ───────────────────────────────────────────── qualidade de dados
ax.add_patch(FancyBboxPatch(
    (12.8, 6.3), 11.0, 2.2, boxstyle="round,pad=0.02,rounding_size=0.12",
    facecolor=DQ_FUNDO, edgecolor=DQ_BORDA, linewidth=1.2, zorder=3))
ax.text(18.3, 7.95, "DATA QUALITY  ·  roda nas três camadas", ha="center", va="center",
        fontsize=9.5, fontweight="bold", color=DQ_TINTA, zorder=4)
ax.text(18.3, 7.30, "completude · validade · unicidade · consistência · integridade referencial",
        ha="center", va="center", fontsize=8.2, color=DQ_TINTA, zorder=4)
ax.text(18.3, 6.72, "relatório JSON em logs/  ·  check crítico aborta a esteira\n"
                    "o recálculo é conferido contra o gabarito oficial do INEP",
        ha="center", va="center", fontsize=7.8, color=DQ_TINTA, zorder=4,
        linespacing=1.5)

for x in (14.5, 18.3, 22.1):
    seta(ax, (x, 10.6), (x, 8.5), "#c98a8a", estilo=(0, (3, 2)))

# ───────────────────────────────────────────────────────────── orquestração
ax.add_patch(FancyBboxPatch(
    (0.3, 3.2), 29.4, 1.8, boxstyle="round,pad=0.02,rounding_size=0.12",
    facecolor=ORQ_FUNDO, edgecolor=ORQ_BORDA, linewidth=1.2, zorder=3))
ax.text(15.0, 4.45, "ORQUESTRAÇÃO", ha="center", va="center",
        fontsize=9.5, fontweight="bold", color=ORQ_TINTA, zorder=4)
ax.text(15.0, 3.72,
        "Step Functions encadeia bronze → silver → gold (.sync — para na 1ª falha)"
        "        ·        "
        "EventBridge guarda a agenda semanal, criada DISABLED de propósito",
        ha="center", va="center", fontsize=8.8, color=ORQ_TINTA, zorder=4)

# ───────────────────────────────────────────────────────────── rodapé
ax.add_patch(FancyBboxPatch(
    (0.3, 0.5), 29.4, 2.2, boxstyle="round,pad=0.02,rounding_size=0.12",
    facecolor=TRILHO, edgecolor=BORDA, linewidth=1, zorder=1))
ax.text(0.9, 2.25, "INFRAESTRUTURA COMO CÓDIGO  ·  FinOps",
        fontsize=9, fontweight="bold", color=MUDO)
ax.text(0.9, 1.60, "Terraform provisiona S3 (versionado, criptografado, com lifecycle), catálogo Glue, "
                   "Athena com trava de 1 GB por query, os 3 Glue jobs, Step Functions, EventBridge e Kinesis.",
        fontsize=8.8, color=TINTA_2)
ax.text(0.9, 1.00, "O batch a 1 DPU custa US$ 0,03 por execução completa (~US$ 0,20/mês em regime). "
                   "O streaming é o item caro (US$ 0,88/h) — por isso tem desligamento disciplinado.",
        fontsize=8.8, color=TINTA_2)

plt.tight_layout()
SAIDA.parent.mkdir(exist_ok=True)
fig.savefig(SAIDA, dpi=150, facecolor=FUNDO, bbox_inches="tight")
print(f"diagrama gerado: {SAIDA}")
