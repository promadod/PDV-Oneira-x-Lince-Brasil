"""Ranking de acompanhamento de recompra por produto."""
from django.db.models import Max
from django.utils import timezone

from .models import Produto, ItemVenda
from .whatsapp_service import gerar_link_whatsapp


def montar_ranking_recompra(lojas_alvo, limite=30):
    hoje = timezone.localdate()
    produtos = Produto.objects.filter(
        loja__in=lojas_alvo,
        rastrear_recompra=True,
        dias_recompra__isnull=False,
        ativo=True,
    ).select_related('loja')

    resultado = []
    for produto in produtos:
        dias_limite = produto.dias_recompra
        agregados = (
            ItemVenda.objects.filter(
                produto=produto,
                venda__status__in=['FINALIZADO', 'RETIRADO_NA_LOJA'],
                venda__cliente__isnull=False,
            )
            .values(
                'venda__cliente_id',
                'venda__cliente__nome',
                'venda__cliente__whatsapp',
                'venda__cliente__telefone',
                'venda__cliente__bairro',
            )
            .annotate(ultima=Max('venda__data_venda__date'))
        )
        for row in agregados:
            if not row['ultima']:
                continue
            dias_sem = (hoje - row['ultima']).days
            if dias_sem < dias_limite:
                continue
            telefone = row['venda__cliente__whatsapp'] or row['venda__cliente__telefone']
            template = produto.mensagem_recompra or (
                'Olá {cliente}, sua {produto} está acabando. Gostaria de fazer um novo pedido?'
            )
            msg = (
                template.replace('{cliente}', row['venda__cliente__nome'] or '')
                .replace('{produto}', produto.nome_venda)
                .replace('{dias}', str(dias_sem))
            )
            resultado.append({
                'cliente_id': row['venda__cliente_id'],
                'cliente': row['venda__cliente__nome'],
                'bairro': row['venda__cliente__bairro'] or '—',
                'produto': produto.nome_venda,
                'produto_id': produto.id,
                'loja': produto.loja.nome,
                'dias_sem_compra': dias_sem,
                'dias_limite': dias_limite,
                'ultima_compra': row['ultima'].strftime('%d/%m/%Y'),
                'whatsapp_link': gerar_link_whatsapp(telefone, msg),
            })

    resultado.sort(key=lambda x: (-x['dias_sem_compra'], x['cliente']))
    return resultado[:limite]
