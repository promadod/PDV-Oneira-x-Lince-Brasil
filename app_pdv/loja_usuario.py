"""Usuário padrão criado junto com uma loja nova."""
import re

from django.contrib.auth.models import User
from django.utils.text import slugify

SENHA_PADRAO_NOVA_LOJA = 'mudar123'

PERMISSOES_USUARIO_PADRAO_LOJA = {
    'perm_dashboard': True,
    'perm_pdv': True,
    'perm_caixa': True,
    'perm_torre': True,
    'perm_estoque': True,
    'perm_relatorios': True,
    'perm_usuarios': True,
    'perm_fiscal': True,
    'perm_fiscal_config': True,
    'usuario_padrao_loja': True,
}


def username_from_loja_nome(nome, loja_id=None):
    bruto = (nome or '').strip().lower()
    if re.fullmatch(r'[a-z0-9.@+-]+', bruto):
        base = bruto
    else:
        base = slugify(bruto, allow_unicode=False)
    base = re.sub(r'[^a-z0-9.@+]', '', base)[:150]
    if not base:
        base = f'loja{loja_id}' if loja_id else 'loja'
    candidato = base
    n = 1
    while User.objects.filter(username=candidato).exists():
        n += 1
        extra = f'-{n}'
        candidato = f'{base[:max(1, 150 - len(extra))]}{extra}'
        if n > 100:
            break
    return candidato[:150]


def criar_usuario_padrao_loja(loja):
    """Cria o operador da loja (login = nome da loja, senha padrão, permissões de gestor)."""
    from .models import PerfilUsuario

    if not loja or not loja.pk:
        return None

    username = username_from_loja_nome(loja.nome, loja.pk)
    user = User.objects.create_user(
        username=username,
        password=SENHA_PADRAO_NOVA_LOJA,
        is_staff=False,
        is_superuser=False,
        is_active=True,
    )
    from .fiscal.access import TELAS_FISCAIS_KEYS

    perfil, _ = PerfilUsuario.objects.get_or_create(user=user)
    perfil.loja = loja
    for campo, valor in PERMISSOES_USUARIO_PADRAO_LOJA.items():
        setattr(perfil, campo, valor)
    perfil.perm_fiscal_telas = list(TELAS_FISCAIS_KEYS)
    perfil.save()
    if not loja.gerente_id:
        type(loja).objects.filter(pk=loja.pk).update(gerente=user)
        loja.gerente_id = user.id
    return user
