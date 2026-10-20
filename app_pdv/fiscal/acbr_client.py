"""Cliente HTTP ACBr API (OAuth 2 client_credentials + Bearer)."""
from __future__ import annotations

import logging
import time
from typing import Any, Optional

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

_TOKEN_CACHE: dict[str, Any] = {'access_token': '', 'expires_at': 0.0}


class AcbrApiError(Exception):
    def __init__(self, message, status_code=None, payload=None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload or {}


def _cfg(name: str, default: str = '') -> str:
    return str(getattr(settings, name, default) or default).strip()


class AcbrApiClient:
    def __init__(
        self,
        *,
        client_id: str | None = None,
        client_secret: str | None = None,
        token_url: str | None = None,
        base_url: str | None = None,
        scope: str | None = None,
        timeout: Optional[int] = None,
    ):
        self.client_id = (client_id if client_id is not None else _cfg('ACBR_API_CLIENT_ID'))
        self.client_secret = (client_secret if client_secret is not None else _cfg('ACBR_API_CLIENT_SECRET'))
        self.token_url = (token_url or _cfg(
            'ACBR_API_TOKEN_URL',
            'https://auth.acbr.api.br/realms/ACBrAPI/protocol/openid-connect/token',
        )).rstrip('/')
        self.base_url = (base_url or _cfg('ACBR_API_BASE', _cfg(
            'ACBR_API_BASE_PRODUCAO',
            'https://prod.acbr.api.br',
        ))).rstrip('/')
        self.scope = scope or _cfg('ACBR_API_SCOPE', 'empresa nfe nfce nfse cep cnpj')
        self.timeout = timeout or int(getattr(settings, 'ACBR_API_TIMEOUT_SECONDS', 45) or 45)

    def credenciais_ok(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def obter_token(self, *, forcar=False) -> str:
        if not self.credenciais_ok():
            raise AcbrApiError(
                'Client ID e Client Secret da ACBr API não estão configurados no .env.',
            )
        agora = time.time()
        if (
            not forcar
            and _TOKEN_CACHE.get('access_token')
            and float(_TOKEN_CACHE.get('expires_at') or 0) > agora + 60
            and _TOKEN_CACHE.get('client_id') == self.client_id
            and _TOKEN_CACHE.get('base_url') == self.base_url
        ):
            return _TOKEN_CACHE['access_token']
        try:
            resp = requests.post(
                self.token_url,
                data={
                    'grant_type': 'client_credentials',
                    'client_id': self.client_id,
                    'client_secret': self.client_secret,
                    'scope': self.scope,
                },
                headers={'Content-Type': 'application/x-www-form-urlencoded', 'Accept': 'application/json'},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            logger.exception('ACBr API token request failed')
            raise AcbrApiError(f'Falha ao obter token ACBr API: {exc}') from exc

        try:
            data = resp.json() if resp.content else {}
        except ValueError:
            data = {'raw': resp.text}

        if resp.status_code >= 400 or not data.get('access_token'):
            msg = (
                (data.get('error_description') if isinstance(data, dict) else None)
                or (data.get('error') if isinstance(data, dict) else None)
                or resp.text
                or 'Erro ao autenticar na ACBr API'
            )
            raise AcbrApiError(
                f'{msg} (endpoint: {self.token_url})',
                status_code=resp.status_code,
                payload=data,
            )

        expires_in = int(data.get('expires_in') or 0)
        _TOKEN_CACHE.update({
            'access_token': data['access_token'],
            'expires_at': agora + max(expires_in, 60),
            'client_id': self.client_id,
            'base_url': self.base_url,
            'token_type': data.get('token_type') or 'Bearer',
            'scope': data.get('scope') or self.scope,
            'expires_in': expires_in,
        })
        return data['access_token']

    def _request(self, method: str, path: str, *, params=None, json_body=None) -> Any:
        token = self.obter_token()
        url = f'{self.base_url}/{path.lstrip("/")}'
        try:
            resp = requests.request(
                method,
                url,
                params=params,
                json=json_body,
                headers={
                    'Authorization': f'Bearer {token}',
                    'Accept': 'application/json',
                    'Content-Type': 'application/json',
                },
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            logger.exception('ACBr API request failed: %s %s', method, url)
            raise AcbrApiError(f'Falha de conexão com ACBr API: {exc}') from exc

        try:
            data = resp.json() if resp.content else {}
        except ValueError:
            data = {'raw': resp.text}

        if resp.status_code >= 400:
            err = data.get('error') if isinstance(data, dict) else None
            if isinstance(err, dict):
                msg = err.get('message') or err.get('code') or str(err)
            else:
                msg = err or data.get('message') or data.get('mensagem') or resp.text or 'Erro ACBr API'
            raise AcbrApiError(str(msg), status_code=resp.status_code, payload=data)
        return data

    def emitir_dfe(self, tipo: str, pedido: dict) -> Any:
        """POST /nfce ou /nfe. O host segue o ambiente (hom ou prod)."""
        caminho = 'nfe' if tipo == 'nfe' else 'nfce'
        return self._request('POST', caminho, json_body=pedido)

    def consultar_dfe(self, tipo: str, documento_id: str) -> Any:
        caminho = 'nfe' if tipo == 'nfe' else 'nfce'
        return self._request('GET', f'{caminho}/{documento_id}')

    def listar_empresas(self) -> Any:
        return self._request('GET', 'empresas')

    def testar_conexao(self) -> dict:
        token = self.obter_token(forcar=True)
        empresas = self.listar_empresas()
        lista = empresas.get('data', empresas) if isinstance(empresas, dict) else empresas
        qtd = len(lista) if isinstance(lista, list) else 0
        return {
            'ok': True,
            'base_url': self.base_url,
            'token_url': self.token_url,
            'token_type': _TOKEN_CACHE.get('token_type') or 'Bearer',
            'scope': _TOKEN_CACHE.get('scope') or self.scope,
            'expires_in': _TOKEN_CACHE.get('expires_in') or 0,
            'token_prefixo': f'{token[:12]}…' if token else '',
            'empresas_cadastradas': qtd,
            'client_id': self.client_id,
        }


def client_from_fiscal_config(config) -> AcbrApiClient:
    """Credenciais digitadas na loja; se vazias, usa o .env do servidor."""
    base = client_from_settings()
    client_id = (getattr(config, 'acbr_client_id', '') or '').strip()
    client_secret = (getattr(config, 'acbr_client_secret', '') or '').strip()
    if client_id and not client_secret:
        if client_id == base.client_id:
            client_secret = base.client_secret
    elif not client_id and not client_secret:
        client_id = base.client_id
        client_secret = base.client_secret
    elif not client_id:
        client_id = base.client_id
    ambiente = (getattr(config, 'ambiente', '') or '').strip().lower()
    if ambiente == 'homologacao':
        api_base = _cfg('ACBR_API_BASE_HOMOLOGACAO', 'https://hom.acbr.api.br')
    elif ambiente == 'producao':
        api_base = _cfg('ACBR_API_BASE_PRODUCAO', 'https://prod.acbr.api.br')
    else:
        api_base = base.base_url
    return AcbrApiClient(
        client_id=client_id,
        client_secret=client_secret,
        token_url=base.token_url,
        base_url=api_base,
        scope=base.scope,
        timeout=base.timeout,
    )


def client_from_settings() -> AcbrApiClient:
    ambiente = _cfg('ACBR_API_AMBIENTE', 'producao').lower()
    if ambiente in ('homologacao', 'hom', 'sandbox'):
        base = _cfg('ACBR_API_BASE_HOMOLOGACAO', 'https://hom.acbr.api.br')
    else:
        base = _cfg('ACBR_API_BASE_PRODUCAO', 'https://prod.acbr.api.br')
    return AcbrApiClient(base_url=_cfg('ACBR_API_BASE') or base)


def acbr_configurada() -> bool:
    return bool(_cfg('ACBR_API_CLIENT_ID') and _cfg('ACBR_API_CLIENT_SECRET'))
