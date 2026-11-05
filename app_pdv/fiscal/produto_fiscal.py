"""Tributação por produto (prioridade sobre matriz) e item JSON Focus."""
from __future__ import annotations

import re
from decimal import Decimal, ROUND_HALF_UP

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
    return _norm_unidade(um)


def _norm_unidade(value) -> str:
    u = str(value or 'UN').strip().upper()[:6]
    if u in ('UN', 'UND', 'UNID'):
        return 'UN'
    if u in ('KG', 'KGS', 'KILO'):
        return 'KG'
    if u in ('L', 'LT', 'LTR', 'LITRO'):
        return 'L'
    return u or 'UN'


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


def aplicar_perfil_tributacao_item(item: dict, perfil: str) -> None:
    if not perfil or perfil == 'produto':
        return
    if perfil == 'cst_61_combustivel':
        item['icms_situacao_tributaria'] = '61'
        return
    csosn_map = {
        'csosn_102': '102',
        'csosn_500': '500',
        'csosn_400': '400',
        'csosn_300': '300',
        'nao_tributada': '400',
        'substituicao': '500',
    }
    csosn = csosn_map.get(perfil)
    if csosn:
        item['icms_situacao_tributaria'] = csosn


def _normalizar_cfop(cfop: str) -> str:
    return ''.join(c for c in (cfop or '') if c.isdigit())[:4]


def _resolver_cst_monofasico_combustivel(cfop: str, dados) -> str:
    from .nfe_catalog import (
        CFOPS_COMBUSTIVEL_REVENDA_CST61,
        CST_ICMS_ISENTO_NAO_TRIB_COMB,
        CST_ICMS_MONOFASICO_COMBUSTIVEL,
    )

    cst_cad = (dados.cst_icms if dados and dados.cst_icms else '').strip()
    if cst_cad in CST_ICMS_ISENTO_NAO_TRIB_COMB:
        return cst_cad
    if cst_cad in CST_ICMS_MONOFASICO_COMBUSTIVEL:
        return cst_cad
    cfop_d = _normalizar_cfop(cfop)
    if cfop_d in CFOPS_COMBUSTIVEL_REVENDA_CST61:
        return '61'
    return '61'


_RE_PESO_KG = re.compile(r'(\d+(?:[.,]\d+)?)\s*kg', re.I)
_RE_BOTIJAO_P = re.compile(r'(?:^|[^A-Za-z0-9])P\s*(0?8|10|13|20|45|90)(?:\b|[^0-9])', re.I)


def _peso_kg_do_rotulo(texto: str) -> float:
    """Extrai kg de 'GLP 13 kg', 'P13', 'P 45' etc. (botijão de GLP)."""
    t = (texto or '').strip()
    if not t:
        return 0.0
    m = _RE_PESO_KG.search(t)
    if m:
        return float(m.group(1).replace(',', '.'))
    m = _RE_BOTIJAO_P.search(t)
    if m:
        return float(m.group(1))
    return 0.0


def _quantidade_kg_monofasico(
    produto,
    *,
    quantidade: float,
    unidade: str,
    peso_liquido_nfe: float | None = None,
    codigo_anp: str = '',
) -> float:
    if peso_liquido_nfe and peso_liquido_nfe > 0:
        return float(peso_liquido_nfe)
    qtd = float(quantidade or 0)
    for attr in ('nome_venda', 'nome', 'codigo', 'codigo_barras'):
        kg_un = _peso_kg_do_rotulo(str(getattr(produto, attr, None) or ''))
        if kg_un > 0:
            return round(kg_un * qtd, 4)
    if (unidade or '').lower() in ('kg', 'kgs'):
        return qtd
    from .nfe_catalog import ANP_GLP_ORIGEM

    anp = (codigo_anp or '').strip()
    un = (unidade or '').strip().lower()
    if anp in ANP_GLP_ORIGEM and un in ('un', 'und', 'unid', 'un.', ''):
        return round(13.0 * qtd, 4)
    return 0.0


