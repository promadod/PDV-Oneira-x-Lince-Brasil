"""URLs de XML/PDF retornadas pela Focus (paths relativos ao host da API)."""
from __future__ import annotations

from .models import FiscalConfig


def focus_host_root(cfg: FiscalConfig) -> str:
    base = (cfg.focus_base_url or '').rstrip('/')
    if base.endswith('/v2'):
        base = base[:-3]
    return base.rstrip('/')


def resolver_url_arquivo_focus(cfg: FiscalConfig, caminho: str) -> str:
    p = (caminho or '').strip()
    if not p:
        return ''
    if p.startswith('http://') or p.startswith('https://'):
        return p
    root = focus_host_root(cfg)
    if not p.startswith('/'):
        p = f'/{p}'
    return f'{root}{p}'


def url_xml_documento(cfg: FiscalConfig, doc) -> str:
    return resolver_url_arquivo_focus(cfg, doc.url_xml or doc.caminho_xml)


def url_pdf_documento(cfg: FiscalConfig, doc) -> str:
    return resolver_url_arquivo_focus(cfg, doc.url_pdf or doc.caminho_pdf)
