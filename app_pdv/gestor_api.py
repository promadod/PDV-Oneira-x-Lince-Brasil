"""
API do Painel Gestor (mobile) — agrega dashboard, relatórios e alertas.
"""
from datetime import datetime, timedelta
from decimal import Decimal

from django.db.models import Sum, Count, F, Value, DecimalField
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone

from .recompra_service import montar_ranking_recompra
from .models import (
    Venda,
    ItemVenda,
    ItemEstoque,
    Transacao,
    PagamentoFiado,
    Loja,
    montar_relatorio_pagamentos,
)

# Faturamento do painel: vendas comprometidas (exclui cancelado, aberto, orçamento)
GESTOR_STATUS_FATURAMENTO = ['FINALIZADO', 'RETIRADO_NA_LOJA', 'EM_PREPARACAO', 'FIADO']

_DECIMAL_ZERO = Value(0, output_field=DecimalField(max_digits=12, decimal_places=2))


def calcular_custo_mercadorias_periodo(lojas_alvo, data_ini, data_fim):
    """CMV do período: soma quantidade × custo (snapshot na venda ou preco_compra atual)."""
    from .models import STATUS_VENDA_FATURADA
    custo_efetivo = Coalesce(F('custo_unitario'), F('produto__preco_compra'), _DECIMAL_ZERO)
    total = ItemVenda.objects.filter(
        venda__loja__in=lojas_alvo,
        venda__data_venda__date__range=[data_ini, data_fim],
        venda__status__in=STATUS_VENDA_FATURADA,
    ).aggregate(
        custo=Sum(
            F('quantidade') * custo_efetivo,
            output_field=DecimalField(max_digits=14, decimal_places=2),
        )
    )['custo'] or Decimal('0')
    return total


class GestorAcessoNegado(Exception):
    pass


def usuario_pode_acessar_gestor(user):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    perfil = getattr(user, 'perfil', None)
    if not perfil:
        return False
    return perfil.perm_dashboard or perfil.perm_relatorios


def lojas_permitidas_gestor(user):
    if user.is_superuser:
        return Loja.objects.filter(ativo=True).order_by('nome')
    qs = user.lojas_gerenciadas.filter(ativo=True).order_by('nome')
    if qs.exists():
        return qs
    perfil = getattr(user, 'perfil', None)
    if perfil and perfil.loja_id:
        return Loja.objects.filter(id=perfil.loja_id, ativo=True)
    return Loja.objects.none()


def resolver_lojas_alvo(user, loja_id_param):
    permitidas = lojas_permitidas_gestor(user)
    if not permitidas.exists():
        raise GestorAcessoNegado('Nenhuma loja vinculada a este usuário.')
    if loja_id_param and str(loja_id_param).lower() != 'todas':
        try:
            lid = int(loja_id_param)
        except (TypeError, ValueError):
            raise GestorAcessoNegado('loja_id inválido.')
        alvo = permitidas.filter(id=lid)
        if not alvo.exists():
            raise GestorAcessoNegado('Loja não permitida.')
        return alvo, str(lid)
    return permitidas, 'todas'


def parse_periodo(periodo, data_inicio=None, data_fim=None):
    hoje = timezone.localdate()
    periodo = (periodo or 'hoje').lower()

    if periodo == 'hoje':
        return hoje, hoje, 'hoje'
    if periodo == 'ontem':
        ontem = hoje - timedelta(days=1)
        return ontem, ontem, 'ontem'
    if periodo in ('7d', '7dias', '7_dias'):
        return hoje - timedelta(days=6), hoje, '7d'
    if periodo in ('mes', 'mês', 'month'):
        return hoje.replace(day=1), hoje, 'mes'
    if periodo == 'custom' and data_inicio and data_fim:
        try:
            ini = datetime.strptime(data_inicio, '%Y-%m-%d').date()
            fim = datetime.strptime(data_fim, '%Y-%m-%d').date()
        except ValueError:
            raise ValueError('Datas inválidas. Use YYYY-MM-DD.')
        if ini > fim:
            ini, fim = fim, ini
        return ini, fim, 'custom'
    return hoje, hoje, 'hoje'


def _vendas_periodo(lojas_alvo, data_ini, data_fim):
    return Venda.objects.filter(
        loja__in=lojas_alvo,
        data_venda__date__range=[data_ini, data_fim],
        status__in=GESTOR_STATUS_FATURAMENTO,
    )


