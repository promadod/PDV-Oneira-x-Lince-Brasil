"""Cliente HTTP Focus NFe (Basic Auth: token como usuário, senha vazia)."""
from __future__ import annotations

import logging
from typing import Any, Optional

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class FocusNFeError(Exception):
    def __init__(self, message, status_code=None, payload=None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload or {}


class FocusNFeClient:
    def __init__(self, token: str, base_url: str, timeout: Optional[int] = None):
        self.token = (token or '').strip()
        self.base_url = (base_url or '').rstrip('/')
        self.timeout = timeout or int(getattr(settings, 'FOCUS_NFE_TIMEOUT_SECONDS', 45) or 45)

    def _headers(self):
        return {'Content-Type': 'application/json', 'Accept': 'application/json'}

    def _auth(self):
        return (self.token, '')

    def _request(self, method: str, path: str, *, params=None, json_body=None) -> Any:
        if not self.token:
            raise FocusNFeError('Token Focus NFe não configurado para esta loja.')
        url = f'{self.base_url}/{path.lstrip("/")}'
        try:
            resp = requests.request(
                method,
                url,
                params=params,
                json=json_body,
                auth=self._auth(),
                headers=self._headers(),
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            logger.exception('Focus NFe request failed: %s %s', method, url)
            raise FocusNFeError(f'Falha de conexão com Focus NFe: {exc}') from exc

        try:
            data = resp.json() if resp.content else {}
        except ValueError:
            data = {'raw': resp.text}

        if resp.status_code >= 400:
            msg = data.get('mensagem') or data.get('message') or data.get('erro') or resp.text or 'Erro Focus NFe'
            raise FocusNFeError(str(msg), status_code=resp.status_code, payload=data)
        return data

    def testar_autenticacao(self) -> dict:
        """Valida token via GET /hooks (documentação: listar gatilhos)."""
        return self._request('GET', 'hooks')

    def emitir_nfe(self, ref: str, payload: dict, *, query_params: dict | None = None) -> Any:
        params = {'ref': ref, **(query_params or {})}
        return self._request('POST', 'nfe', params=params, json_body=payload)

    def emitir_nfce(self, ref: str, payload: dict, *, query_params: dict | None = None) -> Any:
        params = {'ref': ref, **(query_params or {})}
        return self._request('POST', 'nfce', params=params, json_body=payload)

    def emitir_nfse(self, ref: str, payload: dict, *, query_params: dict | None = None) -> Any:
        params = {'ref': ref, **(query_params or {})}
        return self._request('POST', 'nfse', params=params, json_body=payload)

    def consultar(self, tipo: str, ref: str) -> Any:
        # tipo: nfe | nfce | nfse
        return self._request('GET', f'{tipo}/{ref}')

    def cancelar(self, tipo: str, ref: str, justificativa: str) -> Any:
        return self._request('DELETE', f'{tipo}/{ref}', json_body={'justificativa': justificativa})

    def carta_correcao(self, ref: str, correcao: str) -> Any:
        return self._request('POST', f'nfe/{ref}/carta_correcao', json_body={'correcao': correcao})

    def inutilizar(self, payload: dict) -> Any:
        return self._request('POST', 'inutilizacao', json_body=payload)

    def cadastrar_webhook(self, payload: dict) -> Any:
        return self._request('POST', 'hooks', json_body=payload)

    def listar_webhooks(self) -> Any:
        return self._request('GET', 'hooks')


def client_from_config(config) -> FocusNFeClient:
    return FocusNFeClient(token=config.focus_token, base_url=config.focus_base_url)
