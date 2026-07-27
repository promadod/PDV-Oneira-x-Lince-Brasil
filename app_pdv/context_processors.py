from datetime import date

from .models import Loja
from .seguranca import usuario_pode_configurar_loja


def saas_context(request):
    """
    Disponibiliza informações de assinatura (dias restantes) 
    e nome da marca no menu lateral.
    """
    contexto = {
        'nome_marca_pdv': 'Oneira PDV',
        'nome_marca_pdv_max': Loja.NOME_MARCA_PDV_MAX,
        'pode_editar_marca_pdv': False,
        'pode_configurar_loja': False,
    }
    
    if request.user.is_authenticated and hasattr(request.user, 'perfil') and request.user.perfil.loja:
        loja = request.user.perfil.loja
        contexto['loja_atual'] = loja
        contexto['nome_marca_pdv'] = loja.marca_pdv_exibicao()
        contexto['pode_editar_marca_pdv'] = True
        contexto['pode_configurar_loja'] = usuario_pode_configurar_loja(request.user)
        
        if loja.data_vencimento:
            delta = loja.data_vencimento - date.today()
            dias_restantes = delta.days
            
            contexto['saas_dias_restantes'] = dias_restantes
            contexto['saas_vencido'] = (dias_restantes < 0)
            contexto['saas_alerta'] = (dias_restantes <= 5) 
            
    elif request.user.is_authenticated and request.user.is_superuser:
        contexto['pode_configurar_loja'] = usuario_pode_configurar_loja(request.user)

    return contexto
