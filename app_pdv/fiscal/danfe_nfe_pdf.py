"""DANFE NF-e (A4 retrato) gerado a partir do XML autorizado.

O DANFE NFC-e (bobina 80 mm) não serve para modelo 55. Este layout cobre
emitente, destinatário, itens, totais, transporte e protocolo.
"""
from __future__ import annotations

import io
import re
from pathlib import Path
from xml.etree import ElementTree as ET

from reportlab.graphics.barcode import code128
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from .danfe_nfce_pdf import (
    FONT,
    FONT_BOLD,
    FORMAS_PAGAMENTO,
    _NFE,
    _descricao_item,
    _find,
    _fmt_dh,
    _fmt_doc,
    _money,
    _num,
    _qtd,
    _quebrar,
    _txt,
)

W, H = A4
ML, MR, MT, MB = 14.0, 14.0, 14.0, 14.0
INNER = W - ML - MR


def _caixa(c, x, y, w, h):
    c.setLineWidth(0.5)
    c.rect(x, y - h, w, h)


def _rotulo(c, x, y, texto):
    c.setFont(FONT, 5)
    c.drawString(x + 2, y - 7, (texto or '').upper())


def _valor(c, x, y, texto, tamanho=8, negrito=True):
    c.setFont(FONT_BOLD if negrito else FONT, tamanho)
    c.drawString(x + 2, y - 16, texto or '')


def _chave_grupos(chave: str) -> str:
    d = re.sub(r'\D', '', chave or '')
    return ' '.join(d[i:i + 4] for i in range(0, len(d), 4))


