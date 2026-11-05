"""Listagem e somatório de documentos fiscais (período + filtros)."""
from __future__ import annotations

from datetime import datetime, time, timedelta
from decimal import Decimal

from django.db.models import F, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from .models import DocumentoFiscal

# Documentos considerados autorizados nos cards (alinhado à exibição na tabela).
_Q_AUTORIZADO = (
    Q(status='autorizado')
    | Q(status__iexact='autorizada')
    | Q(payload_retorno__status__iexact='autorizado')
    | Q(payload_retorno__status__iexact='autorizada')
    | (
        Q(chave_acesso__gt='')
        & Q(status_sefaz__in=['100', '150'])
        & ~Q(status__in=['cancelado', 'denegado'])
    )
)


def documento_status_efetivo(doc: DocumentoFiscal) -> str:
    """Status para pill da listagem (inclui notas já autorizadas na SEFAZ com status local desatualizado)."""
    payload = doc.payload_retorno if isinstance(doc.payload_retorno, dict) else {}
    ps = (payload.get('status') or '').lower().strip()
    if ps in ('autorizado', 'autorizada'):
        return 'autorizado'
    s = (doc.status or 'rascunho').strip().lower()
    if s in ('autorizado', 'autorizada'):
        return 'autorizado'
    if doc.chave_acesso and (doc.status_sefaz or '').strip() in ('100', '150'):
        if s not in ('cancelado', 'denegado'):
            return 'autorizado'
    return s


def documento_status_rotulo(doc: DocumentoFiscal) -> str:
    rotulos = dict(DocumentoFiscal.STATUS_CHOICES)
    chave = documento_status_efetivo(doc)
    return rotulos.get(chave, chave.replace('_', ' ').title())


def _queryset_agregacao(qs):
    """Agregações sem select_related/order_by (evita contagem distorcida em joins)."""
    return DocumentoFiscal.objects.filter(pk__in=qs.values_list('pk', flat=True))


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
    ag = _queryset_agregacao(qs)
    total_docs = ag.count()
    autorizados_qs = ag.filter(_Q_AUTORIZADO)
    autorizados = autorizados_qs.count()
    cancelados = ag.filter(status='cancelado').count()
    faturamento = autorizados_qs.aggregate(s=Sum('valor_total'))['s'] or Decimal('0')
    zero = Value(Decimal('0'))
    total_taxas = autorizados_qs.filter(venda__isnull=False).aggregate(
        s=Sum(
            Coalesce(F('venda__taxa_entrega'), zero)
            + Coalesce(F('venda__taxa_servico'), zero),
        ),
    )['s'] or Decimal('0')
    return {
        'total_documentos': total_docs,
        'autorizados': autorizados,
        'cancelados': cancelados,
        'faturamento': faturamento,
        'total_taxas': total_taxas,
        'taxa_entrega': total_taxas,
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
