from django.urls import path, include
from . import views
from . import gestor_views
from .views import CustomAuthToken,EntregasDisponiveisView, AssumirEntregaView, MinhasEntregasView, DevolverEntregaView, ReceberLeadTrafficHub


urlpatterns = [
    #--------------------------------Dashboard-----------------------------

    path('', views.dashboard, name='dashboard'),

    # ------------------------------Produtos------------------------------

    path('produtos/', views.lista_produtos, name='lista_produtos'),
    path('produtos/novo/', views.gerenciar_produto, name='novo_produto'),
    path('produtos/editar/<int:id>/', views.gerenciar_produto, name='editar_produto'),
    path('produtos/deletar/<int:id>/', views.deletar_produto, name='deletar_produto'),
    path('produtos/grupos/', views.gerenciar_grupos_produto, name='gerenciar_grupos_produto'),
    path('produtos/grupos/deletar/<int:id>/', views.deletar_grupo_produto, name='deletar_grupo_produto'),

    # ------------------------------Clientes------------------------------

    path('clientes/', views.lista_clientes, name='lista_clientes'),
    path('clientes/novo/', views.gerenciar_cliente, name='novo_cliente'),
    path('clientes/editar/<int:id>/', views.gerenciar_cliente, name='editar_cliente'),
    path('clientes/deletar/<int:id>/', views.deletar_cliente, name='deletar_cliente'),
    path('config/fidelidade/', views.config_fidelidade, name='config_fidelidade'),
    path('config/whatsapp/', views.config_whatsapp, name='config_whatsapp'),
    path('config/nome-marca/', views.api_salvar_nome_marca_pdv, name='api_salvar_nome_marca_pdv'),
    path('config/loja/', views.api_config_loja_pdv, name='api_config_loja_pdv'),

    # ------------------------------Vendas------------------------------

    path('vendas/nova/', views.nova_venda, name='nova_venda'),
    path('teste_venda/', views.teste_venda, name='teste_venda'),
    path('teste_vendas/', views.teste_venda, name='teste_vendas'),
    path('vendas/salvar/', views.salvar_venda, name='salvar_venda'),
    path('vendas/cliente/rapido/', views.api_criar_cliente_pdv, name='api_criar_cliente_pdv'),
    path('vendas/caixa/status/', views.api_status_caixa_pdv, name='api_status_caixa_pdv'),
    path('vendas/excluir/<int:id>/', views.excluir_venda, name='excluir_venda'),

    # ------------------------------Fornecedores------------------------------

    path('fornecedores/', views.lista_fornecedores, name='lista_fornecedores'),
    path('fornecedores/novo/', views.gerenciar_fornecedor, name='novo_fornecedor'),
    path('fornecedores/editar/<int:id>/', views.gerenciar_fornecedor, name='editar_fornecedor'),
    path('fornecedores/deletar/<int:id>/', views.deletar_fornecedor, name='deletar_fornecedor'),

    # ------------------------------Lojas------------------------------

    path('lojas/', views.lista_lojas, name='lista_lojas'),
    path('lojas/novo/', views.gerenciar_loja, name='nova_loja'),
    path('lojas/editar/<int:id>/', views.gerenciar_loja, name='editar_loja'),
    path('api/lojas/', views.api_listar_lojas_rede, name='api_listar_lojas'),

    # ------------------------------Vendas (PDV)------------------------------

    path('vendas/nova/', views.nova_venda, name='nova_venda'),
    path('vendas/salvar/', views.salvar_venda, name='salvar_venda'),
    path('vendas/retomar/<int:id>/', views.retomar_venda, name='retomar_venda'),
    path('vendas/cancelar/<int:id>/', views.cancelar_venda_pdv, name='cancelar_venda_pdv'),
    
    # ------------------------------Histórico ------------------------------

    path('vendas/historico/', views.lista_vendas, name='lista_vendas'),
    path('vendas/detalhes/<int:id>/', views.detalhes_venda, name='detalhes_venda'),
    path('vendas/detalhes/<int:id>/observacao/', views.salvar_observacao_venda, name='salvar_observacao_venda'),

    # ------------------------------Caixa------------------------------

    path('caixa/', views.fluxo_caixa, name='fluxo_caixa'),
    path('caixa/fechar/', views.fechar_caixa, name='fechar_caixa'),
    path('caixa/recibo/<int:id>/', views.ver_recibo_fechamento, name='ver_recibo_fechamento'),

    # ------------------------------Estoque------------------------------ 


    path('estoque/', views.lista_estoque, name='lista_estoque'),
    path('estoque/adicionar/', views.adicionar_estoque, name='adicionar_estoque'),
    path('estoque/transferir/<int:item_id>/', views.transferir_estoque, name='transferir_estoque'),
    path('estoque/transferir-lote/', views.transferir_estoque_lote, name='transferir_estoque_lote'),
    path('estoque/log-transferencias/', views.log_transferencias_estoque, name='log_transferencias_estoque'),
    path('estoque/atualizar-contagem/', views.atualizar_contagem_estoque, name='atualizar_contagem_estoque'),
    path('estoque/contagem-diaria/', views.registrar_contagem_diaria, name='registrar_contagem_diaria'),
    path('estoque/fechamento/', views.registrar_fechamento_estoque, name='registrar_fechamento_estoque'),
    path('estoque/log-fechamento/', views.log_fechamento_estoque, name='log_fechamento_estoque'),

    # ------------------------------Itens------------------------------

    path('itens/', views.lista_itens, name='lista_itens'),
    path('itens/novo/', views.gerenciar_item, name='novo_item'),
    path('itens/editar/<int:id>/', views.gerenciar_item, name='editar_item'),
    path('itens/deletar/<int:id>/', views.deletar_item, name='deletar_item'),


    # ------------------------------Relatórios e Financeiro------------------------------

    path('relatorios/', views.relatorios, name='relatorios'),
    path('mercadorias/pagamento/<int:entrada_id>/', views.registrar_pagamento_mercadoria, name='registrar_pagamento_mercadoria'),
    path('fiado/pagamento/<int:venda_id>/', views.registrar_pagamento_fiado, name='registrar_pagamento_fiado'),
    path('fiado/pagamento-unificado/', views.registrar_pagamento_fiado_unificado, name='registrar_pagamento_fiado_unificado'),
    path('fiado/agendar/', views.criar_parcelas_fiado_agendadas, name='criar_parcelas_fiado_agendadas'),
    path('fiado/parcela/<int:parcela_id>/cancelar/', views.cancelar_parcela_fiado, name='cancelar_parcela_fiado'),
    path('fiado/parcela/<int:parcela_id>/receber/', views.receber_parcela_fiado, name='receber_parcela_fiado'),
    path('categorias/', views.lista_categorias, name='lista_categorias'),
    path('categorias/deletar/<int:id>/', views.deletar_categoria, name='deletar_categoria'),
    path('transacao/nova/', views.adicionar_transacao, name='adicionar_transacao'),
    path('transacao/excluir/<int:id>/', views.excluir_transacao, name='excluir_transacao'),
    path('central_logs/', views.central_logs, name='central_logs'),
    path('dashboard/relatorios/entregas/', views.relatorio_entregadores, name='relatorio_entregas'),



    # ------------------------------Importação------------------------------

    path('importacao/', views.menu_importacao, name='menu_importacao'),
    path('importacao/clientes/', views.importar_clientes, name='importar_clientes'),
    path('importacao/produtos/', views.importar_produtos, name='importar_produtos'),
    path('importacao/modelo/<str:tipo>/', views.baixar_modelo_excel, name='baixar_modelo_excel'),

    # ------------------------------Vendedor------------------------------

    path('vendedores/', views.lista_vendedores, name='lista_vendedores'),
    path('vendedores/cadastrar/', views.cadastrar_vendedor, name='cadastrar_vendedor'),
    path('vendedores/permissoes/<int:id>/', views.gerenciar_permissoes, name='gerenciar_permissoes'),
    path('vendedores/editar/<int:id>/', views.editar_vendedor, name='editar_vendedor'),

    # ------------------------------Entregas------------------------------

    path('entregas/', views.lista_entregas, name='lista_entregas'),
    path('entregas/motoboy/novo/', views.cadastrar_motoboy, name='cadastrar_motoboy'),
    path('entregas/moto/nova/', views.cadastrar_moto, name='cadastrar_moto'),
    path('entregas/motoboy/editar/<int:id>/', views.editar_motoboy, name='editar_motoboy'),
    path('vendas/confirmar-motoboy/<int:venda_id>/', views.confirmar_recebimento_motoboy, name='confirmar_recebimento_motoboy'),
    path('api/', include('transporte.urls')),

    # ------------------------------ROTA DA API (Flutter OBS: Motobot / Diretor)------------------------------

    path('api/login/', CustomAuthToken.as_view(), name='api_token_auth'),

    # ------------------------------ Painel Gestor (mobile) ------------------------------
    path('api/gestor/resumo/', gestor_views.api_gestor_resumo, name='api_gestor_resumo'),
    path('api/gestor/lojas/', gestor_views.api_gestor_lojas, name='api_gestor_lojas'),
    path('api/gestor/financeiro/', gestor_views.api_gestor_financeiro, name='api_gestor_financeiro'),
    path('api/gestor/vendas/', gestor_views.api_gestor_vendas, name='api_gestor_vendas'),
    path('api/gestor/clientes/', gestor_views.api_gestor_clientes, name='api_gestor_clientes'),
    path('api/gestor/estoque/', gestor_views.api_gestor_estoque, name='api_gestor_estoque'),
    path('api/gestor/campanha/', gestor_views.api_gestor_campanha, name='api_gestor_campanha'),

    path('api/entregas/assumir/<int:venda_id>/', AssumirEntregaView.as_view(), name='api_assumir_entrega'),
    path('api/entregas/devolver/<int:venda_id>/', DevolverEntregaView.as_view(), name='api_devolver_entrega'),
    path('api/entregas/minhas/', MinhasEntregasView.as_view(), name='api_minhas_entregas'),
    path('api/entregas/disponiveis/', EntregasDisponiveisView.as_view(), name='api_listar_entregas'),
    path('api/entregas/finalizar/<int:venda_id>/', views.api_finalizar_entrega, name='api_finalizar_entrega'),
    path('api/entregas/ganhos/', views.api_meus_ganhos, name='api_meus_ganhos'),


    # ------------------------------APP Clientes ------------------------------

    path('torre-controle/', views.torre_controle, name='torre_controle'),
    path('api/torre/pedidos/', views.api_pedidos_torre, name='api_pedidos_torre'),
    path('api/torre/atualizar/<int:venda_id>/', views.api_atualizar_status_pedido, name='api_atualizar_status'),
    path('api/produtos/', views.api_listar_produtos, name='api_listar_produtos'),
    path('api/formas-pagamento/', views.api_formas_pagamento, name='api_formas_pagamento'),
    path('api/precos-fornecedor/<int:item_id>/', views.api_precos_fornecedor_item, name='api_precos_fornecedor_item'),
    path('api/pedido/criar/', views.api_criar_pedido, name='api_criar_pedido'),
    path('api/cliente/buscar/', views.api_buscar_cliente, name='api_buscar_cliente'),
    path('api/fidelidade/config/', views.api_fidelidade_config, name='api_fidelidade_config'),
    path('api/fidelidade/status/', views.api_fidelidade_status, name='api_fidelidade_status'),
    path('api/fidelidade/cliente/', views.api_fidelidade_cliente_pdv, name='api_fidelidade_cliente_pdv'),
    path('api/cliente/pedidos/', views.api_meus_pedidos, name='api_meus_pedidos'),
    path('api/venda/conferir/<int:venda_id>/', views.api_conferir_venda, name='api_conferir_venda'),

    # ------------------------------Torre de Controle (APP CLIENTES)------------------------------

    path('torre-controle/', views.torre_controle, name='torre_controle'),
    path('api/torre/dados/', views.api_pedidos_torre,name='api_pedidos_torre'),
    path('api/pedido/status/<int:venda_id>/', views.api_atualizar_status_pedido, name='api_atualizar_status'),
    path('api/taxa_entrega/', views.api_obter_taxa_entrega, name='api_obter_taxa_entrega'),
    path('config/definir_taxa/', views.definir_taxa_entrega, name='definir_taxa_entrega'),
    path('torre-controle/', views.torre_controle, name='app_vendas'),
    path('api/loja/toggle/', views.api_toggle_loja, name='api_toggle_loja'),

    # -------------------------------- Rotas de trafego pago --------------------------------------

    path('api/receber-lead/', ReceberLeadTrafficHub.as_view(), name='receber_lead'),


    # -------------------------------- OUTRAS ROTAS --------------------------------------

    path('sair/', views.fazer_logout, name='logout'),
    path('assinatura/bloqueada/', views.assinatura_bloqueada, name='assinatura_bloqueada'),
    path('assinatura/minha-conta/', views.minha_assinatura, name='minha_assinatura'),

    
]

