"""Remove segredos de textos que vão para logs e mensagens de erro."""
from __future__ import annotations

import logging
import re

_PATTERNS = [
    (re.compile(r"(\bkey=)[^&\s\"']+", re.I), r"\1[REMOVIDO]"),
    (re.compile(r"(bearer\s+)[a-z0-9._\-~+/=]+", re.I), r"\1[REMOVIDO]"),
    (re.compile(r"(access_token|refresh_token|client_secret|api_key)([\"'=:\s]+)[^\s\"'&,}]+", re.I), r"\1\2[REMOVIDO]"),
    (re.compile(r"AIza[0-9A-Za-z_\-]{20,}"), "[REMOVIDO]"),
    (re.compile(r"sk-ant-[0-9A-Za-z_\-]{10,}"), "[REMOVIDO]"),
]


def redact(text: object) -> str:
    result = str(text)
    for pattern, replacement in _PATTERNS:
        result = pattern.sub(replacement, result)
    return result


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage())
        record.args = ()
        return True


def install_redaction() -> None:
    root = logging.getLogger()
    root.addFilter(RedactingFilter())
    for handler in root.handlers:
        handler.addFilter(RedactingFilter())
    # httpx registra a URL completa em INFO, e a URL contém a chave.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
