"""URLs de XML/DANFE retornadas pelo provedor fiscal (paths relativos ao host da API)."""
from __future__ import annotations

import logging
import re
import unicodedata
import zlib
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
        if 'oneirasistemas.com.br' in p or 'lincebrasilsistemas.com.br' in p or 'localhost' in p:
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
  .oneira-danfce-titulo-nfce { display: none !important; }
  .oneira-danfce-emitente-l1, .oneira-danfce-emitente-l2 {
    font-weight: 700 !important; font-style: normal !important;
  }
</style>
"""
    text = re.sub(
        r'<img[^>]+(?:focus|logo|nfce|brasil|sefaz)[^>]*>',
        '',
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r'(<(?:div|span|p|td|font|b|strong|i|em)[^>]*>)\s*NFC-e\s*(</(?:div|span|p|td|font|b|strong|i|em)>)',
        r'\1\2',
        text,
        count=3,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r'>\s*NFC-e\s*<',
        '><',
        text,
        count=3,
        flags=re.IGNORECASE,
    )
    # Primeiras linhas do emitente (razão social + CNPJ/IE) em negrito
    linhas_marcadas = 0
    for tag in ('div', 'span', 'p', 'td', 'font'):
        if linhas_marcadas >= 2:
            break
        pattern = rf'(<{tag}[^>]*>)([^<]{{8,180}})(</{tag}>)'

        def _bold_emitente(match):
            nonlocal linhas_marcadas
            inner = match.group(2).strip()
            upper = inner.upper()
            if linhas_marcadas >= 2:
                return match.group(0)
            if 'CNPJ' in upper or 'LTDA' in upper or 'ME ' in upper or ' EIRELI' in upper:
                linhas_marcadas += 1
                return (
                    f'{match.group(1)}'
                    f'<span class="oneira-danfce-emitente-l{linhas_marcadas}">{inner}</span>'
                    f'{match.group(3)}'
                )
            return match.group(0)

        text, n = re.subn(pattern, _bold_emitente, text, count=4, flags=re.IGNORECASE)
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


def id_documento_acbr(doc: DocumentoFiscal) -> str:
    ret = doc.payload_retorno if isinstance(doc.payload_retorno, dict) else {}
    doc_id = str(ret.get('id') or '').strip()
    if doc_id.startswith(('nfc_', 'nfe_')):
        return doc_id
    return ''


def preencher_caminhos_acbr(doc: DocumentoFiscal) -> None:
    """Aponta XML e DANFCE para a ACBr quando a nota já foi autorizada."""
    doc_id = id_documento_acbr(doc)
    if not doc_id or doc.status not in ('autorizado', 'cancelado'):
        return
    tipo = 'nfe' if doc.tipo == 'nfe' or doc_id.startswith('nfe_') else 'nfce'
    fields = []
    if not (doc.caminho_xml or '').strip():
        doc.caminho_xml = f'acbr:{tipo}/{doc_id}/xml'
        fields.append('caminho_xml')
    if not (doc.caminho_pdf or '').strip():
        doc.caminho_pdf = f'acbr:{tipo}/{doc_id}/pdf'
        fields.append('caminho_pdf')
    if fields:
        fields.append('atualizado_em')
        doc.save(update_fields=fields)


def _baixar_acbr(cfg: FiscalConfig, caminho: str) -> Optional[bytes]:
    from .acbr_client import AcbrApiError, client_from_fiscal_config

    resto = (caminho or '')[5:]
    if not resto:
        return None
    accept = 'application/pdf' if resto.endswith('/pdf') else 'application/xml, text/xml, */*'
    client = client_from_fiscal_config(cfg)
    if not client.credenciais_ok():
        return None
    try:
        return client.baixar_arquivo(resto, accept=accept)
    except AcbrApiError:
        logger.exception('Falha ao baixar arquivo ACBr %s', resto)
        return None


_ALVO_AMBIENTE = 'NOTA FISCAL EMITIDA EM AMBIENTE DE HOMOLOGACAO SEM VALOR FISCAL'
_OP_TEXTO_PDF = re.compile(r'BT [0-9.]+ [0-9.]+ Td \(((?:\\.|[^\\)])*)\) Tj')
_STREAM_FLATE = re.compile(
    rb'(<<[^>]*?/Length\s+)(\d+)([^>]*?>>\s*stream\r?\n)(.*?)(\r?\nendstream)',
    re.S,
)


def _sem_acento(texto: str) -> str:
    base = unicodedata.normalize('NFD', texto or '')
    return ''.join(c for c in base if unicodedata.category(c) != 'Mn')


def _norm_ambiente(texto: str) -> str:
    texto = _sem_acento(texto).upper()
    texto = re.sub(r'[^A-Z0-9 ]+', ' ', texto)
    return re.sub(r'\s+', ' ', texto).strip()


def _classe_texto_danfe(texto: str) -> str:
    """banner: faixa de ambiente. item: descricao trocada pela frase de homologacao."""
    n = _norm_ambiente(texto)
    if len(n) < 8:
        return 'manter'
    if n == 'SEM VALOR FISCAL' or n.startswith('EMITIDA EM AMBIENTE'):
        return 'banner'
    if n.startswith('NOTA FISCAL EMITIDA EM AMBIENTE'):
        return 'banner'
    if n in _ALVO_AMBIENTE:
        return 'item'
    return 'manter'


def _quebrar_descricao(texto: str, largura: int = 19) -> list[str]:
    texto = re.sub(r'\s+', ' ', (texto or '').strip())
    if not texto:
        return []
    linhas = []
    while texto:
        if len(texto) <= largura:
            linhas.append(texto)
            break
        corte = texto.rfind(' ', 0, largura + 1)
        if corte <= 0:
            corte = largura
        linhas.append(texto[:corte].strip())
        texto = texto[corte:].strip()
    return linhas


def _pdf_literal(texto: str) -> str:
    texto = texto.encode('latin-1', errors='ignore').decode('latin-1')
    return texto.replace('\\', r'\\').replace('(', r'\(').replace(')', r'\)')


def _pdf_unescape(texto: str) -> str:
    return re.sub(r'\\([\\()])', r'\1', texto)


def _descricao_primeiro_item(doc: DocumentoFiscal) -> str:
    envio = doc.payload_envio if isinstance(doc.payload_envio, dict) else {}
    itens = envio.get('items') or []
    if itens:
        nome = str(itens[0].get('descricao') or '').strip()
        if nome and _classe_texto_danfe(nome) == 'manter':
            return nome
    produto = getattr(doc, 'produto_avulso', None)
    if produto is not None:
        return (getattr(produto, 'nome_venda', None) or getattr(produto, 'nome', None) or '').strip()
    return ''


def _limpar_stream_danfe(data: bytes, descricao: str) -> tuple[bytes, bool]:
    texto = data.decode('latin-1')
    matches = list(_OP_TEXTO_PDF.finditer(texto))
    classes = [_classe_texto_danfe(_pdf_unescape(m.group(1))) for m in matches]
    if 'banner' not in classes and 'item' not in classes:
        return data, False
    linhas = _quebrar_descricao(descricao)
    item_i = 0
    partes = []
    cursor = 0
    for match, classe in zip(matches, classes):
        partes.append(texto[cursor:match.start(1)])
        if classe == 'item':
            linha = linhas[item_i] if item_i < len(linhas) else ''
            item_i += 1
            partes.append(_pdf_literal(linha))
        elif classe == 'banner':
            partes.append('')
        else:
            partes.append(match.group(1))
        cursor = match.end(1)
    partes.append(texto[cursor:])
    return ''.join(partes).encode('latin-1'), True


def _limpar_prefixo_pdf(prefixo: bytes, descricao: str) -> tuple[bytes, bool]:
    mudou = False

    def _trocar(match: re.Match) -> bytes:
        nonlocal mudou
        bloco_ini = match.group(0)
        if b'FlateDecode' not in bloco_ini:
            return bloco_ini
        try:
            data = zlib.decompress(match.group(4))
        except zlib.error:
            return bloco_ini
        novo, alterou = _limpar_stream_danfe(data, descricao)
        if not alterou:
            return bloco_ini
        mudou = True
        comp = zlib.compress(novo)
        return match.group(1) + str(len(comp)).encode() + match.group(3) + comp + match.group(5)

    return _STREAM_FLATE.sub(_trocar, prefixo), mudou


def _remontar_pdf(prefixo: bytes, pdf_original: bytes) -> bytes:
    objetos = list(re.finditer(rb'(?m)^(\d+) (\d+) obj\b', prefixo))
    entradas = {0: (0, 65535, 'f')}
    tamanho = 1
    for match in objetos:
        num = int(match.group(1))
        entradas[num] = (match.start(), int(match.group(2)), 'n')
        tamanho = max(tamanho, num + 1)
    linhas = [f'xref\n0 {tamanho}\n']
    for i in range(tamanho):
        off, gen, flag = entradas.get(i, (0, 65535, 'f'))
        linhas.append(f'{off:010d} {gen:05d} {flag} \n')
    mi = re.search(rb'trailer\s*<<(.+?)>>', pdf_original, re.S)
    interno = (mi.group(1) if mi else b'\n/Root 1 0 R\n')
    interno = re.sub(rb'/Size\s+\d+', f'/Size {tamanho}'.encode(), interno)
    if b'/Size' not in interno:
        interno = f'\n/Size {tamanho}'.encode() + interno
    xref_pos = len(prefixo)
    return (
        prefixo
        + ''.join(linhas).encode()
        + b'trailer\n<<'
        + interno
        + b'>>\nstartxref\n'
        + str(xref_pos).encode()
        + b'\n%%EOF'
    )


def ocultar_ambiente_danfe(pdf: bytes, descricao: str = '') -> bytes:
    """Tira do DANFCE a faixa de homologação/produção. O XML enviado à SEFAZ não muda."""
    if not pdf or not pdf.startswith(b'%PDF'):
        return pdf
    idx = pdf.rfind(b'\nxref\n')
    if idx < 0:
        return pdf
    prefixo, mudou = _limpar_prefixo_pdf(pdf[:idx + 1], descricao)
    if not mudou:
        return pdf
    return _remontar_pdf(prefixo, pdf)


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
    if formato not in ('xml', 'pdf'):
        return None, '', ''
    if refresh:
        preencher_caminhos_acbr(doc)
    caminho = (doc.caminho_xml if formato == 'xml' else doc.caminho_pdf) or ''
    if caminho.startswith('acbr:'):
        conteudo = _baixar_acbr(cfg, caminho)
        if not conteudo:
            return None, '', ''
        content_type = detectar_content_type(conteudo, caminho)
        ext = 'xml' if formato == 'xml' else 'pdf'
        if formato == 'pdf' and conteudo.startswith(b'%PDF'):
            conteudo = ocultar_ambiente_danfe(conteudo, _descricao_primeiro_item(doc))
        elif formato == 'pdf' and content_type.startswith('text/html'):
            ext = 'html'
            conteudo = personalizar_danfce_html(conteudo)
        fname = f'{doc.chave_acesso or doc.ref}.{ext}'
        return conteudo, content_type, fname

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
    if formato == 'pdf' and conteudo.startswith(b'%PDF'):
        conteudo = ocultar_ambiente_danfe(conteudo, _descricao_primeiro_item(doc))
    elif formato == 'pdf' and content_type.startswith('text/html'):
        ext = 'html'
        conteudo = personalizar_danfce_html(conteudo)
    fname = f'{doc.chave_acesso or doc.ref}.{ext}'
    return conteudo, content_type, fname
