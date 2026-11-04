from django.contrib.admin.models import ADDITION, CHANGE, DELETION, LogEntry
from django.contrib.auth.signals import user_logged_in, user_login_failed
from django.db.models.signals import post_save
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


_ADMIN_FLAG_LABEL = {
    ADDITION: 'criou',
    CHANGE: 'alterou',
    DELETION: 'excluiu',
}


@receiver(post_save, sender=LogEntry)
def registrar_acao_django_admin(sender, instance, created, **kwargs):
    """Espelha o histórico do Django Admin na Central de Logs."""
    if not created:
        return
    modelo = ''
    try:
        ct = instance.content_type
        modelo = ct.model_class().__name__ if ct and ct.model_class() else (ct.model if ct else '')
    except Exception:
        modelo = ''
    if modelo in ('LogAuditoria', 'LogEntry'):
        return
    try:
        detalhe = instance.get_change_message() or ''
    except Exception:
        detalhe = instance.change_message or ''
    verbo = _ADMIN_FLAG_LABEL.get(instance.action_flag, 'registrou')
    descricao = f'[Django Admin] {verbo} {modelo or "registro"}: {instance.object_repr}'
    if detalhe and detalhe not in descricao:
        descricao = f'{descricao} — {detalhe}'
    loja = _loja_do_log_admin(instance, modelo)
    objeto_id = None
    try:
        if instance.object_id:
            objeto_id = int(instance.object_id)
    except (TypeError, ValueError):
        objeto_id = None
    from .models import LogAuditoria
    LogAuditoria.objects.create(
        usuario=instance.user if instance.user_id else None,
        loja=loja,
        acao='ADMIN',
        modelo=modelo or 'Admin',
        objeto_id=objeto_id,
        descricao=descricao[:2000],
        ip=None,
    )


def _loja_do_log_admin(entry, modelo):
    from .models import Loja

    try:
        pk = int(entry.object_id) if entry.object_id else None
    except (TypeError, ValueError):
        return None
    if not pk:
        return None
    if modelo == 'Loja':
        return Loja.objects.filter(pk=pk).first()
    try:
        ct = entry.content_type
        cls = ct.model_class() if ct else None
        if cls is None:
            return None
        obj = cls.objects.filter(pk=pk).first()
        if obj is None:
            return None
        if isinstance(obj, Loja):
            return obj
        loja_id = getattr(obj, 'loja_id', None)
        if loja_id:
            return Loja.objects.filter(pk=loja_id).first()
        perfil = getattr(obj, 'perfil', None)
        if perfil is not None:
            return getattr(perfil, 'loja', None)
    except Exception:
        return None
    return None
