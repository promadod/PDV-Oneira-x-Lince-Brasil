"""Montagem de payloads JSON conforme API Focus NFe (v2)."""
from __future__ import annotations

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
            payload['indicador_inscricao_estadual_destinatario'] = '9'
            _aplicar_endereco_destinatario_nfe(payload, endereco_dados)
        elif len(cpf) == 11:
            payload['cpf_destinatario'] = cpf
            payload['nome_destinatario'] = nome
            payload['indicador_inscricao_estadual_destinatario'] = '9'
            _aplicar_endereco_destinatario_nfe(payload, endereco_dados)
    return payload


def montar_payload_nfe_form(cfg: FiscalConfig, loja, dados: dict) -> dict:
    """NF-e modelo 55 — destinatário + item (formulário dedicado)."""
    cnpj_emit = _digits(cfg.cnpj or loja.cnpj)
    if len(cnpj_emit) != 14:
        raise ValueError('CNPJ do emitente inválido ou não configurado.')
    produto = dados['produto']
    qtd = float(dados['quantidade'])
    v_unit = float(dados['preco_unitario'])
    item = montar_item_focus_json(
        loja, produto,
        quantidade=qtd,
        preco_unitario=v_unit,
        numero_item=1,
        interestadual=False,
    )
    if dados.get('cfop'):
        item['cfop'] = str(dados['cfop']).replace('.', '')[:4]
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
    nome_dest = (dados.get('nome_destinatario') or '').strip()[:60]
    if len(cnpj_dest) == 14:
        payload['cnpj_destinatario'] = cnpj_dest
        payload['nome_destinatario'] = nome_dest or 'DESTINATARIO'
        payload['indicador_inscricao_estadual_destinatario'] = dados.get('ie_destinatario') or '9'
    elif len(cpf_dest) == 11:
        payload['cpf_destinatario'] = cpf_dest
        payload['nome_destinatario'] = nome_dest or 'CONSUMIDOR'
        payload['indicador_inscricao_estadual_destinatario'] = '9'
    else:
        raise ValueError('Informe CPF ou CNPJ do destinatário para NF-e.')
    _aplicar_endereco_destinatario_nfe(payload, dados)
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
