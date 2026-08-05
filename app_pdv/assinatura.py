"""Helpers de bloqueio de assinatura (web + API/app gestor)."""


def loja_esta_bloqueada(loja):
    """True se a loja deve impedir acesso (status ou vencimento + tolerância)."""
    if not loja:
        return False
    esta_vencido = loja.verificar_bloqueio()
    # verificar_bloqueio pode atualizar status_assinatura em memória/banco
    return loja.status_assinatura == 'BLOQUEADO' or esta_vencido


def payload_assinatura_bloqueada(loja, mensagem=None):
    """JSON padrão para o app gestor / clientes de API."""
    nome = getattr(loja, 'nome', None) or 'sua loja'
    msg = mensagem or (
        f'Olá, {nome}. Identificamos uma pendência na sua assinatura. '
        'Para continuar usando o sistema, regularize sua conta.'
    )
    data_venc = getattr(loja, 'data_vencimento', None)
    valor = getattr(loja, 'valor_mensalidade', None)
    return {
        'erro': msg,
        'assinatura_bloqueada': True,
        'loja': {
            'nome': nome,
            'data_vencimento': data_venc.isoformat() if data_venc else None,
            'valor_mensalidade': str(valor) if valor is not None else None,
            'link_pagamento_atual': getattr(loja, 'link_pagamento_atual', None) or '',
        },
    }


def loja_do_usuario(user):
    perfil = getattr(user, 'perfil', None)
    if not perfil:
        return None
    return getattr(perfil, 'loja', None)