def _aplicar_icms_monofasico_combustivel(
    item: dict,
    *,
    cst: str,
    dados,
    qtd_kg: float,
) -> None:
    from .nfe_catalog import CST_ICMS_MONOFASICO_COMBUSTIVEL

    if cst not in CST_ICMS_MONOFASICO_COMBUSTIVEL:
        return
    item['icms_situacao_tributaria'] = cst
    item.pop('icms_aliquota', None)
    item.pop('icms_aliquota_ad_rem', None)
    if cst != '61':
        return
    ad_rem = dados.icms_aliquota_ad_rem if dados and dados.icms_aliquota_ad_rem else None
    if not ad_rem or float(ad_rem) <= 0:
        raise ValueError(
            'Produto sujeito à tributação monofásica (CST 61): cadastre a alíquota ICMS ad rem (R$/kg) '
            'no cadastro fiscal do produto.',
        )
    if qtd_kg <= 0:
        raise ValueError(
            'Informe o peso líquido (kg) na seção Transportador/volumes ou use produto com unidade kg / '
            'descrição com peso (ex.: GLP 13 kg). A quantidade tributada (qBCMonoRet) é obrigatória para CST 61.',
        )
    ad = float(Decimal(str(ad_rem)))
    qtd = float(Decimal(str(qtd_kg)))
    v_icms = float(
        (Decimal(str(qtd_kg)) * Decimal(str(ad_rem))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
    )
    item['icms_base_calculo_mono_retido'] = qtd
    item['icms_aliquota_retido'] = ad
    item['icms_valor_mono_retido'] = v_icms


def _aplicar_origens_combustivel_focus(item: dict, dados, *, uf_consumo: str) -> None:
    """
    origComb (LA18-20): obrigatório se pGNn ou pGNi != 0 no grupo combustível.
    pOrig deve totalizar 100 por indImport (LA21-20 para GLP), não confundir com % GN na mistura.
    """
    from .nfe_catalog import codigo_uf_ibge

    if not dados:
        return
    pct_gn_n = _dec(dados.pct_gn_nacional) if dados.pct_gn_nacional else 0.0
    pct_gn_i = _dec(dados.pct_gn_importado) if dados.pct_gn_importado else 0.0
    if pct_gn_n <= 0 and pct_gn_i <= 0:
        item.pop('origens_combustivel', None)
        return
    uf_ibge = codigo_uf_ibge(uf_consumo or 'RJ')
    origens: list[dict] = []
    if pct_gn_n > 0:
        origens.append({
            'indicador_importacao': '0',
            'uf_origem': uf_ibge,
            'percentual_originario_uf': 100.0,
        })
    if pct_gn_i > 0:
        origens.append({
            'indicador_importacao': '1',
            'uf_origem': uf_ibge,
            'percentual_originario_uf': 100.0,
        })
    item['origens_combustivel'] = origens


def _aplicar_unidade_tributavel_anp(
    item: dict,
    produto,
    dados,
    *,
    quantidade: float,
    peso_liquido_kg: float | None,
) -> None:
    """SEFAZ 854: uTrib do grupo comb deve bater com a tabela ANP (GLP = KG)."""
    from .nfe_catalog import unidade_tributavel_anp

    anp = (
        (dados.codigo_anp if dados else '')
        or item.get('combustivel_codigo_anp')
        or item.get('codigo_anp')
        or ''
    )
    u_anp = unidade_tributavel_anp(anp)
    item['unidade_comercial'] = _norm_unidade(item.get('unidade_comercial'))
    item['unidade_tributavel'] = _norm_unidade(item.get('unidade_tributavel'))
    if not u_anp:
        return
    item['unidade_tributavel'] = u_anp
    if u_anp != 'KG':
        return
    q_kg = _quantidade_kg_monofasico(
        produto,
        quantidade=float(quantidade),
        unidade=item.get('unidade_comercial') or 'UN',
        peso_liquido_nfe=peso_liquido_kg,
        codigo_anp=str(anp or ''),
    )
    if q_kg <= 0:
        return
    item['quantidade_tributavel'] = q_kg
    v_bruto = Decimal(str(item.get('valor_bruto') or 0))
    if v_bruto > 0:
        item['valor_unitario_tributavel'] = float(
            (v_bruto / Decimal(str(q_kg))).quantize(Decimal('0.0000000001'), rounding=ROUND_HALF_UP),
        )


def _aplicar_grupo_combustivel_focus(item: dict, dados, *, cfop: str, uf_consumo: str) -> None:
    from .nfe_catalog import cfop_exige_grupo_combustivel

    cfop_d = ''.join(c for c in (cfop or '') if c.isdigit())[:4]
    anp = (dados.codigo_anp if dados else '').strip()
    if cfop_exige_grupo_combustivel(cfop_d) and not anp:
        raise ValueError(
            f'CFOP {cfop_d} é de combustível: cadastre código ANP e descrição ANP no cadastro fiscal do produto.',
        )
    if not anp:
        return
    desc = ((dados.descricao_anp if dados else '') or 'GLP').strip()[:95]
    uf = (uf_consumo or getattr(dados, 'uf', '') or 'RJ').strip().upper()[:2]
    item['combustivel_codigo_anp'] = anp
    item['combustivel_descricao_anp'] = desc
    item['combustivel_sigla_uf'] = uf
    if dados.pct_glp:
        item['combustivel_percentual_glp'] = _dec(dados.pct_glp)
    if dados.pct_gn_nacional:
        item['combustivel_percentual_gas_natural_nacional'] = _dec(dados.pct_gn_nacional)
    if dados.pct_gn_importado:
        item['combustivel_percentual_gas_natural_importado'] = _dec(dados.pct_gn_importado)


CAMPOS_DADOS_FISCAIS_REPLICAR = (
    'tipo', 'ncm', 'cest', 'origem', 'unidade_tributavel',
    'codigo_servico', 'descricao_servico', 'nbs', 'codigo_class_trib', 'cst_ibs_cbs',
    'cfop_venda', 'cfop_interestadual', 'codigo_beneficio_fiscal',
    'csosn', 'cst_icms', 'cst_pis', 'cst_cofins',
    'aliquota_icms', 'aliquota_pis', 'aliquota_cofins',
    'codigo_anp', 'descricao_anp', 'icms_aliquota_ad_rem',
    'pct_glp', 'pct_gn_nacional', 'pct_gn_importado',
)


def replicar_dados_fiscais(origem: ProdutoDadosFiscais, destinos):
    """Copia os parâmetros fiscais de um produto para outros da mesma loja."""
    copiados = 0
    loja_id = origem.produto.loja_id
    for destino in destinos:
        if destino.pk == origem.pk:
            continue
        if destino.produto.loja_id != loja_id:
            continue
        for campo in CAMPOS_DADOS_FISCAIS_REPLICAR:
            setattr(destino, campo, getattr(origem, campo))
        destino.save()
        copiados += 1
    return copiados


def montar_item_focus_json(
    loja,
    produto,
    *,
    quantidade: float,
    preco_unitario: float,
    numero_item: int = 1,
    interestadual=False,
    cfop_override: str | None = None,
    uf_consumo: str = '',
    perfil_tributacao: str = 'produto',
    peso_liquido_kg: float | None = None,
    forcar_monofasico_combustivel: bool = False,
    valor_desconto: float = 0,
    valor_acrescimo: float = 0,
) -> dict:
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
    desc_item = round(max(float(valor_desconto or 0), 0), 2)
    acre_item = round(max(float(valor_acrescimo or 0), 0), 2)
    if desc_item > 0:
        item['valor_desconto'] = desc_item
    if acre_item > 0:
        item['valor_outras_despesas'] = acre_item
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
    if cfop_override:
        item['cfop'] = str(cfop_override).replace('.', '')[:4]
    cfop_item = _normalizar_cfop(item['cfop'])
    from .nfe_catalog import cfop_exige_grupo_combustivel, produto_sujeito_icms_monofasico

    anp = (dados.codigo_anp if dados else '') or ''
    monofasico = produto_sujeito_icms_monofasico(cfop_item, anp, ncm=trib['ncm'])
    if forcar_monofasico_combustivel and cfop_exige_grupo_combustivel(cfop_item) and not monofasico:
        raise ValueError(
            f'CFOP {cfop_item} exige produto de combustível: cadastre código ANP e alíquota ad rem no produto.',
        )
    if monofasico:
        from .nfe_catalog import CST_ICMS_ISENTO_NAO_TRIB_COMB

        cst_mono = _resolver_cst_monofasico_combustivel(cfop_item, dados)
        if cst_mono in CST_ICMS_ISENTO_NAO_TRIB_COMB:
            item['icms_situacao_tributaria'] = cst_mono
            item.pop('icms_aliquota', None)
        else:
            qtd_kg = _quantidade_kg_monofasico(
                produto,
                quantidade=qtd,
                unidade=trib['unidade'],
                peso_liquido_nfe=peso_liquido_kg,
                codigo_anp=anp,
            )
            _aplicar_icms_monofasico_combustivel(item, cst=cst_mono, dados=dados, qtd_kg=qtd_kg)
    else:
        aplicar_perfil_tributacao_item(item, perfil_tributacao)
    _aplicar_grupo_combustivel_focus(item, dados, cfop=item['cfop'], uf_consumo=uf_consumo)
    if monofasico:
        _aplicar_origens_combustivel_focus(item, dados, uf_consumo=uf_consumo)
    _aplicar_unidade_tributavel_anp(
        item, produto, dados,
        quantidade=qtd,
        peso_liquido_kg=peso_liquido_kg,
    )
    return item
