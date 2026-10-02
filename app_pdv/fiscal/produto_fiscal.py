"""Tributação por produto (prioridade sobre matriz) e item JSON Focus."""
from __future__ import annotations

from decimal import Decimal

from .models import ProdutoDadosFiscais, RegraTributaria


def resolver_regra(loja, ncm='', uf_destino='', operacao='venda'):
    qs = RegraTributaria.objects.filter(loja=loja, ativa=True, operacao=operacao)
    if ncm:
        especifica = qs.filter(ncm=ncm).first()
        if especifica:
            if not especifica.uf_destino or especifica.uf_destino.upper() == (uf_destino or '').upper():
                return especifica
    if uf_destino:
        por_uf = qs.filter(ncm='', uf_destino__iexact=uf_destino).first()
        if por_uf:
            return por_uf
    return qs.filter(ncm='', uf_destino='').first()


def _unidade(produto) -> str:
    um = getattr(produto, 'unidade_medida', None) or 'UN'
    um = str(um).upper()
    if um == 'KG':
        return 'kg'
    if um == 'L':
        return 'l'
    return 'un'


def _dec(value) -> float:
    if value is None:
        return 0.0
    return float(Decimal(str(value)))


def tributacao_do_produto(loja, produto, dados: ProdutoDadosFiscais | None, *, interestadual=False):
    ncm = (dados.ncm if dados and dados.ncm else '00000000').replace('.', '')[:8]
    regra = resolver_regra(loja, ncm=ncm, operacao='venda')

    cfop = ''
    if dados:
        cfop = (dados.cfop_interestadual if interestadual else dados.cfop_venda) or ''
    if not cfop and regra:
        cfop = regra.cfop or '5102'
    if not cfop:
        cfop = '5102'

    csosn = (dados.csosn if dados and dados.csosn else '') or (
        regra.csosn if regra and regra.csosn else '102'
    )
    cst_icms = (dados.cst_icms if dados and dados.cst_icms else '') or (
        regra.cst_icms if regra else ''
    )
    icms_st = csosn or cst_icms or '102'

    cst_pis = (dados.cst_pis if dados and dados.cst_pis else '') or (
        regra.cst_pis if regra else '49'
    )
    cst_cofins = (dados.cst_cofins if dados and dados.cst_cofins else '') or (
        regra.cst_cofins if regra else '49'
    )

    aliq_icms = dados.aliquota_icms if dados and dados.aliquota_icms else (
        regra.aliquota_icms if regra else 0
    )
    aliq_pis = dados.aliquota_pis if dados and dados.aliquota_pis else (
        regra.aliquota_pis if regra else 0
    )
    aliq_cofins = dados.aliquota_cofins if dados and dados.aliquota_cofins else (
        regra.aliquota_cofins if regra else 0
    )

    return {
        'ncm': ncm,
        'cfop': cfop,
        'icms_situacao_tributaria': icms_st,
        'cst_pis': cst_pis,
        'cst_cofins': cst_cofins,
        'aliquota_icms': aliq_icms,
        'aliquota_pis': aliq_pis,
        'aliquota_cofins': aliq_cofins,
        'origem': dados.origem if dados else '0',
        'unidade': (dados.unidade_tributavel if dados and dados.unidade_tributavel else None) or _unidade(produto),
        'codigo_beneficio_fiscal': (dados.codigo_beneficio_fiscal if dados else '') or '',
        'codigo_class_trib': (dados.codigo_class_trib if dados else '') or '',
        'cst_ibs_cbs': (dados.cst_ibs_cbs if dados else '') or '',
    }


def montar_item_focus_json(loja, produto, *, quantidade: float, preco_unitario: float, numero_item: int = 1,
                           interestadual=False) -> dict:
    try:
        dados = produto.dados_fiscais
    except ProdutoDadosFiscais.DoesNotExist:
        dados = None
    trib = tributacao_do_produto(loja, produto, dados, interestadual=interestadual)
    qtd = float(quantidade)
    v_unit = float(preco_unitario)
    v_bruto = round(qtd * v_unit, 2)
    item = {
        'numero_item': str(numero_item),
        'codigo_produto': str(produto.pk),
        'codigo_ncm': trib['ncm'],
        'descricao': (produto.nome_venda or getattr(produto, 'nome', ''))[:120],
        'quantidade_comercial': qtd,
        'quantidade_tributavel': qtd,
        'valor_unitario_comercial': v_unit,
        'valor_unitario_tributavel': v_unit,
        'valor_bruto': v_bruto,
        'unidade_comercial': trib['unidade'],
        'unidade_tributavel': trib['unidade'],
        'cfop': trib['cfop'],
        'icms_origem': trib['origem'],
        'icms_situacao_tributaria': trib['icms_situacao_tributaria'],
    }
    if trib['codigo_beneficio_fiscal']:
        item['codigo_beneficio_fiscal'] = trib['codigo_beneficio_fiscal']
    if trib['aliquota_icms']:
        item['icms_aliquota'] = _dec(trib['aliquota_icms'])
    if trib['cst_pis']:
        item['pis_situacao_tributaria'] = trib['cst_pis']
    if trib['aliquota_pis']:
        item['pis_aliquota'] = _dec(trib['aliquota_pis'])
    if trib['cst_cofins']:
        item['cofins_situacao_tributaria'] = trib['cst_cofins']
    if trib['aliquota_cofins']:
        item['cofins_aliquota'] = _dec(trib['aliquota_cofins'])
    if dados and dados.codigo_anp:
        item['codigo_anp'] = dados.codigo_anp.strip()
        if dados.descricao_anp:
            item['descricao_anp'] = dados.descricao_anp.strip()[:95]
        if dados.icms_aliquota_ad_rem:
            item['icms_aliquota_ad_rem'] = _dec(dados.icms_aliquota_ad_rem)
        if dados.pct_glp:
            item['percentual_glp'] = _dec(dados.pct_glp)
        if dados.pct_gn_nacional:
            item['percentual_gn_nacional'] = _dec(dados.pct_gn_nacional)
        if dados.pct_gn_importado:
            item['percentual_gn_importado'] = _dec(dados.pct_gn_importado)
    return item
