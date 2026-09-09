from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect


def loja_fiscal_habilitada(loja):
    return bool(loja and getattr(loja, 'fiscal_habilitado', False))


def usuario_pode_fiscal(user):
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    perfil = getattr(user, 'perfil', None)
    return bool(perfil and getattr(perfil, 'perm_fiscal', False))


def requer_acesso_fiscal(view_func):
    """Exige login, loja com módulo fiscal ativo e perm_fiscal (ou superuser)."""

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        from app_pdv.views import check_loja

        loja = check_loja(request)
        if not loja:
            return redirect('admin:index')
        if not loja_fiscal_habilitada(loja):
            messages.warning(
                request,
                'O módulo fiscal não está habilitado para esta loja. Contate o suporte Oneira.',
            )
            return redirect('dashboard')
        if not usuario_pode_fiscal(request.user):
            messages.error(request, 'Você não tem permissão para acessar o módulo fiscal.')
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)

    return _wrapped
