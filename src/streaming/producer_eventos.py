"""
Producer de eventos de streaming (simulação de ingestão quase em tempo real).

Gera eventos JSON de novas medições do indicador. Tem dois destinos:

- pasta (default): grava um arquivo por lote na landing, que o consumer local de
  pasta (Spark Structured Streaming) lê. É o modo de desenvolvimento.
- kinesis: publica cada evento no Kinesis Data Stream via boto3 put_records, que o
  Glue Streaming job consome na AWS. É o modo "sistema externo de verdade" — o
  producer simula um sistema que manda eventos pra borda (o Kinesis), não algo que
  roda dentro do pipeline.

É Python puro, sem Spark — roda em qualquer versão.

Uso:
    python src/streaming/producer_eventos.py                       # 5 lotes de 3 eventos a cada 2s (pasta)
    python src/streaming/producer_eventos.py --lotes 10 --eventos 5 --intervalo 1
    python src/streaming/producer_eventos.py --lotes 0             # contínuo (Ctrl+C para parar)
    python src/streaming/producer_eventos.py --destino kinesis     # publica no stream alfabetiza-eventos
    python src/streaming/producer_eventos.py --destino kinesis --stream outro-nome
"""
import argparse
import json
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.utils.logger import get_logger

load_dotenv()
logger = get_logger("streaming.producer")

LAKE_PATH = os.environ.get("LAKE_PATH", "./data")
LANDING = Path(LAKE_PATH) / "bronze" / "streaming" / "landing"
SILVER_MUNICIPIO = Path(LAKE_PATH) / "silver" / "resultados" / "municipio"
STREAM_PADRAO = "alfabetiza-eventos"

TIPOS_EVENTO = ["nova_medicao", "revisao_indicador", "atualizacao_meta"]
ANOS = [2023, 2024]
# usados só se a Silver ainda não existir — capitais, para os eventos serem plausíveis
MUNICIPIOS_FALLBACK = [3550308, 3304557, 2927408, 5300108, 4106902, 2304400, 1302603]


def carregar_municipios() -> list[int]:
    """Amostra a lista real de municípios da Silver; cai no fallback se não houver."""
    try:
        import pyarrow.parquet as pq

        tabela = pq.read_table(SILVER_MUNICIPIO, columns=["id_municipio"])
        ids = [int(v) for v in set(tabela.column("id_municipio").to_pylist()) if v is not None]
        if ids:
            logger.info("%d municípios carregados da Silver", len(ids))
            return ids
    except Exception as exc:
        logger.warning("não deu para ler municípios da Silver (%s); usando fallback", exc)
    return MUNICIPIOS_FALLBACK


def gerar_evento(municipios: list[int]) -> dict:
    return {
        "id_municipio": random.choice(municipios),
        "ano": random.choice(ANOS),
        # medição em torno do ponto de corte de 743, com dispersão realista
        "proficiencia_media": round(random.gauss(743, 35), 1),
        "tipo_evento": random.choice(TIPOS_EVENTO),
        "event_timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def escrever_lote(eventos: list[dict]) -> Path:
    """Grava os eventos como NDJSON. Escrita atômica: nome temporário que o Spark
    ignora (prefixo '.') e depois rename, para o consumer nunca ler pela metade."""
    LANDING.mkdir(parents=True, exist_ok=True)
    marca = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    destino = LANDING / f"evento_{marca}.json"
    temp = LANDING / f".{destino.name}.tmp"
    conteudo = "\n".join(json.dumps(e, ensure_ascii=False) for e in eventos)
    temp.write_text(conteudo + "\n", encoding="utf-8")
    os.replace(temp, destino)
    return destino


def publicar_kinesis(eventos: list[dict], cliente, stream: str) -> None:
    """Publica o lote no Kinesis. partition_key = id_municipio para distribuir os
    eventos entre shards de forma determinística (o mesmo município cai no mesmo
    shard, o que preserva ordem por município se um dia houver mais de um shard)."""
    registros = [
        {
            "Data": (json.dumps(e, ensure_ascii=False) + "\n").encode("utf-8"),
            "PartitionKey": str(e["id_municipio"]),
        }
        for e in eventos
    ]
    resposta = cliente.put_records(Records=registros, StreamName=stream)
    if resposta.get("FailedRecordCount"):
        logger.warning("%d de %d registros falharam no put_records",
                       resposta["FailedRecordCount"], len(registros))


def main() -> None:
    parser = argparse.ArgumentParser(description="Producer de eventos de streaming do indicador.")
    parser.add_argument("--lotes", type=int, default=5, help="total de lotes (0 = contínuo)")
    parser.add_argument("--eventos", type=int, default=3, help="eventos por lote")
    parser.add_argument("--intervalo", type=float, default=2.0, help="segundos entre lotes")
    parser.add_argument("--destino", choices=["pasta", "kinesis"], default="pasta",
                        help="onde publicar os eventos (default: pasta / modo dev)")
    parser.add_argument("--stream", default=STREAM_PADRAO,
                        help=f"nome do Kinesis stream no modo kinesis (default: {STREAM_PADRAO})")
    args = parser.parse_args()

    cliente_kinesis = None
    if args.destino == "kinesis":
        import boto3

        cliente_kinesis = boto3.client("kinesis")
        alvo = f"kinesis://{args.stream}"
    else:
        alvo = str(LANDING)

    municipios = carregar_municipios()
    logger.info("Gerando eventos em %s (lotes=%s, eventos/lote=%d, intervalo=%.1fs)",
                alvo, args.lotes or "∞", args.eventos, args.intervalo)

    lote, total = 0, 0
    try:
        while args.lotes == 0 or lote < args.lotes:
            eventos = [gerar_evento(municipios) for _ in range(args.eventos)]
            if args.destino == "kinesis":
                publicar_kinesis(eventos, cliente_kinesis, args.stream)
                detalhe = args.stream
            else:
                detalhe = escrever_lote(eventos).name
            lote += 1
            total += len(eventos)
            logger.info("lote %d: %d eventos -> %s", lote, len(eventos), detalhe)
            if args.lotes == 0 or lote < args.lotes:
                time.sleep(args.intervalo)
    except KeyboardInterrupt:
        logger.info("interrompido pelo usuário")

    logger.info("Producer finalizado: %d lotes, %d eventos publicados", lote, total)


if __name__ == "__main__":
    main()
