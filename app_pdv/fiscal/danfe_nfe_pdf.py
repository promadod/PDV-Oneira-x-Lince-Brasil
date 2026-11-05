"""DANFE NF-e (A4 retrato) no layout padrão SEFAZ.

Gera a partir do XML autorizado. O DANFE NFC-e (bobina 80 mm) não se aplica ao modelo 55.
"""
from __future__ import annotations

import io
import re
from pathlib import Path
from xml.etree import ElementTree as ET

from reportlab.graphics.barcode import code128
from reportlab.lib.colors import black, white, Color
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from .danfe_nfce_pdf import (
    FONT,
    FONT_BOLD,
    _NFE,
    _descricao_item,
    _find,
    _fmt_dh,
    _fmt_doc,
    _money,
    _qtd,
    _quebrar,
    _txt,
)

W, H = A4
ML, MR, MT, MB = 10.0, 10.0, 8.0, 10.0
INNER = W - ML - MR
CINZA = Color(0.88, 0.88, 0.88)


def _folha_branca(c):
    c.setFillColor(white)
    c.rect(0, 0, W, H, stroke=0, fill=1)
    c.setFillColor(black)
    c.setStrokeColor(black)


def _caixa(c, x, y, w, h, *, fill=None):
    c.setLineWidth(0.4)
    if fill is not None:
        c.setFillColor(fill)
        c.rect(x, y - h, w, h, stroke=1, fill=1)
        c.setFillColor(black)
    else:
        c.rect(x, y - h, w, h)


def _fit(texto: str, fonte: str, tamanho: float, largura: float) -> str:
    t = (texto or '').strip()
    if not t or stringWidth(t, fonte, tamanho) <= largura:
        return t
    ell = '...'
    while t and stringWidth(t + ell, fonte, tamanho) > largura:
        t = t[:-1]
    return (t + ell) if t else ''


def _texto(c, x, y, w, texto, fonte, tamanho, alinhar='L'):
    t = _fit(texto, fonte, tamanho, max(w - 4, 4))
    c.setFont(fonte, tamanho)
    if alinhar == 'R':
        c.drawRightString(x + w - 2, y, t)
    elif alinhar == 'C':
        c.drawCentredString(x + w / 2, y, t)
    else:
        c.drawString(x + 2, y, t)


def _celula(c, x, y, w, h, rotulo, valor, *, alinhar='L', fill=None, tam_valor=8):
    _caixa(c, x, y, w, h, fill=fill)
    c.setFont(FONT, 4.5)
    c.drawString(x + 2, y - 6, (rotulo or '').upper())
    _texto(c, x, y - h + 5, w, valor or '', FONT_BOLD if alinhar == 'R' else FONT, tam_valor, alinhar)


def _faixa(c, x, y, w, titulo, h=9):
    _caixa(c, x, y, w, h)
    c.setFont(FONT_BOLD, 6)
    c.drawString(x + 2, y - 7, (titulo or '').upper())
    return h


def _chave_grupos(chave: str) -> str:
    d = re.sub(r'\D', '', chave or '')
    return ' '.join(d[i:i + 4] for i in range(0, len(d), 4))


def _fmt_nnf(n: str) -> str:
    d = re.sub(r'\D', '', n or '').zfill(9)
    return f'{d[:3]}.{d[3:6]}.{d[6:]}'


def _fmt_cep(value: str) -> str:
    d = re.sub(r'\D', '', value or '')
    if len(d) == 8:
        return f'{d[:5]}-{d[5:]}'
    return value or ''


def _fmt_fone(value: str) -> str:
    d = re.sub(r'\D', '', value or '')
    if len(d) == 11:
        return f'({d[:2]}){d[2:7]}-{d[7:]}'
    if len(d) == 10:
        return f'({d[:2]}){d[2:6]}-{d[6:]}'
    return value or ''


def _data_hora(dh: str) -> tuple[str, str]:
    txt = _fmt_dh(dh)
    if ' ' in txt:
        a, b = txt.split(' ', 1)
        return a, b[:8]
    return txt, ''


