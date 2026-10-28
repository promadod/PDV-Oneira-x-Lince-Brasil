"""Cliente HTTP do worker ACBrLib (sidecar Docker)."""
from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any, Optional

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class AcbrLibError(Exception):
    def __init__(self, message, status_code=None, payload=None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload or {}


def _cfg(name: str, default: str = '') -> str:
    return str(getattr(settings, name, default) or default).strip()


def acbr_lib_habilitada() -> bool:
    flag = _cfg('ACBR_LIB_ENABLED', 'False').lower()
    return flag in ('1', 'true', 'yes', 'on')


def worker_base_url() -> str:
    return _cfg('ACBR_LIB_WORKER_URL', 'http://acbr-lib:8091').rstrip('/')


class AcbrLibClient:
    def __init__(self, *, base_url: str | None = None, timeout: Optional[int] = None):
        self.base_url = (base_url or worker_base_url()).rstrip('/')
        self.timeout = timeout or int(getattr(settings, 'ACBR_LIB_TIMEOUT_SECONDS', 120) or 120)

    def health(self) -> dict:
        try:
            resp = requests.get(f'{self.base_url}/health', timeout=min(self.timeout, 15))
            data = resp.json() if resp.content else {}
        except requests.RequestException as exc:
            raise AcbrLibError(f'Worker ACBrLib inacessível: {exc}') from exc
        if resp.status_code >= 400:
            raise AcbrLibError(
                data.get('erro') or f'Worker health HTTP {resp.status_code}',
                status_code=resp.status_code,
                payload=data if isinstance(data, dict) else {},
            )
        return data if isinstance(data, dict) else {'raw': data}

    def _post(self, path: str, body: dict) -> dict:
        url = f'{self.base_url}/{path.lstrip("/")}'
        try:
            resp = requests.post(url, json=body, timeout=self.timeout)
        except requests.RequestException as exc:
            logger.exception('ACBrLib worker %s', path)
            raise AcbrLibError(f'Falha de conexão com worker ACBrLib: {exc}') from exc
        try:
            data = resp.json() if resp.content else {}
        except ValueError:
            data = {'raw': resp.text}
        if resp.status_code >= 400 or (isinstance(data, dict) and data.get('ok') is False):
            msg = (
                (data.get('erro') if isinstance(data, dict) else None)
                or (data.get('detalhe') if isinstance(data, dict) else None)
                or resp.text
                or f'Erro worker HTTP {resp.status_code}'
            )
            raise AcbrLibError(str(msg), status_code=resp.status_code, payload=data if isinstance(data, dict) else {})
        return data if isinstance(data, dict) else {'raw': data}

    def status_servico(self, config: dict) -> dict:
        return self._post('status', {'config': config})

    def emitir(self, config: dict, ini: str) -> dict:
        return self._post('emitir', {'config': config, 'ini': ini})


def config_worker_from_fiscal(cfg) -> dict:
    """Monta o bloco config enviado ao worker a partir de FiscalConfig."""
    pfx = (getattr(cfg, 'acbr_lib_pfx_path', '') or '').strip().replace('\\', '/')
    # No compose, media_data → /app/media (web) e /media (worker).
    # Sempre envia o path que o worker enxerga.
    if pfx:
        if pfx.startswith('/media/'):
            pfx_worker = pfx
        elif pfx.startswith('/app/media/'):
            pfx_worker = '/media/' + pfx[len('/app/media/'):]
        elif Path(pfx).is_absolute():
            pfx_worker = pfx
        else:
            pfx_worker = f'/media/{pfx.lstrip("/")}'
    else:
        pfx_worker = ''
    return {
        'uf': (cfg.uf or 'RJ').upper()[:2],
        'ambiente': cfg.ambiente or 'homologacao',
        'modelo': '65',  # sobrescrito na emissão
        'pfx_path': pfx_worker,
        'pfx_senha': getattr(cfg, 'acbr_lib_pfx_senha', '') or '',
        'csc_id': (cfg.csc_id or '').strip(),
        'csc_token': (cfg.csc_token or '').strip(),
        'schemas_path': _cfg('ACBR_LIB_SCHEMAS_PATH', '/opt/acbrlib/Schemas/NFe'),
        'forma_emissao': '9' if getattr(cfg, 'contingencia_ativa', False) else '0',
    }


def salvar_arquivos_lib(loja_id: int, chave: str, *, xml_b64: str = '', pdf_b64: str = '') -> dict[str, str]:
    """Grava XML/PDF no MEDIA_ROOT e devolve caminhos relativos."""
    from django.conf import settings as dj_settings

    media = Path(getattr(dj_settings, 'MEDIA_ROOT', '.') or '.')
    pasta = media / 'fiscal' / 'lib' / str(loja_id)
    pasta.mkdir(parents=True, exist_ok=True)
    base = (chave or 'sem_chave').strip() or 'sem_chave'
    out: dict[str, str] = {}
    if xml_b64:
        path = pasta / f'{base}.xml'
        path.write_bytes(base64.b64decode(xml_b64))
        out['caminho_xml'] = str(path.relative_to(media)).replace('\\', '/')
    if pdf_b64:
        path = pasta / f'{base}.pdf'
        path.write_bytes(base64.b64decode(pdf_b64))
        out['caminho_pdf'] = str(path.relative_to(media)).replace('\\', '/')
    return out


def client_from_settings() -> AcbrLibClient:
    return AcbrLibClient()
