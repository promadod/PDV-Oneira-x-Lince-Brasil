"""Montagem de payloads JSON conforme API Focus NFe (v2)."""
from __future__ import annotations

import copy
from decimal import Decimal

from django.utils import timezone

from .models import FiscalConfig
from .produto_fiscal import montar_item_focus_json, resolver_regra

# Códigos internos PDV → tabela SEFAZ (forma_pagamento)
_MAP_FORMA_PAGAMENTO = {
    'DINHEIRO': '01',
    'PIX': '17',
    'CREDITO': '03',
    'DEBITO': '04',
    'CORTESIA': '90',
    'FIADO': '99',
}


def _digits(value: str) -> str:
    return ''.join(c for c in (value or '') if c.isdigit())


def _map_forma_pagamento(codigo: str | None) -> str:
    if not codigo:
        return '99'
    key = (codigo or '').strip().upper()
    return _MAP_FORMA_PAGAMENTO.get(key, '99')


def _formas_pagamento_venda(venda) -> list[dict]:
    from app_pdv.models import LiquidacaoVenda

    linhas = []
    if venda.pagamento_dividido:
        for liq in LiquidacaoVenda.objects.filter(venda=venda).order_by('id'):
            linhas.append({
                'forma_pagamento': _map_forma_pagamento(liq.meio_liquidacao),
                'valor_pagamento': float(liq.valor),
            })
    if not linhas:
        codigo = venda.meio_liquidacao or venda.forma_pagamento
        linhas.append({
            'forma_pagamento': _map_forma_pagamento(codigo),
            'valor_pagamento': float(venda.total or 0),
        })
    return linhas


def montar_payload_nfce(cfg: FiscalConfig, loja, venda) -> dict:
    """Payload mínimo válido para POST /v2/nfce?ref=… (Focus)."""
    if not venda:
        raise ValueError('NFC-e exige uma venda vinculada.')

    cnpj = _digits(cfg.cnpj or loja.cnpj)
    if len(cnpj) != 14:
        raise ValueError('CNPJ do emitente inválido ou não configurado.')

    tz = timezone.get_current_timezone()
    agora = timezone.localtime(timezone.now(), tz)
    data_emissao = agora.isoformat(timespec='seconds')

    items = []
    from app_pdv.models import ItemVenda

    for idx, item in enumerate(
        ItemVenda.objects.filter(venda=venda).select_related('produto'),
        start=1,
    ):
        items.append(
            montar_item_focus_json(
                loja, item.produto,
                quantidade=float(item.quantidade),
                preco_unitario=float(item.preco_unitario),
                numero_item=idx,
            )
        )

    if not items:
        raise ValueError('A venda não possui itens para emitir NFC-e.')

    payload = {
        'cnpj_emitente': cnpj,
        'data_emissao': data_emissao,
        'natureza_operacao': 'VENDA AO CONSUMIDOR',
        'presenca_comprador': '1',
        'modalidade_frete': '9',
        'local_destino': '1',
        'indicador_inscricao_estadual_destinatario': '9',
        'items': items,
        'formas_pagamento': _formas_pagamento_venda(venda),
    }
    # Série/número: controle automático no painel da API (não enviar no JSON — Focus).
    return payload


def _aplicar_destinatario_nfce(payload: dict, *, cpf: str = '', cnpj: str = '', nome: str = ''):
    cpf_d = _digits(cpf)
    cnpj_d = _digits(cnpj)
    nome = (nome or '').strip()[:60]
    if len(cpf_d) == 11:
        payload['cpf_destinatario'] = cpf_d
        if nome:
            payload['nome_destinatario'] = nome
        payload['indicador_inscricao_estadual_destinatario'] = '9'
    elif len(cnpj_d) == 14:
        payload['cnpj_destinatario'] = cnpj_d
        if nome:
            payload['nome_destinatario'] = nome
        payload['indicador_inscricao_estadual_destinatario'] = '9'


