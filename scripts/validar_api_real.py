"""Valida a YouTube Data API de verdade, com consultas limitadas. É o único teste que fala com o Google.

Sem chave: não consulta dados, registra a validação como PENDENTE e sai com código 0.
Com chave: usa no máximo 3 unidades gerais e 1 chamada do balde de busca, contadas no registro de cota local.
A evidência guarda só contagens e nomes de campos: nenhum título ou nome devolvido pela API, e nunca a chave.

Uso, a partir da raiz:
    uv run --directory backend python ../scripts/validar_api_real.py --saida ../docs/evidencias
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "backend")]

from app.config import get_settings  # noqa: E402
from app.db import to_iso, utcnow  # noqa: E402
from app.intel import api_status  # noqa: E402
from app.intel.common import default_client  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--saida", type=Path, default=ROOT / "docs" / "evidencias")
    args = parser.parse_args()
    settings = get_settings()
    now = utcnow()
    evidence: dict = {"executado_em": to_iso(now), "alvo": settings.api_target}
    if settings.api_target != "google":
        evidence.update(estado="invalido", motivo="YTI_YOUTUBE_BASE_URL aponta para uma API simulada: isto não valida o YouTube.")
        code = 2
    elif not settings.youtube_api_key:
        evidence.update(estado="pendente", motivo="YOUTUBE_API_KEY não configurada. Nenhuma consulta com dados foi feita.")
        code = 0
    else:
        result = api_status.run_check(settings, default_client, now, with_search=True)
        evidence.update(estado="aprovado" if result["ok"] else "reprovado", tipo=result["kind"], mensagem=result["message"], acao=result["action"], etapas=result["details"].get("steps", []),
                        proveniencia=result["details"].get("provenance"))
        code = 0 if result["ok"] else 1
    args.saida.mkdir(parents=True, exist_ok=True)
    (args.saida / "api_real.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({key: evidence[key] for key in ("estado", "motivo", "tipo", "mensagem") if key in evidence}, ensure_ascii=False))
    print("VALIDAÇÃO REAL: " + evidence["estado"].upper())
    return code


if __name__ == "__main__":
    raise SystemExit(main())