def _imposto_grupo(det, nome: str):
    imposto = _find(det, 'imposto')
    if imposto is None:
        return None
    return _find(imposto, nome)


def _cst_item(det) -> str:
    icms = _imposto_grupo(det, 'ICMS')
    if icms is None:
        return ''
    for filho in list(icms):
        cst = (filho.findtext(f'{_NFE}CST') or filho.findtext(f'{_NFE}CSOSN') or '').strip()
        if cst:
            orig = (filho.findtext(f'{_NFE}orig') or '').strip()
            return f'{orig}{cst}' if orig else cst
    return ''


def _txt_icms(det, tag: str) -> str:
    icms = _imposto_grupo(det, 'ICMS')
    if icms is None:
        return ''
    for filho in list(icms):
        val = (filho.findtext(f'{_NFE}{tag}') or '').strip()
        if val:
            return val
    return ''


def _txt_ipi(det, tag: str) -> str:
    ipi = _imposto_grupo(det, 'IPI')
    if ipi is None:
        return ''
    for filho in list(ipi):
        val = (filho.findtext(f'{_NFE}{tag}') or '').strip()
        if val:
            return val
    return ''


def _montar_itens(inf) -> list[dict]:
    itens = []
    for det in inf.findall(f'{_NFE}det'):
        prod = _find(det, 'prod')
        itens.append({
            'codigo': _txt(prod, 'cProd'),
            'descricao': _descricao_item(det, prod),
            'ncm': _txt(prod, 'NCM'),
            'cst': _cst_item(det),
            'cfop': _txt(prod, 'CFOP'),
            'un': _txt(prod, 'uCom') or _txt(prod, 'uTrib'),
            'qtd': _qtd(_txt(prod, 'qCom')),
            'vunit': _money(_txt(prod, 'vUnCom')),
            'vtotal': _money(_txt(prod, 'vProd')),
            'vdesc': _money(_txt(prod, 'vDesc')),
            'vbc': _money(_txt_icms(det, 'vBC')),
            'vicms': _money(_txt_icms(det, 'vICMS')),
            'vipi': _money(_txt_ipi(det, 'vIPI')),
            'picms': _money(_txt_icms(det, 'pICMS')),
            'pipi': _money(_txt_ipi(det, 'pIPI')),
        })
    return itens


def _desenhar_barras(c, chave: str, x: float, y_base: float, max_w: float, altura: float):
    digits = re.sub(r'\D', '', chave or '')
    if not digits:
        return
    try:
        probe = code128.Code128(digits, barHeight=altura, barWidth=1.0, humanReadable=False)
        bw = ((max_w * 0.96) / probe.width) if probe.width else 0.4
        barra = code128.Code128(digits, barHeight=altura, barWidth=bw, humanReadable=False)
        if barra.width > max_w and barra.width:
            barra = code128.Code128(
                digits, barHeight=altura, barWidth=bw * max_w / barra.width, humanReadable=False,
            )
        x0 = x + max(0, (max_w - barra.width) / 2.0)
        barra.drawOn(c, x0, y_base)
    except Exception:
        c.setFont(FONT, 6)
        c.drawCentredString(x + max_w / 2, y_base + altura / 2, digits)