def montar_payload_nfce_avulso(
    cfg: FiscalConfig,
    loja,
    produto,
    *,
    quantidade: float,
    preco_unitario: float,
    forma_pagamento: str = '99',
    interestadual: bool = False,
    valor_desconto: float = 0,
    valor_acrescimo: float = 0,
    cpf_destinatario: str = '',
    cnpj_destinatario: str = '',
    nome_destinatario: str = '',
) -> dict:
    """NFC-e avulsa — um produto (padrão NetFiscal / balcão sem venda PDV)."""
    cnpj = _digits(cfg.cnpj or loja.cnpj)
    if len(cnpj) != 14:
        raise ValueError('CNPJ do emitente inválido ou não configurado.')
    tz = timezone.get_current_timezone()
    data_emissao = timezone.localtime(timezone.now(), tz).isoformat(timespec='seconds')
    item = montar_item_focus_json(
        loja, produto,
        quantidade=quantidade,
        preco_unitario=preco_unitario,
        numero_item=1,
        interestadual=interestadual,
    )
    bruto = round(float(quantidade) * float(preco_unitario), 2)
    desconto = round(max(float(valor_desconto or 0), 0), 2)
    acrescimo = round(max(float(valor_acrescimo or 0), 0), 2)
    total = round(max(bruto - desconto + acrescimo, 0.01), 2)
    payload = {
        'cnpj_emitente': cnpj,
        'data_emissao': data_emissao,
        'natureza_operacao': 'VENDA AO CONSUMIDOR',
        'presenca_comprador': '1',
        'modalidade_frete': '9',
        'local_destino': '2' if interestadual else '1',
        'indicador_inscricao_estadual_destinatario': '9',
        'items': [item],
        'formas_pagamento': [{'forma_pagamento': forma_pagamento, 'valor_pagamento': total}],
    }
    if desconto > 0:
        payload['valor_desconto'] = desconto
    if acrescimo > 0:
        payload['valor_outras_despesas'] = acrescimo
    _aplicar_destinatario_nfce(
        payload,
        cpf=cpf_destinatario,
        cnpj=cnpj_destinatario,
        nome=nome_destinatario,
    )
    return payload


def _aplicar_ie_destinatario_nfe(payload: dict, dados: dict, *, destinatario_cnpj: bool):
    """indIEDest + IE conforme MOC NF-e (Focus: inscricao_estadual_destinatario)."""
    if not destinatario_cnpj:
        payload['indicador_inscricao_estadual_destinatario'] = '9'
        payload.pop('inscricao_estadual_destinatario', None)
        return
    ind = str(dados.get('indicador_ie_destinatario') or '9').strip()
    ie_raw = (dados.get('inscricao_estadual_destinatario') or '').strip()
    ie_digits = ''.join(c for c in ie_raw if c.isdigit())
    if ind == '1':
        if not ie_digits:
            raise ValueError(
                'Informe a Inscrição Estadual (IE) do destinatário ou selecione '
                '“Isento de IE” / “Não contribuinte”.',
            )
        payload['indicador_inscricao_estadual_destinatario'] = '1'
        payload['inscricao_estadual_destinatario'] = ie_digits[:14]
    elif ind == '2':
        payload['indicador_inscricao_estadual_destinatario'] = '2'
        payload.pop('inscricao_estadual_destinatario', None)
    else:
        payload['indicador_inscricao_estadual_destinatario'] = '9'
        payload.pop('inscricao_estadual_destinatario', None)


