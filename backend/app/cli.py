"""Comandos de operação: python -m app.cli <comando>."""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time

from . import collector, demo, scheduler
from .ai.generation import generate_for_topic
from .config import get_settings
from .connectors import oauth
from .connectors.youtube_data import YouTubeDataClient
from .db import connect, migrate, utcnow
from .logging_safe import install_redaction, redact
from .policy import apply_retention, delete_channel_data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="yti")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate", help="Aplica migrações")
    sub.add_parser("demo-reset", help="Recria os dados fictícios")
    add = sub.add_parser("add-channel", help="Monitora um canal (UC... ou @handle)")
    add.add_argument("reference")
    add.add_argument("--max-videos", type=int, default=50)
    search = sub.add_parser("search", help="Pesquisa um nicho")
    search.add_argument("query")
    search.add_argument("--language")
    search.add_argument("--country")
    search.add_argument("--published-after", help="RFC 3339, ex.: 2026-10-01T00:00:00Z")
    search.add_argument("--pages", type=int, default=1)
    sub.add_parser("collect", help="Roda as tarefas vencidas uma vez")
    loop = sub.add_parser("scheduler", help="Roda as tarefas em ciclo")
    loop.add_argument("--interval-seconds", type=int, default=300)
    auth = sub.add_parser("authorize-channel", help="Autoriza um canal próprio com OAuth")
    auth.add_argument("reference")
    revoke = sub.add_parser("revoke-channel", help="Revoga e apaga os dados de um canal próprio")
    revoke.add_argument("channel_id")
    delete = sub.add_parser("delete-channel-data", help="Apaga os dados locais de um canal")
    delete.add_argument("channel_id")
    sub.add_parser("retention", help="Aplica a política de retenção agora")
    tick = sub.add_parser("research-tick", help="Roda as pesquisas agendadas vencidas. Com dados reais, exige limites aprovados")
    tick.add_argument("--loop-seconds", type=int, default=0, help="Repete a cada N segundos. Mínimo: 300. Sem isto, roda uma vez")
    generate = sub.add_parser("generate", help="Gera ideias para um tema")
    generate.add_argument("topic")
    generate.add_argument("--format", choices=["short", "long"], required=True)

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    install_redaction()
    settings = get_settings()
    conn = connect(settings.db_path)
    migrate(conn)
    now = utcnow()

    def live_client() -> YouTubeDataClient:
        if settings.mode != "live":
            raise SystemExit("Este comando faz chamadas reais. Defina YTI_MODE=live no .env.")
        return YouTubeDataClient(settings, conn)

    try:
        if args.command == "migrate":
            print("Banco atualizado:", settings.db_path)
        elif args.command == "demo-reset":
            if settings.mode != "demo":
                raise SystemExit("demo-reset só funciona com YTI_MODE=demo.")
            demo.reset_demo(conn, now)
            print("Dados fictícios recriados.")
        elif args.command == "add-channel":
            client = live_client()
            channel_id = collector.add_channel(client, conn, args.reference, now)
            found = collector.collect_channel_videos(client, conn, settings, channel_id, now, args.max_videos)
            print(f"Canal {channel_id} monitorado; {len(found)} vídeos coletados.")
        elif args.command == "search":
            print(json.dumps(collector.search_niche(
                live_client(), conn, settings, args.query, now, language=args.language, country=args.country,
                published_after=args.published_after, pages=args.pages)))
        elif args.command == "collect":
            print(json.dumps(_run_jobs(conn, settings, now)))
        elif args.command == "scheduler":
            while True:
                print(json.dumps(_run_jobs(conn, settings, utcnow())), flush=True)
                time.sleep(args.interval_seconds)
        elif args.command == "authorize-channel":
            client = live_client()
            client_id, client_secret = oauth.load_client_secrets(settings.oauth_client_secrets)
            tokens = oauth.run_browser_flow(client_id, client_secret)
            channel_id = collector.register_own_channel(client, conn, settings, oauth.KeyringTokenStore(), args.reference, tokens, now)
            print(f"Canal próprio autorizado: {channel_id}")
        elif args.command == "revoke-channel":
            collector.revoke_own_channel(conn, oauth.KeyringTokenStore(), args.channel_id)
            print("Autorização revogada e dados apagados.")
        elif args.command == "delete-channel-data":
            delete_channel_data(conn, args.channel_id)
            print("Dados locais apagados.")
        elif args.command == "research-tick":
            from .intel import automation
            from .studio.store import open_studio

            studio = open_studio(settings)
            try:
                while True:
                    print(json.dumps(automation.tick(conn, studio, settings, utcnow()), ensure_ascii=False), flush=True)
                    if not args.loop_seconds:
                        break
                    time.sleep(max(args.loop_seconds, 300))
            finally:
                studio.close()
        elif args.command == "retention":
            print(json.dumps(apply_retention(conn, settings, now)))
        elif args.command == "generate":
            print(json.dumps(generate_for_topic(conn, settings, args.topic, args.format), ensure_ascii=False, indent=1))
    except SystemExit:
        raise
    except Exception as error:  # noqa: BLE001 - erro legível e sem segredos na linha de comando
        print(f"Erro: {redact(error)}", file=sys.stderr)
        return 1
    finally:
        conn.close()
    return 0


def _run_jobs(conn, settings, now) -> dict:
    if settings.mode != "live":
        return {"modo": "demo", "resultado": "Nenhuma coleta: o modo demo não faz chamadas externas."}
    client = YouTubeDataClient(settings, conn) if settings.youtube_api_key else None
    try:
        return scheduler.run_due(conn, scheduler.build_runners(conn, settings, client), now)
    finally:
        if client:
            client.close()


if __name__ == "__main__":
    raise SystemExit(main())