def montar_danfe_nfe_pdf(xml_bytes: bytes) -> bytes:
    root = ET.fromstring(xml_bytes)
    inf = root.find(f'.//{_NFE}infNFe')
    if inf is None:
        raise ValueError('XML sem infNFe')

    ide = _find(inf, 'ide')
    emit = _find(inf, 'emit')
    ender = _find(emit, 'enderEmit')
    dest = _find(inf, 'dest')
    ender_dest = _find(dest, 'enderDest') if dest is not None else None
    tot = _find(inf, 'total/ICMSTot')
    transp = _find(inf, 'transp')
    transporta = _find(transp, 'transporta') if transp is not None else None
    veic = _find(transp, 'veicTransp') if transp is not None else None
    vol = _find(transp, 'vol') if transp is not None else None
    prot = root.find(f'.//{_NFE}infProt')
    inf_adic = _find(inf, 'infAdic')

    chave = (inf.get('Id') or '').replace('NFe', '')
    numero = _txt(ide, 'nNF')
    nnf = _fmt_nnf(numero)
    serie = _txt(ide, 'serie').zfill(3)
    tp_nf = _txt(ide, 'tpNF') or '1'
    natureza = _txt(ide, 'natOp')
    dh_emi = _txt(ide, 'dhEmi')
    dh_sai = _txt(ide, 'dhSaiEnt') or dh_emi
    data_emi, hora_emi = _data_hora(dh_emi)
    data_sai, hora_sai = _data_hora(dh_sai)
    n_prot = _txt(prot, 'nProt')
    dh_prot_d, dh_prot_h = _data_hora(_txt(prot, 'dhRecbto'))
    v_nf = _money(_txt(tot, 'vNF'))
    nome_emit = _txt(emit, 'xNome') or _txt(emit, 'xFant') or 'EMITENTE'
    nome_dest = _txt(dest, 'xNome') or 'NÃO INFORMADO'
    cnpj_emit = _fmt_doc(_txt(emit, 'CNPJ') or _txt(emit, 'CPF'))
    ie_emit = _txt(emit, 'IE')
    ie_st = _txt(emit, 'IEST')
    fone_emit = _fmt_fone(_txt(ender, 'fone'))

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setPageCompression(0)
    c.setTitle(f'DANFE NF-e {nnf}')
    c.setAuthor('Oneira PDV')
    _folha_branca(c)

    y = H - MT
    # --- Canhoto ---
    h_can = 42
    w_nf = 108
    _caixa(c, ML, y, INNER - w_nf, 18)
    c.setFont(FONT, 5.5)
    c.drawString(ML + 3, y - 8, _fit(
        f'RECEBEMOS DE {nome_emit} OS PRODUTOS / SERVIÇOS CONSTANTES DA NOTA FISCAL INDICADO AO LADO',
        FONT, 5.5, INNER - w_nf - 8,
    ))
    c.drawString(ML + 3, y - 16, _fit(
        f'EMISSÃO: {data_emi} - DEST. / REM.: {nome_dest} - VALOR TOTAL: R$ {v_nf}',
        FONT, 5.5, INNER - w_nf - 8,
    ))
    _celula(c, ML, y - 18, 90, h_can - 18, 'DATA DE RECEBIMENTO', '')
    _celula(c, ML + 90, y - 18, INNER - w_nf - 90, h_can - 18, 'IDENTIFICAÇÃO E ASSINATURA DO RECEBEDOR', '')
    _caixa(c, ML + INNER - w_nf, y, w_nf, h_can)
    c.setFont(FONT_BOLD, 9)
    c.drawCentredString(ML + INNER - w_nf / 2, y - 12, 'NF-e')
    c.setFont(FONT_BOLD, 8)
    c.drawCentredString(ML + INNER - w_nf / 2, y - 24, f'Nº {nnf}')
    c.drawCentredString(ML + INNER - w_nf / 2, y - 36, f'SÉRIE {serie}')
    y -= h_can + 3
    c.setDash(1.5, 1.5)
    c.setLineWidth(0.4)
    c.line(ML, y + 1, ML + INNER, y + 1)
    c.setDash()
    y -= 4

    # --- Identificação do emitente / DANFE / chave ---
    h_cab = 88
    w_emit = INNER * 0.42
    w_meio = INNER * 0.22
    w_dir = INNER - w_emit - w_meio
    _caixa(c, ML, y, w_emit, h_cab)
    c.setFont(FONT, 4.5)
    c.drawString(ML + 3, y - 7, 'IDENTIFICAÇÃO DO EMITENTE')
    c.setFont(FONT_BOLD, 8)
    ty = y - 18
    for linha in _quebrar(nome_emit, FONT_BOLD, 8, w_emit - 8)[:2]:
        c.drawCentredString(ML + w_emit / 2, ty, linha)
        ty -= 10
    cep = _fmt_cep(_txt(ender, 'CEP'))
    end_linhas = [
        ', '.join(p for p in (_txt(ender, 'xLgr'), _txt(ender, 'nro')) if p),
        ' - '.join(p for p in (_txt(ender, 'xBairro'), f'CEP:{cep}' if cep else '', _txt(ender, 'xMun'), _txt(ender, 'UF')) if p),
    ]
    if fone_emit:
        end_linhas.append(f'TEL: {fone_emit}')
    c.setFont(FONT, 6.5)
    for linha in end_linhas:
        for pedaco in _quebrar(linha, FONT, 6.5, w_emit - 10)[:2]:
            c.drawCentredString(ML + w_emit / 2, ty, pedaco)
            ty -= 9

    _caixa(c, ML + w_emit, y, w_meio, h_cab)
    cx = ML + w_emit + w_meio / 2
    c.setFont(FONT_BOLD, 11)
    c.drawCentredString(cx, y - 14, 'DANFE')
    c.setFont(FONT_BOLD, 5.5)
    c.drawCentredString(cx, y - 24, 'DOCUMENTO AUXILIAR DA')
    c.drawCentredString(cx, y - 31, 'NOTA FISCAL ELETRÔNICA')
    c.setFont(FONT, 6)
    c.drawString(ML + w_emit + 6, y - 44, '0 - ENTRADA')
    c.drawString(ML + w_emit + 6, y - 53, '1 - SAÍDA')
    _caixa(c, ML + w_emit + w_meio - 22, y - 38, 16, 16)
    c.setFont(FONT_BOLD, 11)
    c.drawCentredString(ML + w_emit + w_meio - 14, y - 50, tp_nf)
    c.setFont(FONT_BOLD, 7)
    c.drawCentredString(cx, y - 68, f'Nº {nnf}   fl. 1 /1')
    c.drawCentredString(cx, y - 80, f'SÉRIE {serie}')

    _caixa(c, ML + w_emit + w_meio, y, w_dir, h_cab)
    bar_w = w_dir - 8
    _desenhar_barras(c, chave, ML + w_emit + w_meio + 4, y - 38, bar_w, 28)
    c.setFont(FONT, 4.5)
    c.drawString(ML + w_emit + w_meio + 4, y - 46, 'CHAVE DE ACESSO')
    c.setFont(FONT, 6)
    c.drawCentredString(ML + w_emit + w_meio + w_dir / 2, y - 56, _chave_grupos(chave))
    c.setFont(FONT, 5)
    c.drawCentredString(ML + w_emit + w_meio + w_dir / 2, y - 68, 'Consulta de autenticidade no portal nacional da NF-e')
    c.drawCentredString(ML + w_emit + w_meio + w_dir / 2, y - 76, 'www.nfe.fazenda.gov.br/portal')
    c.drawCentredString(ML + w_emit + w_meio + w_dir / 2, y - 84, 'ou no site da Sefaz Autorizadora')
    y -= h_cab

    # Natureza + protocolo
    h_nat = 22
    w_nat = INNER * 0.62
    _celula(c, ML, y, w_nat, h_nat, 'NATUREZA DE OPERAÇÃO', natureza, tam_valor=8)
    _celula(
        c, ML + w_nat, y, INNER - w_nat, h_nat,
        'PROTOCOLO DE AUTORIZAÇÃO DE USO',
        f'{n_prot} {dh_prot_d} {dh_prot_h}'.strip(),
        tam_valor=7,
    )
    y -= h_nat

    h_ie = 20
    w1, w2 = INNER * 0.34, INNER * 0.33
    _celula(c, ML, y, w1, h_ie, 'INSCRIÇÃO ESTADUAL', ie_emit)
    _celula(c, ML + w1, y, w2, h_ie, 'INSCRIÇÃO ESTADUAL DO SUBST. TRIB.', ie_st)
    _celula(c, ML + w1 + w2, y, INNER - w1 - w2, h_ie, 'CNPJ / CPF', cnpj_emit)
    y -= h_ie

    # Destinatário
    y -= _faixa(c, ML, y, INNER, 'DESTINATÁRIO / REMETENTE')
    h_d = 20
    doc_dest = _fmt_doc(_txt(dest, 'CNPJ') or _txt(dest, 'CPF'))
    _celula(c, ML, y, INNER * 0.62, h_d, 'NOME / RAZÃO SOCIAL', nome_dest, tam_valor=7.5)
    _celula(c, ML + INNER * 0.62, y, INNER * 0.22, h_d, 'CNPJ / CPF', doc_dest, alinhar='R', tam_valor=7)
    _celula(c, ML + INNER * 0.84, y, INNER * 0.16, h_d, 'DATA DA EMISSÃO', data_emi, alinhar='C', tam_valor=7)
    y -= h_d
    end_dest = ', '.join(p for p in (_txt(ender_dest, 'xLgr'), _txt(ender_dest, 'nro')) if p)
    _celula(c, ML, y, INNER * 0.46, h_d, 'ENDEREÇO', end_dest, tam_valor=7)
    _celula(c, ML + INNER * 0.46, y, INNER * 0.20, h_d, 'BAIRRO / DISTRITO', _txt(ender_dest, 'xBairro'), tam_valor=7)
    _celula(c, ML + INNER * 0.66, y, INNER * 0.18, h_d, 'CEP', _fmt_cep(_txt(ender_dest, 'CEP')), alinhar='C', tam_valor=7)
    _celula(c, ML + INNER * 0.84, y, INNER * 0.16, h_d, 'DATA SAÍDA / ENTRADA', data_sai, alinhar='C', tam_valor=7)
    y -= h_d
    _celula(c, ML, y, INNER * 0.32, h_d, 'MUNICÍPIO', _txt(ender_dest, 'xMun'), tam_valor=7)
    _celula(c, ML + INNER * 0.32, y, INNER * 0.16, h_d, 'FONE / FAX', _fmt_fone(_txt(ender_dest, 'fone')), tam_valor=7)
    _celula(c, ML + INNER * 0.48, y, INNER * 0.08, h_d, 'UF', _txt(ender_dest, 'UF'), alinhar='C', tam_valor=8)
    _celula(c, ML + INNER * 0.56, y, INNER * 0.28, h_d, 'INSCRIÇÃO ESTADUAL', _txt(dest, 'IE'), tam_valor=7)
    _celula(c, ML + INNER * 0.84, y, INNER * 0.16, h_d, 'HORA DA SAÍDA', hora_sai, alinhar='C', tam_valor=7)
    y -= h_d

    # Cálculo do imposto (antes dos itens, como o DANFE padrão)
    y -= _faixa(c, ML, y, INNER, 'CÁLCULO DO IMPOSTO')
    h_imp = 22
    cols5 = [INNER * 0.20, INNER * 0.16, INNER * 0.20, INNER * 0.18, INNER * 0.26]
    labs1 = [
        ('BASE DE CÁLCULO DO ICMS', _txt(tot, 'vBC')),
        ('VALOR DO ICMS', _txt(tot, 'vICMS')),
        ('BASE CÁLC. ICMS SUBST.', _txt(tot, 'vBCST')),
        ('VALOR DO ICMS SUBST.', _txt(tot, 'vST')),
        ('VALOR TOTAL DOS PRODUTOS', _txt(tot, 'vProd')),
    ]
    x = ML
    for i, (lab, val) in enumerate(labs1):
        _celula(c, x, y, cols5[i], h_imp, lab, _money(val), alinhar='R', tam_valor=8)
        x += cols5[i]
    y -= h_imp
    cols6 = [INNER * 0.15, INNER * 0.14, INNER * 0.14, INNER * 0.16, INNER * 0.15, INNER * 0.26]
    labs2 = [
        ('VALOR DO FRETE', _txt(tot, 'vFrete')),
        ('VALOR DO SEGURO', _txt(tot, 'vSeg')),
        ('DESCONTO', _txt(tot, 'vDesc')),
        ('OUTRAS DESP. ACESS.', _txt(tot, 'vOutro')),
        ('VALOR DO IPI', _txt(tot, 'vIPI')),
        ('VALOR TOTAL DA NOTA', _txt(tot, 'vNF')),
    ]
    x = ML
    for i, (lab, val) in enumerate(labs2):
        destaque = i == 5
        _celula(
            c, x, y, cols6[i], h_imp, lab, _money(val), alinhar='R',
            fill=CINZA if destaque else None, tam_valor=9 if destaque else 8,
        )
        x += cols6[i]
    y -= h_imp

    # Transportador
    y -= _faixa(c, ML, y, INNER, 'TRANSPORTADOR / VOLUMES TRANSPORTADOS')
    h_t = 20
    mod_frete = _txt(transp, 'modFrete')
    nomes_frete = {
        '0': '0 - REMETENTE', '1': '1 - DESTINATÁRIO',
        '2': '2 - TERCEIROS', '3': '3 - PRÓPRIO REMET.',
        '4': '4 - PRÓPRIO DEST.', '9': '9 - SEM FRETE',
    }
    _celula(c, ML, y, INNER * 0.40, h_t, 'RAZÃO SOCIAL', _txt(transporta, 'xNome'), tam_valor=7)
    _celula(c, ML + INNER * 0.40, y, INNER * 0.18, h_t, 'FRETE POR CONTA', nomes_frete.get(mod_frete, mod_frete), tam_valor=6.5)
    _celula(c, ML + INNER * 0.58, y, INNER * 0.10, h_t, 'CÓDIGO ANTT', _txt(transp, 'RNTC') or _txt(veic, 'RNTC'), tam_valor=7)
    _celula(c, ML + INNER * 0.68, y, INNER * 0.12, h_t, 'PLACA DO VEÍCULO', _txt(veic, 'placa'), tam_valor=7)
    _celula(c, ML + INNER * 0.80, y, INNER * 0.05, h_t, 'UF', _txt(veic, 'UF'), alinhar='C', tam_valor=7)
    _celula(c, ML + INNER * 0.85, y, INNER * 0.15, h_t, 'CNPJ / CPF', _fmt_doc(_txt(transporta, 'CNPJ') or _txt(transporta, 'CPF')), tam_valor=6.5)
    y -= h_t
    _celula(c, ML, y, INNER * 0.40, h_t, 'ENDEREÇO', _txt(transporta, 'xEnder'), tam_valor=7)
    _celula(c, ML + INNER * 0.40, y, INNER * 0.28, h_t, 'MUNICÍPIO', _txt(transporta, 'xMun'), tam_valor=7)
    _celula(c, ML + INNER * 0.68, y, INNER * 0.05, h_t, 'UF', _txt(transporta, 'UF'), alinhar='C', tam_valor=7)
    _celula(c, ML + INNER * 0.73, y, INNER * 0.27, h_t, 'INSCRIÇÃO ESTADUAL', _txt(transporta, 'IE'), tam_valor=7)
    y -= h_t
    _celula(c, ML, y, INNER * 0.12, h_t, 'QUANTIDADE', _txt(vol, 'qVol'), alinhar='C', tam_valor=7)
    _celula(c, ML + INNER * 0.12, y, INNER * 0.20, h_t, 'ESPÉCIE', _txt(vol, 'esp'), tam_valor=7)
    _celula(c, ML + INNER * 0.32, y, INNER * 0.16, h_t, 'MARCA', _txt(vol, 'marca'), tam_valor=7)
    _celula(c, ML + INNER * 0.48, y, INNER * 0.16, h_t, 'NUMERAÇÃO', _txt(vol, 'nVol'), tam_valor=7)
    _celula(c, ML + INNER * 0.64, y, INNER * 0.18, h_t, 'PESO BRUTO (Kg)', _txt(vol, 'pesoB'), alinhar='R', tam_valor=7)
    _celula(c, ML + INNER * 0.82, y, INNER * 0.18, h_t, 'PESO LÍQUIDO (Kg)', _txt(vol, 'pesoL'), alinhar='R', tam_valor=7)
    y -= h_t

    # Produtos
    y -= _faixa(c, ML, y, INNER, 'DADOS DO PRODUTO / SERVIÇOS')
    cols = [
        ('CÓDIGO DO PROD. / SERV.', 48, 'L'),
        ('DESCRIÇÃO DO PRODUTO / SERVIÇO', 0, 'L'),
        ('NCM / SH', 46, 'C'),
        ('CST', 24, 'C'),
        ('CFOP', 26, 'C'),
        ('UNID.', 24, 'C'),
        ('QUANT.', 38, 'R'),
        ('VALOR UNITÁRIO', 48, 'R'),
        ('VALOR TOTAL', 48, 'R'),
        ('DESCONTO', 36, 'R'),
        ('BASE CÁLC. ICMS', 42, 'R'),
        ('VALOR I.C.M.S.', 38, 'R'),
        ('VALOR I.P.I.', 34, 'R'),
        ('ALÍQ. ICMS', 28, 'R'),
        ('ALÍQ. IPI', 26, 'R'),
    ]
    largura_desc = INNER - sum(w for _, w, _ in cols if w)
    cols[1] = (cols[1][0], largura_desc, 'L')
    h_head = 16
    _caixa(c, ML, y, INNER, h_head)
    x = ML
    for i, (nome, larg, alinhar) in enumerate(cols):
        if i:
            c.setLineWidth(0.3)
            c.line(x, y, x, y - h_head)
        linhas_h = nome.split('\n') if '\n' in nome else _quebrar(nome, FONT, 4.2, larg - 2)[:2]
        ty = y - 6
        for linha in linhas_h:
            _texto(c, x, ty, larg, linha, FONT, 4.2, 'C' if alinhar != 'L' else 'L')
            ty -= 5.5
        x += larg
    y -= h_head

    itens = _montar_itens(inf)
    h_adic = 70
    y_min_itens = MB + h_adic
    h_lin = 12
    keys = ['codigo', 'descricao', 'ncm', 'cst', 'cfop', 'un', 'qtd', 'vunit', 'vtotal', 'vdesc', 'vbc', 'vicms', 'vipi', 'picms', 'pipi']
    for item in itens:
        if y - h_lin < y_min_itens:
            break
        _caixa(c, ML, y, INNER, h_lin)
        x = ML
        for i, ((_, larg, alinhar), key) in enumerate(zip(cols, keys)):
            if i:
                c.setLineWidth(0.25)
                c.line(x, y, x, y - h_lin)
            _texto(c, x, y - 9, larg, item.get(key, ''), FONT, 6, alinhar)
            x += larg
        y -= h_lin

    # Dados adicionais no rodapé
    y = MB + h_adic
    _faixa(c, ML, y, INNER, 'DADOS ADICIONAIS')
    y -= 9
    w_inf = INNER * 0.62
    inf_cpl = _txt(inf_adic, 'infCpl')
    inf_fisco = _txt(inf_adic, 'infAdFisco')
    _caixa(c, ML, y, w_inf, h_adic - 9)
    _caixa(c, ML + w_inf, y, INNER - w_inf, h_adic - 9)
    c.setFont(FONT, 4.5)
    c.drawString(ML + 2, y - 6, 'INFORMAÇÕES COMPLEMENTARES')
    c.drawString(ML + w_inf + 2, y - 6, 'RESERVADO AO FISCO')
    c.setFont(FONT, 6.5)
    ty = y - 16
    extra = inf_cpl or ''
    if n_prot and 'Protocolo' not in extra:
        extra = (extra + '  ' if extra else '') + f'Protocolo: {n_prot} {dh_prot_d} {dh_prot_h}'
    for linha in _quebrar(extra, FONT, 6.5, w_inf - 8)[:6]:
        c.drawString(ML + 3, ty, linha)
        ty -= 8
    ty = y - 16
    for linha in _quebrar(inf_fisco, FONT, 6.5, INNER - w_inf - 8)[:6]:
        c.drawString(ML + w_inf + 3, ty, linha)
        ty -= 8

    c.showPage()
    c.save()
    return buf.getvalue()


def regenerar_pdf_nfe_de_xml(caminho_xml: str | Path, caminho_pdf: str | Path) -> bool:
    xml_path, pdf_path = Path(caminho_xml), Path(caminho_pdf)
    if not xml_path.is_file():
        return False
    xml_bytes = xml_path.read_bytes()
    if not re.search(rb'<mod>\s*55\s*</mod>', xml_bytes):
        return False
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(montar_danfe_nfe_pdf(xml_bytes))
    return True