def _aplicar_endereco_destinatario_nfe(payload: dict, dados: dict):
    logradouro = (dados.get('logradouro') or '').strip()
    bairro = (dados.get('bairro') or '').strip()
    municipio = (dados.get('municipio') or '').strip()
    uf = (dados.get('uf') or '').strip().upper()[:2]
    cep = _digits(dados.get('cep') or '')
    if not logradouro or not bairro or not municipio or len(uf) != 2 or len(cep) != 8:
        raise ValueError(
            'Endereço completo do destinatário é obrigatório (CEP, logradouro, número, bairro, município e UF).',
        )
    payload['logradouro_destinatario'] = logradouro[:60]
    payload['numero_destinatario'] = str(dados.get('numero') or 'S/N')[:10]
    compl = (dados.get('complemento') or '').strip()
    if compl:
        payload['complemento_destinatario'] = compl[:60]
    payload['bairro_destinatario'] = bairro[:60]
    payload['municipio_destinatario'] = municipio[:60]
    payload['uf_destinatario'] = uf
    payload['cep_destinatario'] = cep
    ibge = _digits(dados.get('codigo_municipio') or '')
    if len(ibge) == 7:
        payload['codigo_municipio_destinatario'] = ibge


def montar_payload_nfe_de_venda(cfg: FiscalConfig, loja, venda) -> dict:
    payload = montar_payload_nfce(cfg, loja, venda)
    payload['natureza_operacao'] = payload.get('natureza_operacao') or 'VENDA'
    payload['modalidade_frete'] = '9'
    payload['local_destino'] = '1'
    cliente = getattr(venda, 'cliente', None)
    if cliente:
        cpf = _digits(getattr(cliente, 'cpf', '') or '')
        cnpj = _digits(getattr(cliente, 'cnpj', '') or '')
        nome = (getattr(cliente, 'nome', '') or getattr(cliente, 'razao_social', '') or '')[:60]
        endereco_dados = {
            'logradouro': getattr(cliente, 'endereco', '') or '',
            'numero': 'S/N',
            'bairro': getattr(cliente, 'bairro', '') or '',
            'municipio': getattr(cliente, 'cidade', '') or getattr(loja, 'municipio', '') or '',
            'uf': getattr(cliente, 'uf', '') or getattr(loja, 'uf', '') or '',
            'cep': getattr(cliente, 'cep', '') or '',
        }
        if len(cnpj) == 14:
            payload['cnpj_destinatario'] = cnpj
            payload['nome_destinatario'] = nome
            _aplicar_ie_destinatario_nfe(payload, endereco_dados, destinatario_cnpj=True)
            _aplicar_endereco_destinatario_nfe(payload, endereco_dados)
        elif len(cpf) == 11:
            payload['cpf_destinatario'] = cpf
            payload['nome_destinatario'] = nome
            _aplicar_ie_destinatario_nfe(payload, endereco_dados, destinatario_cnpj=False)
            _aplicar_endereco_destinatario_nfe(payload, endereco_dados)
    return payload


def _inferir_consumidor_final(dados: dict) -> str:
    from .nfe_catalog import cfop_sugere_consumidor_final

    cfop = ''.join(c for c in str(dados.get('cfop') or '') if c.isdigit())[:4]
    ind_ie = str(dados.get('indicador_ie_destinatario') or '9')
    if cfop_sugere_consumidor_final(cfop) == '1':
        return '1'
    if ind_ie == '9':
        return '1'
    return '0'


def _peso_liquido_de_payload(payload: dict, item: dict | None = None) -> float:
    vols = payload.get('volumes') or []
    if vols:
        pl = float(vols[0].get('peso_liquido') or 0)
        if pl > 0:
            return pl
    if item:
        pl = float(item.get('icms_base_calculo_mono_retido') or 0)
        if pl > 0:
            return pl
    return 0.0


