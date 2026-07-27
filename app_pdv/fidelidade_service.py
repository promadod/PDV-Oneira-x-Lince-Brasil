"""Plano de fidelidade — progresso, promoção e desconto."""
from decimal import Decimal

from .models import Cliente, Produto


def obter_config_fidelidade(loja):
    if not loja.fidelidade_ativa:
        return None
    return {
        'ativa': True,
        'tipo_meta': loja.fidelidade_tipo_meta,
        'meta': float(loja.fidelidade_meta or 0),
        'desconto_pct': float(loja.fidelidade_desconto_pct or 0),
    }


def status_fidelidade_cliente(cliente, loja):
    cfg = obter_config_fidelidade(loja)
    if not cfg or not cliente:
        return {
            'ativa': False,
            'progresso': 0,
            'meta': 0,
            'tipo_meta': 'PRODUTOS',
            'desconto_pct': 0,
            'promocao_disponivel': False,
            'percentual_progresso': 0,
        }
    meta = Decimal(str(cfg['meta']))
    progresso = Decimal(str(cliente.progresso_fidelidade or 0))
    pct = float((progresso / meta * 100) if meta > 0 else 0)
    return {
        'ativa': True,
        'progresso': float(progresso),
        'meta': float(meta),
        'tipo_meta': cfg['tipo_meta'],
        'desconto_pct': cfg['desconto_pct'],
        'promocao_disponivel': bool(cliente.promocao_fidelidade_ativa),
        'percentual_progresso': min(round(pct, 1), 100),
    }


def listar_acompanhamento_fidelidade(loja):
    """Clientes com progresso no plano de fidelidade."""
    cfg = obter_config_fidelidade(loja)
    if not cfg:
        return []
    meta = Decimal(str(cfg['meta']))
    clientes = Cliente.objects.filter(loja=loja).order_by('-progresso_fidelidade', 'nome')
    lista = []
    for c in clientes:
        prog = Decimal(str(c.progresso_fidelidade or 0))
        falta = max(meta - prog, Decimal('0'))
        lista.append({
            'id': c.id,
            'nome': c.nome,
            'progresso': float(prog),
            'meta': float(meta),
            'falta': float(falta),
            'tipo_meta': cfg['tipo_meta'],
            'promocao_disponivel': c.promocao_fidelidade_ativa,
            'percentual': min(float(prog / meta * 100) if meta > 0 else 0, 100),
        })
    return lista


def calcular_desconto_fidelidade(cliente, loja, total_produtos, usar_promocao=False):
    if not usar_promocao or not cliente or not cliente.promocao_fidelidade_ativa:
        return Decimal('0')
    cfg = obter_config_fidelidade(loja)
    if not cfg:
        return Decimal('0')
    pct = Decimal(str(cfg['desconto_pct']))
    return (Decimal(str(total_produtos)) * pct / Decimal('100')).quantize(Decimal('0.01'))


def registrar_progresso_fidelidade(venda):
    """Atualiza progresso do cliente ao finalizar venda."""
    if venda.status not in ('FINALIZADO', 'RETIRADO_NA_LOJA') or not venda.cliente:
        return
    loja = venda.loja
    if not loja.fidelidade_ativa:
        return

    cliente = venda.cliente
    meta = Decimal(str(loja.fidelidade_meta or 0))
    if meta <= 0:
        return

    if loja.fidelidade_tipo_meta == 'PONTOS':
        incremento = Decimal(str(venda.total or 0))
    else:
        incremento = sum(
            (item.quantidade for item in venda.itens.all()),
            Decimal('0'),
        )

    if venda.observacao and 'FIDELIDADE: promoção utilizada' in venda.observacao:
        cliente.promocao_fidelidade_ativa = False
        cliente.progresso_fidelidade = Decimal('0')
    else:
        cliente.progresso_fidelidade = Decimal(str(cliente.progresso_fidelidade or 0)) + incremento
        if cliente.progresso_fidelidade >= meta:
            cliente.promocao_fidelidade_ativa = True
            cliente.progresso_fidelidade = meta

    cliente.save(update_fields=['progresso_fidelidade', 'promocao_fidelidade_ativa'])
