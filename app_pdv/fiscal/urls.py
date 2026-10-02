from django.urls import path

from . import views

urlpatterns = [
    path('', views.fiscal_hub, name='fiscal_hub'),
    path('focus/', views.fiscal_focus, name='fiscal_focus'),
    path('config/', views.fiscal_config, name='fiscal_config'),
    path('matriz/', views.fiscal_matriz, name='fiscal_matriz'),
    path('matriz/<int:pk>/excluir/', views.fiscal_matriz_excluir, name='fiscal_matriz_excluir'),
    path('produtos/', views.fiscal_produtos, name='fiscal_produtos'),
    path('produtos/<int:produto_id>/', views.fiscal_produto_editar, name='fiscal_produto_editar'),
    path('documentos/', views.fiscal_documentos, name='fiscal_documentos'),
    path('documentos/<int:pk>/', views.fiscal_documento_detalhe, name='fiscal_documento_detalhe'),
    path('documentos/<int:pk>/cancelar/', views.fiscal_documento_cancelar, name='fiscal_documento_cancelar'),
    path('documentos/<int:pk>/cce/', views.fiscal_documento_cce, name='fiscal_documento_cce'),
    path('emitir/', views.fiscal_emitir, name='fiscal_emitir'),
    path('emitir/avulsa/', views.fiscal_emitir_avulsa, name='fiscal_emitir_avulsa'),
    path('emitir/lote/', views.fiscal_emitir_lote, name='fiscal_emitir_lote'),
    path('emitir/lote/<int:pk>/', views.fiscal_lote_detalhe, name='fiscal_lote_detalhe'),
    path('webhooks/', views.fiscal_webhooks, name='fiscal_webhooks'),
    path('contingencia/', views.fiscal_contingencia, name='fiscal_contingencia'),
    path('arquivos/', views.fiscal_arquivos, name='fiscal_arquivos'),
    path('reforma/', views.fiscal_reforma, name='fiscal_reforma'),
    path('inutilizacao/', views.fiscal_inutilizacao, name='fiscal_inutilizacao'),
    path('manifestacao/', views.fiscal_manifestacao, name='fiscal_manifestacao'),
    path('manifestacao/<int:pk>/', views.fiscal_manifestar, name='fiscal_manifestar'),
]
