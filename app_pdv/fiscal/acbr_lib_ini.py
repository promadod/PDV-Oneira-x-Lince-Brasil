"""Converte o payload interno (formato Focus) para INI da ACBrLibNFe."""
from __future__ import annotations

import random
from datetime import datetime

from django.utils import timezone

from .nfe_catalog import codigo_uf_ibge

_HOMOLOG_XPROD = 'NOTA FISCAL EMITIDA EM AMBIENTE DE HOMOLOGACAO - SEM VALOR FISCAL'
_TPAG_COM_CARTAO = {'03', '04', '17'}


def _num(value, default=0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _digitos(value) -> str:
    return ''.join(c for c in str(value or '') if c.isdigit())


def _fmt_money(value) -> str:
    return f'{_num(value):.2f}'


def _fmt_qtd(value) -> str:
    return f'{_num(value, 1):.4f}'.rstrip('0').rstrip('.') if '.' in f'{_num(value, 1):.4f}' else f'{_num(value, 1):.0f}'


def _dh_emi(payload: dict) -> str:
    raw = payload.get('data_emissao') or ''
    if raw:
        try:
            dt = datetime.fromisoformat(str(raw).replace('Z', '+00:00'))
            return timezone.localtime(dt).strftime('%d/%m/%Y %H:%M:%S')
        except (TypeError, ValueError):
            pass
    return timezone.localtime(timezone.now()).strftime('%d/%m/%Y %H:%M:%S')


def _ini_escape(value) -> str:
    return str(value or '').replace('\n', ' ').replace('\r', ' ')


def _section(name: str, pairs: dict) -> str:
    lines = [f'[{name}]']
    for k, v in pairs.items():
        if v is None or v == '':
            continue
        lines.append(f'{k}={_ini_escape(v)}')
    return '\n'.join(lines)


def montar_ini_nfe(
    cfg,
    payload: dict,
    *,
    tipo: str,
    numero: int,
    serie: int,
) -> str:
    """Gera texto INI (modelo ACBr) para NF-e/NFC-e a partir do payload interno."""
    itens = list(payload.get('items') or [])
    if not itens:
        raise ValueError('A nota não tem itens para enviar à ACBrLib.')

    homologacao = cfg.ambiente != 'producao'
    cnpj = _digitos(payload.get('cnpj_emitente') or cfg.cnpj)
    if len(cnpj) != 14:
        raise ValueError('CNPJ do emitente inválido ou não configurado.')
    ibge = _digitos(cfg.codigo_ibge)
    if len(ibge) != 7:
        raise ValueError('Informe o código IBGE do município em Config. Fiscal antes de emitir.')
    uf = (cfg.uf or 'RJ').upper()[:2]
    cuf = codigo_uf_ibge(uf)
    modelo = '55' if tipo == 'nfe' else '65'
    cnf = f'{random.randint(10000000, 99999999)}'

    sections: list[str] = []
    sections.append(_section('infNFe', {'versao': '4.00'}))
    sections.append(_section('Identificacao', {
        'cNF': cnf,
        'natOp': (payload.get('natureza_operacao') or 'VENDA')[:60],
        'indPag': '0',
        'mod': modelo,
        'serie': str(int(serie or 1)),
        'nNF': str(int(numero)),
        'dhEmi': _dh_emi(payload),
        'tpNF': '1',
        'idDest': str(int(payload.get('local_destino') or 1)),
        'tpAmb': '1' if not homologacao else '2',
        'tpImp': '1' if tipo == 'nfe' else '4',
        'tpEmis': '9' if payload.get('forma_emissao') == 'offline' else '1',
        'finNFe': str(int(payload.get('finalidade_emissao') or 1)),
        'indFinal': '1',
        'indPres': str(int(payload.get('presenca_comprador') or 1)),
        'procEmi': '0',
        'cMunFG': ibge,
        'verProc': 'OneiraPDV',
    }))
    sections.append(_section('Emitente', {
        'CRT': str(cfg.crt or '1'),
        'CNPJCPF': cnpj,
        'xNome': (cfg.razao_social or cfg.nome_fantasia or 'EMITENTE')[:60],
        'xFant': (cfg.nome_fantasia or cfg.razao_social or '')[:60],
        'IE': _digitos(cfg.inscricao_estadual) or 'ISENTO',
        'IM': _digitos(cfg.inscricao_municipal),
        'CNAE': _digitos(cfg.cnae),
        'xLgr': (cfg.logradouro or 'NAO INFORMADO')[:60],
        'nro': (cfg.numero or 'S/N')[:60],
        'xCpl': (cfg.complemento or '')[:60],
        'xBairro': (cfg.bairro or 'CENTRO')[:60],
        'cMun': ibge,
        'xMun': (cfg.municipio or '')[:60],
        'cUF': cuf,
        'UF': uf,
        'CEP': _digitos(cfg.cep).zfill(8)[:8],
        'cPais': '1058',
        'xPais': 'BRASIL',
    }))

    cpf = _digitos(payload.get('cpf_destinatario'))
    cnpj_dest = _digitos(payload.get('cnpj_destinatario'))
    nome_dest = (payload.get('nome_destinatario') or '').strip()
    dest_pairs: dict = {}
    if len(cpf) == 11:
        dest_pairs['CNPJCPF'] = cpf
    elif len(cnpj_dest) == 14:
        dest_pairs['CNPJCPF'] = cnpj_dest
    if dest_pairs or nome_dest or tipo == 'nfe':
        dest_pairs['xNome'] = (nome_dest or 'CONSUMIDOR NAO IDENTIFICADO')[:60]
        dest_pairs['indIEDest'] = str(int(payload.get('indicador_inscricao_estadual_destinatario') or 9))
        ie_dest = _digitos(payload.get('inscricao_estadual_destinatario'))
        if ie_dest:
            dest_pairs['IE'] = ie_dest
        if payload.get('logradouro_destinatario') or tipo == 'nfe':
            dest_pairs.update({
                'xLgr': (payload.get('logradouro_destinatario') or payload.get('logradouro') or 'NAO INFORMADO')[:60],
                'nro': (payload.get('numero_destinatario') or payload.get('numero') or 'S/N')[:60],
                'xBairro': (payload.get('bairro_destinatario') or payload.get('bairro') or 'CENTRO')[:60],
                'cMun': _digitos(payload.get('codigo_municipio_destinatario') or payload.get('codigo_municipio') or ibge)[:7],
                'xMun': (payload.get('municipio_destinatario') or payload.get('municipio') or cfg.municipio or '')[:60],
                'UF': (payload.get('uf_destinatario') or payload.get('uf') or uf)[:2].upper(),
                'CEP': _digitos(payload.get('cep_destinatario') or payload.get('cep') or cfg.cep).zfill(8)[:8],
                'cPais': '1058',
                'xPais': 'BRASIL',
            })
        sections.append(_section('Destinatario', dest_pairs))

    v_prod = 0.0
    v_desc = 0.0
    v_outro = 0.0
    for i, item in enumerate(itens, start=1):
        idx = f'{i:03d}'
        qtd = _num(item.get('quantidade_comercial'), 1) or 1
        v_unit = _num(item.get('valor_unitario_comercial'))
        bruto = round(_num(item.get('valor_bruto'), qtd * v_unit), 2)
        desc = round(_num(item.get('valor_desconto')), 2)
        outro = round(_num(item.get('valor_outras_despesas')), 2)
        v_prod += bruto
        v_desc += desc
        v_outro += outro
        unidade = (item.get('unidade_comercial') or 'UN')[:6]
        descricao = (item.get('descricao') or 'PRODUTO')[:120]
        if homologacao and i == 1:
            descricao = _HOMOLOG_XPROD
        ncm = _digitos(item.get('codigo_ncm')).zfill(8)[:8] or '00000000'
        prod = {
            'cProd': str(item.get('codigo_produto') or i)[:60],
            'cEAN': 'SEM GTIN',
            'xProd': descricao,
            'NCM': ncm,
            'CFOP': _digitos(item.get('cfop') or '5102')[:4] or '5102',
            'uCom': unidade,
            'qCom': _fmt_qtd(qtd),
            'vUnCom': _fmt_money(v_unit),
            'vProd': _fmt_money(bruto),
            'cEANTrib': 'SEM GTIN',
            'uTrib': (item.get('unidade_tributavel') or unidade)[:6],
            'qTrib': _fmt_qtd(item.get('quantidade_tributavel') or qtd),
            'vUnTrib': _fmt_money(item.get('valor_unitario_tributavel') or v_unit),
            'indTot': '1',
        }
        cest = _digitos(item.get('cest'))
        if cest:
            prod['CEST'] = cest[:7]
        if desc > 0:
            prod['vDesc'] = _fmt_money(desc)
        if outro > 0:
            prod['vOutro'] = _fmt_money(outro)
        sections.append(_section(f'Produto{idx}', prod))

        origem = str(item.get('icms_origem') or '0')[:1]
        cst = _digitos(item.get('icms_situacao_tributaria') or '102')[:3] or '102'
        icms = {'orig': origem}
        if len(cst) == 3:
            icms['CSOSN'] = cst
        else:
            icms['CST'] = cst.zfill(2)
        sections.append(_section(f'ICMS{idx}', icms))

        for trib, key in (('PIS', 'pis'), ('COFINS', 'cofins')):
            cst_t = _digitos(item.get(f'{key}_situacao_tributaria') or '49').zfill(2)[:2]
            sections.append(_section(f'{trib}{idx}', {
                'CST': cst_t,
                'vBC': '0.00',
                f'p{trib}': '0.00',
                f'v{trib}': '0.00',
            }))

    if not v_desc:
        v_desc = round(_num(payload.get('valor_desconto')), 2)
    if not v_outro:
        v_outro = round(_num(payload.get('valor_outras_despesas')), 2)
    v_nf = round(max(v_prod - v_desc + v_outro, 0), 2)

    sections.append(_section('Total', {
        'vBC': '0.00',
        'vICMS': '0.00',
        'vICMSDeson': '0.00',
        'vBCST': '0.00',
        'vST': '0.00',
        'vProd': _fmt_money(v_prod),
        'vFrete': _fmt_money(payload.get('valor_frete')),
        'vSeg': '0.00',
        'vDesc': _fmt_money(v_desc),
        'vII': '0.00',
        'vIPI': '0.00',
        'vPIS': '0.00',
        'vCOFINS': '0.00',
        'vOutro': _fmt_money(v_outro),
        'vNF': _fmt_money(v_nf),
        'vTotTrib': '0.00',
    }))
    sections.append(_section('Transportador', {
        'modFrete': str(int(payload.get('modalidade_frete') or 9)),
    }))

    pagamentos = list(payload.get('formas_pagamento') or [])
    if not pagamentos:
        pagamentos = [{'forma_pagamento': '01', 'valor_pagamento': v_nf}]
    for i, pag in enumerate(pagamentos, start=1):
        tpag = str(pag.get('forma_pagamento') or '01').zfill(2)[:2]
        pairs = {
            'tPag': tpag,
            'vPag': _fmt_money(pag.get('valor_pagamento') or v_nf),
            'indPag': '0',
        }
        if tpag == '99':
            pairs['xPag'] = (str(pag.get('descricao_pagamento') or 'Outros').strip() or 'Outros')[:60]
        if tpag in _TPAG_COM_CARTAO:
            pairs['tpIntegra'] = '2'
        sections.append(_section(f'pag{i:03d}', pairs))

    return '\n\n'.join(sections) + '\n'
