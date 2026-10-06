"""URLs de XML/DANFE retornadas pelo provedor fiscal (paths relativos ao host da API)."""
from __future__ import annotations

import logging
import re
from typing import Optional

import requests

from .models import DocumentoFiscal, FiscalConfig

logger = logging.getLogger(__name__)


def focus_host_root(cfg: FiscalConfig) -> str:
    base = (cfg.focus_base_url or '').rstrip('/')
    if base.endswith('/v2'):
        base = base[:-3]
    return base.rstrip('/')


def hosts_arquivo_fiscal(cfg: FiscalConfig) -> list[str]:
    """Hosts possíveis para download de DANFE/DANFCE (API v2 e portal de arquivos)."""
    hosts: list[str] = []
    root = focus_host_root(cfg)
    if root:
        hosts.append(root)
    if cfg.ambiente == 'producao':
        hosts.append('https://api.focusnfe.com.br')
    else:
        hosts.append('https://homologacao.focusnfe.com.br')
        hosts.append('https://api.focusnfe.com.br')
    # dedupe preserving order
    seen = set()
    out = []
    for h in hosts:
        h = h.rstrip('/')
        if h and h not in seen:
            seen.add(h)
            out.append(h)
    return out


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


def _chave_numerica(doc: DocumentoFiscal) -> str:
    chave = re.sub(r'\D', '', doc.chave_acesso or '')
    return chave if len(chave) == 44 else ''


def urls_danfce_candidatas(cfg: FiscalConfig, doc: DocumentoFiscal) -> list[str]:
    """URLs do cupom NFC-e (HTML), ex.: /notas_fiscais_consumidor/Nfe{chave}.html"""
    chave = _chave_numerica(doc)
    if not chave or doc.tipo != 'nfce':
        return []
    urls = []
    for host in hosts_arquivo_fiscal(cfg):
        for prefix in ('Nfe', 'NFe'):
            urls.append(f'{host}/notas_fiscais_consumidor/{prefix}{chave}.html')
    return urls


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


def _tipo_consulta_api(doc: DocumentoFiscal) -> str:
    if doc.tipo in ('nfe', 'nfce', 'nfse'):
        return doc.tipo
    return 'nfce'


def sincronizar_caminhos_focus(doc: DocumentoFiscal, cfg: FiscalConfig) -> DocumentoFiscal:
    """Atualiza caminhos XML/DANFE a partir da consulta na API (GET /v2/{tipo}/{ref})."""
    from .focus_client import client_from_config

    if not cfg.focus_token or not doc.ref:
        return doc
    try:
        client = client_from_config(cfg)
        retorno = client.consultar(_tipo_consulta_api(doc), doc.ref)
    except Exception:
        logger.exception('Falha ao consultar documento %s na API fiscal', doc.ref)
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
    head = conteudo[:1200].lower()
    if b'<!doctype html' in head or b'<html' in head:
        return 'text/html; charset=utf-8'
    if (url or '').lower().endswith('.html'):
        return 'text/html; charset=utf-8'
    if conteudo[:5] == b'<?xml' or (conteudo[:1] == b'<' and b'<nfe' in head and b'<html' not in head):
        return 'application/xml; charset=utf-8'
    if (url or '').lower().endswith('.xml'):
        return 'application/xml; charset=utf-8'
    return 'application/octet-stream'


def personalizar_danfce_html(conteudo: bytes) -> bytes:
    """Remove marcas/logos do layout padrão do DANFCE (topo NFC-e / mapa)."""
    try:
        text = conteudo.decode('utf-8')
    except UnicodeDecodeError:
        return conteudo
    css = """
<style id="oneira-danfce-branding">
  img[src*="focus"], img[src*="Focus"], img[src*="brasil"], img[src*="Brasil"],
  img[alt*="NFC"], img[title*="NFC"], .logo, .logo-nfce, #logo, #logotipo,
  header img, .topo img, .cabecalho img, table img[width="60"], table img[height="60"] {
    display: none !important; visibility: hidden !important; height: 0 !important; width: 0 !important;
  }
  .oneira-danfce-hide { display: none !important; }
</style>
"""
    text = re.sub(
        r'<img[^>]+(?:focus|logo|nfce|brasil|sefaz)[^>]*>',
        '',
        text,
        flags=re.IGNORECASE,
    )
    if '</head>' in text:
        text = text.replace('</head>', css + '</head>', 1)
    elif re.search(r'<body[^>]*>', text, flags=re.I):
        text = re.sub(r'(<body[^>]*>)', r'\1' + css, text, count=1, flags=re.I)
    else:
        text = css + text
    return text.encode('utf-8')


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
        logger.warning('Download arquivo HTTP %s — %s', resp.status_code, url[:140])
    except requests.RequestException:
        logger.exception('Erro ao baixar arquivo: %s', url[:140])
    return None


def _baixar_com_fallbacks(cfg: FiscalConfig, urls: list[str]) -> tuple[Optional[bytes], str]:
    for url in urls:
        if not url:
            continue
        data = baixar_arquivo_focus(cfg, url)
        if data:
            return data, url
    return None, ''


def obter_conteudo_documento(
    cfg: FiscalConfig,
    doc: DocumentoFiscal,
    *,
    formato: str,
    refresh: bool = True,
) -> tuple[Optional[bytes], str, str]:
    """
    Retorna (bytes, content_type, filename).
    formato: xml | pdf  (pdf inclui DANFCE HTML para NFC-e)
    """
    if formato == 'xml':
        urls = [url_xml_documento(cfg, doc)]
        ext = 'xml'
    elif formato == 'pdf':
        urls = [url_pdf_documento(cfg, doc)] + urls_danfce_candidatas(cfg, doc)
        ext = 'pdf'
    else:
        return None, '', ''

    conteudo, url_usada = _baixar_com_fallbacks(cfg, urls)
    if (not conteudo or not conteudo.strip()) and refresh:
        sincronizar_caminhos_focus(doc, cfg)
        if formato == 'xml':
            urls = [url_xml_documento(cfg, doc)]
        else:
            urls = [url_pdf_documento(cfg, doc)] + urls_danfce_candidatas(cfg, doc)
        conteudo, url_usada = _baixar_com_fallbacks(cfg, urls)

    if not conteudo:
        return None, '', ''

    content_type = detectar_content_type(conteudo, url_usada or '')
    if formato == 'pdf' and content_type.startswith('text/html'):
        ext = 'html'
        conteudo = personalizar_danfce_html(conteudo)
    fname = f'{doc.chave_acesso or doc.ref}.{ext}'
    return conteudo, content_type, fname
