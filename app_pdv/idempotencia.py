"""Idempotência de operações críticas (ex.: salvar venda) contra clique duplo / retry."""
from __future__ import annotations

from typing import Optional, Tuple

from django.db import IntegrityError, transaction

from .models import IdempotenciaOperacao


def normalizar_chave(chave) -> str:
    if not chave:
        return ''
    return str(chave).strip()[:64]


def reivindicar(loja, endpoint: str, chave, usuario=None) -> Tuple[bool, Optional[dict]]:
    """
    Reserva a chave antes de processar.
    Retorna (True, None) se pode processar; (False, resposta) se já existe.
    """
    chave = normalizar_chave(chave)
    if not chave:
        return True, None

    try:
        with transaction.atomic():
            IdempotenciaOperacao.objects.create(
                loja=loja,
                endpoint=endpoint,
                chave=chave,
                usuario=usuario if getattr(usuario, 'is_authenticated', False) else None,
                resposta={},
            )
        return True, None
    except IntegrityError:
        row = IdempotenciaOperacao.objects.filter(
            loja=loja, endpoint=endpoint, chave=chave
        ).first()
        if row and isinstance(row.resposta, dict) and row.resposta.get('status'):
            return False, row.resposta
        return False, {
            'status': 'erro',
            'mensagem': 'Operação já em andamento. Aguarde alguns segundos e não clique novamente.',
        }


def concluir(loja, endpoint: str, chave, resposta: dict) -> None:
    chave = normalizar_chave(chave)
    if not chave or not isinstance(resposta, dict):
        return
    IdempotenciaOperacao.objects.filter(
        loja=loja, endpoint=endpoint, chave=chave
    ).update(resposta=resposta)


def liberar(loja, endpoint: str, chave) -> None:
    """Remove a reserva para permitir nova tentativa após erro."""
    chave = normalizar_chave(chave)
    if not chave:
        return
    IdempotenciaOperacao.objects.filter(
        loja=loja, endpoint=endpoint, chave=chave
    ).delete()
