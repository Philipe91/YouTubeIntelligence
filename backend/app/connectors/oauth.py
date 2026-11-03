"""OAuth 2.0 para canais próprios (app para computador, loopback + PKCE).

Somente escopos de leitura. O refresh token fica no Gerenciador de Credenciais do Windows
via keyring; o SQLite nunca guarda tokens. Não testado com conta real: exige suas credenciais.
"""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Protocol
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from ..logging_safe import redact

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
SCOPES = (
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/youtube.readonly",
)
KEYRING_SERVICE = "youtube-intelligence"


class OAuthError(RuntimeError):
    def __init__(self, message: str, invalid_grant: bool = False):
        super().__init__(redact(message))
        self.invalid_grant = invalid_grant


class TokenStore(Protocol):
    def get(self, channel_id: str) -> str | None: ...
    def set(self, channel_id: str, refresh_token: str) -> None: ...
    def delete(self, channel_id: str) -> None: ...


class KeyringTokenStore:
    def get(self, channel_id: str) -> str | None:
        import keyring

        return keyring.get_password(KEYRING_SERVICE, f"oauth:{channel_id}")

    def set(self, channel_id: str, refresh_token: str) -> None:
        import keyring

        keyring.set_password(KEYRING_SERVICE, f"oauth:{channel_id}", refresh_token)

    def delete(self, channel_id: str) -> None:
        import keyring
        from keyring.errors import PasswordDeleteError

        try:
            keyring.delete_password(KEYRING_SERVICE, f"oauth:{channel_id}")
        except PasswordDeleteError:
            pass


def load_client_secrets(path: str) -> tuple[str, str]:
    if not path:
        raise OAuthError("YOUTUBE_OAUTH_CLIENT_SECRETS não configurado. Veja o README, seção Modo real.")
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    block = data.get("installed")
    if not block:
        raise OAuthError("O arquivo precisa ser de um cliente OAuth do tipo 'App para computador'.")
    return block["client_id"], block["client_secret"]


def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    return verifier, base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def build_auth_url(client_id: str, redirect_uri: str, state: str, challenge: str) -> str:
    return AUTH_URL + "?" + urlencode({
        "client_id": client_id, "redirect_uri": redirect_uri, "response_type": "code", "scope": " ".join(SCOPES),
        "access_type": "offline", "prompt": "consent", "state": state, "code_challenge": challenge,
        "code_challenge_method": "S256",
    })


def run_browser_flow(client_id: str, client_secret: str, transport: httpx.BaseTransport | None = None) -> dict:
    """Abre o navegador, recebe o código em 127.0.0.1 e troca pelos tokens."""
    captured: dict[str, str] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            query = parse_qs(urlparse(self.path).query)
            for key in ("code", "state", "error"):
                if key in query:
                    captured[key] = query[key][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write("Autorização recebida. Pode fechar esta aba.".encode())

        def log_message(self, *args):
            return  # A URL de retorno contém o código de autorização.

    server = HTTPServer(("127.0.0.1", 0), Handler)
    redirect_uri = f"http://127.0.0.1:{server.server_address[1]}"
    state = secrets.token_urlsafe(24)
    verifier, challenge = pkce_pair()
    webbrowser.open(build_auth_url(client_id, redirect_uri, state, challenge))
    server.timeout = 300
    server.handle_request()
    server.server_close()

    if captured.get("error") or not captured.get("code"):
        raise OAuthError(f"Autorização não concluída: {captured.get('error', 'sem resposta')}.")
    if captured.get("state") != state:
        raise OAuthError("Resposta de autorização com state inválido.")
    return exchange_code(client_id, client_secret, captured["code"], redirect_uri, verifier, transport)


def _post_token(payload: dict, transport: httpx.BaseTransport | None) -> dict:
    with httpx.Client(timeout=30.0, transport=transport) as client:
        response = client.post(TOKEN_URL, data=payload)
    if response.status_code != 200:
        try:
            code = response.json().get("error", "desconhecido")
        except ValueError:
            code = "desconhecido"
        raise OAuthError(f"Falha ao obter token: {code}.", invalid_grant=code == "invalid_grant")
    return response.json()


def exchange_code(client_id, client_secret, code, redirect_uri, verifier, transport=None) -> dict:
    return _post_token({
        "client_id": client_id, "client_secret": client_secret, "code": code, "code_verifier": verifier,
        "grant_type": "authorization_code", "redirect_uri": redirect_uri,
    }, transport)


def refresh_access_token(client_id, client_secret, refresh_token, transport=None) -> str:
    data = _post_token({
        "client_id": client_id, "client_secret": client_secret, "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }, transport)
    return data["access_token"]


def revoke_token(token: str, transport: httpx.BaseTransport | None = None) -> None:
    with httpx.Client(timeout=30.0, transport=transport) as client:
        client.post(REVOKE_URL, data={"token": token})
