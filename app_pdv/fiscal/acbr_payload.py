"""Converte o payload interno (formato Focus) para o pedido de emissão da ACBr API."""
from __future__ import annotations

from .models import FiscalConfig
from .nfe_catalog import codigo_uf_ibge

_HOMOLOG_XPROD = 'NOTA FISCAL EMITIDA EM AMBIENTE DE HOMOLOGACAO - SEM VALOR FISCAL'

_CSOSN_SN102 = {'102', '103', '300', '400'}
_PIS_NT = {'04', '05', '06', '07', '08', '09'}
# NFC-e no RJ exige o grupo card (tpIntegra) em crédito, débito e PIX.
_TPAG_COM_CARTAO = {'03', '04', '17'}


def _det_pagamento(pag: dict, v_nf: float) -> dict:
    """Grupo detPag. Cartão e PIX sem TEF vão como pagamento não integrado."""
    tpag = str(pag.get('forma_pagamento') or '01').zfill(2)[:2]
    det = {
        'tPag': tpag,
        'vPag': round(_num(pag.get('valor_pagamento'), v_nf), 2),
    }
    if tpag in _TPAG_COM_CARTAO:
        det['card'] = {'tpIntegra': 2}
    if tpag == '99':
        det['xPag'] = (str(pag.get('descricao_pagamento') or 'Outros').strip() or 'Outros')[:60]
    return det


