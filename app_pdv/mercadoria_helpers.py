"""Helpers do relatório CMV / agendamento de pagamento de mercadorias."""
from decimal import Decimal

from django.utils import timezone
from django.utils.timezone import localtime

from .models import (
    EntradaEstoque,
    ParcelaMercadoriaAgendada,
    saldo_agendavel_entrada,
    total_parcelas_agendadas_entrada,
)


def listar_entradas_abertas_cmv(lojas_cmv):
    qs = (
        EntradaEstoque.objects.filter(
            loja__in=lojas_cmv,
            status_pagamento__in=['PENDENTE', 'PARCIAL'],
        )
        .select_related('item', 'fornecedor', 'loja')
        .order_by('data_entrada')
    )
    lista = []
    for e in qs:
        lista.append({
            'entrada': e,
            'id': e.id,
            'item': e.item.nome,
            'fornecedor': e.fornecedor.nome if e.fornecedor_id else '—',
            'loja': e.loja.nome,
            'data_entrada': localtime(e.data_entrada).strftime('%d/%m/%Y'),
            'quantidade': e.quantidade,
            'valor_total': e.valor_total,
            'valor_pago': e.valor_pago,
            'saldo_a_pagar': e.saldo_a_pagar,
            'saldo_agendavel': saldo_agendavel_entrada(e),
            'total_agendado': total_parcelas_agendadas_entrada(e),
            'status': e.status_pagamento,
            'status_label': e.get_status_pagamento_display(),
        })
    return lista


def listar_parcelas_mercadoria(lojas_cmv, data_inicio, data_fim, status=None, busca=None):
    qs = (
        ParcelaMercadoriaAgendada.objects.filter(
            loja__in=lojas_cmv,
            data_vencimento__range=[data_inicio, data_fim],
        )
        .select_related('entrada__item', 'entrada__fornecedor', 'loja')
        .order_by('data_vencimento', 'entrada__item__nome')
    )

    status_filtro = (status or '').strip().upper()
    if status_filtro in ('AGENDADO', 'PAGO', 'CANCELADO'):
        qs = qs.filter(status=status_filtro)
    elif status_filtro == 'ATRASADA':
        qs = qs.filter(status='AGENDADO', data_vencimento__lt=timezone.localdate())

    busca_txt = (busca or '').strip()
    if busca_txt:
        from django.db.models import Q
        qs = qs.filter(
            Q(entrada__item__nome__icontains=busca_txt)
            | Q(entrada__fornecedor__nome__icontains=busca_txt)
            | Q(entrada__id__icontains=busca_txt)
        )

    lista = []
    total_agendado = Decimal('0')
    total_atrasado = Decimal('0')
    total_pago = Decimal('0')

    for p in qs:
        atrasada = p.esta_atrasada
        if p.status == 'AGENDADO':
            total_agendado += p.valor
            if atrasada:
                total_atrasado += p.valor
        elif p.status == 'PAGO':
            total_pago += p.valor
        fornecedor = '—'
        if p.entrada.fornecedor_id:
            fornecedor = p.entrada.fornecedor.nome
        lista.append({
            'parcela': p,
            'id': p.id,
            'status': p.status,
            'status_label': p.get_status_display(),
            'entrada_id': p.entrada_id,
            'item': p.entrada.item.nome,
            'fornecedor': fornecedor,
            'entrada': localtime(p.data_entrada).strftime('%d/%m/%Y %H:%M'),
            'vencimento': p.data_vencimento.strftime('%d/%m/%Y'),
            'vencimento_iso': p.data_vencimento.isoformat(),
            'valor': p.valor,
            'atrasada': atrasada,
            'loja': p.loja.nome,
        })

    return lista, {
        'qtd': len(lista),
        'total_agendado': total_agendado,
        'total_atrasado': total_atrasado,
        'total_pago': total_pago,
    }
