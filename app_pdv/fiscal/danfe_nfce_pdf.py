"""DANFE NFC-e (bobina 80 mm) gerado a partir do XML autorizado.

O PDF nativo da ACBrLib no Linux corrompe acentos, omite o telefone do emitente,
deixa a descrição do produto vazar para o rodapé e imprime "ACBrLibNFE Demo".
Este layout replica o DANFE que a ACBr API entregava.
"""
from __future__ import annotations

import io
import re
from pathlib import Path
from xml.etree import ElementTree as ET

from reportlab.graphics import renderPDF
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib.colors import Color, black, white
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

_NFE = '{http://www.portalfiscal.inf.br/nfe}'

PAGE_W = 226.77  # 80 mm
MARGIN = 8.0
CONTENT_W = PAGE_W - 2 * MARGIN
FONT = 'Helvetica'
FONT_BOLD = 'Helvetica-Bold'
GRAY = Color(0.85, 0.85, 0.85)

FORMAS_PAGAMENTO = {
    '01': 'Dinheiro',
    '02': 'Cheque',
    '03': 'Cartão de Crédito',
    '04': 'Cartão de Débito',
    '05': 'Crédito Loja',
    '10': 'Vale Alimentação',
    '11': 'Vale Refeição',
    '12': 'Vale Presente',
    '13': 'Vale Combustível',
    '15': 'Boleto Bancário',
    '16': 'Depósito Bancário',
    '17': 'Pagamento Instantâneo (PIX) - Dinâmico',
    '18': 'Transferência bancária, Carteira Digital',
    '19': 'Programa de fidelidade, Cashback, Crédito Virtual',
    '20': 'Pagamento Instantâneo (PIX) - Estático',
    '21': 'Crédito em Loja',
    '22': 'Pagamento Eletrônico não Informado',
    '90': 'Sem pagamento',
    '99': 'Outros',
}


def _find(parent, path: str):
    if parent is None:
        return None
    return parent.find('/'.join(f'{_NFE}{p}' for p in path.split('/')))


def _txt(parent, path: str) -> str:
    node = _find(parent, path)
    return (node.text or '').strip() if node is not None and node.text else ''