def _num(value, default=0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _icms(item: dict) -> dict:
    origem = int(str(item.get('icms_origem') or '0')[:1] or '0')
    cst = ''.join(c for c in str(item.get('icms_situacao_tributaria') or '102') if c.isdigit())[:3]
    if cst in _CSOSN_SN102:
        return {'ICMSSN102': {'orig': origem, 'CSOSN': cst}}
    if cst == '101':
        return {'ICMSSN101': {'orig': origem, 'CSOSN': '101', 'pCredSN': 0, 'vCredICMSSN': 0}}
    if cst == '500':
        return {'ICMSSN500': {
            'orig': origem, 'CSOSN': '500',
            'vBCSTRet': 0, 'pST': 0, 'vICMSSubstituto': 0, 'vICMSSTRet': 0,
        }}
    if cst == '900':
        return {'ICMSSN900': {'orig': origem, 'CSOSN': '900'}}
    if len(cst) == 2:
        return {'ICMS40': {'orig': origem, 'CST': cst}}
    return {'ICMSSN102': {'orig': origem, 'CSOSN': '102'}}


def _pis_cofins(item: dict, qual: str) -> dict:
    prefixo = 'PIS' if qual == 'pis' else 'COFINS'
    cst = str(item.get(f'{qual}_situacao_tributaria') or '49').zfill(2)[:2]
    if cst in _PIS_NT:
        return {f'{prefixo}NT': {'CST': cst}}
    aliq = _num(item.get(f'{qual}_aliquota'))
    base = _num(item.get('valor_bruto'))
    valor = round(base * aliq / 100, 2) if aliq else 0
    return {f'{prefixo}Outr': {'CST': cst, 'vBC': base, f'p{prefixo}': aliq, f'v{prefixo}': valor}}


def _item_det(item: dict, *, homologacao: bool, primeiro: bool) -> dict:
    qtd = _num(item.get('quantidade_comercial'), 1) or 1
    v_unit = _num(item.get('valor_unitario_comercial'))
    v_prod = round(_num(item.get('valor_bruto'), qtd * v_unit), 2)
    unidade = (item.get('unidade_comercial') or 'UN')[:6]
    ncm = ''.join(c for c in str(item.get('codigo_ncm') or '') if c.isdigit()).zfill(8)[:8]
    descricao = (item.get('descricao') or 'PRODUTO')[:120]
    if homologacao and primeiro:
        descricao = _HOMOLOG_XPROD
    prod = {
        'cProd': str(item.get('codigo_produto') or '1')[:60],
        'cEAN': 'SEM GTIN',
        'xProd': descricao,
        'NCM': ncm or '00000000',
        'CFOP': ''.join(c for c in str(item.get('cfop') or '5102') if c.isdigit())[:4] or '5102',
        'uCom': unidade,
        'qCom': qtd,
        'vUnCom': v_unit,
        'vProd': v_prod,
        'cEANTrib': 'SEM GTIN',
        'uTrib': (item.get('unidade_tributavel') or unidade)[:6],
        'qTrib': _num(item.get('quantidade_tributavel'), qtd) or qtd,
        'vUnTrib': _num(item.get('valor_unitario_tributavel'), v_unit),
        'indTot': 1,
    }
    cest = ''.join(c for c in str(item.get('cest') or '') if c.isdigit())
    if cest:
        prod['CEST'] = cest[:7]
    v_desc = _num(item.get('valor_desconto'))
    if v_desc > 0:
        prod['vDesc'] = round(v_desc, 2)
    v_outro = _num(item.get('valor_outras_despesas'))
    if v_outro > 0:
        prod['vOutro'] = round(v_outro, 2)
    return {
        'nItem': int(item.get('numero_item') or 1),
        'prod': prod,
        'imposto': {
            'ICMS': _icms(item),
            'PIS': _pis_cofins(item, 'pis'),
            'COFINS': _pis_cofins(item, 'cofins'),
        },
    }


def pedido_emissao(cfg: FiscalConfig, payload: dict, *, tipo: str, ref: str, numero: int, serie: int) -> dict:
    """Monta NfePedidoEmissao (POST /nfce ou /nfe)."""
    homologacao = cfg.ambiente != 'producao'
    itens = list(payload.get('items') or [])
    if not itens:
        raise ValueError('A nota não tem itens para enviar à ACBr.')
    dets = [_item_det(item, homologacao=homologacao, primeiro=i == 0) for i, item in enumerate(itens)]
    v_prod = round(sum(_num(d['prod']['vProd']) for d in dets), 2)
    v_desc = round(sum(_num(d['prod'].get('vDesc')) for d in dets), 2)
    v_outro = round(sum(_num(d['prod'].get('vOutro')) for d in dets), 2)
    if not v_desc:
        v_desc = round(_num(payload.get('valor_desconto')), 2)
        if v_desc and dets:
            dets[0]['prod']['vDesc'] = v_desc
    if not v_outro:
        v_outro = round(_num(payload.get('valor_outras_despesas')), 2)
        if v_outro and dets:
            dets[0]['prod']['vOutro'] = v_outro
    v_nf = round(max(v_prod - v_desc + v_outro, 0), 2)
    cnpj = ''.join(c for c in (payload.get('cnpj_emitente') or cfg.cnpj or '') if c.isdigit())
    if len(cnpj) != 14:
        raise ValueError('CNPJ do emitente inválido ou não configurado.')
    ibge = ''.join(c for c in (cfg.codigo_ibge or '') if c.isdigit())
    if len(ibge) != 7:
        raise ValueError('Informe o código IBGE do município em Config. Fiscal antes de emitir.')
    pagamentos = [_det_pagamento(pag, v_nf) for pag in (payload.get('formas_pagamento') or [])]
    if not pagamentos:
        pagamentos.append({'tPag': '01', 'vPag': v_nf})
    ide = {
        'cUF': int(codigo_uf_ibge(cfg.uf or 'RJ')),
        'natOp': (payload.get('natureza_operacao') or 'VENDA')[:60],
        'mod': 55 if tipo == 'nfe' else 65,
        'serie': int(serie or 1),
        'nNF': int(numero),
        'dhEmi': payload.get('data_emissao'),
        'tpNF': 1,
        'idDest': int(payload.get('local_destino') or 1),
        'cMunFG': ibge,
        'tpImp': 1 if tipo == 'nfe' else 4,
        'tpEmis': 9 if payload.get('forma_emissao') == 'offline' else 1,
        'finNFe': 1,
        'indFinal': 1,
        'indPres': int(payload.get('presenca_comprador') or 1),
        'procEmi': 0,
        'verProc': 'OneiraPDV',
    }
    inf = {
        'versao': '4.00',
        'ide': ide,
        'emit': {
            'CNPJ': cnpj,
            'xNome': (cfg.razao_social or '')[:60] or None,
            'CRT': int(cfg.crt or 1),
        },
        'det': dets,
        'total': {'ICMSTot': {
            'vBC': 0, 'vICMS': 0, 'vICMSDeson': 0, 'vFCP': 0,
            'vBCST': 0, 'vST': 0, 'vFCPST': 0, 'vFCPSTRet': 0,
            'vProd': v_prod, 'vFrete': 0, 'vSeg': 0, 'vDesc': v_desc,
            'vII': 0, 'vIPI': 0, 'vIPIDevol': 0, 'vPIS': 0, 'vCOFINS': 0,
            'vOutro': v_outro, 'vNF': v_nf,
        }},
        'transp': {'modFrete': int(payload.get('modalidade_frete') or 9)},
        'pag': {'detPag': pagamentos},
    }
    inf['emit'] = {k: v for k, v in inf['emit'].items() if v not in (None, '')}
    cpf = ''.join(c for c in str(payload.get('cpf_destinatario') or '') if c.isdigit())
    cnpj_dest = ''.join(c for c in str(payload.get('cnpj_destinatario') or '') if c.isdigit())
    nome = (payload.get('nome_destinatario') or '')[:60]
    if len(cpf) == 11 or len(cnpj_dest) == 14:
        dest = {'indIEDest': int(payload.get('indicador_inscricao_estadual_destinatario') or 9)}
        if len(cpf) == 11:
            dest['CPF'] = cpf
        else:
            dest['CNPJ'] = cnpj_dest
        if nome:
            dest['xNome'] = nome
        inf['dest'] = dest
    return {
        'ambiente': 'producao' if cfg.ambiente == 'producao' else 'homologacao',
        'referencia': ref[:50],
        'infNFe': inf,
    }


def retorno_acbr_para_interno(dfe: dict) -> dict:
    """Deixa a resposta da ACBr no formato já lido por _aplicar_retorno_focus."""
    if not isinstance(dfe, dict):
        return {'status': 'erro', 'mensagem_sefaz': str(dfe)}
    status = (dfe.get('status') or '').lower()
    mapa = {
        'autorizado': 'autorizado',
        'rejeitado': 'erro_autorizacao',
        'denegado': 'denegado',
        'cancelado': 'cancelado',
        'pendente': 'processando_autorizacao',
        'erro': 'erro',
    }
    aut = dfe.get('autorizacao') if isinstance(dfe.get('autorizacao'), dict) else {}
    return {
        **dfe,
        'status': mapa.get(status, status or 'erro'),
        'numero': dfe.get('numero') or '',
        'serie': dfe.get('serie') or '',
        'chave_nfe': dfe.get('chave') or '',
        'status_sefaz': str(aut.get('codigo_status') or ''),
        'mensagem_sefaz': aut.get('motivo_status') or aut.get('mensagem') or dfe.get('mensagem') or '',
        'protocolo': aut.get('numero_protocolo') or '',
    }
