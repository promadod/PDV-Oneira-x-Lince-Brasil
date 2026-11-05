"""Relatórios do módulo fiscal (dados PDV + documentos Focus)."""
from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from io import StringIO

from django.db.models import Count, F, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from app_pdv.models import ItemVenda, Venda

from .models import DocumentoFiscal, NFeRecebida

RELATORIOS_FISCAIS = [
    ('compras', 'Compras', 'NF-e recebidas / entradas registradas'),
    ('resumo-compras', 'Resumo das compras', 'Totais por emitente no período'),
    ('resumo-documentos', 'Resumo NF-e / NFC-e / SAT', 'Documentos emitidos por tipo'),
    ('documentos-detalhado', 'NF-e / NFC-e / SAT detalhado', 'Lista completa de documentos'),
    ('resumo-nfse', 'Resumo NFS-e', 'Notas de serviço emitidas'),
    ('movimentacao-produtos', 'Movimentação dos produtos', 'Itens vendidos no PDV'),
    ('tributos', 'Tributos', 'Indicadores a partir dos documentos fiscais'),
    ('resumo-vendas', 'Resumo de vendas', 'Vendas finalizadas no período'),
    ('resumo-vendas-pis-cofins', 'Resumo de vendas PIS/COFINS', 'Base estimada sobre vendas'),
    ('devolucao-compras', 'Devolução — Compras', 'Devoluções de entrada (manifestação)'),
    ('sped-efd', 'SPED Fiscal — EFD', 'Exportação auxiliar para escrituração'),
    ('sintegra', 'SINTEGRA', 'Exportação auxiliar Sintegra'),
]


def periodo_bounds(data_de: date | None, data_ate: date | None) -> tuple[datetime, datetime]:
    hoje = timezone.localdate()
    de = data_de or date(hoje.year, hoje.month, 1)
    ate = data_ate or hoje
    tz = timezone.get_current_timezone()
    ini = timezone.make_aware(datetime.combine(de, time.min), tz)
    fim = timezone.make_aware(datetime.combine(ate, time.max), tz)
    return ini, fim