def _totais_vendas(qs):
    agg = qs.aggregate(total=Sum('total'), qtd=Count('id'))
    total = float(agg['total'] or 0)
    qtd = agg['qtd'] or 0
    ticket = round(total / qtd, 2) if qtd else 0.0
    return total, qtd, ticket


def calcular_fiado_aberto(lojas_alvo):
    vendas = Venda.objects.filter(
        loja__in=lojas_alvo,
        eh_fiado=True,
        status='FIADO',
    ).prefetch_related('pagamentos_fiado')
    total = Decimal('0')
    for v in vendas:
        total += v.saldo_devedor
    return float(total)


def montar_grafico_dias(lojas_alvo, data_fim, dias=7):
    data_ini = data_fim - timedelta(days=dias - 1)
    vendas = Venda.objects.filter(
        loja__in=lojas_alvo,
        data_venda__date__range=[data_ini, data_fim],
        status__in=GESTOR_STATUS_FATURAMENTO,
    ).annotate(dia=TruncDate('data_venda')).values('dia').annotate(
        total=Sum('total')
    ).order_by('dia')

    mapa = {v['dia']: float(v['total'] or 0) for v in vendas}
    pontos = []
    cursor = data_ini
    while cursor <= data_fim:
        pontos.append({
            'data': cursor.isoformat(),
            'label': cursor.strftime('%d/%m'),
            'total': mapa.get(cursor, 0.0),
        })
        cursor += timedelta(days=1)
    return pontos


def montar_por_loja(lojas_alvo, data_ini, data_fim):
    rows = _vendas_periodo(lojas_alvo, data_ini, data_fim).values(
        'loja_id', 'loja__nome', 'loja__nome_unidade'
    ).annotate(
        total=Sum('total'),
        qtd_vendas=Count('id'),
    ).order_by('-total')

    return [
        {
            'loja_id': r['loja_id'],
            'nome': r['loja__nome'],
            'nome_unidade': r['loja__nome_unidade'] or '',
            'total': float(r['total'] or 0),
            'qtd_vendas': r['qtd_vendas'],
        }
        for r in rows
    ]


def montar_por_pagamento(lojas_alvo, data_ini, data_fim):
    vendas = _vendas_periodo(lojas_alvo, data_ini, data_fim)
    multi = lojas_alvo.count() > 1
    lista, total_geral = montar_relatorio_pagamentos(lojas_alvo, vendas, multi_loja=multi)
    return [
        {
            'codigo': item.get('codigo', ''),
            'nome': item.get('nome', item.get('codigo', '')),
            'total': float(item.get('total', 0) or 0),
            'qtd': item.get('qtd', 0),
            'cor': item.get('cor', '#9c27b0'),
            'icone': item.get('icone', 'fa-wallet'),
        }
        for item in lista
    ], float(total_geral or 0)


def montar_ranking_entregadores(lojas_alvo, data_ini, data_fim, limite=10):
    rows = (
        _vendas_periodo(lojas_alvo, data_ini, data_fim)
        .filter(eh_entrega=True, entregador__isnull=False, status_entrega='ENTREGUE')
        .values('entregador_id', 'entregador__first_name', 'entregador__username')
        .annotate(qtd=Count('id'), total=Sum('total'))
        .order_by('-qtd')[:limite]
    )
    return [
        {
            'entregador_id': r['entregador_id'],
            'nome': (r['entregador__first_name'] or r['entregador__username'] or 'Motoboy'),
            'qtd_entregas': r['qtd'],
            'total_vendido': float(r['total'] or 0),
        }
        for r in rows
    ]


def montar_ranking_bairros(lojas_alvo, data_ini, data_fim, limite=10):
    vendas = (
        _vendas_periodo(lojas_alvo, data_ini, data_fim)
        .filter(eh_entrega=True)
        .select_related('cliente')
    )
    buckets = {}
    for v in vendas:
        bairro = 'Sem bairro'
        if v.cliente and v.cliente.bairro:
            bairro = v.cliente.bairro.strip() or 'Sem bairro'
        elif v.endereco_entrega:
            bairro = v.endereco_entrega.split(',')[-1].strip()[:80] or 'Sem bairro'
        if bairro not in buckets:
            buckets[bairro] = {'qtd': 0, 'total': 0.0}
        buckets[bairro]['qtd'] += 1
        buckets[bairro]['total'] += float(v.total or 0)

    ranking = sorted(
        [
            {'bairro': nome, 'qtd_pedidos': dados['qtd'], 'total': round(dados['total'], 2)}
            for nome, dados in buckets.items()
        ],
        key=lambda x: (-x['qtd_pedidos'], -x['total']),
    )
    return ranking[:limite]


