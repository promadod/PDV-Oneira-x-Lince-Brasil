from django.shortcuts import redirect
from django.urls import reverse
from django.contrib.auth import logout
from django.contrib import messages
from django.contrib.auth.models import AnonymousUser
from django.http import JsonResponse
from .assinatura import (
    loja_do_usuario,
    loja_esta_bloqueada,
    payload_assinatura_bloqueada,
)
from .seguranca import (
    conta_congelada_username,
    ip_bloqueado,
    minutos_restantes_bloqueio_ip,
    obter_ip_cliente,
    usuario_eh_superuser,
)


def _usuario_da_requisicao(request):
    """
    Session (web) ou Authorization: Token … (app gestor / API).
    DRF só autentica o token na view; o middleware precisa resolver sozinho.
    """
    user = getattr(request, 'user', None)
    if user is not None and user.is_authenticated:
        return user

    auth = request.META.get('HTTP_AUTHORIZATION', '') or ''
    if not auth.lower().startswith('token '):
        return user if user is not None else AnonymousUser()

    key = auth.split(' ', 1)[1].strip()
    if not key:
        return AnonymousUser()

    from rest_framework.authtoken.models import Token

    try:
        return Token.objects.select_related('user', 'user__perfil', 'user__perfil__loja').get(
            key=key
        ).user
    except Token.DoesNotExist:
        return AnonymousUser()


class BloqueioPagamentoMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def _resposta_bloqueio(self, request, loja):
        # App gestor (React/Vercel) e demais clientes de API: JSON, não redirect HTML
        if request.path.startswith('/api/'):
            return JsonResponse(payload_assinatura_bloqueada(loja), status=403)
        return redirect('assinatura_bloqueada')

    def __call__(self, request):
        user = _usuario_da_requisicao(request)

        # 1. Se não estiver logado, libera
        if not user.is_authenticated:
            return self.get_response(request)

        # 2. Se for Superuser, libera
        if user.is_superuser:
            return self.get_response(request)

        # 3. URLs liberadas (NÃO liberar /api/ inteiro — o app gestor deve respeitar o bloqueio)
        urls_liberadas = [
            reverse('logout'),
            reverse('assinatura_bloqueada'),
            '/admin/',
            '/static/',
            '/media/',
            '/api/login/',  # login trata assinatura em CustomAuthToken
        ]

        for url in urls_liberadas:
            if request.path.startswith(url):
                return self.get_response(request)

        # 4. Verifica a Loja
        try:
            loja = loja_do_usuario(user)
            if loja:
                loja.registrar_acesso()
                if loja_esta_bloqueada(loja):
                    return self._resposta_bloqueio(request, loja)
        except Exception as e:
            print(f"Erro Middleware: {e}")

        return self.get_response(request)


class LoginProtecaoMiddleware:
    """Bloqueia tentativas de login quando IP está em cooldown (superusuário isento)."""

    ROTAS_LOGIN = ('/accounts/login/', '/api/login/')

    def __init__(self, get_response):
        self.get_response = get_response

    def _extrair_username(self, request):
        username = (request.POST.get('username') or '').strip()
        if username:
            return username
        if request.path == '/api/login/' and request.body:
            import json
            try:
                body = json.loads(request.body.decode('utf-8'))
                return (body.get('username') or '').strip()
            except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
                pass
        return ''

    def __call__(self, request):
        if request.method == 'POST' and request.path in self.ROTAS_LOGIN:
            username = self._extrair_username(request)

            if not usuario_eh_superuser(username):
                ip = obter_ip_cliente(request)
                if ip_bloqueado(ip):
                    mins = minutos_restantes_bloqueio_ip(ip)
                    msg = (
                        f'Muitas tentativas de login. IP bloqueado por {mins} minuto(s). '
                        'Contate o administrador se precisar de acesso imediato.'
                    )
                    if request.path == '/api/login/':
                        return JsonResponse({'erro': msg, 'bloqueio_ip': True}, status=429)
                    messages.error(request, msg)
                    return redirect('login')

                if conta_congelada_username(username):
                    msg = (
                        'Conta congelada por segurança. '
                        'Solicite ao administrador do sistema para descongelar.'
                    )
                    if request.path == '/api/login/':
                        return JsonResponse({'erro': msg, 'conta_congelada': True}, status=403)
                    messages.error(request, msg)
                    return redirect('login')

        return self.get_response(request)


class SessaoUnicaMiddleware:
    """Encerra sessão web se login foi feito em outro navegador (superusuário isento)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and not request.user.is_superuser:
            urls_liberadas = (
                reverse('logout'),
                '/admin/',
                '/static/',
                '/media/',
                '/accounts/login/',
            )
            if not any(request.path.startswith(u) for u in urls_liberadas):
                perfil = getattr(request.user, 'perfil', None)
                sk = request.session.session_key
                if perfil and perfil.session_key_ativa and sk and perfil.session_key_ativa != sk:
                    logout(request)
                    messages.warning(
                        request,
                        'Sessão encerrada: sua conta foi acessada em outro dispositivo.',
                    )
                    return redirect('login')

        return self.get_response(request)
