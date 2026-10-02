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
    if cfg.serie_nfce:
        payload['serie'] = str(cfg.serie_nfce)
    if cfg.proximo_numero_nfce:
        payload['numero'] = str(cfg.proximo_numero_nfce)
    return payload


def montar_payload_nfce_avulso(
    cfg: FiscalConfig,
    loja,
    produto,
    *,
    quantidade: float,
    preco_unitario: float,
    forma_pagamento: str = '99',
    interestadual: bool = False,
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
    total = round(float(quantidade) * float(preco_unitario), 2)
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
    if cfg.serie_nfce:
        payload['serie'] = str(cfg.serie_nfce)
    if cfg.proximo_numero_nfce:
        payload['numero'] = str(cfg.proximo_numero_nfce)
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
        )
    if tipo == 'nfce':
        return montar_payload_nfce(cfg, loja, venda)
    if tipo == 'nfe':
        base = montar_payload_nfce(cfg, loja, venda) if venda else {}
        base['serie'] = str(cfg.serie_nfe)
        if cfg.proximo_numero_nfe:
            base['numero'] = str(cfg.proximo_numero_nfe)
        return base
    # NFS-e: corpo específico por município — mantém snapshot até implementação dedicada
    from .services import montar_snapshot_itens

    snapshot = montar_snapshot_itens(loja, venda) if venda else {'itens': []}
    valor = Decimal(str(venda.total)) if venda else Decimal('0')
    return {
        'cnpj_emitente': _digits(cfg.cnpj or getattr(loja, 'cnpj', '')),
        'valor_total': float(valor),
        'itens': snapshot.get('itens', []),
    }