def montar_financeiro(lojas_alvo, data_ini, data_fim):
    from .models import STATUS_VENDA_FATURADA
    total_vendas = Venda.objects.filter(
        loja__in=lojas_alvo,
        data_venda__date__range=[data_ini, data_fim],
        status__in=STATUS_VENDA_FATURADA,
        eh_fiado=False,
    ).aggregate(Sum('total'))['total__sum'] or 0

    receitas_fiado = PagamentoFiado.objects.filter(
        loja__in=lojas_alvo,
        data_pagamento__date__range=[data_ini, data_fim],
    ).aggregate(Sum('valor'))['valor__sum'] or 0

    transacoes = Transacao.objects.filter(
        loja__in=lojas_alvo,
        data__range=[data_ini, data_fim],
    )
    receitas_extras = transacoes.filter(categoria__tipo='RECEITA').aggregate(
        Sum('valor')
    )['valor__sum'] or 0
    despesas = transacoes.filter(categoria__tipo='DESPESA').aggregate(
        Sum('valor')
    )['valor__sum'] or 0

    custo_mercadorias = calcular_custo_mercadorias_periodo(lojas_alvo, data_ini, data_fim)
    custo_mercadorias_val = float(custo_mercadorias)
    total_receber = float(total_vendas + receitas_fiado + receitas_extras)
    total_pagar = float(despesas)
    lucro_liquido = round(total_receber - total_pagar - custo_mercadorias_val, 2)
    return {
        'receitas_vendas': float(total_vendas),
        'receitas_fiado': float(receitas_fiado),
        'receitas_extras': float(receitas_extras),
        'total_receber': total_receber,
        'total_pagar': total_pagar,
        'custo_mercadorias': custo_mercadorias_val,
        'saldo': lucro_liquido,
        'lucro_liquido': lucro_liquido,
    }


def montar_estoque_gestor(lojas_alvo):
    """Lista completa de estoque das lojas permitidas (espelha /estoque/ do PDV)."""
    itens = ItemEstoque.objects.filter(
        loja__in=lojas_alvo,
    ).select_related('loja').order_by('loja__nome', 'nome')

    multi_loja = lojas_alvo.count() > 1
    lista = []
    for item in itens:
        cheios = float(item.quantidade_estoque)
        entry = {
            'id': item.id,
            'nome': item.nome,
            'cheios': cheios,
            'unidade': item.unidade_medida,
            'estoque_baixo': cheios <= 10,
        }
        if multi_loja:
            entry['loja'] = item.loja.nome
            entry['loja_id'] = item.loja_id
        if item.loja.controla_vasilhame_vazio:
            entry['vazios'] = float(item.quantidade_vazios)
            entry['controla_vasilhame_vazio'] = True
        else:
            entry['controla_vasilhame_vazio'] = False
        lista.append(entry)

    return {
        'itens': lista,
        'total_itens': len(lista),
        'itens_baixo': sum(1 for i in lista if i['estoque_baixo']),
        'multi_loja': multi_loja,
    }


def montar_alertas(lojas_alvo):
    estoque_baixo = ItemEstoque.objects.filter(
        loja__in=lojas_alvo,
        quantidade_estoque__lte=10,
    ).order_by('quantidade_estoque')[:10]

    itens_estoque = []
    for item in estoque_baixo:
        entry = {
            'nome': item.nome,
            'cheios': float(item.quantidade_estoque),
        }
        if item.loja.controla_vasilhame_vazio:
            entry['vazios'] = float(item.quantidade_vazios)
        itens_estoque.append(entry)

    entregas_pendentes = Venda.objects.filter(
        loja__in=lojas_alvo,
        eh_entrega=True,
        status__in=GESTOR_STATUS_FATURAMENTO,
    ).exclude(
        status_entrega='ENTREGUE',
    ).count()

    return {
        'estoque_baixo': itens_estoque,
        'entregas_pendentes': entregas_pendentes,
    }


def montar_lista_lojas(lojas_permitidas):
    return [
        {
            'id': loja.id,
            'nome': loja.nome,
            'nome_unidade': loja.nome_unidade or '',
        }
        for loja in lojas_permitidas
    ]


