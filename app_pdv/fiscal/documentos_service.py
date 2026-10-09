"""Listagem e somatório de documentos fiscais (período + filtros)."""
from __future__ import annotations

from datetime import datetime, time, timedelta
from decimal import Decimal

from django.db.models import Count, Sum
from django.utils import timezone

from .models import DocumentoFiscal


def _parse_date(value: str):
    value = (value or '').strip()
    if not value:
        return None
    for fmt in ('%Y-%m-%d', '%d/%m/%Y'):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def resolver_periodo(request) -> tuple[datetime, datetime, str, str, str]:
    """Retorna (início, fim, periodo_key, data_inicial_str, data_final_str) em TZ local."""
    tz = timezone.get_current_timezone()
    now = timezone.localtime(timezone.now(), tz)
    today = now.date()
    periodo = (request.GET.get('periodo') or 'mes_atual').strip() or 'mes_atual'
    di_str = (request.GET.get('data_inicial') or '').strip()
    df_str = (request.GET.get('data_final') or '').strip()

    def _start_end(d0, d1):
        start = timezone.make_aware(datetime.combine(d0, time.min), tz)
        end = timezone.make_aware(datetime.combine(d1, time.max), tz)
        return start, end

    if periodo == 'hoje':
        start, end = _start_end(today, today)
    elif periodo == 'ontem':
        ontem = today - timedelta(days=1)
        start, end = _start_end(ontem, ontem)
    elif periodo == '7dias':
        start, end = _start_end(today - timedelta(days=6), today)
    elif periodo == 'mes_anterior':
        first_this = today.replace(day=1)
        last_prev = first_this - timedelta(days=1)
        start, end = _start_end(last_prev.replace(day=1), last_prev)
    elif periodo == 'personalizado':
        d_ini = _parse_date(di_str) or today.replace(day=1)
        d_fim = _parse_date(df_str) or today
        if d_fim < d_ini:
            d_ini, d_fim = d_fim, d_ini
        start, end = _start_end(d_ini, d_fim)
        di_str = d_ini.isoformat()
        df_str = d_fim.isoformat()
    else:
        periodo = 'mes_atual'
        start, end = _start_end(today.replace(day=1), today)

    if periodo != 'personalizado':
        di_str = timezone.localtime(start, tz).date().isoformat()
        df_str = timezone.localtime(end, tz).date().isoformat()

    return start, end, periodo, di_str, df_str


def queryset_documentos_periodo(loja, *, start: datetime, end: datetime, tipo: str = '', status: str = ''):
    qs = (
        DocumentoFiscal.objects.filter(loja=loja, criado_em__gte=start, criado_em__lte=end)
        .select_related('venda', 'venda__cliente', 'produto_avulso', 'criado_por')
        .order_by('-criado_em')
    )
    if tipo:
        qs = qs.filter(tipo=tipo)
    if status:
        qs = qs.filter(status=status)
    return qs


def somatorio_documentos(qs) -> dict:
    """Agregados no mesmo recorte de filtros (tipo/status/período)."""
    base = qs
    total_docs = base.count()
    por_status = {
        row['status']: row['c']
        for row in base.values('status').annotate(c=Count('id'))
    }
    autorizados = por_status.get('autorizado', 0)
    cancelados = por_status.get('cancelado', 0)
    faturamento = base.filter(status='autorizado').aggregate(
        s=Sum('valor_total'),
    )['s'] or Decimal('0')
    taxa_entrega = base.filter(status='autorizado', venda__isnull=False).aggregate(
        s=Sum('venda__taxa_entrega'),
    )['s'] or Decimal('0')
    return {
        'total_documentos': total_docs,
        'autorizados': autorizados,
        'cancelados': cancelados,
        'faturamento': faturamento,
        'taxa_entrega': taxa_entrega,
    }


def cliente_documento(doc: DocumentoFiscal) -> str:
    venda = doc.venda
    if venda and venda.cliente_id:
        return (venda.cliente.nome or '')[:80]
    payload = doc.payload_envio if isinstance(doc.payload_envio, dict) else {}
    nome = (payload.get('nome_destinatario') or '').strip()
    if nome:
        return nome[:80]
    return '—'


def operador_documento(doc: DocumentoFiscal) -> str:
    if doc.criado_por_id:
        return (doc.criado_por.get_username() or doc.criado_por.email or '—')[:60]
    return '—'