def reenriquecer_payload_nfe_reemissao(loja, payload: dict) -> dict:
    """
    Reconstrói itens da NF-e (ICMS monofásico CST 61, combustível, etc.).
    Usado na reemissão para não reenviar JSON antigo com CSOSN 102 (rejeição 960).
    """
    from app_pdv.models import Produto

    from .nfe_catalog import cfop_exige_grupo_combustivel
    from .produto_fiscal import montar_item_focus_json

    p = copy.deepcopy(payload)
    items = p.get('items') or []
    if not items:
        return p
    uf = (p.get('uf_destinatario') or 'RJ')[:2]
    peso_l = _peso_liquido_de_payload(p, items[0])
    for idx, item in enumerate(items):
        cfop = ''.join(c for c in str(item.get('cfop') or '') if c.isdigit())[:4]
        pid = item.get('codigo_produto')
        produto = None
        if pid:
            produto = Produto.objects.filter(pk=int(pid), loja=loja).select_related('dados_fiscais').first()
        if not produto:
            continue
        qtd = float(item.get('quantidade_comercial') or item.get('quantidade') or 1)
        v_unit = float(item.get('valor_unitario_comercial') or item.get('valor_unitario') or 0)
        if v_unit <= 0 and qtd > 0:
            bruto = float(item.get('valor_bruto') or 0)
            if bruto > 0:
                v_unit = round(bruto / qtd, 2)
        trib = 'cst_61_combustivel' if cfop_exige_grupo_combustivel(cfop) else 'produto'
        pl_item = peso_l or _peso_liquido_de_payload(p, item)
        p['items'][idx] = montar_item_focus_json(
            loja,
            produto,
            quantidade=qtd,
            preco_unitario=v_unit,
            numero_item=int(item.get('numero_item') or idx + 1),
            cfop_override=cfop or None,
            uf_consumo=uf,
            perfil_tributacao=trib,
            peso_liquido_kg=pl_item or None,
            forcar_monofasico_combustivel=True,
        )
    tz = timezone.get_current_timezone()
    p['data_emissao'] = timezone.localtime(timezone.now(), tz).isoformat(timespec='seconds')
    p.pop('serie', None)
    p.pop('numero', None)
    if not p.get('consumidor_final'):
        cfop0 = ''.join(c for c in str(items[0].get('cfop') or '') if c.isdigit())[:4]
        p['consumidor_final'] = _inferir_consumidor_final({
            'cfop': cfop0,
            'indicador_ie_destinatario': p.get('indicador_inscricao_estadual_destinatario') or '9',
        })
    return p


def _aplicar_volumes_transporte(payload: dict, dados: dict) -> None:
    q_vol = int(dados.get('quantidade_volumes') or 0)
    peso_l = float(dados.get('peso_liquido') or 0)
    peso_b = float(dados.get('peso_bruto') or 0)
    if q_vol <= 0 and peso_l <= 0 and peso_b <= 0:
        return
    vol: dict = {}
    if q_vol > 0:
        vol['quantidade'] = q_vol
    elif peso_l > 0 or peso_b > 0:
        vol['quantidade'] = 1
    if peso_l > 0:
        vol['peso_liquido'] = round(peso_l, 3)
    if peso_b > 0:
        vol['peso_bruto'] = round(peso_b, 3)
    if vol:
        payload['volumes'] = [vol]