def montar_resumo_gestor(user, loja_id_param='todas', periodo='hoje', data_inicio=None, data_fim=None):
    if not usuario_pode_acessar_gestor(user):
        raise GestorAcessoNegado('Sem permissão para o painel gestor.')

    lojas_alvo, loja_id_resolvido = resolver_lojas_alvo(user, loja_id_param)
    data_ini, data_fim_res, periodo_res = parse_periodo(periodo, data_inicio, data_fim)

    vendas_periodo = _vendas_periodo(lojas_alvo, data_ini, data_fim_res)
    fat_periodo, qtd, ticket = _totais_vendas(vendas_periodo)

    ontem = data_fim_res - timedelta(days=1)
    if periodo_res == 'hoje':
        fat_ontem, _, _ = _totais_vendas(_vendas_periodo(lojas_alvo, ontem, ontem))
    else:
        fat_ontem = None

    variacao_pct = None
    if fat_ontem is not None and fat_ontem > 0:
        variacao_pct = round(((fat_periodo - fat_ontem) / fat_ontem) * 100, 2)

    por_pagamento, _ = montar_por_pagamento(lojas_alvo, data_ini, data_fim_res)

    kpis = {
        'faturamento_periodo': fat_periodo,
        'faturamento_ontem': fat_ontem,
        'variacao_pct': variacao_pct,
        'vendas_qtd': qtd,
        'ticket_medio': ticket,
        'fiado_aberto': calcular_fiado_aberto(lojas_alvo),
    }
    if periodo_res == 'hoje':
        kpis['faturamento_hoje'] = fat_periodo
    elif periodo_res == 'ontem':
        kpis['faturamento_hoje'] = fat_periodo

    return {
        'periodo': periodo_res,
        'data_inicio': data_ini.isoformat(),
        'data_fim': data_fim_res.isoformat(),
        'loja_id': loja_id_resolvido,
        'lojas': montar_lista_lojas(lojas_permitidas_gestor(user)),
        'kpis': kpis,
        'grafico_7_dias': montar_grafico_dias(lojas_alvo, data_fim_res, dias=7),
        'por_loja': montar_por_loja(lojas_alvo, data_ini, data_fim_res),
        'por_pagamento': por_pagamento,
        'ranking_entregadores': montar_ranking_entregadores(lojas_alvo, data_ini, data_fim_res),
        'ranking_bairros': montar_ranking_bairros(lojas_alvo, data_ini, data_fim_res),
        'ranking_recompra': montar_ranking_recompra(lojas_alvo, limite=15),
        'financeiro': montar_financeiro(lojas_alvo, data_ini, data_fim_res),
        'alertas': montar_alertas(lojas_alvo),
    }


def _formatar_itens_venda(venda):
    partes = []
    for item in venda.itens.select_related('produto__item_estoque').all():
        qtd = item.quantidade
        ie = getattr(item.produto, 'item_estoque', None) if item.produto_id else None
        unidade = (ie.unidade_medida if ie else None) or 'UN'
        if unidade == 'UN':
            qtd_fmt = f"{int(qtd)}"
        else:
            qtd_fmt = f"{qtd:.3f}".rstrip('0').rstrip('.')
        partes.append(f"{qtd_fmt}x {item.produto.nome_venda}")
    return ', '.join(partes) if partes else '—'


def montar_vendas_gestor(user, loja_id_param='todas', periodo='hoje', data_inicio=None, data_fim=None, limite=50):
    if not usuario_pode_acessar_gestor(user):
        raise GestorAcessoNegado('Sem permissão para o painel gestor.')

    lojas_alvo, loja_id_resolvido = resolver_lojas_alvo(user, loja_id_param)
    data_ini, data_fim_res, periodo_res = parse_periodo(periodo, data_inicio, data_fim)

    vendas = _vendas_periodo(lojas_alvo, data_ini, data_fim_res).select_related(
        'cliente', 'loja'
    ).prefetch_related(
        'itens__produto__item_estoque'
    ).order_by('-data_venda')[:limite]

    lista = []
    for v in vendas:
        lista.append({
            'id': v.id,
            'data': timezone.localtime(v.data_venda).strftime('%d/%m/%Y %H:%M'),
            'cliente': v.cliente.nome if v.cliente else 'Consumidor Final',
            'loja': v.loja.nome,
            'itens_resumo': _formatar_itens_venda(v),
            'total': float(v.total or 0),
            'status': v.status,
            'status_label': v.get_status_display(),
            'forma_pagamento': v.get_nome_forma_pagamento() if v.forma_pagamento else '',
            'eh_fiado': v.eh_fiado,
        })

    return {
        'periodo': periodo_res,
        'data_inicio': data_ini.isoformat(),
        'data_fim': data_fim_res.isoformat(),
        'loja_id': loja_id_resolvido,
        'vendas': lista,
    }
