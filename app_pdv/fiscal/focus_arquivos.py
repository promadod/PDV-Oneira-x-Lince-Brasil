"""URLs de XML/PDF retornadas pela Focus (paths relativos ao host da API)."""
from __future__ import annotations

import logging
from typing import Optional

import requests

from .models import DocumentoFiscal, FiscalConfig

logger = logging.getLogger(__name__)


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
        if 'oneirasistemas.com.br' in p or 'localhost' in p:
            path_only = p.split('.com.br', 1)[-1].split('.br', 1)[-1]
            if not path_only.startswith('/'):
                path_only = '/' + path_only.lstrip('/')
            root = focus_host_root(cfg)
            return f'{root}{path_only}' if root else p
        return p
    root = focus_host_root(cfg)
    if not p.startswith('/'):
        p = f'/{p}'
    return f'{root}{p}'


def _url_armazenada_valida(cfg: FiscalConfig, url: str) -> bool:
    u = (url or '').strip()
    if not u:
        return False
    if 'focusnfe.com.br' in u:
        return True
    if u.startswith('/') and focus_host_root(cfg):
        return True
    return False


def url_xml_documento(cfg: FiscalConfig, doc) -> str:
    caminho = (doc.caminho_xml or '').strip()
    if caminho:
        return resolver_url_arquivo_focus(cfg, caminho)
    if _url_armazenada_valida(cfg, doc.url_xml):
        return resolver_url_arquivo_focus(cfg, doc.url_xml)
    return (doc.url_xml or '').strip()


def url_pdf_documento(cfg: FiscalConfig, doc) -> str:
    caminho = (doc.caminho_pdf or '').strip()
    if caminho:
        return resolver_url_arquivo_focus(cfg, caminho)
    if _url_armazenada_valida(cfg, doc.url_pdf):
        return resolver_url_arquivo_focus(cfg, doc.url_pdf)
    return (doc.url_pdf or '').strip()


def _tipo_consulta_focus(doc: DocumentoFiscal) -> str:
    if doc.tipo in ('nfe', 'nfce', 'nfse'):
        return doc.tipo
    return 'nfce'


def sincronizar_caminhos_focus(doc: DocumentoFiscal, cfg: FiscalConfig) -> DocumentoFiscal:
    """Atualiza caminhos XML/DANFE a partir da consulta Focus (GET /v2/{tipo}/{ref})."""
    from .focus_client import client_from_config

    if not cfg.focus_token or not doc.ref:
        return doc
    try:
        client = client_from_config(cfg)
        retorno = client.consultar(_tipo_consulta_focus(doc), doc.ref)
    except Exception:
        logger.exception('Falha ao consultar documento %s na Focus', doc.ref)
        return doc
    if not isinstance(retorno, dict):
        return doc
    caminho_xml = retorno.get('caminho_xml_nota_fiscal') or retorno.get('caminho_xml') or ''
    caminho_pdf = retorno.get('caminho_danfe') or retorno.get('caminho_pdf') or ''
    if caminho_xml:
        doc.caminho_xml = str(caminho_xml)
        doc.url_xml = resolver_url_arquivo_focus(cfg, str(caminho_xml))
    if caminho_pdf:
        doc.caminho_pdf = str(caminho_pdf)
        doc.url_pdf = resolver_url_arquivo_focus(cfg, str(caminho_pdf))
    if caminho_xml or caminho_pdf:
        doc.save(update_fields=['caminho_xml', 'caminho_pdf', 'url_xml', 'url_pdf', 'atualizado_em'])
    return doc


def detectar_content_type(conteudo: bytes, url: str = '') -> str:
    if not conteudo:
        return 'application/octet-stream'
    if conteudo[:4] == b'%PDF':
        return 'application/pdf'
    head = conteudo[:800].lower()
    if conteudo[:5] == b'<?xml' or (conteudo[:1] == b'<' and b'nfe' in head):
        return 'application/xml; charset=utf-8'
    if b'<!doctype html' in head or b'<html' in head:
        return 'text/html; charset=utf-8'
    if (url or '').lower().endswith('.html'):
        return 'text/html; charset=utf-8'
    if (url or '').lower().endswith('.xml'):
        return 'application/xml; charset=utf-8'
    return 'application/octet-stream'


def baixar_arquivo_focus(cfg: FiscalConfig, url: str) -> Optional[bytes]:
    if not url or not cfg.focus_token:
        return None
    try:
        resp = requests.get(
            url,
            auth=(cfg.focus_token.strip(), ''),
            timeout=90,
            headers={'Accept': '*/*'},
        )
        if resp.status_code == 200 and resp.content:
            return resp.content
        logger.warning('Focus arquivo HTTP %s para %s', resp.status_code, url[:120])
    except requests.RequestException:
        logger.exception('Erro ao baixar arquivo Focus: %s', url[:120])
    return None


def obter_conteudo_documento(
    cfg: FiscalConfig,
    doc: DocumentoFiscal,
    *,
    formato: str,
    refresh: bool = True,
) -> tuple[Optional[bytes], str, str]:
    """
    Retorna (bytes, content_type, filename).
    formato: xml | pdf
    """
    if formato == 'xml':
        url = url_xml_documento(cfg, doc)
        ext = 'xml'
    elif formato == 'pdf':
        url = url_pdf_documento(cfg, doc)
        ext = 'pdf'
    else:
        return None, '', ''

    conteudo = baixar_arquivo_focus(cfg, url) if url else None
    if (not conteudo or not conteudo.strip()) and refresh:
        sincronizar_caminhos_focus(doc, cfg)
        if formato == 'xml':
            url = url_xml_documento(cfg, doc)
        else:
            url = url_pdf_documento(cfg, doc)
        conteudo = baixar_arquivo_focus(cfg, url) if url else None

    if not conteudo:
        return None, '', ''

    content_type = detectar_content_type(conteudo, url or '')
    if formato == 'pdf' and content_type.startswith('text/html'):
        ext = 'html'
    fname = f'{doc.chave_acesso or doc.ref}.{ext}'
    return conteudo, content_type, fname