def _cst_item(det) -> str:
    imposto = _find(det, 'imposto')
    icms = _find(imposto, 'ICMS') if imposto is not None else None
    if icms is None:
        return ''
    for filho in list(icms):
        cst = (filho.findtext(f'{_NFE}CST') or filho.findtext(f'{_NFE}CSOSN') or '').strip()
        if cst:
            orig = (filho.findtext(f'{_NFE}orig') or '').strip()
            return f'{orig}{cst}' if orig else cst
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
        })
    return itens


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
    prot = root.find(f'.//{_NFE}infProt')
    inf_adic = _find(inf, 'infAdic')

    chave = (inf.get('Id') or '').replace('NFe', '')
    numero = _txt(ide, 'nNF').zfill(9)
    serie = _txt(ide, 'serie').zfill(3)
    tp_nf = _txt(ide, 'tpNF') or '1'
    natureza = _txt(ide, 'natOp')
    dh_emi = _fmt_dh(_txt(ide, 'dhEmi'))
    dh_sai = _fmt_dh(_txt(ide, 'dhSaiEnt'))

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setPageCompression(0)
    c.setTitle(f'DANFE NF-e {numero}')
    c.setAuthor('Oneira PDV')

    y = H - MT
    # --- Cabeçalho ---
    h_cab = 92
    w_emit = INNER * 0.46
    w_meio = INNER * 0.22
    w_dir = INNER - w_emit - w_meio
    _caixa(c, ML, y, w_emit, h_cab)
    _caixa(c, ML + w_emit, y, w_meio, h_cab)
    _caixa(c, ML + w_emit + w_meio, y, w_dir, h_cab)

    c.setFont(FONT_BOLD, 8)
    c.drawString(ML + 4, y - 14, (_txt(emit, 'xNome') or _txt(emit, 'xFant') or 'EMITENTE')[:52])
    c.setFont(FONT, 6.5)
    mun = ', '.join(p for p in (_txt(ender, 'xMun'), _txt(ender, 'UF')) if p)
    end_emit = ', '.join(p for p in (
        _txt(ender, 'xLgr'), _txt(ender, 'nro'), _txt(ender, 'xBairro'), mun,
    ) if p)
    ty = y - 26
    for linha in _quebrar(end_emit, FONT, 6.5, w_emit - 8):
        c.drawString(ML + 4, ty, linha)
        ty -= 9
    fone = re.sub(r'\D', '', _txt(ender, 'fone'))
    c.drawString(ML + 4, ty, f'CNPJ: {_fmt_doc(_txt(emit, "CNPJ"))}  IE: {_txt(emit, "IE")}')
    if fone:
        c.drawString(ML + 4, ty - 9, f'Fone: {fone}')

    cx = ML + w_emit + w_meio / 2
    c.setFont(FONT_BOLD, 11)
    c.drawCentredString(cx, y - 18, 'DANFE')
    c.setFont(FONT, 6)
    c.drawCentredString(cx, y - 28, 'Documento Auxiliar da')
    c.drawCentredString(cx, y - 36, 'Nota Fiscal Eletrônica')
    c.setFont(FONT, 6.5)
    c.drawCentredString(cx, y - 50, '0 — ENTRADA')
    c.drawCentredString(cx, y - 60, '1 — SAÍDA')
    c.setFont(FONT_BOLD, 10)
    c.drawCentredString(cx, y - 74, tp_nf)
    c.setFont(FONT_BOLD, 8)
    c.drawCentredString(cx, y - 88, f'Nº {numero}  Série {serie}')

    dx = ML + w_emit + w_meio + 4
    c.setFont(FONT, 5)
    c.drawString(dx, y - 10, 'CHAVE DE ACESSO')
    try:
        barra = code128.Code128(chave or '0', barHeight=28, barWidth=0.72, humanReadable=False)
        barra.drawOn(c, dx, y - 46)
    except Exception:
        c.setFont(FONT, 7)
        c.drawString(dx, y - 30, chave)
    c.setFont(FONT, 6)
    for i, linha in enumerate(_quebrar(_chave_grupos(chave), FONT, 6, w_dir - 8)):
        c.drawString(dx, y - 58 - i * 8, linha)
    c.setFont(FONT, 5.5)
    c.drawString(dx, y - 86, 'Consulta de autenticidade no portal nacional da NF-e')

    y -= h_cab + 2
    h_nat = 28
    w_nat = INNER * 0.62
    _caixa(c, ML, y, w_nat, h_nat)
    _caixa(c, ML + w_nat, y, INNER - w_nat, h_nat)
    _rotulo(c, ML, y, 'NATUREZA DA OPERAÇÃO')
    _valor(c, ML, y, natureza[:70], 8)
    _rotulo(c, ML + w_nat, y, 'PROTOCOLO DE AUTORIZAÇÃO DE USO')
    n_prot = _txt(prot, 'nProt')
    dh_prot = _fmt_dh(_txt(prot, 'dhRecbto'))
    _valor(c, ML + w_nat, y, f'{n_prot}  {dh_prot}'.strip(), 7)

    y -= h_nat + 2
    h_dest = 48
    _caixa(c, ML, y, INNER, h_dest)
    _rotulo(c, ML, y, 'DESTINATÁRIO / REMETENTE')
    c.setFont(FONT_BOLD, 7.5)
    c.drawString(ML + 2, y - 18, (_txt(dest, 'xNome') or 'NÃO INFORMADO')[:70])
    c.setFont(FONT, 7)
    doc_dest = _txt(dest, 'CNPJ') or _txt(dest, 'CPF')
    rot = 'CNPJ' if _txt(dest, 'CNPJ') else 'CPF'
    c.drawString(ML + 2, y - 30, f'{rot}: {_fmt_doc(doc_dest)}   IE: {_txt(dest, "IE") or "ISENTO"}')
    mun_d = ', '.join(p for p in (_txt(ender_dest, 'xMun'), _txt(ender_dest, 'UF')) if p)
    end_d = ', '.join(p for p in (
        _txt(ender_dest, 'xLgr'), _txt(ender_dest, 'nro'), _txt(ender_dest, 'xBairro'), mun_d,
        _txt(ender_dest, 'CEP'),
    ) if p)
    c.drawString(ML + 2, y - 42, (end_d or '')[:110])
    c.setFont(FONT, 6.5)
    c.drawRightString(W - MR - 2, y - 18, f'Emissão: {dh_emi}')
    if dh_sai:
        c.drawRightString(W - MR - 2, y - 30, f'Saída: {dh_sai}')

    y -= h_dest + 2
    itens = _montar_itens(inf)
    cols = [
        ('CÓDIGO', 48),
        ('DESCRIÇÃO DOS PRODUTOS / SERVIÇOS', 0),
        ('NCM', 48),
        ('CST', 32),
        ('CFOP', 30),
        ('UN', 22),
        ('QTDE', 40),
        ('V. UNIT', 50),
        ('V. TOTAL', 54),
    ]
    largura_desc = INNER - sum(w for n, w in cols if n != 'DESCRIÇÃO DOS PRODUTOS / SERVIÇOS')
    cols[1] = ('DESCRIÇÃO DOS PRODUTOS / SERVIÇOS', largura_desc)
    h_head = 12
    _caixa(c, ML, y, INNER, h_head)
    c.setFont(FONT_BOLD, 5.5)
    x = ML
    for nome, larg in cols:
        c.drawString(x + 1, y - 9, nome)
        x += larg
    y -= h_head

    c.setFont(FONT, 6.5)
    for item in itens:
        linhas_desc = _quebrar(item['descricao'], FONT, 6.5, largura_desc - 4) or ['']
        h_lin = 9 + 8 * (len(linhas_desc) - 1)
        if y - h_lin < MB + 120:
            c.showPage()
            y = H - MT
        _caixa(c, ML, y, INNER, h_lin + 2)
        valores = [
            item['codigo'][:12],
            linhas_desc[0],
            item['ncm'],
            item['cst'],
            item['cfop'],
            item['un'][:4],
            item['qtd'],
            item['vunit'],
            item['vtotal'],
        ]
        x = ML
        base = y - 10
        for i, ((nome, larg), val) in enumerate(zip(cols, valores)):
            if i >= 6:
                c.drawRightString(x + larg - 2, base, val)
            else:
                c.drawString(x + 1, base, val)
            x += larg
        for extra in linhas_desc[1:]:
            base -= 8
            c.drawString(ML + cols[0][1] + 1, base, extra)
        y -= h_lin + 2

    y -= 2
    h_tot = 42
    if y - h_tot < MB + 80:
        c.showPage()
        y = H - MT
    campos_tot = [
        ('BASE CÁLC. ICMS', _txt(tot, 'vBC')),
        ('VALOR ICMS', _txt(tot, 'vICMS')),
        ('BASE CÁLC. ICMS ST', _txt(tot, 'vBCST')),
        ('VALOR ICMS ST', _txt(tot, 'vST')),
        ('VALOR PRODUTOS', _txt(tot, 'vProd')),
        ('VALOR FRETE', _txt(tot, 'vFrete')),
        ('VALOR SEGURO', _txt(tot, 'vSeg')),
        ('DESCONTO', _txt(tot, 'vDesc')),
        ('VALOR IPI', _txt(tot, 'vIPI')),
        ('VALOR PIS', _txt(tot, 'vPIS')),
        ('VALOR COFINS', _txt(tot, 'vCOFINS')),
        ('OUTRAS DESP.', _txt(tot, 'vOutro')),
        ('VALOR TOTAL NF', _txt(tot, 'vNF')),
    ]
    n_col = 5
    cw = INNER / n_col
    rh = h_tot / 3
    for i, (nome, val) in enumerate(campos_tot):
        linha, col = divmod(i, n_col)
        if linha > 1:
            break
        x = ML + col * cw
        yy = y - linha * rh
        _caixa(c, x, yy, cw, rh)
        _rotulo(c, x, yy, nome)
        c.setFont(FONT_BOLD, 7)
        c.drawRightString(x + cw - 3, yy - 16, _money(val))
    x = ML + 3 * cw
    _caixa(c, x, y - 2 * rh, cw * 2, rh)
    _rotulo(c, x, y - 2 * rh, 'VALOR TOTAL DA NOTA')
    c.setFont(FONT_BOLD, 10)
    c.drawRightString(ML + INNER - 4, y - 2 * rh - 16, _money(_txt(tot, 'vNF')))
    y -= h_tot + 2

    h_tr = 36
    _caixa(c, ML, y, INNER, h_tr)
    _rotulo(c, ML, y, 'TRANSPORTADOR / VOLUMES')
    mod_frete = _txt(transp, 'modFrete')
    nomes_frete = {
        '0': 'Por conta do emitente', '1': 'Por conta do destinatário',
        '2': 'Por conta de terceiros', '3': 'Próprio emitente',
        '4': 'Próprio destinatário', '9': 'Sem ocorrência de transporte',
    }
    c.setFont(FONT, 7)
    c.drawString(ML + 2, y - 18, f'Frete: {nomes_frete.get(mod_frete, mod_frete)}')
    vol = _find(transp, 'vol') if transp is not None else None
    if vol is not None:
        c.drawString(
            ML + 2, y - 30,
            f'Volumes: {_txt(vol, "qVol") or "-"}   Peso L: {_txt(vol, "pesoL") or "-"} kg   '
            f'Peso B: {_txt(vol, "pesoB") or "-"} kg',
        )
    y -= h_tr + 2

    h_pag = 28
    _caixa(c, ML, y, INNER, h_pag)
    _rotulo(c, ML, y, 'FORMAS DE PAGAMENTO')
    pags = []
    for pag in inf.findall(f'{_NFE}pag'):
        for det_pag in pag.findall(f'{_NFE}detPag'):
            t_pag = _txt(det_pag, 'tPag')
            pags.append(f'{FORMAS_PAGAMENTO.get(t_pag, t_pag)}: {_money(_txt(det_pag, "vPag"))}')
    c.setFont(FONT, 7)
    c.drawString(ML + 2, y - 18, '   |   '.join(pags)[:120] if pags else '—')
    y -= h_pag + 2

    inf_cpl = _txt(inf_adic, 'infCpl')
    inf_fisco = _txt(inf_adic, 'infAdFisco')
    extra = '  '.join(p for p in (inf_cpl, inf_fisco) if p)
    linhas_info = _quebrar(extra, FONT, 6.5, INNER - 8)[:6] if extra else ['']
    h_info = 14 + 9 * max(len(linhas_info), 1)
    if y - h_info < MB:
        c.showPage()
        y = H - MT
    _caixa(c, ML, y, INNER, h_info)
    _rotulo(c, ML, y, 'DADOS ADICIONAIS')
    c.setFont(FONT, 6.5)
    ty = y - 16
    for linha in linhas_info:
        c.drawString(ML + 2, ty, linha)
        ty -= 9
    if n_prot:
        c.setFont(FONT, 6)
        c.drawString(ML + 2, y - h_info + 4, f'Protocolo de autorização: {n_prot}  {dh_prot}')

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