def _num(value: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _money(value) -> str:
    return f'{_num(value):,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def _qtd(value: str) -> str:
    return f'{_num(value):.2f}'.replace('.', ',')


def _fmt_doc(value: str) -> str:
    d = re.sub(r'\D', '', value or '')
    if len(d) == 14:
        return f'{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}'
    if len(d) == 11:
        return f'{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}'
    return value or ''


def _fmt_dh(value: str) -> str:
    if 'T' not in (value or ''):
        return value or ''
    data, hora = value.split('T', 1)
    partes = data.split('-')
    if len(partes) == 3:
        data = f'{partes[2]}/{partes[1]}/{partes[0]}'
    return f'{data} {hora[:8]}'


def _quebrar(texto: str, fonte: str, tamanho: float, largura: float) -> list[str]:
    palavras = (texto or '').split()
    if not palavras:
        return ['']
    linhas, atual = [], ''
    for palavra in palavras:
        teste = f'{atual} {palavra}'.strip()
        if stringWidth(teste, fonte, tamanho) <= largura:
            atual = teste
            continue
        if atual:
            linhas.append(atual)
        while stringWidth(palavra, fonte, tamanho) > largura and len(palavra) > 1:
            corte = len(palavra)
            while corte > 1 and stringWidth(palavra[:corte], fonte, tamanho) > largura:
                corte -= 1
            linhas.append(palavra[:corte])
            palavra = palavra[corte:]
        atual = palavra
    if atual:
        linhas.append(atual)
    return linhas


class _Layout:
    """Empilha blocos de cima para baixo; a altura da página sai do conteúdo."""

    def __init__(self):
        self.blocos: list[tuple[float, object]] = []

    def add(self, altura: float, desenhar):
        self.blocos.append((altura, desenhar))

    def texto(self, texto: str, tamanho: float = 7, negrito: bool = False, alinhar: str = 'center'):
        fonte = FONT_BOLD if negrito else FONT
        for linha in _quebrar(texto, fonte, tamanho, CONTENT_W):
            def desenhar(c, y, linha=linha):
                c.setFont(fonte, tamanho)
                base = y - tamanho
                if alinhar == 'center':
                    c.drawCentredString(PAGE_W / 2, base, linha)
                elif alinhar == 'right':
                    c.drawRightString(PAGE_W - MARGIN, base, linha)
                else:
                    c.drawString(MARGIN, base, linha)
            self.add(tamanho + 1.6, desenhar)

    def par(self, esquerda: str, direita: str, tamanho: float = 7, negrito: bool = False):
        fonte = FONT_BOLD if negrito else FONT
        largura_dir = stringWidth(direita, fonte, tamanho)
        linhas = _quebrar(esquerda, fonte, tamanho, CONTENT_W - largura_dir - 6)
        for i, linha in enumerate(linhas):
            def desenhar(c, y, linha=linha, mostra_dir=(i == 0)):
                c.setFont(fonte, tamanho)
                c.drawString(MARGIN, y - tamanho, linha)
                if mostra_dir:
                    c.drawRightString(PAGE_W - MARGIN, y - tamanho, direita)
            self.add(tamanho + 1.6, desenhar)

    def tracejado(self):
        def desenhar(c, y):
            c.setDash(2, 1.5)
            c.setLineWidth(0.6)
            c.line(MARGIN, y - 3, PAGE_W - MARGIN, y - 3)
            c.setDash()
        self.add(7, desenhar)

    def espaco(self, altura: float):
        self.add(altura, lambda c, y: None)

    @property
    def altura(self) -> float:
        return sum(h for h, _ in self.blocos)


def _bloco_itens(layout: _Layout, itens: list[dict]):
    tam = 6.5
    col_cod = MARGIN
    col_desc = MARGIN + 30
    col_total = PAGE_W - MARGIN
    col_unit = col_total - 36
    col_un = col_unit - 40
    col_qtd = col_un - 1
    largura_desc = (col_qtd - 21) - col_desc

    def cabecalho(c, y):
        c.setFont(FONT_BOLD, tam)
        base = y - tam
        c.drawString(col_cod, base, 'CÓDIGO')
        c.drawString(col_desc, base, 'DESCRIÇÃO')
        c.drawRightString(col_qtd, base, 'QTDE')
        c.drawString(col_un + 2, base, 'UN')
        c.drawRightString(col_unit, base, 'VL UNIT')
        c.drawRightString(col_total, base, 'VL TOTAL')
    layout.add(tam + 2, cabecalho)

    for item in itens:
        linhas = _quebrar(item['descricao'], FONT, tam, largura_desc)
        for i, linha in enumerate(linhas):
            def desenhar(c, y, linha=linha, primeira=(i == 0), item=item):
                c.setFont(FONT, tam)
                base = y - tam
                if primeira:
                    c.drawString(col_cod, base, item['codigo'][:8])
                    c.drawRightString(col_qtd, base, item['qtd'])
                    c.drawString(col_un + 2, base, item['un'][:4])
                    c.drawRightString(col_unit, base, item['vunit'])
                    c.drawRightString(col_total, base, item['vtotal'])
                c.drawString(col_desc, base, linha)
            layout.add(tam + 1.4, desenhar)


def _bloco_homologacao(layout: _Layout):
    altura = 26

    def desenhar(c, y):
        c.setFillColor(GRAY)
        c.rect(MARGIN, y - altura, CONTENT_W, altura, stroke=0, fill=1)
        c.setFillColor(black)
        c.setFont(FONT_BOLD, 7)
        c.drawCentredString(PAGE_W / 2, y - 11, 'EMITIDA EM AMBIENTE DE HOMOLOGAÇÃO')
        c.drawCentredString(PAGE_W / 2, y - 20, 'SEM VALOR FISCAL')
        c.setFillColor(black)
    layout.add(altura + 4, desenhar)


def _bloco_qrcode(layout: _Layout, url: str):
    lado = 118

    def desenhar(c, y):
        widget = QrCodeWidget(url, barLevel='M')
        x0, y0, x1, y1 = widget.getBounds()
        largura, altura = x1 - x0, y1 - y0
        desenho = Drawing(lado, lado, transform=[lado / largura, 0, 0, lado / altura, 0, 0])
        desenho.add(widget)
        renderPDF.draw(desenho, c, (PAGE_W - lado) / 2, y - lado)
    layout.add(lado + 4, desenhar)


def montar_danfe_nfce_pdf(xml_bytes: bytes) -> bytes:
    root = ET.fromstring(xml_bytes)
    inf = root.find(f'.//{_NFE}infNFe')
    if inf is None:
        raise ValueError('XML sem infNFe')

    ide = _find(inf, 'ide')
    emit = _find(inf, 'emit')
    ender = _find(emit, 'enderEmit')
    dest = _find(inf, 'dest')
    tot = _find(inf, 'total/ICMSTot')
    prot = root.find(f'.//{_NFE}infProt')
    supl = root.find(f'.//{_NFE}infNFeSupl')

    layout = _Layout()
    layout.espaco(4)

    # --- Emitente ---
    layout.texto(_txt(emit, 'xNome') or _txt(emit, 'xFant') or 'EMITENTE', 8.5, True)
    municipio = ', '.join(p for p in (_txt(ender, 'xMun'), _txt(ender, 'UF')) if p)
    endereco = ', '.join(p for p in (
        _txt(ender, 'xLgr'), _txt(ender, 'nro'), _txt(ender, 'xBairro'), municipio,
    ) if p)
    layout.texto(endereco, 6.5)
    doc_emit = _txt(emit, 'CNPJ') or _txt(emit, 'CPF')
    layout.texto(f'CNPJ: {_fmt_doc(doc_emit)} IE: {_txt(emit, "IE")}', 6.5)
    fone = re.sub(r'\D', '', _txt(ender, 'fone'))
    if fone:
        layout.texto(f'Fone: {fone}', 6.5)
    layout.tracejado()

    layout.texto('DANFE NFC-e Documento Auxiliar da', 7.5, True)
    layout.texto('Nota Fiscal de Consumidor Eletronica', 7.5, True)
    layout.espaco(3)

    tp_amb = _txt(ide, 'tpAmb')
    if tp_amb == '2':
        _bloco_homologacao(layout)
    tp_emis = _txt(ide, 'tpEmis')
    if tp_emis == '9':
        layout.texto('EMITIDA EM CONTINGÊNCIA', 7.5, True)
        layout.texto('Pendente de autorização', 6.5)
        layout.espaco(2)

    # --- Itens ---
    itens = []
    for det in inf.findall(f'{_NFE}det'):
        prod = _find(det, 'prod')
        itens.append({
            'codigo': _txt(prod, 'cProd'),
            'descricao': _txt(prod, 'xProd'),
            'qtd': _qtd(_txt(prod, 'qCom')),
            'un': _txt(prod, 'uCom'),
            'vunit': _money(_txt(prod, 'vUnCom')),
            'vtotal': _money(_txt(prod, 'vProd')),
        })
    _bloco_itens(layout, itens)
    layout.tracejado()

    # --- Totais ---
    layout.par('Qtd. Total de Itens', str(len(itens)))
    v_desc = _num(_txt(tot, 'vDesc'))
    v_frete = _num(_txt(tot, 'vFrete'))
    v_outro = _num(_txt(tot, 'vOutro'))
    if v_desc or v_frete or v_outro:
        layout.par('Valor Total R$', _money(_txt(tot, 'vProd')))
        if v_desc:
            layout.par('Desconto R$', _money(v_desc))
        if v_frete:
            layout.par('Frete R$', _money(v_frete))
        if v_outro:
            layout.par('Outras Despesas R$', _money(v_outro))
    layout.par('Valor a Pagar R$', _money(_txt(tot, 'vNF')), 10, True)

    layout.par('FORMA PAGAMENTO', 'VALOR PAGO R$', 6.5)
    troco = 0.0
    for pag in inf.findall(f'{_NFE}pag'):
        for det_pag in pag.findall(f'{_NFE}detPag'):
            t_pag = _txt(det_pag, 'tPag')
            nome = FORMAS_PAGAMENTO.get(t_pag, f'Pagamento {t_pag}')
            layout.par(nome, _money(_txt(det_pag, 'vPag')), 6.5)
        troco += _num(_txt(pag, 'vTroco'))
    layout.par('Troco R$', _money(troco), 6.5)
    layout.tracejado()

    # --- Consulta ---
    layout.texto('Consulte pela Chave de Acesso em', 7.5, True)
    url_chave = _txt(supl, 'urlChave') or 'www.fazenda.rj.gov.br/nfce/consulta'
    layout.texto(url_chave, 6.5)
    chave = (inf.get('Id') or '').replace('NFe', '')
    layout.texto(' '.join(chave[i:i + 4] for i in range(0, len(chave), 4)), 6.5)
    layout.espaco(2)

    # --- Consumidor ---
    doc_dest = _txt(dest, 'CPF') or _txt(dest, 'CNPJ') or _txt(dest, 'idEstrangeiro')
    if doc_dest:
        rotulo = 'CPF' if _txt(dest, 'CPF') else ('CNPJ' if _txt(dest, 'CNPJ') else 'ID')
        layout.texto(f'CONSUMIDOR {rotulo}: {_fmt_doc(doc_dest)}', 6.5, True)
        nome_dest = _txt(dest, 'xNome')
        if nome_dest:
            layout.texto(nome_dest, 6.5)
    else:
        layout.texto('CONSUMIDOR NÃO IDENTIFICADO', 6.5)

    numero = _txt(ide, 'nNF').zfill(9)
    serie = _txt(ide, 'serie').zfill(3)
    layout.texto(f'NFCe n. {numero} Série {serie} {_fmt_dh(_txt(ide, "dhEmi"))}', 7, True)
    layout.espaco(8)

    # --- Autorização ---
    layout.texto('Via Consumidor', 9.5, True)
    n_prot = _txt(prot, 'nProt')
    if n_prot:
        layout.texto(f'Protocolo de Autorização: {n_prot}', 6.5)
        layout.texto(f'Data de Autorização: {_fmt_dh(_txt(prot, "dhRecbto"))}', 6.5)
    layout.espaco(3)
    qr = _txt(supl, 'qrCode')
    if qr:
        _bloco_qrcode(layout, qr)
    layout.tracejado()

    v_trib = _num(_txt(tot, 'vTotTrib'))
    trib = _money(v_trib) if v_trib else '-----'
    layout.texto(f'Tributos Totais Incidentes (Lei Federal 12.741/2012): R$ {trib}', 6, alinhar='left')
    layout.espaco(6)

    altura = layout.altura + 6
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(PAGE_W, altura))
    c.setTitle(f'NFC-e {numero}')
    c.setFillColor(white)
    c.rect(0, 0, PAGE_W, altura, stroke=0, fill=1)
    c.setFillColor(black)
    y = altura - 3
    for h, desenhar in layout.blocos:
        desenhar(c, y)
        y -= h
    c.showPage()
    c.save()
    return buf.getvalue()


def regenerar_pdf_de_xml(caminho_xml: str | Path, caminho_pdf: str | Path) -> bool:
    xml_path, pdf_path = Path(caminho_xml), Path(caminho_pdf)
    if not xml_path.is_file():
        return False
    xml_bytes = xml_path.read_bytes()
    if b'<mod>65</mod>' not in xml_bytes:
        return False
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(montar_danfe_nfce_pdf(xml_bytes))
    return True
