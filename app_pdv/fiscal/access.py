from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect

# Telas operacionais do módulo fiscal (Integração API e Config ficam em perm_fiscal_config).
TELAS_FISCAIS = [
    ('hub', 'Hub'),
    ('matriz', 'Matriz tributária'),
    ('produtos', 'Produtos'),
    ('avulsa', 'Avulsa'),
    ('documentos', 'Documentos'),
    ('nfce', 'NFC-e'),
    ('lote', 'NFC-e Lote'),
    ('nfe', 'NF-e'),
    ('contabilidade', 'Contabilidade'),
    ('relatorios', 'Relatórios'),
    ('webhooks', 'Webhooks'),
    ('contingencia', 'Contingência'),
    ('arquivos', 'Arquivos'),
    ('reforma', 'Reforma'),
    ('inutilizacao', 'Inutilização'),
    ('manifestacao', 'Manifestação'),
]

TELAS_FISCAIS_KEYS = [key for key, _label in TELAS_FISCAIS]

_URL_PARA_TELA = {
    'fiscal_hub': 'hub',
    'fiscal_matriz': 'matriz',
    'fiscal_matriz_excluir': 'matriz',
    'fiscal_produtos': 'produtos',
    'fiscal_produto_editar': 'produtos',
    'fiscal_produtos_replicar': 'produtos',
    'fiscal_emitir_avulsa': 'avulsa',
    'fiscal_documentos': 'documentos',
    'fiscal_documento_detalhe': 'documentos',
    'fiscal_documento_reemitir': 'documentos',
    'fiscal_documento_cancelar': 'documentos',
    'fiscal_documento_cce': 'documentos',
    'fiscal_documento_arquivo': 'documentos',
    'fiscal_documento_editar': 'documentos',
    'fiscal_emitir': 'nfce',
    'fiscal_venda_preview': 'nfce',
    'fiscal_emitir_lote': 'lote',
    'fiscal_lote_detalhe': 'lote',
    'fiscal_emitir_nfe': 'nfe',
    'fiscal_natureza_criar': 'nfe',
    'fiscal_contabilidade': 'contabilidade',
    'fiscal_contabilidade_baixar': 'contabilidade',
    'fiscal_relatorios': 'relatorios',
    'fiscal_relatorio': 'relatorios',
    'fiscal_webhooks': 'webhooks',
    'fiscal_contingencia': 'contingencia',
    'fiscal_arquivos': 'arquivos',
    'fiscal_reforma': 'reforma',
    'fiscal_inutilizacao': 'inutilizacao',
    'fiscal_manifestacao': 'manifestacao',
    'fiscal_manifestar': 'manifestacao',
}

URLS_CONFIG_FISCAL = {
    'fiscal_focus',
    'fiscal_focus_salvar',
    'fiscal_focus_testar',
    'fiscal_focus_registrar_webhooks',
    'fiscal_acbr_testar',
    'fiscal_acbr_lib_testar',
    'fiscal_config',
}


def loja_fiscal_habilitada(loja):
    return bool(loja and getattr(loja, 'fiscal_habilitado', False))


def usuario_pode_fiscal(user):
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    perfil = getattr(user, 'perfil', None)
    return bool(perfil and getattr(perfil, 'perm_fiscal', False))


def _perfil(user):
    return getattr(user, 'perfil', None) if user else None


def usuario_e_padrao_loja(user, loja=None):
    if not user or not user.is_authenticated:
        return False
    perfil = _perfil(user)
    if perfil and getattr(perfil, 'usuario_padrao_loja', False):
        return True
    if loja and getattr(loja, 'gerente_id', None) and loja.gerente_id == user.id:
        return True
    return False


def usuario_pode_config_fiscal(user, loja=None):
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    if usuario_e_padrao_loja(user, loja):
        return True
    perfil = _perfil(user)
    return bool(perfil and getattr(perfil, 'perm_fiscal_config', False))


def telas_fiscais_do_usuario(user, loja=None):
    if not user or not user.is_authenticated:
        return set()
    if user.is_superuser or usuario_e_padrao_loja(user, loja):
        return set(TELAS_FISCAIS_KEYS)
    if not usuario_pode_fiscal(user):
        return set()
    perfil = _perfil(user)
    escolhidas = list(getattr(perfil, 'perm_fiscal_telas', None) or [])
    return {k for k in escolhidas if k in TELAS_FISCAIS_KEYS}


def usuario_pode_tela_fiscal(user, url_name, loja=None):
    if not usuario_pode_fiscal(user):
        return False
    nome = (url_name or '').strip()
    if nome in URLS_CONFIG_FISCAL:
        return usuario_pode_config_fiscal(user, loja)
    tela = _URL_PARA_TELA.get(nome)
    if not tela:
        return True
    return tela in telas_fiscais_do_usuario(user, loja)


def requer_acesso_fiscal(view_func):
    """Exige login, loja com módulo fiscal ativo, perm_fiscal e tela liberada."""

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
        url_name = ''
        if getattr(request, 'resolver_match', None):
            url_name = request.resolver_match.url_name or ''
        if not usuario_pode_tela_fiscal(request.user, url_name, loja):
            messages.error(request, 'Você não tem permissão para esta tela do módulo fiscal.')
            if 'hub' in telas_fiscais_do_usuario(request.user, loja):
                return redirect('fiscal_hub')
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)

    return _wrapped