def montar_payload_nfe_form(cfg: FiscalConfig, loja, dados: dict) -> dict:
    """NF-e modelo 55 — destinatário + item (formulário dedicado)."""
    cnpj_emit = _digits(cfg.cnpj or loja.cnpj)
    if len(cnpj_emit) != 14:
        raise ValueError('CNPJ do emitente inválido ou não configurado.')
    produto = dados['produto']
    qtd = float(dados['quantidade'])
    v_unit = float(dados['preco_unitario'])
    perfil_trib = dados.get('tributacao') or dados.get('tributacao_nfe') or 'produto'
    item = montar_item_focus_json(
        loja, produto,
        quantidade=qtd,
        preco_unitario=v_unit,
        numero_item=1,
        interestadual=False,
        cfop_override=dados.get('cfop'),
        uf_consumo=(dados.get('uf') or '')[:2],
        perfil_tributacao=perfil_trib,
        peso_liquido_kg=float(dados.get('peso_liquido') or 0) or None,
        forcar_monofasico_combustivel=True,
    )
    bruto = round(qtd * v_unit, 2)
    desconto = round(max(float(dados.get('valor_desconto') or 0), 0), 2)
    acrescimo = round(max(float(dados.get('valor_acrescimo') or 0), 0), 2)
    total = round(max(bruto - desconto + acrescimo, 0.01), 2)
    tz = timezone.get_current_timezone()
    data_emissao = timezone.localtime(timezone.now(), tz).isoformat(timespec='seconds')
    cnpj_dest = _digits(dados.get('cnpj_destinatario') or '')
    cpf_dest = _digits(dados.get('cpf_destinatario') or '')
    payload = {
        'cnpj_emitente': cnpj_emit,
        'data_emissao': data_emissao,
        'natureza_operacao': (dados.get('natureza_operacao') or 'VENDA')[:60],
        'tipo_documento': '1',
        'finalidade_emissao': dados.get('finalidade_emissao') or '1',
        'consumidor_final': dados.get('consumidor_final') or _inferir_consumidor_final(dados),
        'presenca_comprador': dados.get('presenca_comprador') or '1',
        'modalidade_frete': dados.get('modalidade_frete') or '9',
        'local_destino': '1',
        'items': [item],
        'formas_pagamento': [{
            'forma_pagamento': dados.get('forma_pagamento') or '99',
            'valor_pagamento': total,
        }],
    }
    if desconto > 0:
        payload['valor_desconto'] = desconto
    if acrescimo > 0:
        payload['valor_outras_despesas'] = acrescimo
    frete = round(max(float(dados.get('valor_frete') or 0), 0), 2)
    if frete > 0:
        payload['valor_frete'] = frete
    nome_dest = (dados.get('nome_destinatario') or '').strip()[:60]
    if len(cnpj_dest) == 14:
        payload['cnpj_destinatario'] = cnpj_dest
        payload['nome_destinatario'] = nome_dest or 'DESTINATARIO'
        _aplicar_ie_destinatario_nfe(payload, dados, destinatario_cnpj=True)
    elif len(cpf_dest) == 11:
        payload['cpf_destinatario'] = cpf_dest
        payload['nome_destinatario'] = nome_dest or 'CONSUMIDOR'
        _aplicar_ie_destinatario_nfe(payload, dados, destinatario_cnpj=False)
    else:
        raise ValueError('Informe CPF ou CNPJ do destinatário para NF-e.')
    _aplicar_endereco_destinatario_nfe(payload, dados)
    _aplicar_volumes_transporte(payload, dados)
    return payload


def montar_payload_emissao(cfg: FiscalConfig, loja, *, tipo: str, venda=None, avulso=None) -> dict:
    if avulso:
        produto = avulso['produto']
        return montar_payload_nfce_avulso(
            cfg, loja, produto,
            quantidade=avulso['quantidade'],
            preco_unitario=avulso['preco_unitario'],
            forma_pagamento=avulso.get('forma_pagamento', '99'),
            interestadual=avulso.get('interestadual', False),
            valor_desconto=avulso.get('valor_desconto', 0),
            valor_acrescimo=avulso.get('valor_acrescimo', 0),
            cpf_destinatario=avulso.get('cpf_destinatario', ''),
            cnpj_destinatario=avulso.get('cnpj_destinatario', ''),
            nome_destinatario=avulso.get('nome_destinatario', ''),
        )
    if tipo == 'nfce':
        return montar_payload_nfce(cfg, loja, venda)
    if tipo == 'nfe':
        if venda:
            return montar_payload_nfe_de_venda(cfg, loja, venda)
        raise ValueError('NF-e exige venda vinculada ou emissão pelo formulário NF-e.')
    # NFS-e: corpo específico por município — mantém snapshot até implementação dedicada
    from .services import montar_snapshot_itens

    snapshot = montar_snapshot_itens(loja, venda) if venda else {'itens': []}
    valor = Decimal(str(venda.total)) if venda else Decimal('0')
    return {
        'cnpj_emitente': _digits(cfg.cnpj or getattr(loja, 'cnpj', '')),
        'valor_total': float(valor),
        'itens': snapshot.get('itens', []),
    }