def gerar_relatorio(loja, slug: str, *, data_de=None, data_ate=None) -> dict:
    ini, fim = periodo_bounds(data_de, data_ate)
    ctx = {
        'slug': slug,
        'data_de': data_de or ini.date(),
        'data_ate': data_ate or fim.date(),
        'titulo': next((t for s, t, _ in RELATORIOS_FISCAIS if s == slug), slug),
    }

    if slug == 'compras':
        qs = NFeRecebida.objects.filter(loja=loja, criado_em__range=(ini, fim)).order_by('-data_emissao', '-id')
        ctx['linhas'] = list(qs[:500])
        ctx['total'] = qs.aggregate(s=Sum('valor_total'))['s'] or Decimal('0')
        return ctx

    if slug == 'resumo-compras':
        qs = (
            NFeRecebida.objects.filter(loja=loja, criado_em__range=(ini, fim))
            .values('cnpj_emitente', 'nome_emitente')
            .annotate(qtd=Count('id'), total=Sum('valor_total'))
            .order_by('-total')
        )
        ctx['linhas'] = list(qs)
        return ctx

    if slug in ('resumo-documentos', 'documentos-detalhado', 'tributos'):
        docs = DocumentoFiscal.objects.filter(loja=loja, criado_em__range=(ini, fim)).order_by('-criado_em')
        if slug == 'resumo-documentos':
            por_tipo = (
                docs.values('tipo', 'status')
                .annotate(qtd=Count('id'), total=Sum('valor_total'))
                .order_by('tipo', 'status')
            )
            ctx['linhas'] = list(por_tipo)
            ctx['sat_qtd'] = 0
            ctx['sat_total'] = Decimal('0')
        elif slug == 'documentos-detalhado':
            ctx['linhas'] = list(docs[:1000])
        else:
            autorizados = docs.filter(status='autorizado')
            ctx['linhas'] = list(
                autorizados.values('tipo').annotate(qtd=Count('id'), total=Sum('valor_total')),
            )
            ctx['total_autorizado'] = autorizados.aggregate(s=Sum('valor_total'))['s'] or Decimal('0')
        return ctx

    if slug == 'resumo-nfse':
        docs = DocumentoFiscal.objects.filter(
            loja=loja,
            tipo__in=('nfse', 'nfse_nacional'),
            criado_em__range=(ini, fim),
        )
        ctx['linhas'] = list(
            docs.values('tipo', 'status').annotate(qtd=Count('id'), total=Sum('valor_total')),
        )
        ctx['detalhe'] = list(docs.order_by('-criado_em')[:200])
        return ctx

    if slug == 'movimentacao-produtos':
        itens = (
            ItemVenda.objects.filter(
                venda__loja=loja,
                venda__data_venda__range=(ini, fim),
                venda__status__in=('FINALIZADO', 'RETIRADO_NA_LOJA'),
            )
            .values('produto__nome_venda', 'produto_id')
            .annotate(qtd=Sum('quantidade'), total=Sum(F('quantidade') * F('preco_unitario')))
            .order_by('produto__nome_venda')
        )
        ctx['linhas'] = list(itens)
        return ctx

    if slug == 'resumo-vendas':
        vendas = Venda.objects.filter(
            loja=loja,
            data_venda__range=(ini, fim),
            status__in=('FINALIZADO', 'RETIRADO_NA_LOJA'),
        )
        por_dia = (
            vendas.annotate(dia=TruncDate('data_venda'))
            .values('dia')
            .annotate(qtd=Count('id'), total=Sum('total'))
            .order_by('dia')
        )
        ctx['linhas'] = list(por_dia)
        ctx['total'] = vendas.aggregate(s=Sum('total'))['s'] or Decimal('0')
        ctx['qtd'] = vendas.count()
        return ctx

    if slug == 'resumo-vendas-pis-cofins':
        vendas = Venda.objects.filter(
            loja=loja,
            data_venda__range=(ini, fim),
            status__in=('FINALIZADO', 'RETIRADO_NA_LOJA'),
        )
        total = vendas.aggregate(s=Sum('total'))['s'] or Decimal('0')
        pis = (total * Decimal('0.0065')).quantize(Decimal('0.01'))
        cofins = (total * Decimal('0.03')).quantize(Decimal('0.01'))
        ctx['base'] = total
        ctx['pis'] = pis
        ctx['cofins'] = cofins
        ctx['observacao'] = (
            'Valores estimados (PIS 0,65% e COFINS 3% sobre receita). '
            'Ajuste conforme regime e matriz tributária da loja.'
        )
        return ctx

    if slug == 'devolucao-compras':
        qs = NFeRecebida.objects.filter(
            loja=loja,
            criado_em__range=(ini, fim),
            manifestacao__in=('desconhecimento', 'nao_realizada'),
        ).order_by('-criado_em')
        ctx['linhas'] = list(qs)
        return ctx

    if slug in ('sped-efd', 'sintegra'):
        docs = DocumentoFiscal.objects.filter(
            loja=loja,
            status='autorizado',
            criado_em__range=(ini, fim),
        ).order_by('criado_em')
        buf = StringIO()
        buf.write(f'# {slug.upper()} — exportação auxiliar Oneira\n')
        buf.write(f'# Loja: {loja.nome}\n')
        buf.write(f'# Período: {ctx["data_de"]} a {ctx["data_ate"]}\n')
        buf.write('# Registros baseados em documentos autorizados no sistema.\n')
        for d in docs:
            buf.write(
                f'{d.chave_acesso or d.ref};{d.get_tipo_display()};{d.numero};{d.serie};'
                f'{d.valor_total};{d.criado_em.date()}\n',
            )
        ctx['arquivo_texto'] = buf.getvalue()
        ctx['nome_arquivo'] = f'{slug}_{loja.id}_{ctx["data_de"]}_{ctx["data_ate"]}.txt'
        return ctx

    ctx['erro'] = 'Relatório não encontrado.'
    return ctx
