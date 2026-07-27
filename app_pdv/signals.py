from django.contrib.auth.signals import user_logged_in, user_login_failed
from django.dispatch import receiver

from .seguranca import (
    encerrar_outras_sessoes_web,
    invalidar_tokens_api,
    limpar_falhas_apos_sucesso,
    registrar_falha_login,
)


@receiver(user_login_failed)
def ao_falhar_login(sender, credentials, request, **kwargs):
    username = credentials.get('username') if credentials else ''
    registrar_falha_login(request, username)


@receiver(user_logged_in)
def ao_logar_com_sucesso(sender, request, user, **kwargs):
    limpar_falhas_apos_sucesso(request, user)
    if not user.is_superuser:
        invalidar_tokens_api(user)
        if request.session.session_key:
            encerrar_outras_sessoes_web(user, request.session.session_key)
    try:
        from .audit_log import registrar_log
        registrar_log(
            request, 'LOGIN',
            f'Login: {user.username}',
            modelo='User', objeto_id=user.id,
        )
    except Exception:
        pass
