"""Controle de rate limit, congelamento de conta e sessão única."""
from datetime import timedelta

from django.contrib.auth.models import User
from django.contrib.sessions.models import Session
from django.utils import timezone

from .models import BloqueioIPLogin, PerfilUsuario

LIMITE_FALHAS_IP = 5
MINUTOS_BLOQUEIO_IP = 15
LIMITE_FALHAS_CONTA = 10


def obter_ip_cliente(request):
    """IP real atrás de proxy (PythonAnywhere, nginx, etc.)."""
    if request is None:
        return ''
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        return xff.split(',')[0].strip()
    xri = request.META.get('HTTP_X_REAL_IP')
    if xri:
        return xri.strip()
    return request.META.get('REMOTE_ADDR', '') or ''


def usuario_eh_superuser(username):
    if not username:
        return False
    return User.objects.filter(username__iexact=username.strip(), is_superuser=True).exists()


def _perfil(user):
    if not user or not user.is_authenticated:
        return None
    return getattr(user, 'perfil', None)


def usuario_pode_configurar_loja(user):
    """Dono/gestor com permissões completas (ou superuser) pode alterar flags da loja."""
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    perfil = _perfil(user)
    if not perfil or not perfil.loja_id:
        return False
    return all([
        perfil.perm_dashboard,
        perfil.perm_pdv,
        perfil.perm_caixa,
        perfil.perm_estoque,
        perfil.perm_relatorios,
        perfil.perm_usuarios,
    ])


def conta_congelada_username(username):
    if not username or usuario_eh_superuser(username):
        return False
    user = User.objects.filter(username__iexact=username.strip()).select_related('perfil').first()
    if not user or user.is_superuser:
        return False
    perfil = _perfil(user)
    return bool(perfil and perfil.conta_congelada)


def conta_congelada_user(user):
    if not user or user.is_superuser:
        return False
    perfil = _perfil(user)
    return bool(perfil and perfil.conta_congelada)


def ip_bloqueado(ip):
    if not ip:
        return False
    reg = BloqueioIPLogin.objects.filter(ip=ip).first()
    if not reg:
        return False
    if reg.bloqueado_ate and reg.bloqueado_ate <= timezone.now():
        reg.tentativas = 0
        reg.bloqueado_ate = None
        reg.save(update_fields=['tentativas', 'bloqueado_ate'])
        return False
    return reg.esta_bloqueado


def minutos_restantes_bloqueio_ip(ip):
    reg = BloqueioIPLogin.objects.filter(ip=ip).first()
    if not reg or not reg.bloqueado_ate:
        return 0
    delta = reg.bloqueado_ate - timezone.now()
    return max(0, int(delta.total_seconds() // 60) + 1)


def registrar_falha_login(request, username):
    """Incrementa contadores de IP e conta (superusuário isento)."""
    username = (username or '').strip()
    if usuario_eh_superuser(username):
        return

    ip = obter_ip_cliente(request)
    if ip:
        reg, _ = BloqueioIPLogin.objects.get_or_create(ip=ip, defaults={'tentativas': 0})
        reg.tentativas += 1
        reg.ultimo_usuario_tentado = username[:150]
        reg.ultima_tentativa = timezone.now()
        if reg.tentativas >= LIMITE_FALHAS_IP:
            reg.bloqueado_ate = timezone.now() + timedelta(minutes=MINUTOS_BLOQUEIO_IP)
        reg.save()

    user = User.objects.filter(username__iexact=username).first()
    if user and not user.is_superuser:
        perfil, _ = PerfilUsuario.objects.get_or_create(user=user)
        perfil.tentativas_login_falhas += 1
        if perfil.tentativas_login_falhas >= LIMITE_FALHAS_CONTA and not perfil.conta_congelada:
            perfil.conta_congelada = True
            perfil.congelada_em = timezone.now()
            perfil.motivo_congelamento = (
                f'{LIMITE_FALHAS_CONTA} tentativas de login inválidas. '
                'Conta congelada por segurança.'
            )
        perfil.save()


def limpar_falhas_apos_sucesso(request, user):
    if user.is_superuser:
        return
    ip = obter_ip_cliente(request)
    if ip:
        BloqueioIPLogin.objects.filter(ip=ip).update(
            tentativas=0, bloqueado_ate=None, observacao=''
        )
    perfil = _perfil(user)
    if perfil:
        perfil.tentativas_login_falhas = 0
        perfil.save(update_fields=['tentativas_login_falhas'])


def liberar_ip(ip):
    BloqueioIPLogin.objects.filter(ip=ip).delete()


def descongelar_conta(user):
    perfil = _perfil(user)
    if not perfil:
        return
    perfil.conta_congelada = False
    perfil.motivo_congelamento = ''
    perfil.congelada_em = None
    perfil.tentativas_login_falhas = 0
    perfil.save()


def encerrar_outras_sessoes_web(user, session_key_atual=None):
    """Invalida sessões Django anteriores (sessão única web)."""
    if user.is_superuser:
        return
    perfil = _perfil(user)
    if not perfil:
        return
    if perfil.session_key_ativa and perfil.session_key_ativa != session_key_atual:
        Session.objects.filter(session_key=perfil.session_key_ativa).delete()
    if session_key_atual:
        perfil.session_key_ativa = session_key_atual
        perfil.save(update_fields=['session_key_ativa'])


def registrar_token_ativo(user, token_key):
    """Guarda token válido para sessão única na API mobile."""
    if user.is_superuser:
        return
    perfil = _perfil(user)
    if perfil:
        perfil.token_ativo = token_key
        perfil.save(update_fields=['token_ativo'])


def invalidar_sessao_web(user):
    """Encerra sessão web ativa (ex.: login novo via API mobile)."""
    if user.is_superuser:
        return
    perfil = _perfil(user)
    if perfil and perfil.session_key_ativa:
        Session.objects.filter(session_key=perfil.session_key_ativa).delete()
        perfil.session_key_ativa = None
        perfil.save(update_fields=['session_key_ativa'])


def invalidar_tokens_api(user):
    from rest_framework.authtoken.models import Token
    Token.objects.filter(user=user).delete()
    perfil = _perfil(user)
    if perfil:
        perfil.token_ativo = None
        perfil.save(update_fields=['token_ativo'])


def token_api_valido(user, token_key):
    if user.is_superuser:
        return True
    perfil = _perfil(user)
    if not perfil or not perfil.token_ativo:
        return True
    return perfil.token_ativo == token_key
