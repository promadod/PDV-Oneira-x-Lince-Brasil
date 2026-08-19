'''SUMARIO DE FUNÇÕES 
45   | HELPER FUNCTION (SAAS)
70   | PRODUTOS
142  | CLIENTES
178  | VENDAS
365  | DASHBOARD
436  | FORNECEDORES
469  | LOJAS
502  | CAIXA
583  | ESTOQUE
607  | GESTÃO DE CATEGORIAS
637  | LANÇAR RECEITAS / DESPESAS NO CAIXA
660  | CENTRAL  DE RELATORIOS
853  | IMPORTAÇÃO
995  | VENDEDOR
1030 | ENTREGAS(MOTOBOY)
1110 | APP DO MOTOBOY (FLUTTER)
1261 | AREA DE APIS (DEMAIS ENDPOINTS)
1312 | FUNÇÃO AJUDANTE
1457 | APP DO CLIENTE E TORRE DE CONTROLE
'''
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.http import JsonResponse, HttpResponseForbidden, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction, IntegrityError
from decimal import Decimal
from django.db.models import Sum, Count, F, Q, Value, Max, DecimalField
from django.db.models.functions import Coalesce, TruncDate

DECIMAL_ZERO = Value(Decimal('0'), output_field=DecimalField(max_digits=12, decimal_places=2))
from django.core.serializers.json import DjangoJSONEncoder
from django.core.paginator import Paginator
from django.utils.timezone import make_aware, localtime
from django.utils import timezone
from datetime import datetime, date, timedelta
import json
from collections import defaultdict
import pandas as pd
import io
import unicodedata

# Imports de Models e Forms 
from .models import (
    Venda, ItemVenda, Produto, Cliente, Fornecedor, Loja, GrupoProduto,
    CategoriaTransacao, Transacao, Caixa, Motoboy, Moto, 
    EntradaEstoque, ItemEstoque, PerfilUsuario, LogTransferenciaEstoque,
    LogFechamentoEstoqueDiario,
    FormaPagamentoLoja, PrecoFornecedorItem, PagamentoFiado, PagamentoMercadoria,
    LiquidacaoVenda, ParcelaFiadoAgendada, ParcelaMercadoriaAgendada,
    saldo_agendavel_venda, saldo_agendavel_entrada, LogAuditoria,
    validar_forma_pagamento, montar_resumo_pagamentos_loja,
    montar_relatorio_pagamentos, get_nome_forma_pagamento, criar_formas_pagamento_padrao,
    validar_meio_liquidacao, montar_resumo_liquidacao_loja, calcular_entradas_gaveta,
    get_nome_meio_liquidacao, validar_liquidacoes_payload, persistir_liquidacoes_venda,
    ORIGEM_VENDA_CHOICES, STATUS_COMPROMETIDOS, STATUS_VENDA_FATURADA, STATUS_GERA_LIQUIDACAO,
    MEIO_LIQUIDACAO_VENDA_CHOICES,
    produtos_disponiveis_pdv, validar_estoque_item_venda, estoque_diario_ativo,
    produto_baixa_apenas_vasilhame_vazio, ComponenteKit, recalcular_custo_kit,
    custo_unitario_produto_venda,
)
from .filtros_venda import (
    FILTROS_STATUS_HISTORICO,
    HISTORICO_POR_PAGINA,
    filtrar_vendas_historico,
)
from .fiado_helpers import (
    listar_vendas_fiado_abertas, agrupar_fiado_por_cliente,
    listar_parcelas_agendadas, distribuir_pagamento_fiado,
)
from .mercadoria_helpers import listar_entradas_abertas_cmv, listar_parcelas_mercadoria
from .balanca import config_balanca_loja, gerar_csv_carga_balanca
from .forms import (
    ProdutoForm, ClienteForm, FornecedorForm, LojaForm, 
    CategoriaTransacaoForm, TransacaoForm, ImportacaoForm, 
    CadastroVendedorForm, MotoboyForm, MotoForm, 
    EntradaEstoqueForm, ItemEstoqueForm, PermissoesUsuarioForm, EditarVendedorForm
)
from django.contrib.auth.models import User, Group
from django.contrib.auth import logout

# Imports DRF (API)
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.authtoken.models import Token
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from app_pdv.authentication import SessaoUnicaTokenAuthentication as TokenAuthentication
from rest_framework.permissions import IsAuthenticated, AllowAny
from .serializers import UserSerializer, ProdutoCatalogoSerializer
from .gestor_api import usuario_pode_acessar_gestor, calcular_custo_mercadorias_periodo
from .recompra_service import montar_ranking_recompra
from .clientes_service import montar_estatisticas_clientes, montar_links_campanha
from .fidelidade_service import (
    obter_config_fidelidade, status_fidelidade_cliente, calcular_desconto_fidelidade,
    listar_acompanhamento_fidelidade,
)
from .audit_log import registrar_log
from .seguranca import usuario_pode_configurar_loja
from .whatsapp_service import (
    notificar_novo_pedido_empresa, notificar_cliente_saiu_entrega,
    notificar_cliente_entrega_concluida,
)

# ------------------------- HELPER FUNCTION (SAAS) -------------------------------------
def get_loja_usuario(user):
    """
    Retorna a loja vinculada ao usuário.
    Se não tiver loja, retorna None ou lança erro.
    """
    try:
        if user.is_superuser:
            
            if hasattr(user, 'perfil') and user.perfil.loja:
                return user.perfil.loja
            return Loja.objects.first()
        
        return user.perfil.loja
    except AttributeError:
        return None

def check_loja(request):
    """Verifica se o usuário tem loja, senão redireciona ou avisa"""
    loja = get_loja_usuario(request.user)
    if not loja:
        messages.error(request, "Seu usuário não está vinculado a nenhuma Loja. Contate o suporte.")
        return None
    return loja


@login_required
def api_status_caixa_pdv(request):
    """Status do turno de caixa para sincronizar o rodapé da tela de vendas."""
    loja = check_loja(request)
    if not loja:
        return JsonResponse({'status': 'erro', 'mensagem': 'Usuário sem loja vinculada.'}, status=403)

    caixa = _caixa_turno_aberto(loja)
    primeiro_nome, sobrenome = _dados_operador_pdv(request)
    hora_abertura = _hora_exibicao_caixa(caixa.data_hora_abertura if caixa else None)
    data_abertura = _data_exibicao_caixa(caixa.data_hora_abertura if caixa else None)

    return JsonResponse({
        'status': 'ok',
        'caixa_aberto': bool(caixa),
        'hora_abertura': hora_abertura,
        'data_abertura': data_abertura,
        'primeiro_nome': primeiro_nome,
        'sobrenome': sobrenome,
        'nome_loja': loja.marca_pdv_exibicao(),
        'cnpj_loja': (loja.cnpj or '').strip(),
    })


@login_required
def api_salvar_nome_marca_pdv(request):
    from .models import Loja as LojaModel
    loja = check_loja(request)
    if not loja:
        return JsonResponse({'status': 'erro', 'mensagem': 'Usuário sem loja vinculada.'}, status=403)
    if request.method != 'POST':
        return JsonResponse({'status': 'erro', 'mensagem': 'Método inválido.'}, status=405)
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'status': 'erro', 'mensagem': 'Dados inválidos.'}, status=400)
    nome = (data.get('nome') or '').strip()
    if not nome:
        return JsonResponse({'status': 'erro', 'mensagem': 'Informe um nome.'}, status=400)
    if len(nome) > LojaModel.NOME_MARCA_PDV_MAX:
        return JsonResponse({
            'status': 'erro',
            'mensagem': f'Máximo de {LojaModel.NOME_MARCA_PDV_MAX} caracteres.',
        }, status=400)
    loja.nome_marca_pdv = nome
    loja.save(update_fields=['nome_marca_pdv'])
    return JsonResponse({'status': 'ok', 'nome': loja.marca_pdv_exibicao()})


@login_required
def api_config_loja_pdv(request):
    """Lê/salva flags de operação da loja (modal engrenagem)."""
    loja = check_loja(request)
    if not loja:
        return JsonResponse({'status': 'erro', 'mensagem': 'Usuário sem loja vinculada.'}, status=403)
    if not usuario_pode_configurar_loja(request.user):
        return JsonResponse({'status': 'erro', 'mensagem': 'Sem permissão para configurar a loja.'}, status=403)

    # Instância fresca do banco (evita objeto antigo via perfil/relacionamento).
    loja = Loja.objects.get(pk=loja.pk)

    if request.method == 'GET':
        campos_meta = []
        for nome in CAMPOS_CONFIG_LOJA_PDV:
            field = Loja._meta.get_field(nome)
            tipo_interno = field.get_internal_type()
            if tipo_interno == 'BooleanField':
                tipo = 'bool'
            elif field.choices:
                tipo = 'choice'
            elif tipo_interno in (
                'DecimalField', 'FloatField', 'IntegerField',
                'PositiveIntegerField', 'PositiveSmallIntegerField', 'SmallIntegerField',
            ):
                tipo = 'decimal'
            else:
                tipo = 'choice' if field.choices else 'text'
            item = {
                'nome': nome,
                'label': str(field.verbose_name),
                'help': str(field.help_text or ''),
                'tipo': tipo,
                'valor': _serializar_valor_campo_loja(field, getattr(loja, nome)),
            }
            if field.choices:
                item['opcoes'] = [{'value': str(c[0]), 'label': str(c[1])} for c in field.choices]
            campos_meta.append(item)
        return JsonResponse({
            'status': 'ok',
            'loja_id': loja.id,
            'loja_nome': loja.nome,
            'campos': campos_meta,
        })

    if request.method != 'POST':
        return JsonResponse({'status': 'erro', 'mensagem': 'Método inválido.'}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'status': 'erro', 'mensagem': 'Dados inválidos.'}, status=400)

    if not isinstance(data, dict):
        return JsonResponse({'status': 'erro', 'mensagem': 'Payload inválido.'}, status=400)

    alterados = []
    campos_para_salvar = []
    for nome in CAMPOS_CONFIG_LOJA_PDV:
        if nome not in data:
            continue
        field = Loja._meta.get_field(nome)
        try:
            valor_novo = _parse_valor_campo_loja(field, data[nome])
        except Exception:
            return JsonResponse({
                'status': 'erro',
                'mensagem': f'Valor inválido para "{field.verbose_name}".',
            }, status=400)
        valor_antigo = getattr(loja, nome)
        if valor_antigo != valor_novo:
            setattr(loja, nome, valor_novo)
            campos_para_salvar.append(nome)
            alterados.append(f'{field.verbose_name}: {valor_antigo} → {valor_novo}')

    if 'trabalha_com_balanca_granel' in campos_para_salvar and loja.trabalha_com_balanca_granel:
        if not loja.trabalha_com_leitor_codigo_barras:
            loja.trabalha_com_leitor_codigo_barras = True
            if 'trabalha_com_leitor_codigo_barras' not in campos_para_salvar:
                campos_para_salvar.append('trabalha_com_leitor_codigo_barras')
            alterados.append('Trabalha com leitor de código de barras?: False → True')

    if campos_para_salvar:
        loja.save(update_fields=campos_para_salvar)
        loja.refresh_from_db(fields=campos_para_salvar)
        registrar_log(
            request, 'CONFIG',
            'Configurações da loja alteradas: ' + '; '.join(alterados),
            modelo='Loja', objeto_id=loja.id, loja=loja,
        )

    valores = {
        nome: _serializar_valor_campo_loja(Loja._meta.get_field(nome), getattr(loja, nome))
        for nome in CAMPOS_CONFIG_LOJA_PDV
    }
    return JsonResponse({
        'status': 'ok',
        'alterados': len(campos_para_salvar),
        'loja_id': loja.id,
        'valores': valores,
    })


# --------------------------- PRODUTOS (ESTOQUE) ------------------------------------


@login_required
def lista_produtos(request):
    loja = check_loja(request)
    if not loja: return redirect('admin:index')
    
    produtos = Produto.objects.filter(loja=loja).select_related('grupo', 'item_estoque').prefetch_related(
        'componentes_kit__item_estoque'
    ).order_by('nome_venda')
    return render(request, 'app_pdv/lista_produtos.html', {
        'produtos': produtos,
        'loja': loja,
    })


@login_required
def exportar_carga_balanca(request):
    """CSV com o mesmo código do cadastro para carregar no MGV (Prix 4 Uno e 3 Fit)."""
    loja = check_loja(request)
    if not loja:
        return redirect('admin:index')
    produtos = (
        Produto.objects.filter(loja=loja)
        .exclude(codigo_barras='')
        .select_related('item_estoque')
        .order_by('nome_venda')
    )
    conteudo = gerar_csv_carga_balanca(produtos, loja)
    response = HttpResponse('\ufeff' + conteudo, content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="carga_balanca_mgv.csv"'
    return response

@login_required
def gerenciar_grupos_produto(request):
    loja = check_loja(request)
    if not loja:
        return redirect('admin:index')
    if not loja.divide_produtos_por_grupos:
        messages.warning(request, 'Grupos de produtos não estão habilitados para esta loja.')
        return redirect('lista_produtos')

    if request.method == 'POST':
        nome = (request.POST.get('nome') or '').strip()
        if nome:
            GrupoProduto.objects.get_or_create(loja=loja, nome=nome)
            registrar_log(
                request, 'CRIAR',
                f'Grupo de produto "{nome}" cadastrado',
                modelo='GrupoProduto', loja=loja,
            )
            messages.success(request, f'Grupo "{nome}" cadastrado.')
        return redirect('gerenciar_grupos_produto')

    grupos = GrupoProduto.objects.filter(loja=loja).order_by('ordem', 'nome')
    return render(request, 'app_pdv/grupos_produto.html', {'grupos': grupos, 'loja': loja})

@login_required
def deletar_grupo_produto(request, id):
    loja = check_loja(request)
    if not loja:
        return redirect('admin:index')
    grupo = get_object_or_404(GrupoProduto, pk=id, loja=loja)
    nome = grupo.nome
    gid = grupo.id
    Produto.objects.filter(loja=loja, grupo=grupo).update(grupo=None)
    grupo.delete()
    registrar_log(
        request, 'EXCLUIR',
        f'Grupo de produto "{nome}" removido',
        modelo='GrupoProduto', objeto_id=gid, loja=loja,
    )
    messages.success(request, 'Grupo removido.')
    return redirect('gerenciar_grupos_produto')

def _salvar_componentes_kit(produto, loja, post):
    ComponenteKit.objects.filter(produto_kit=produto).delete()
    if not produto.eh_kit:
        return
    itens_ids = post.getlist('kit_item_estoque')
    qtds = post.getlist('kit_quantidade')
    for ordem, (item_id, qtd_str) in enumerate(zip(itens_ids, qtds)):
        item_id = (item_id or '').strip()
        qtd_str = (qtd_str or '').strip().replace(',', '.')
        if not item_id or not qtd_str:
            continue
        try:
            item = ItemEstoque.objects.get(pk=int(item_id), loja=loja)
            qtd = Decimal(qtd_str)
            if qtd <= 0:
                continue
        except (ValueError, ItemEstoque.DoesNotExist):
            continue
        ComponenteKit.objects.create(
            produto_kit=produto, item_estoque=item, quantidade=qtd, ordem=ordem,
        )
    recalcular_custo_kit(produto)

@login_required
def gerenciar_produto(request, id=None):
    loja = check_loja(request)
    if not loja: return redirect('admin:index')
    produto = get_object_or_404(Produto, pk=id, loja=loja) if id else None
    fornecedores = Fornecedor.objects.filter(loja=loja).order_by('nome')

    def _precos_por_item(item_estoque_id):
        if not item_estoque_id:
            return {}
        return {
            p.fornecedor_id: p.preco_compra
            for p in PrecoFornecedorItem.objects.filter(
                loja=loja, item_estoque_id=item_estoque_id, ativo=True
            )
        }

    if request.method == 'POST':
        form = ProdutoForm(request.POST, request.FILES, instance=produto, loja=loja)
        if form.is_valid():
            try:
                obj = form.save(commit=False)
                obj.loja = loja
                if obj.eh_kit:
                    obj.item_estoque = None
                    obj.quantidade_baixa = Decimal('1')
                obj.save()
                _salvar_componentes_kit(obj, loja, request.POST)
                if obj.eh_kit and not obj.componentes_kit.exists():
                    messages.error(request, 'Kit deve ter ao menos um componente de estoque.')
                    return redirect('editar_produto', id=obj.id)

                if not obj.eh_kit and obj.item_estoque_id:
                    item_estoque = obj.item_estoque
                    data_val = (request.POST.get('item_data_validade') or '').strip()
                    obs_val = (request.POST.get('item_observacao') or '').strip()
                    if data_val:
                        item_estoque.data_validade = data_val
                    elif request.POST.get('item_data_validade_limpar') == '1':
                        item_estoque.data_validade = None
                    item_estoque.observacao = obs_val
                    item_estoque.save(update_fields=['data_validade', 'observacao'])

                    for forn in fornecedores:
                        campo = f'preco_forn_{forn.id}'
                        valor_str = (request.POST.get(campo) or '').strip().replace(',', '.')
                        if not valor_str:
                            PrecoFornecedorItem.objects.filter(
                                loja=loja, item_estoque=item_estoque, fornecedor=forn
                            ).delete()
                            continue
                        try:
                            preco = Decimal(valor_str)
                        except Exception:
                            continue
                        PrecoFornecedorItem.objects.update_or_create(
                            loja=loja,
                            item_estoque=item_estoque,
                            fornecedor=forn,
                            defaults={'preco_compra': preco, 'ativo': True},
                        )
                registrar_log(
                    request,
                    'EDITAR' if id else 'CRIAR',
                    f'Produto "{obj.nome_venda}" {"atualizado" if id else "criado"}',
                    modelo='Produto', objeto_id=obj.id, loja=loja,
                )
                messages.success(request, f'Produto "{obj.nome_venda}" salvo com sucesso.')
                return redirect('lista_produtos')
            except IntegrityError:
                messages.error(
                    request,
                    'Não foi possível salvar: conflito de dados (ex.: código de barras já usado).',
                )
            except Exception as exc:
                messages.error(request, f'Erro ao salvar produto: {exc}')
        else:
            messages.error(request, 'Não foi possível salvar. Corrija os campos destacados abaixo.')
    else:
        form = ProdutoForm(instance=produto, loja=loja)

    item_id = None
    if produto and produto.item_estoque_id:
        item_id = produto.item_estoque_id
    elif request.method == 'POST':
        item_id = request.POST.get('item_estoque')

    precos_map = _precos_por_item(item_id)
    tabela_precos = [
        {'fornecedor': f, 'preco': precos_map.get(f.id, '')}
        for f in fornecedores
    ]

    item_validade = ''
    item_observacao = ''
    if item_id:
        item_obj = ItemEstoque.objects.filter(pk=item_id, loja=loja).first()
        if item_obj:
            item_validade = item_obj.data_validade.isoformat() if item_obj.data_validade else ''
            item_observacao = item_obj.observacao or ''

    itens_meta = {
        str(i.id): {
            'data_validade': i.data_validade.isoformat() if i.data_validade else '',
            'observacao': i.observacao or '',
        }
        for i in ItemEstoque.objects.filter(loja=loja).only('id', 'data_validade', 'observacao')
    }

    componentes_kit = []
    if produto and produto.eh_kit:
        componentes_kit = list(
            produto.componentes_kit.select_related('item_estoque').order_by('ordem', 'id')
        )
    itens_estoque_loja = ItemEstoque.objects.filter(loja=loja).order_by('nome')

    return render(request, 'app_pdv/form_produto.html', {
        'form': form,
        'titulo': 'Cadastro de Produto',
        'tabela_precos': tabela_precos,
        'item_estoque_id': item_id,
        'item_validade': item_validade,
        'item_observacao': item_observacao,
        'itens_meta_json': json.dumps(itens_meta, cls=DjangoJSONEncoder),
        'loja': loja,
        'componentes_kit': componentes_kit,
        'itens_estoque_loja': itens_estoque_loja,
    })

@login_required
def deletar_produto(request, id):
    loja = check_loja(request)
    produto = get_object_or_404(Produto, pk=id, loja=loja)
    nome = produto.nome_venda
    pid = produto.id
    produto.delete()
    registrar_log(
        request, 'EXCLUIR',
        f'Produto "{nome}" excluído',
        modelo='Produto', objeto_id=pid, loja=loja,
    )
    return redirect('lista_produtos')

@login_required
def lista_itens(request):
    loja = check_loja(request)
    if not loja: return redirect('admin:index')
    
    itens = ItemEstoque.objects.filter(loja=loja).order_by('nome')
    return render(request, 'app_pdv/lista_itens.html', {'itens': itens})

@login_required
@login_required
def gerenciar_item(request, id=None):
    loja = check_loja(request)
    if not loja: return redirect('admin:index')

    item = get_object_or_404(ItemEstoque, pk=id, loja=loja) if id else None
    
    if request.method == 'POST':
        form = ItemEstoqueForm(request.POST, instance=item)
        if form.is_valid():
            try:
                obj = form.save(commit=False)
                obj.loja = loja
                obj.save()
                return redirect('lista_itens')
            except IntegrityError:
                
                nome_tentado = form.cleaned_data.get('nome')
                messages.error(request, f"Erro: Já existe um item cadastrado com o nome '{nome_tentado}'. Use outro nome ou edite o existente.")
                
    else:
        form = ItemEstoqueForm(instance=item)
    
    return render(request, 'app_pdv/form_generico.html', {'form': form, 'titulo': 'Cadastrar Item no Estoque'})

@login_required
def deletar_item(request, id):
    loja = check_loja(request)
    item = get_object_or_404(ItemEstoque, pk=id, loja=loja)
    item.delete()
    return redirect('lista_itens')


# ---------------------------------- CLIENTES ----------------------------------------------
@login_required
def lista_clientes(request):
    loja = check_loja(request)
    if not loja:
        return redirect('admin:index')

    filtros = {
        'nome': (request.GET.get('nome') or '').strip(),
        'bairro': (request.GET.get('bairro') or '').strip(),
        'whatsapp': (request.GET.get('whatsapp') or '').strip(),
        'dias_sem_comprar': (request.GET.get('dias_sem_comprar') or '').strip(),
        'ultima_compra': (request.GET.get('ultima_compra') or '').strip(),
    }
    filtros_ativos = any(filtros.values())

    stats = montar_estatisticas_clientes(Loja.objects.filter(id=loja.id), filtros=filtros)
    publico = request.GET.get('campanha', '')
    links_campanha = []
    if publico in ('ativos', 'inativos'):
        desconto = request.GET.get('desconto')
        desconto_val = float(desconto) if desconto else None
        links_campanha = montar_links_campanha(loja, publico=publico, desconto_pct=desconto_val)

    return render(request, 'app_pdv/lista_clientes.html', {
        'stats': stats,
        'loja': loja,
        'filtros': filtros,
        'filtros_ativos': filtros_ativos,
        'publico_campanha': publico,
        'links_campanha': links_campanha,
        'desconto_campanha': loja.campanha_desconto_pct,
    })

@login_required
def deletar_cliente(request, id):
    loja = check_loja(request)
    cliente = get_object_or_404(Cliente, pk=id, loja=loja)
    cliente.delete()
    return redirect('lista_clientes')

@login_required
def gerenciar_cliente(request, id=None):
    loja = check_loja(request)
    if not loja: return redirect('admin:index')

    cliente = get_object_or_404(Cliente, pk=id, loja=loja) if id else None
    
    if request.method == 'POST':
        form = ClienteForm(request.POST, instance=cliente)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.loja = loja
            obj.save()
            return redirect('lista_clientes')
    else:
        form = ClienteForm(instance=cliente)
    
    return render(request, 'app_pdv/form_generico.html', {'form': form, 'titulo': 'Cadastro de Cliente'})


@login_required
def config_fidelidade(request):
    loja = check_loja(request)
    if not loja:
        return redirect('admin:index')
    from .forms import ConfigFidelidadeForm
    if request.method == 'POST':
        form = ConfigFidelidadeForm(request.POST, instance=loja)
        if form.is_valid():
            form.save()
            messages.success(request, 'Configuração de fidelidade salva!')
            return redirect('config_fidelidade')
    else:
        form = ConfigFidelidadeForm(instance=loja)
    acompanhamento = listar_acompanhamento_fidelidade(loja) if loja.fidelidade_ativa else []
    return render(request, 'app_pdv/config_fidelidade.html', {
        'form': form,
        'loja': loja,
        'acompanhamento': acompanhamento,
    })


@login_required
def config_whatsapp(request):
    loja = check_loja(request)
    if not loja:
        return redirect('admin:index')
    from .forms import ConfigWhatsAppForm
    if request.method == 'POST':
        form = ConfigWhatsAppForm(request.POST, instance=loja)
        if form.is_valid():
            form.save()
            messages.success(request, 'Configurações de WhatsApp salvas!')
            return redirect('config_whatsapp')
    else:
        form = ConfigWhatsAppForm(instance=loja)
    return render(request, 'app_pdv/config_whatsapp.html', {'form': form, 'loja': loja})


# ----------------------------- VENDAS ------------------------------------

@login_required
def lista_vendas(request):
    loja = check_loja(request)
    if not loja:
        return redirect('admin:index')

    vendas = Venda.objects.filter(loja=loja).select_related(
        'cliente', 'entregador', 'quem_recebeu'
    ).order_by('-data_venda')

    vendas, filtros, filtros_ativos, meta = filtrar_vendas_historico(vendas, request.GET)

    if meta.get('erro_periodo'):
        total_geral = Decimal('0')
        total_resultados = 0
        page_obj = None
    else:
        total_geral = vendas.aggregate(total=Sum('total'))['total'] or 0
        total_resultados = vendas.count()
        paginator = Paginator(vendas, HISTORICO_POR_PAGINA)
        page_obj = paginator.get_page(request.GET.get('page'))

    qs_params = request.GET.copy()
    qs_params.pop('page', None)
    querystring = qs_params.urlencode()

    return render(request, 'app_pdv/lista_vendas.html', {
        'vendas': page_obj,
        'page_obj': page_obj,
        'filtros': filtros,
        'filtros_ativos': filtros_ativos,
        'meta_historico': meta,
        'querystring': querystring,
        'opcoes_status': FILTROS_STATUS_HISTORICO,
        'opcoes_origem': ORIGEM_VENDA_CHOICES,
        'opcoes_meio_liquidacao': MEIO_LIQUIDACAO_VENDA_CHOICES,
        'opcoes_forma_pagamento': loja.get_formas_pagamento_ativas(),
        'total_resultados': total_resultados,
        'total_geral': total_geral,
        'por_pagina': HISTORICO_POR_PAGINA,
    })

@login_required
def detalhes_venda(request, id):
    loja = check_loja(request)
    venda = get_object_or_404(Venda, pk=id, loja=loja)
    itens = ItemVenda.objects.filter(venda=venda)
    pagamentos_fiado = venda.pagamentos_fiado.all() if venda.eh_fiado else []
    liquidacoes = list(venda.liquidacoes.all())
    auto_print = request.GET.get('autoprint') == '1' and loja.impressao_automatica
    subtotal_consumo = sum(
        (item.quantidade * item.preco_unitario for item in itens),
        Decimal('0'),
    )
    return render(request, 'app_pdv/detalhes_venda.html', {
        'venda': venda, 'itens': itens, 'pagamentos_fiado': pagamentos_fiado,
        'liquidacoes': liquidacoes,
        'impressao_automatica': loja.impressao_automatica,
        'auto_print': auto_print,
        'subtotal_consumo': subtotal_consumo,
        'modo_taxa_servico': loja_usa_taxa_servico(loja),
    })


@login_required
def salvar_observacao_venda(request, id):
    loja = check_loja(request)
    if not loja:
        return JsonResponse({'status': 'erro', 'mensagem': 'Usuário sem loja vinculada.'}, status=403)

    venda = get_object_or_404(Venda, pk=id, loja=loja)

    if request.method != 'POST':
        return JsonResponse({'status': 'erro', 'mensagem': 'Método inválido.'}, status=405)

    if venda.status == 'CANCELADO':
        return JsonResponse(
            {'status': 'erro', 'mensagem': 'Venda cancelada não pode ser alterada.'}, status=400
        )

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'status': 'erro', 'mensagem': 'Dados inválidos.'}, status=400)

    observacao = (data.get('observacao') or '').strip()
    venda.observacao = observacao or None
    venda.save(update_fields=['observacao'])

    return JsonResponse({'status': 'sucesso', 'observacao': venda.observacao or ''})

@login_required
def nova_venda(request):
    loja = check_loja(request)
    if not loja: return redirect('admin:index')

    # Garante criação de novas formas (ex.: CORTESIA) em lojas antigas
    if not FormaPagamentoLoja.objects.filter(loja=loja, codigo='CORTESIA').exists():
        criar_formas_pagamento_padrao(loja)

    produtos = produtos_disponiveis_pdv(loja)
    clientes = Cliente.objects.filter(loja=loja)

    context = _context_tela_vendas(
        loja, produtos, clientes, request=request, liquidacoes_json='[]',
    )
    return render(request, 'app_pdv/vendas.html', context)


@login_required
def teste_venda(request):
    """Redireciona para a tela oficial de vendas (protótipo migrado)."""
    return redirect('nova_venda')

@login_required
def excluir_venda(request, id):
    loja = check_loja(request)
    venda = get_object_or_404(Venda, pk=id, loja=loja)
    
    
    if venda.status in ['ABERTO', 'ORCAMENTO', 'AGUARDANDO_FINALIZAR']:
        registrar_log(
            request, 'EXCLUIR',
            f'Venda #{venda.id} excluída (status {venda.status})',
            modelo='Venda', objeto_id=venda.id, loja=loja,
        )
        venda.delete()
    
    return redirect('lista_vendas')


def _valor_decimal_payload(val, default='0'):
    if val is None or val == '':
        return Decimal(str(default))
    try:
        return Decimal(str(val).strip().replace(',', '.'))
    except Exception:
        return Decimal(str(default))


def loja_usa_taxa_servico(loja):
    return not loja.trabalha_com_entregas and loja.cobra_taxa_servico


def _mapa_codigos_barras_pdv(loja, produtos_pdv=None):
    """Mapa código de barras / PLU / ID interno → nome para busca no PDV."""
    from .balanca import chaves_busca_plu, config_balanca_loja
    qs = Produto.objects.filter(loja=loja).only('id', 'nome_venda', 'codigo_barras')
    mapa = {}
    cfg = config_balanca_loja(loja)
    for p in qs:
        mapa[str(p.id)] = p.nome_venda
        codigo = (p.codigo_barras or '').strip()
        if codigo:
            for chave in chaves_busca_plu(codigo, cfg['plu_digitos']):
                mapa[chave] = p.nome_venda
    return mapa


def _lista_codigos_produtos_pdv(loja):
    """Lista para modal gabarito de códigos no PDV."""
    qs = Produto.objects.filter(loja=loja).only('id', 'nome_venda', 'codigo_barras').order_by('nome_venda')
    return [
        {
            'id': p.id,
            'nome': p.nome_venda,
            'codigo_barras': (p.codigo_barras or '').strip(),
        }
        for p in qs
    ]


MEIOS_LIQUIDACAO_CODIGOS = frozenset({'DINHEIRO', 'PIX', 'CREDITO', 'DEBITO'})


def _caixa_turno_aberto(loja):
    return Caixa.objects.filter(loja=loja, status=True).first()


def _localtime_caixa(dt):
    if not dt:
        return None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return timezone.localtime(dt)


def _hora_exibicao_caixa(dt):
    """Hora local (Brasil) para exibição no PDV e tela de caixa."""
    local = _localtime_caixa(dt)
    return local.strftime('%H:%M') if local else None


def _data_exibicao_caixa(dt):
    local = _localtime_caixa(dt)
    return local.strftime('%d/%m/%Y') if local else None


def _dados_operador_pdv(request):
    primeiro_nome = ''
    sobrenome = ''
    if request and getattr(request, 'user', None) and request.user.is_authenticated:
        nome_usuario = (request.user.get_full_name() or request.user.username or '').strip()
        partes_nome = nome_usuario.split(None, 1)
        primeiro_nome = partes_nome[0] if partes_nome else request.user.username
        sobrenome = partes_nome[1] if len(partes_nome) > 1 else ''
    return primeiro_nome, sobrenome


CAMPOS_CONFIG_LOJA_PDV = [
    # Entregas
    'trabalha_com_entregas', 'monitorar_entrega', 'usa_moveon',
    'taxa_entrega_pdv',
    # PDV
    'impressao_automatica', 'trabalha_com_leitor_codigo_barras',
    'trabalha_com_balanca_granel', 'balanca_ean_prefixo',
    'balanca_plu_digitos', 'balanca_ean_variavel',
    'cobra_taxa_servico', 'taxa_servico_pct',
    # Depósito / Fiado
    'usa_fiado', 'permite_pagamento_dividido', 'controla_vasilhame_vazio',
    'estoque_diario', 'permite_venda_completa', 'divide_produtos_por_grupos',
    'gerencia_pagamento_mercadorias',
    # Fidelidade
    'fidelidade_ativa', 'fidelidade_tipo_meta', 'fidelidade_meta', 'fidelidade_desconto_pct',
]


def _serializar_valor_campo_loja(field, valor):
    """Normaliza valor do modelo Loja para JSON/API."""
    if field.get_internal_type() == 'BooleanField':
        return bool(valor)
    if field.get_internal_type() in (
        'DecimalField', 'FloatField', 'IntegerField',
        'PositiveIntegerField', 'PositiveSmallIntegerField', 'SmallIntegerField',
    ):
        if valor is None:
            return None
        return float(valor)
    return '' if valor is None else str(valor)


def _parse_valor_campo_loja(field, bruto):
    """Converte payload JSON para o tipo do campo (bool/decimal/char)."""
    tipo = field.get_internal_type()
    if tipo == 'BooleanField':
        if isinstance(bruto, bool):
            return bruto
        if isinstance(bruto, (int, float)):
            return bool(bruto)
        if isinstance(bruto, str):
            return bruto.strip().lower() in ('1', 'true', 't', 'yes', 'y', 'on', 'sim')
        return False
    if tipo in ('DecimalField', 'FloatField'):
        return Decimal(str(bruto).strip().replace(',', '.'))
    if tipo in ('IntegerField', 'PositiveIntegerField', 'PositiveSmallIntegerField', 'SmallIntegerField'):
        return int(Decimal(str(bruto).strip().replace(',', '.')))
    texto = '' if bruto is None else str(bruto).strip()
    if field.choices:
        validos = {str(c[0]) for c in field.choices}
        if texto not in validos:
            raise ValueError(f'Valor inválido para {field.name}')
    return texto


def formas_lancamento_avulsas(loja):
    """Formas de tipo de lançamento sem duplicar meios de liquidação padrão."""
    avulsas = []
    for forma in loja.get_formas_pagamento_ativas():
        if forma.codigo.upper() in MEIOS_LIQUIDACAO_CODIGOS:
            continue
        avulsas.append({
            'codigo': forma.codigo,
            'nome': forma.nome,
            'cor': forma.cor,
            'icone': forma.icone,
        })
    codigos = {f['codigo'].upper() for f in avulsas}
    if 'AVARIA' not in codigos:
        avulsas.append({
            'codigo': 'AVARIA',
            'nome': 'Avaria',
            'cor': '#cf6679',
            'icone': 'fa-box-open',
        })
    return avulsas


def _context_tela_vendas(loja, produtos, clientes, request=None, **extra):
    from .models import MEIOS_LIQUIDACAO_PADRAO

    caixa_aberto = _caixa_turno_aberto(loja)
    primeiro_nome, sobrenome = _dados_operador_pdv(request)
    formas_avulsas = formas_lancamento_avulsas(loja)

    ctx = {
        'produtos': produtos,
        'clientes': clientes,
        'taxa_padrao': loja.taxa_entrega_pdv,
        'formas_pagamento': loja.get_formas_pagamento_ativas(),
        'usa_fiado': loja.usa_fiado,
        'permite_pagamento_dividido': loja.permite_pagamento_dividido,
        'controla_vasilhame_vazio': loja.controla_vasilhame_vazio,
        'permite_venda_completa': loja.permite_venda_completa,
        'fidelidade_ativa': loja.fidelidade_ativa,
        'estoque_diario': estoque_diario_ativo(loja),
        'trabalha_com_entregas': loja.trabalha_com_entregas,
        'impressao_automatica': loja.impressao_automatica,
        'modo_taxa_servico': loja_usa_taxa_servico(loja),
        'taxa_servico_pct': loja.taxa_servico_pct,
        'leitor_codigo_barras': loja.trabalha_com_leitor_codigo_barras,
        'trabalha_com_balanca_granel': loja.trabalha_com_balanca_granel,
        'balanca_config_json': json.dumps(config_balanca_loja(loja), cls=DjangoJSONEncoder),
        'mapa_codigos_barras_json': json.dumps(
            _mapa_codigos_barras_pdv(loja),
            cls=DjangoJSONEncoder,
        ),
        'lista_codigos_produtos_json': json.dumps(
            _lista_codigos_produtos_pdv(loja),
            cls=DjangoJSONEncoder,
        ),
        'meios_pagamento_cards': [
            m for m in MEIOS_LIQUIDACAO_PADRAO if m['codigo'] != 'CORTESIA'
        ],
        'formas_lancamento_avulsas': formas_avulsas,
        'formas_lancamento_avulsas_json': json.dumps(formas_avulsas, cls=DjangoJSONEncoder),
    }
    ctx.update(extra)
    # Rodapé do PDV: sempre recalculado após extra para não ser sobrescrito.
    dt_abertura = caixa_aberto.data_hora_abertura if caixa_aberto else None
    ctx.update({
        'caixa_aberto': bool(caixa_aberto),
        'caixa_turno': caixa_aberto,
        'hora_abertura_caixa': _hora_exibicao_caixa(dt_abertura),
        'data_abertura_caixa': _data_exibicao_caixa(dt_abertura),
        'nome_loja': loja.marca_pdv_exibicao(),
        'cnpj_loja': (loja.cnpj or '').strip(),
        'primeiro_nome': primeiro_nome,
        'sobrenome': sobrenome,
    })
    return ctx


def _subtotal_itens_payload(data):
    return sum(
        _valor_decimal_payload(it.get('preco')) * _valor_decimal_payload(it.get('quantidade'))
        for it in data.get('itens', [])
    )


def vendas_turno_caixa(caixa):
    inicio = caixa.data_hora_abertura
    if not inicio:
        inicio = datetime.combine(caixa.data, datetime.min.time())
    fim = caixa.data_hora_fechamento or timezone.now()
    return Venda.objects.filter(
        loja=caixa.loja,
        status__in=STATUS_VENDA_FATURADA,
        data_venda__gte=inicio,
        data_venda__lte=fim,
    )


def agregar_produtos_vendas(vendas_qs, loja=None):
    rows = ItemVenda.objects.filter(
        venda__in=vendas_qs,
    ).select_related('produto__grupo').values(
        'produto__nome_venda',
        'produto__grupo__nome',
        'produto__grupo__ordem',
        'produto__grupo_id',
    ).annotate(
        qtd=Sum('quantidade'),
        total=Sum(F('quantidade') * F('preco_unitario')),
    ).order_by('produto__grupo__ordem', 'produto__grupo__nome', 'produto__nome_venda')

    flat = [
        {
            'nome': r['produto__nome_venda'],
            'qtd': float(r['qtd'] or 0),
            'total': float(r['total'] or 0),
        }
        for r in rows
    ]

    if not (loja and loja.divide_produtos_por_grupos):
        return flat, None

    grupos_map = {}
    for r in rows:
        gid = r['produto__grupo_id']
        key = gid or 0
        if key not in grupos_map:
            grupos_map[key] = {
                'grupo': r['produto__grupo__nome'] or 'Sem grupo',
                'ordem': r['produto__grupo__ordem'] if gid else 9999,
                'itens': [],
            }
        grupos_map[key]['itens'].append({
            'nome': r['produto__nome_venda'],
            'qtd': float(r['qtd'] or 0),
            'total': float(r['total'] or 0),
        })

    por_grupo = sorted(grupos_map.values(), key=lambda g: (g['ordem'], g['grupo']))
    return flat, por_grupo


@transaction.atomic 
@login_required
def salvar_venda(request):
    loja = check_loja(request)
    if not loja: 
        return JsonResponse({'status': 'erro', 'mensagem': 'Usuário sem loja vinculada'}, status=403)

    if request.method == 'POST':
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'status': 'erro', 'mensagem': 'Dados inválidos.'}, status=400)

        try:
            return _processar_salvar_venda(request, loja, data)
        except Exception as exc:
            import traceback
            traceback.print_exc()
            return JsonResponse(
                {'status': 'erro', 'mensagem': f'Erro ao salvar venda: {exc}'},
                status=500,
            )

    return JsonResponse({'status': 'erro', 'mensagem': 'Método inválido'}, status=400)


def _processar_salvar_venda(request, loja, data):

        eh_fiado = bool(data.get('eh_fiado')) and loja.usa_fiado
        valor_pago_inicial = _valor_decimal_payload(data.get('valor_pago_inicial'))
        total_final_venda = _valor_decimal_payload(data.get('total_final'))
        usar_fidelidade = bool(data.get('usar_fidelidade')) and loja.fidelidade_ativa
        desconto_fidelidade = Decimal('0')
        pagamento_dividido = False
        meio_liquidacao = None
        forma_pagamento = None
        eh_cortesia = False
        eh_avaria = False
        tipo_venda = data.get('tipo_venda', 'FINALIZADO')
        if tipo_venda == 'CORTESIA' or data.get('eh_cortesia'):
            eh_cortesia = True
        if tipo_venda == 'AVARIA' or data.get('eh_avaria'):
            eh_avaria = True
        eh_sem_receita = eh_cortesia or eh_avaria
        status_request = data.get('status', 'FINALIZADO')
        pendente_liquidacao = (
            not eh_fiado
            and not eh_sem_receita
            and (status_request == 'AGUARDANDO_FINALIZAR' or tipo_venda == 'ORCAMENTO')
        )

        cliente_id = data.get('cliente_id')
        eh_retirada_loja = (
            tipo_venda == 'RETIRADO_NA_LOJA'
            or data.get('status') == 'RETIRADO_NA_LOJA'
        )
        if eh_fiado:
            eh_entrega = False
        elif eh_retirada_loja:
            eh_entrega = False
        elif cliente_id and loja.trabalha_com_entregas:
            eh_entrega = True
        elif cliente_id:
            eh_entrega = False
        else:
            eh_entrega = bool(data.get('eh_entrega', False))

        if eh_fiado:
            if not cliente_id:
                return JsonResponse({'status': 'erro', 'mensagem': 'Venda fiado exige cliente cadastrado.'}, status=400)
            if eh_entrega:
                return JsonResponse({'status': 'erro', 'mensagem': 'Venda fiado não pode ser entrega.'}, status=400)
            forma_pagamento = 'FIADO'
            meio_liquidacao = data.get('meio_liquidacao') if valor_pago_inicial > 0 else None
            if valor_pago_inicial > 0 and not validar_meio_liquidacao(meio_liquidacao):
                return JsonResponse({'status': 'erro', 'mensagem': 'Meio de liquidação inválido para o pagamento parcial.'}, status=400)
        else:
            forma_pagamento = data.get('forma_pagamento')
            if eh_cortesia:
                forma_pagamento = 'CORTESIA'
            elif eh_avaria:
                forma_pagamento = 'AVARIA'
            if eh_sem_receita and eh_fiado:
                return JsonResponse({'status': 'erro', 'mensagem': 'Cortesia e avaria não podem ser usadas com venda consignada.'}, status=400)
            if pendente_liquidacao:
                forma_pagamento = None
                meio_liquidacao = None
                pagamento_dividido = False
            elif not eh_sem_receita and not validar_forma_pagamento(loja, forma_pagamento):
                return JsonResponse({'status': 'erro', 'mensagem': 'Tipo de lançamento inválido para esta loja.'}, status=400)
            else:
                pagamento_dividido = bool(data.get('pagamento_dividido')) and loja.permite_pagamento_dividido and not eh_sem_receita
                if pagamento_dividido and data.get('eh_fiado'):
                    return JsonResponse({'status': 'erro', 'mensagem': 'Pagamento dividido não pode ser usado com venda consignada.'}, status=400)

                if eh_cortesia:
                    meio_liquidacao = 'CORTESIA'
                    pagamento_dividido = False
                elif eh_avaria:
                    meio_liquidacao = None
                    pagamento_dividido = False
                elif pagamento_dividido:
                    meio_liquidacao = 'MISTO'
                else:
                    meio_liquidacao = data.get('meio_liquidacao')
                    if not validar_meio_liquidacao(meio_liquidacao):
                        return JsonResponse({'status': 'erro', 'mensagem': 'Meio de liquidação inválido.'}, status=400)

        subtotal_itens = _subtotal_itens_payload(data)
        usa_taxa_servico = loja_usa_taxa_servico(loja) and not eh_sem_receita

        if usar_fidelidade and cliente_id and not eh_fiado and not eh_sem_receita:
            try:
                cliente_fid = Cliente.objects.get(id=cliente_id, loja=loja)
            except Cliente.DoesNotExist:
                cliente_fid = None
            if cliente_fid:
                desconto_fidelidade = calcular_desconto_fidelidade(
                    cliente_fid, loja, subtotal_itens, usar_promocao=True
                )

        taxa_servico_pct_val = Decimal('0')
        taxa_servico_valor = Decimal('0')
        nova_taxa_entrega = Decimal('0')

        if usa_taxa_servico:
            taxa_servico_pct_val = _valor_decimal_payload(
                data.get('taxa_servico_pct'),
                default=str(loja.taxa_servico_pct or 10),
            )
            if taxa_servico_pct_val < 0:
                taxa_servico_pct_val = Decimal('0')
            if data.get('atualizar_padrao') is True:
                loja.taxa_servico_pct = taxa_servico_pct_val
                loja.save(update_fields=['taxa_servico_pct'])
        else:
            taxa_entrega_payload = _valor_decimal_payload(data.get('taxa_entrega'))
            if taxa_entrega_payload > 0 and not eh_entrega:
                return JsonResponse({
                    'status': 'erro',
                    'mensagem': (
                        'Taxa de entrega só pode ser aplicada em vendas com entrega. '
                        'Selecione um cliente para entrega.'
                    ),
                }, status=400)
            if eh_entrega:
                nova_taxa_entrega = taxa_entrega_payload
                if data.get('atualizar_padrao') is True:
                    loja.taxa_entrega_pdv = nova_taxa_entrega
                    loja.save(update_fields=['taxa_entrega_pdv'])

        if eh_sem_receita:
            total_final_venda = Decimal('0')
            taxa_servico_valor = Decimal('0')
            taxa_servico_pct_val = Decimal('0')
            nova_taxa_entrega = Decimal('0')
        else:
            base_apos_fid = max(subtotal_itens - desconto_fidelidade, Decimal('0'))
            if usa_taxa_servico:
                taxa_servico_valor = (
                    base_apos_fid * taxa_servico_pct_val / Decimal('100')
                ).quantize(Decimal('0.01'))
            total_final_venda = base_apos_fid + taxa_servico_valor + nova_taxa_entrega

        if eh_fiado and valor_pago_inicial > total_final_venda:
            return JsonResponse(
                {'status': 'erro', 'mensagem': 'Valor pago não pode ser maior que o total.'},
                status=400,
            )

        if not eh_sem_receita and total_final_venda <= 0:
            return JsonResponse({'status': 'erro', 'mensagem': 'Total da venda inválido.'}, status=400)

        endereco_entrega = ""
        
        if eh_entrega:
            cliente_id = data.get('cliente_id')
            if cliente_id:
                try:
                    cli = Cliente.objects.get(id=cliente_id, loja=loja)
                    endereco_entrega = cli.endereco if cli.endereco else "Endereço não cadastrado no cliente"
                except Cliente.DoesNotExist:
                    endereco_entrega = "Cliente não encontrado"
            else:
                endereco_entrega = "Cliente Avulso"

        status_entrega_inicial = 'PENDENTE' if eh_entrega else 'ENTREGUE'
        
        venda_id = data.get('venda_id') 
        valor_troco = data.get('troco_para')
        if pagamento_dividido or (meio_liquidacao and meio_liquidacao != 'DINHEIRO'):
            valor_troco = None
        elif not valor_troco or valor_troco == '':
            valor_troco = None
        else:
            valor_troco = _valor_decimal_payload(valor_troco)
            if valor_troco <= 0:
                valor_troco = None

        # VARIÁVEL PARA CONTROLAR SE É UMA VENDA NOVA QUE PRECISA BAIXAR ESTOQUE
        dar_baixa_estoque = False
        status_venda = 'FIADO' if eh_fiado else data.get('status', 'FINALIZADO')
        if not eh_fiado and tipo_venda == 'ORCAMENTO':
            status_venda = 'ORCAMENTO'
        elif not eh_fiado and eh_retirada_loja:
            status_venda = 'RETIRADO_NA_LOJA'
            eh_entrega = False
        elif not eh_fiado and eh_cortesia and status_venda not in ('AGUARDANDO_FINALIZAR', 'EM_PREPARACAO'):
            status_venda = 'FINALIZADO'
            eh_entrega = False
        elif not eh_fiado and eh_avaria:
            status_venda = 'FINALIZADO'
            eh_entrega = False
        if eh_entrega and not eh_fiado and status_venda == 'FINALIZADO':
            status_venda = 'EM_PREPARACAO'

        if venda_id:
            try:
                venda = Venda.objects.get(id=venda_id, loja=loja)
                venda.cliente_id = data.get('cliente_id') if data.get('cliente_id') else None
                venda.status = status_venda
                venda.forma_pagamento = forma_pagamento
                venda.meio_liquidacao = meio_liquidacao
                venda.eh_fiado = eh_fiado
                venda.taxa_entrega = nova_taxa_entrega
                venda.taxa_servico = taxa_servico_valor
                venda.taxa_servico_pct = taxa_servico_pct_val
                venda.total = total_final_venda
                venda.troco_para = valor_troco if not pagamento_dividido else None
                venda.eh_entrega = eh_entrega
                venda.endereco_entrega = endereco_entrega
                venda.pagamento_dividido = pagamento_dividido
                venda.eh_cortesia = eh_cortesia
                venda.eh_avaria = eh_avaria
                venda.desconto_fidelidade = desconto_fidelidade
                
                if eh_entrega:
                    venda.status_entrega = 'PENDENTE'
                
                venda.save()
                
                # Exclui os itens antigos da venda aberta para recriar com os do carrinho atual
                ItemVenda.objects.filter(venda=venda).delete()
                PagamentoFiado.objects.filter(venda=venda).delete()
                LiquidacaoVenda.objects.filter(venda=venda).delete()
                nova_venda = venda 
                
                if venda.status in ['FINALIZADO', 'RETIRADO_NA_LOJA', 'FIADO']:
                    dar_baixa_estoque = True

            except Venda.DoesNotExist:
                 return JsonResponse({'status': 'erro', 'mensagem': 'Venda não encontrada'}, status=404)
        else:
            nova_venda = Venda.objects.create(
                loja=loja, 
                cliente_id=data.get('cliente_id') if data.get('cliente_id') else None,
                vendedor=request.user,
                status=status_venda,
                forma_pagamento=forma_pagamento,
                meio_liquidacao=meio_liquidacao,
                pagamento_dividido=pagamento_dividido,
                taxa_entrega=nova_taxa_entrega,
                taxa_servico=taxa_servico_valor,
                taxa_servico_pct=taxa_servico_pct_val,
                total=total_final_venda,
                eh_entrega=eh_entrega,
                endereco_entrega=endereco_entrega,
                status_entrega=status_entrega_inicial,
                troco_para=valor_troco if not pagamento_dividido else None,
                eh_fiado=eh_fiado,
                eh_cortesia=eh_cortesia,
                eh_avaria=eh_avaria,
                desconto_fidelidade=desconto_fidelidade,
                conferencia_ok=False,
            )
            if nova_venda.status in ['FINALIZADO', 'RETIRADO_NA_LOJA', 'FIADO']:
                dar_baixa_estoque = True

        if status_venda in STATUS_COMPROMETIDOS:
            for item in data.get('itens', []):
                try:
                    produto = Produto.objects.select_related('item_estoque', 'item_estoque__loja').get(
                        id=item['id'], loja=loja
                    )
                except Produto.DoesNotExist:
                    return JsonResponse(
                        {'status': 'erro', 'mensagem': 'Produto não encontrado.'}, status=400
                    )
                err = validar_estoque_item_venda(
                    loja, produto, item['quantidade'],
                    venda_completa=bool(item.get('venda_completa')),
                )
                if err:
                    return JsonResponse({'status': 'erro', 'mensagem': err}, status=400)

        # --- CRIANDO OS ITENS E BAIXANDO DO ESTOQUE (SE NECESSÁRIO) ---
        for item in data['itens']:
            try:
                produto = Produto.objects.get(id=item['id'], loja=loja)
                quantidade_vendida = item['quantidade']
                baixa_vazio = produto.vende_vasilhame_vazio and loja.controla_vasilhame_vazio
                item_venda_completa = bool(item.get('venda_completa'))
                
                ItemVenda.objects.create(
                    venda=nova_venda,
                    produto=produto,
                    quantidade=quantidade_vendida,
                    preco_unitario=item['preco'],
                    custo_unitario=custo_unitario_produto_venda(produto),
                    baixa_vasilhame_vazio=baixa_vazio and not item_venda_completa,
                    venda_completa=item_venda_completa,
                )
                # Baixa de estoque (e vazios) via signals em models.py

            except Produto.DoesNotExist:
                pass 

        status_gera_liquidacao = (not eh_fiado) and (not eh_sem_receita) and status_venda in STATUS_GERA_LIQUIDACAO
        if status_gera_liquidacao:
            caixa_aberto = Caixa.objects.filter(loja=loja, status=True).first()
            total_final = total_final_venda

            if pagamento_dividido:
                liquidacoes = data.get('liquidacoes') or []
                err = validar_liquidacoes_payload(total_final, liquidacoes, exige_multiplo=True)
            else:
                liquidacoes = [{
                    'meio_liquidacao': meio_liquidacao,
                    'valor': total_final,
                    'troco_para': valor_troco if meio_liquidacao == 'DINHEIRO' and valor_troco else None,
                }]
                err = validar_liquidacoes_payload(total_final, liquidacoes)

            if err:
                return JsonResponse({'status': 'erro', 'mensagem': err}, status=400)

            persistir_liquidacoes_venda(
                nova_venda, liquidacoes, caixa=caixa_aberto, usuario=request.user
            )
            nova_venda.forma_pagamento = forma_pagamento
            nova_venda.save(update_fields=['forma_pagamento'])
        else:
            LiquidacaoVenda.objects.filter(venda=nova_venda).delete()

        if eh_fiado and valor_pago_inicial > 0:
            caixa_aberto = Caixa.objects.filter(loja=loja, status=True).first()
            liquidacoes_entrada = data.get('liquidacoes') or []
            if len(liquidacoes_entrada) > 1:
                for liq in liquidacoes_entrada:
                    meio_ent = liq.get('meio_liquidacao')
                    val_ent = _valor_decimal_payload(liq.get('valor'))
                    if val_ent <= 0 or not validar_meio_liquidacao(meio_ent):
                        continue
                    PagamentoFiado.objects.create(
                        loja=loja,
                        venda=nova_venda,
                        valor=val_ent,
                        meio_liquidacao=meio_ent,
                        observacao='Pagamento parcial na venda',
                        registrado_por=request.user,
                        caixa=caixa_aberto,
                    )
            else:
                PagamentoFiado.objects.create(
                    loja=loja,
                    venda=nova_venda,
                    valor=valor_pago_inicial,
                    meio_liquidacao=meio_liquidacao or 'DINHEIRO',
                    observacao='Pagamento parcial na venda',
                    registrado_por=request.user,
                    caixa=caixa_aberto,
                )
            if nova_venda.saldo_devedor <= 0:
                nova_venda.status = 'FINALIZADO'
                nova_venda.save(update_fields=['status'])

        # =================================================================
        # GATILHO MOVEON: DISPARA A CORRIDA ASSIM QUE A VENDA É SALVA!
        # =================================================================
        if eh_entrega and loja.monitorar_entrega and getattr(loja, 'usa_moveon', False):
            from transporte.models import Corrida
            if not Corrida.objects.filter(venda_pdv_id=nova_venda.id).exists():
                zap = nova_venda.cliente.whatsapp if (nova_venda.cliente and nova_venda.cliente.whatsapp) else ""
                
                Corrida.objects.create(
                    venda_pdv_id=nova_venda.id,
                    cliente_nome=f"Entrega: {loja.nome} (Para: {nova_venda.cliente.nome if nova_venda.cliente else 'Avulso'})",
                    cliente_whatsapp=zap,
                    origem_texto=loja.nome, 
                    destino_texto=nova_venda.endereco_entrega or "Endereço não informado",
                    valor_cobrado=nova_venda.taxa_entrega,
                    status='SOLICITADO' # Isso faz aparecer no App!
                )
        # =================================================================

        if usar_fidelidade and desconto_fidelidade > 0 and nova_venda.cliente:
            obs = nova_venda.observacao or ''
            if 'FIDELIDADE: promoção utilizada' not in obs:
                nova_venda.observacao = (obs + '\nFIDELIDADE: promoção utilizada').strip()
                nova_venda.save(update_fields=['observacao'])

        registrar_log(
            request, 'VENDA',
            f'Venda #{nova_venda.id} — R$ {nova_venda.total} — status {nova_venda.status}',
            modelo='Venda', objeto_id=nova_venda.id, loja=loja,
        )

        return JsonResponse({'status': 'sucesso', 'venda_id': nova_venda.id})


@login_required
@transaction.atomic
def cancelar_venda_pdv(request, id):
    loja = check_loja(request)
    venda = get_object_or_404(Venda, pk=id, loja=loja)
    
    # Proteção: Se já estiver cancelada, não faz nada
    if venda.status == 'CANCELADO':
        messages.warning(request, 'Esta venda já foi cancelada anteriormente.')
        return redirect('detalhes_venda', id=id)

    # O SISTEMA VAI LER ESSA MUDANÇA E DEVOLVER OS ITENS MAGIGAMENTE PELO SIGNALS DO MODEL!
    venda.status = 'CANCELADO'
    venda.save()
    registrar_log(
        request, 'VENDA',
        f'Venda #{venda.id} cancelada — estoque estornado',
        modelo='Venda', objeto_id=venda.id, loja=loja,
    )
    
    messages.success(request, f'Venda #{venda.id} cancelada e estoque estornado com sucesso!')
    return redirect('detalhes_venda', id=id)

@login_required
def retomar_venda(request, id):
    loja = check_loja(request)
    # Busca a venda pausada
    venda = get_object_or_404(Venda, pk=id, loja=loja)
    
    # Se já estiver finalizada, não deixa editar, joga pra lista
    if venda.status in ('FINALIZADO', 'RETIRADO_NA_LOJA', 'CANCELADO'):
        messages.warning(request, "Esta venda já foi finalizada ou cancelada.")
        return redirect('lista_vendas')

    # Recupera os itens dessa venda para preencher o carrinho do JavaScript
    itens_venda = ItemVenda.objects.filter(venda=venda).select_related(
        'produto__item_estoque'
    )
    lista_itens = []
    
    for item in itens_venda:
        unidade = 'UN'
        if item.produto.item_estoque_id:
            unidade = item.produto.item_estoque.unidade_medida or 'UN'
        lista_itens.append({
            'id': str(item.produto.id),
            'nome': item.produto.nome_venda,
            'preco': float(item.preco_unitario),
            'quantidade': float(item.quantidade),
            'unidade': unidade,
            'venda_completa': bool(item.venda_completa),
        })
    
    # Transforma em JSON para o template ler
    itens_json = json.dumps(lista_itens, cls=DjangoJSONEncoder)
    
    produtos = produtos_disponiveis_pdv(loja)
    clientes = Cliente.objects.filter(loja=loja)

    # Envia tudo para a mesma tela de Vendas.html, mas com os dados preenchidos
    # Garante criação de novas formas (ex.: CORTESIA) em lojas antigas
    if not FormaPagamentoLoja.objects.filter(loja=loja, codigo='CORTESIA').exists():
        criar_formas_pagamento_padrao(loja)

    liquidacoes_json = '[]'
    if venda.liquidacoes.exists():
        liquidacoes_json = json.dumps([
            {
                'meio_liquidacao': liq.meio_liquidacao,
                'valor': float(liq.valor),
                'troco_para': float(liq.troco_para) if liq.troco_para else None,
            }
            for liq in venda.liquidacoes.all()
        ], cls=DjangoJSONEncoder)

    context = _context_tela_vendas(
        loja, produtos, clientes,
        request=request,
        venda_aberta=venda,
        itens_json=itens_json,
        liquidacoes_json=liquidacoes_json,
        taxa_servico_pct=venda.taxa_servico_pct if venda.taxa_servico_pct else loja.taxa_servico_pct,
    )
    return render(request, 'app_pdv/vendas.html', context)


# ------------------------- DASHBOARD ------------------------------

@login_required
def dashboard(request):

    # --- TRAVA DE SEGURANÇA E REDIRECIONAMENTO DE CAIXAS ---
    # Se o usuário não for o dono E não tiver a permissão para ver o Dashboard, joga ele pro PDV.
    if hasattr(request.user, 'perfil') and not request.user.is_superuser and not request.user.perfil.perm_dashboard:
        return redirect('nova_venda') 
    # ---------------------------------------------------------

    # 1. IDENTIFICA AS LOJAS DO USUÁRIO (Visão de Rede)
    if request.user.is_superuser:
        lojas_permitidas = Loja.objects.all()
    else:
        lojas_permitidas = request.user.lojas_gerenciadas.all()
        if not lojas_permitidas.exists():
            loja_unica = check_loja(request)
            if not loja_unica: return redirect('admin:index')
            lojas_permitidas = Loja.objects.filter(id=loja_unica.id)

    # 2. VERIFICA O QUE ELE SELECIONOU NO FILTRO (Todas ou Específica)
    loja_selecionada_id = request.GET.get('loja_id', 'todas')
    
    if loja_selecionada_id != 'todas':
        lojas_alvo = lojas_permitidas.filter(id=loja_selecionada_id)
    else:
        lojas_alvo = lojas_permitidas

    hoje = datetime.now()
    ano = hoje.year
    mes = hoje.month

    # --- ATUALIZANDO TODOS OS FILTROS PARA USAR loja__in=lojas_alvo ---

    vendas_mes_qs = Venda.objects.filter(
        loja__in=lojas_alvo,
        data_venda__year=ano, 
        data_venda__month=mes,
        status__in=STATUS_VENDA_FATURADA,
    )

    faturamento_total = vendas_mes_qs.aggregate(Sum('total'))['total__sum'] or 0
    
    melhor_cliente = vendas_mes_qs.values('cliente__nome').annotate(
        total_gasto=Sum('total')
    ).order_by('-total_gasto').first()

    produto_campeao_qs = ItemVenda.objects.filter(
        venda__loja__in=lojas_alvo,
        venda__data_venda__year=ano,
        venda__data_venda__month=mes,
        venda__status__in=STATUS_VENDA_FATURADA,
    ).values('produto__nome_venda').annotate(
        lucro_total=Sum(
            (F('preco_unitario') - Coalesce(F('custo_unitario'), F('produto__preco_compra'), DECIMAL_ZERO))
            * F('quantidade'),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        )
    ).order_by('-lucro_total').first()

    estoque_baixo = ItemEstoque.objects.filter(
        loja__in=lojas_alvo,
        quantidade_estoque__lte=10
    ).order_by('quantidade_estoque')[:3]

    data_inicio_grafico = hoje - timedelta(days=15)
    
    vendas_diarias = Venda.objects.filter(
        loja__in=lojas_alvo,
        data_venda__date__gte=data_inicio_grafico,
        status__in=STATUS_VENDA_FATURADA,
    ).annotate(
        data_formatada=TruncDate('data_venda')
    ).values('data_formatada').annotate(
        total=Sum('total')
    ).order_by('data_formatada')
    
    grafico_datas = []
    grafico_valores = []
    
    for v in vendas_diarias:
        grafico_datas.append(v['data_formatada'].strftime('%d/%m'))
        grafico_valores.append(float(v['total']))

    ultimas_vendas = Venda.objects.filter(loja__in=lojas_alvo).select_related('cliente').order_by('-data_venda')[:6]

    context = {
        'vendas_mes': faturamento_total,
        'melhor_cliente': melhor_cliente,
        'produto_campeao': produto_campeao_qs,
        'estoque_baixo': estoque_baixo,
        'ultimas_vendas': ultimas_vendas,
        'grafico_labels': json.dumps(grafico_datas),  
        'grafico_data': json.dumps(grafico_valores),
        
        # Variáveis do Dropdown
        'lojas_permitidas': lojas_permitidas,
        'loja_selecionada_id': loja_selecionada_id,
        'mostrar_filtro_lojas': lojas_permitidas.count() > 1,
        'ranking_recompra': montar_ranking_recompra(lojas_alvo, limite=15),
    }
    return render(request, 'app_pdv/dashboard.html', context)


# ---------------------- FORNECEDORES -----------------------------------

@login_required
def deletar_fornecedor(request, id):
    loja = check_loja(request)
    get_object_or_404(Fornecedor, pk=id, loja=loja).delete()
    return redirect('lista_fornecedores')

@login_required
def lista_fornecedores(request):
    loja = check_loja(request)
    if not loja: return redirect('admin:index')
    fornecedores = Fornecedor.objects.filter(loja=loja)
    return render(request, 'app_pdv/lista_fornecedores.html', {'fornecedores': fornecedores})

@login_required
def gerenciar_fornecedor(request, id=None):
    loja = check_loja(request)
    if not loja: return redirect('admin:index')

    fornecedor = get_object_or_404(Fornecedor, pk=id, loja=loja) if id else None
    if request.method == 'POST':
        form = FornecedorForm(request.POST, instance=fornecedor)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.loja = loja
            obj.save()
            return redirect('lista_fornecedores')
    else:
        form = FornecedorForm(instance=fornecedor)
    return render(request, 'app_pdv/form_generico.html', {'form': form, 'titulo': 'Fornecedor'})


# -------------------------- LOJAS (Apenas SuperAdmin ou Dono vê) --------------------------------------
@login_required
def lista_lojas(request):
    
    if request.user.is_superuser:
        lojas = Loja.objects.all()
    else:
        lojas = Loja.objects.filter(id=request.user.perfil.loja.id)
        
    return render(request, 'app_pdv/lista_lojas.html', {'lojas': lojas})

@login_required
def gerenciar_loja(request, id=None):
    
    loja_usuario = check_loja(request)
    
    if not request.user.is_superuser:
        
        if str(id) != str(loja_usuario.id):
             messages.error(request, "Você não tem permissão para editar outras lojas.")
             return redirect('lista_lojas')

    loja = get_object_or_404(Loja, pk=id) if id else None
    if request.method == 'POST':
        form = LojaForm(request.POST, instance=loja)
        if form.is_valid():
            form.save()
            return redirect('lista_lojas')
    else:
        form = LojaForm(instance=loja)
    return render(request, 'app_pdv/form_generico.html', {'form': form, 'titulo': 'Loja'})

@api_view(['GET'])
@permission_classes([AllowAny]) # Deixa qualquer cliente ver as lojas sem precisar de login
def api_listar_lojas_rede(request):
    slug_rede = request.GET.get('rede')
    
    if slug_rede:
        lojas = Loja.objects.filter(rede__slug=slug_rede, ativo=True)
    else:
        lojas = Loja.objects.filter(ativo=True)

    lista = []
    for loja in lojas:
        # Blindagem 1: Pega o nome da unidade, se não existir pega o nome da loja
        nome_exibicao = getattr(loja, 'nome_unidade', None)
        if not nome_exibicao:
            nome_exibicao = loja.nome
            
        # Blindagem 2: Pega o bairro, se não existir no banco, envia vazio sem dar erro
        bairro_exibicao = getattr(loja, 'cidade_bairro', "")
        
        lista.append({
            'id': loja.id,
            'nome': nome_exibicao,
            'bairro': bairro_exibicao
        })
        
    return JsonResponse(lista, safe=False)


# ---------------------------- CAIXA --------------------------------

@login_required
def fluxo_caixa(request):
    loja = check_loja(request)
    if not loja: return redirect('admin:index')
    
    hoje = date.today()
    caixa_aberto = Caixa.objects.filter(loja=loja, status=True).first()
    
    if request.method == 'POST' and not caixa_aberto:
        saldo_inicial = request.POST.get('saldo_inicial')
        if loja:
            caixa_novo = Caixa.objects.create(
                loja=loja, 
                saldo_inicial=saldo_inicial,
                data_hora_abertura=timezone.now()
            )
            registrar_log(
                request, 'CAIXA',
                f'Caixa aberto — saldo inicial R$ {saldo_inicial}',
                modelo='Caixa', objeto_id=caixa_novo.id, loja=loja,
            )
            messages.success(request, "Novo turno aberto com sucesso!")
            return redirect('fluxo_caixa')

    context = {
        'hoje': hoje,
        'caixa_aberto': False,
        'historico_turnos': [] 
    }

    if caixa_aberto:
        inicio_turno = caixa_aberto.data_hora_abertura
        if not inicio_turno:
             inicio_turno = datetime.combine(caixa_aberto.data, datetime.min.time())
        
        vendas_turno = Venda.objects.filter(
            loja=loja, 
            status__in=STATUS_VENDA_FATURADA,
            data_venda__gte=inicio_turno  
        )

        pagamentos_fiado_turno = PagamentoFiado.objects.filter(
            loja=loja,
            data_pagamento__gte=inicio_turno,
        )
        pagamentos_mercadoria_turno = PagamentoMercadoria.objects.filter(
            loja=loja,
            data_pagamento__gte=inicio_turno,
        )
        
        total_vendas = vendas_turno.aggregate(Sum('total'))['total__sum'] or 0
        total_fiado_turno = pagamentos_fiado_turno.aggregate(Sum('valor'))['valor__sum'] or 0
        total_dinheiro = calcular_entradas_gaveta(
            vendas_turno, pagamentos_fiado_turno, pagamentos_mercadoria_turno,
        )
        resumo_pagamentos = montar_resumo_liquidacao_loja(
            vendas_turno, pagamentos_fiado_turno, pagamentos_mercadoria_turno,
        )

        # --- BUSCA APENAS TRANSAÇÕES AMARRADAS NESTE TURNO ---
        transacoes_caixa = Transacao.objects.filter(caixa=caixa_aberto)
        
        entradas_dinheiro = transacoes_caixa.filter(categoria__tipo='RECEITA').aggregate(Sum('valor'))['valor__sum'] or 0
        saidas_dinheiro = transacoes_caixa.filter(categoria__tipo='DESPESA').aggregate(Sum('valor'))['valor__sum'] or 0

        saldo_atual_caixa = (caixa_aberto.saldo_inicial + total_dinheiro + entradas_dinheiro) - saidas_dinheiro

        context.update({
            'caixa_aberto': True,
            'caixa': caixa_aberto, 
            'saldo_inicial': caixa_aberto.saldo_inicial,
            'saldo_atual_caixa': saldo_atual_caixa,
            'total_vendas': total_vendas,
            'total_fiado_turno': total_fiado_turno,
            'total_recebido_turno': total_vendas + total_fiado_turno,
            'total_dinheiro': total_dinheiro,
            'resumo_pagamentos': resumo_pagamentos,
        })
    
    turnos_fechados = Caixa.objects.filter(loja=loja, data=hoje, status=False).order_by('-id')
    context['historico_turnos'] = turnos_fechados
    
    return render(request, 'app_pdv/caixa.html', context)


@login_required
def fechar_caixa(request):
    loja = check_loja(request)
    caixa = Caixa.objects.filter(loja=loja, status=True).first() 
    
    if not caixa:
        messages.error(request, "Não há caixa aberto para fechar.")
        return redirect('fluxo_caixa') 

    if request.method == 'POST':
        vendas = vendas_turno_caixa(caixa)
        inicio_turno = caixa.data_hora_abertura
        if not inicio_turno:
            inicio_turno = datetime.combine(caixa.data, datetime.min.time())

        pagamentos_fiado = PagamentoFiado.objects.filter(
            loja=loja,
            data_pagamento__gte=inicio_turno,
        )
        pagamentos_mercadoria = PagamentoMercadoria.objects.filter(
            loja=loja,
            data_pagamento__gte=inicio_turno,
        ).select_related('entrada__item', 'entrada__fornecedor')
        
        total_vendas = vendas.aggregate(Sum('total'))['total__sum'] or 0
        total_fiado = pagamentos_fiado.aggregate(Sum('valor'))['valor__sum'] or 0
        total_pag_mercadoria = pagamentos_mercadoria.aggregate(Sum('valor'))['valor__sum'] or 0
        dinheiro_vendas = calcular_entradas_gaveta(vendas, pagamentos_fiado, pagamentos_mercadoria)
        
        # --- USA APENAS AS TRANSAÇÕES DESTE TURNO NA NOTA ---
        transacoes_caixa = Transacao.objects.filter(caixa=caixa)
        
        entradas_dinheiro = transacoes_caixa.filter(categoria__tipo='RECEITA').aggregate(Sum('valor'))['valor__sum'] or 0
        saidas_dinheiro = transacoes_caixa.filter(categoria__tipo='DESPESA').aggregate(Sum('valor'))['valor__sum'] or 0

        saldo_final_calculado = (caixa.saldo_inicial + dinheiro_vendas + entradas_dinheiro) - saidas_dinheiro
        
        caixa.saldo_final = saldo_final_calculado
        caixa.data_hora_fechamento = timezone.now()
        caixa.status = False
        caixa.save()
        registrar_log(
            request, 'CAIXA',
            f'Caixa fechado — saldo final R$ {saldo_final_calculado}',
            modelo='Caixa', objeto_id=caixa.id, loja=loja,
        )

        resumo_pgto = montar_resumo_liquidacao_loja(vendas, pagamentos_fiado, pagamentos_mercadoria)
        produtos_vendidos, produtos_por_grupo = agregar_produtos_vendas(vendas, loja)
        total_produtos_qtd = sum(p['qtd'] for p in produtos_vendidos)
        total_produtos_valor = sum(p['total'] for p in produtos_vendidos)

        context = {
            'caixa': caixa,
            'operador': request.user,
            'data_fechamento': timezone.localtime(timezone.now()),
            'total_vendas': total_vendas,
            'total_fiado': total_fiado,
            'total_recebido': total_vendas + total_fiado,
            'total_pag_mercadoria': total_pag_mercadoria,
            'pagamentos_mercadoria': pagamentos_mercadoria,
            'dinheiro_vendas': dinheiro_vendas, 
            'entradas': entradas_dinheiro, 
            'saidas': saidas_dinheiro,     
            'resumo_pgto': resumo_pgto,
            'produtos_vendidos': produtos_vendidos,
            'produtos_por_grupo': produtos_por_grupo,
            'divide_produtos_por_grupos': loja.divide_produtos_por_grupos,
            'total_produtos_qtd': total_produtos_qtd,
            'total_produtos_valor': total_produtos_valor,
        }
        return render(request, 'app_pdv/recibo_fechamento.html', context)
    
    return redirect('fluxo_caixa')


# -------------------------- Estoque --------------------------------------

def limpar_nome_extremo(nome):
    """Normaliza nome para parear itens entre filiais (mesma lógica da transferência unitária)."""
    if not nome:
        return ""
    sem_acento = unicodedata.normalize('NFKD', str(nome)).encode('ASCII', 'ignore').decode('utf-8')
    return " ".join(sem_acento.lower().split())


def lojas_destino_transferencia(user, loja_origem):
    """Lojas para onde o usuário pode transferir (exceto a origem)."""
    if user.is_superuser:
        return Loja.objects.exclude(id=loja_origem.id).filter(ativo=True)
    return user.lojas_gerenciadas.exclude(id=loja_origem.id).filter(ativo=True)


def loja_destino_e_permitida(user, loja_origem, loja_destino):
    return lojas_destino_transferencia(user, loja_origem).filter(pk=loja_destino.pk).exists()


def mapa_itens_destino_por_nome_limpo(loja_destino):
    """Um ItemEstoque por nome normalizado (primeiro ganha se houver colisão improvável)."""
    m = {}
    for item in ItemEstoque.objects.filter(loja=loja_destino):
        k = limpar_nome_extremo(item.nome)
        if k not in m:
            m[k] = item
    return m


def transferir_um_item_estoque(item_origem, loja_origem, loja_destino, qtd, user, destino_map=None):
    """
    Transfere quantidade da origem para o item homônimo (nome normalizado) no destino.
    destino_map: opcional, dict nome_limpo -> ItemEstoque (reuso em lote).
    Retorna (True, None) ou (False, mensagem_erro).
    """
    if item_origem.loja_id != loja_origem.id:
        return False, 'Item não pertence à loja de origem.'
    if qtd <= 0:
        return False, 'A quantidade deve ser maior que zero.'
    if qtd > item_origem.quantidade_estoque:
        return False, (
            f"Estoque insuficiente para '{item_origem.nome}'! "
            f"Disponível: {item_origem.estoque_formatado}."
        )

    if destino_map is None:
        destino_map = mapa_itens_destino_por_nome_limpo(loja_destino)

    nome_limpo = limpar_nome_extremo(item_origem.nome)
    item_destino = destino_map.get(nome_limpo)
    if not item_destino:
        return False, (
            f"BLOQUEADO: O item '{item_origem.nome}' não foi encontrado na {loja_destino.nome} "
            'nem mesmo ignorando acentos. Importe a planilha na filial destino primeiro.'
        )

    item_origem.quantidade_estoque -= qtd
    item_origem.save()

    item_destino.quantidade_estoque += qtd
    item_destino.save()

    LogTransferenciaEstoque.objects.create(
        loja_origem=loja_origem,
        loja_destino=loja_destino,
        item_nome=item_origem.nome,
        quantidade=qtd,
        usuario=user,
    )
    return True, None


@login_required
def lista_estoque(request):
    loja = check_loja(request)
    itens = ItemEstoque.objects.filter(loja=loja).order_by('nome')
    usa_estoque_diario = estoque_diario_ativo(loja)
    hoje = date.today()
    precisa_abertura = False
    fechamento_hoje = False
    if usa_estoque_diario:
        precisa_abertura = not LogFechamentoEstoqueDiario.objects.filter(
            loja=loja, data_referencia=hoje, tipo='ABERTURA'
        ).exists()
        fechamento_hoje = LogFechamentoEstoqueDiario.objects.filter(
            loja=loja, data_referencia=hoje, tipo='FECHAMENTO'
        ).exists()

    itens_contagem = [
        {
            'id': i.id,
            'nome': i.nome,
            'cheios': float(i.quantidade_estoque),
            'vazios': float(i.quantidade_vazios),
            'unidade': i.unidade_medida,
        }
        for i in itens
    ]

    return render(request, 'app_pdv/lista_estoque.html', {
        'itens': itens,
        'controla_vasilhame_vazio': loja.controla_vasilhame_vazio,
        'estoque_diario': usa_estoque_diario,
        'precisa_abertura': precisa_abertura,
        'fechamento_hoje': fechamento_hoje,
        'itens_contagem_json': json.dumps(itens_contagem, cls=DjangoJSONEncoder),
    })


@login_required
@transaction.atomic
def atualizar_contagem_estoque(request):
    loja = check_loja(request)
    if not loja or not estoque_diario_ativo(loja):
        return JsonResponse({'status': 'erro', 'mensagem': 'Estoque diário não está ativo nesta loja.'}, status=403)

    if request.method != 'POST':
        return JsonResponse({'status': 'erro', 'mensagem': 'Método inválido.'}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'status': 'erro', 'mensagem': 'Dados inválidos.'}, status=400)

    item = get_object_or_404(ItemEstoque, pk=data.get('item_id'), loja=loja)
    try:
        cheios = Decimal(str(data.get('quantidade_estoque', item.quantidade_estoque)))
        vazios = Decimal(str(data.get('quantidade_vazios', item.quantidade_vazios)))
    except Exception:
        return JsonResponse({'status': 'erro', 'mensagem': 'Quantidades inválidas.'}, status=400)

    if cheios < 0 or vazios < 0:
        return JsonResponse({'status': 'erro', 'mensagem': 'Quantidades não podem ser negativas.'}, status=400)

    item.quantidade_estoque = cheios
    item.quantidade_vazios = vazios
    item.save(update_fields=['quantidade_estoque', 'quantidade_vazios'])

    return JsonResponse({
        'status': 'sucesso',
        'cheios_formatado': item.estoque_formatado_curto,
        'vazios_formatado': item.vazios_formatado_curto,
    })


def _aplicar_contagem_itens(loja, linhas, usuario):
    """linhas: list of dicts item_id, quantidade_estoque, quantidade_vazios"""
    ids = [l['item_id'] for l in linhas]
    itens_map = {
        i.id: i
        for i in ItemEstoque.objects.select_for_update().filter(loja=loja, pk__in=ids)
    }
    if len(itens_map) != len(set(ids)):
        return False, 'Um ou mais itens são inválidos.'

    atualizados = []
    for linha in linhas:
        item = itens_map.get(linha['item_id'])
        if not item:
            return False, f'Item ID {linha["item_id"]} não encontrado.'
        try:
            cheios = Decimal(str(linha['quantidade_estoque']))
            vazios = Decimal(str(linha['quantidade_vazios']))
        except Exception:
            return False, f'Quantidade inválida para "{item.nome}".'
        if cheios < 0 or vazios < 0:
            return False, f'Quantidades negativas não permitidas para "{item.nome}".'
        item.quantidade_estoque = cheios
        item.quantidade_vazios = vazios
        item.save(update_fields=['quantidade_estoque', 'quantidade_vazios'])
        atualizados.append(item)
    return True, atualizados


def _registrar_log_estoque_diario(loja, itens, tipo, usuario, data_ref=None):
    data_ref = data_ref or date.today()
    for item in itens:
        LogFechamentoEstoqueDiario.objects.create(
            loja=loja,
            item_estoque=item,
            data_referencia=data_ref,
            tipo=tipo,
            quantidade_cheios=item.quantidade_estoque,
            quantidade_vazios=item.quantidade_vazios,
            usuario=usuario,
        )


@login_required
@transaction.atomic
def registrar_contagem_diaria(request):
    loja = check_loja(request)
    if not loja or not estoque_diario_ativo(loja):
        return JsonResponse({'status': 'erro', 'mensagem': 'Estoque diário não está ativo nesta loja.'}, status=403)

    if request.method != 'POST':
        return JsonResponse({'status': 'erro', 'mensagem': 'Método inválido.'}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'status': 'erro', 'mensagem': 'Dados inválidos.'}, status=400)

    hoje = date.today()
    if LogFechamentoEstoqueDiario.objects.filter(loja=loja, data_referencia=hoje, tipo='ABERTURA').exists():
        return JsonResponse({'status': 'erro', 'mensagem': 'Abertura do dia já foi registrada.'}, status=400)

    linhas = data.get('itens') or []
    if not linhas:
        return JsonResponse({'status': 'erro', 'mensagem': 'Informe ao menos um item.'}, status=400)

    ok, result = _aplicar_contagem_itens(loja, linhas, request.user)
    if not ok:
        return JsonResponse({'status': 'erro', 'mensagem': result}, status=400)

    _registrar_log_estoque_diario(loja, result, 'ABERTURA', request.user, hoje)
    return JsonResponse({'status': 'sucesso', 'mensagem': 'Contagem de abertura registrada.'})


@login_required
@transaction.atomic
def registrar_fechamento_estoque(request):
    loja = check_loja(request)
    if not loja or not estoque_diario_ativo(loja):
        return JsonResponse({'status': 'erro', 'mensagem': 'Estoque diário não está ativo nesta loja.'}, status=403)

    if request.method != 'POST':
        return JsonResponse({'status': 'erro', 'mensagem': 'Método inválido.'}, status=405)

    hoje = date.today()
    if LogFechamentoEstoqueDiario.objects.filter(loja=loja, data_referencia=hoje, tipo='FECHAMENTO').exists():
        return JsonResponse(
            {'status': 'erro', 'mensagem': 'Fechamento do dia já foi registrado hoje.'}, status=400
        )

    itens = list(ItemEstoque.objects.filter(loja=loja).order_by('nome'))
    if not itens:
        return JsonResponse({'status': 'erro', 'mensagem': 'Nenhum item no estoque.'}, status=400)

    _registrar_log_estoque_diario(loja, itens, 'FECHAMENTO', request.user, hoje)
    return JsonResponse({
        'status': 'sucesso',
        'mensagem': f'Fechamento registrado para {len(itens)} item(ns).',
    })


@login_required
def log_fechamento_estoque(request):
    loja = check_loja(request)
    if not loja:
        return redirect('admin:index')

    qs = LogFechamentoEstoqueDiario.objects.filter(loja=loja).select_related(
        'item_estoque', 'usuario'
    ).order_by('-registrado_em', 'item_estoque__nome')

    tipo = (request.GET.get('tipo') or 'TODOS').upper()
    if tipo in ('ABERTURA', 'FECHAMENTO'):
        qs = qs.filter(tipo=tipo)

    q = (request.GET.get('q') or '').strip()
    if q:
        qs = qs.filter(item_estoque__nome__icontains=q)

    data_ini = (request.GET.get('data_ini') or '').strip()
    data_fim = (request.GET.get('data_fim') or '').strip()
    if data_ini:
        try:
            qs = qs.filter(data_referencia__gte=date.fromisoformat(data_ini))
        except ValueError:
            messages.error(request, 'Data inicial inválida.')
    if data_fim:
        try:
            qs = qs.filter(data_referencia__lte=date.fromisoformat(data_fim))
        except ValueError:
            messages.error(request, 'Data final inválida.')

    logs = qs[:500]

    return render(
        request,
        'app_pdv/log_fechamento_estoque.html',
        {
            'logs': logs,
            'tipo': tipo,
            'q': q,
            'data_ini': data_ini,
            'data_fim': data_fim,
            'estoque_diario': estoque_diario_ativo(loja),
        },
    )

@login_required
def adicionar_estoque(request):
    loja = check_loja(request)
    if request.method == 'POST':
        form = EntradaEstoqueForm(request.POST, loja=loja)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.loja = loja
            obj.save()
            registrar_log(
                request, 'ESTOQUE',
                f'Entrada estoque: {obj.item.nome} +{obj.quantidade}',
                modelo='EntradaEstoque', objeto_id=obj.id, loja=loja,
            )
            return redirect('lista_estoque')
    else:
        form = EntradaEstoqueForm(loja=loja)
    return render(request, 'app_pdv/form_entrada_estoque.html', {
        'form': form, 'titulo': 'Abastecer Estoque (Entrada)'
    })


@login_required
def api_precos_fornecedor_item(request, item_id):
    loja = check_loja(request)
    if not loja:
        return JsonResponse({'erro': 'Loja não encontrada'}, status=403)

    item = get_object_or_404(ItemEstoque, pk=item_id, loja=loja)
    precos = PrecoFornecedorItem.objects.filter(
        loja=loja, item_estoque=item, ativo=True
    ).select_related('fornecedor').order_by('fornecedor__nome')

    dados = [
        {
            'fornecedor_id': p.fornecedor_id,
            'fornecedor_nome': p.fornecedor.nome,
            'preco_compra': float(p.preco_compra),
        }
        for p in precos
    ]
    return JsonResponse(dados, safe=False)

@login_required
@transaction.atomic
def transferir_estoque(request, item_id):
    loja_origem = check_loja(request)
    if not loja_origem:
        return redirect('admin:index')

    item_origem = get_object_or_404(ItemEstoque, pk=item_id, loja=loja_origem)
    lojas_destino = lojas_destino_transferencia(request.user, loja_origem)

    if request.method == 'POST':
        loja_destino_id = request.POST.get('loja_destino')
        qtd_transferir_str = (request.POST.get('quantidade') or '').replace(',', '.')

        try:
            qtd_transferir = Decimal(qtd_transferir_str)
        except Exception:
            messages.error(request, 'Quantidade inválida.')
            return redirect('transferir_estoque', item_id=item_id)

        loja_destino = get_object_or_404(Loja, id=loja_destino_id)
        if not loja_destino_e_permitida(request.user, loja_origem, loja_destino):
            messages.error(request, 'Filial destino não permitida para o seu usuário.')
            return redirect('transferir_estoque', item_id=item_id)

        ok, err = transferir_um_item_estoque(
            item_origem, loja_origem, loja_destino, qtd_transferir, request.user
        )
        if not ok:
            messages.error(request, err)
            return redirect('transferir_estoque', item_id=item_id)

        registrar_log(
            request, 'TRANSFERIR',
            f"Transferiu {qtd_transferir} {item_origem.unidade_medida} de '{item_origem.nome}' "
            f'para {loja_destino.nome}',
            modelo='ItemEstoque', objeto_id=item_origem.id, loja=loja_origem,
        )
        messages.success(
            request,
            f"Sucesso! {qtd_transferir} {item_origem.unidade_medida} de '{item_origem.nome}' "
            f'foram transferidos para a {loja_destino.nome}.',
        )
        return redirect('lista_estoque')

    return render(request, 'app_pdv/transferir_estoque.html', {
        'item': item_origem,
        'lojas': lojas_destino,
    })


def _executar_transferencia_lote(loja_origem, loja_destino, linhas, user):
    """
    linhas: lista de (item_id, Decimal qtd).
    Valida tudo, bloqueia linhas e aplica em uma única transação (tudo ou nada).
    Retorna (True, None) ou (False, mensagem_erro).
    """
    if not linhas:
        return False, 'Nenhuma linha para transferir.'

    destino_map = mapa_itens_destino_por_nome_limpo(loja_destino)

    ids_origem = sorted({i for i, _ in linhas})
    origem_por_id = {
        i.id: i
        for i in ItemEstoque.objects.filter(
            loja=loja_origem, pk__in=ids_origem
        ).select_for_update().order_by('pk')
    }
    if len(origem_por_id) != len(set(ids_origem)):
        return False, 'Um ou mais itens de origem são inválidos ou não pertencem à sua loja.'

    preparados = []
    for item_id, qtd in linhas:
        item_origem = origem_por_id.get(item_id)
        if not item_origem:
            return False, f'Item ID {item_id} inválido.'
        if qtd <= 0:
            return False, f'A quantidade deve ser maior que zero para "{item_origem.nome}".'
        if qtd > item_origem.quantidade_estoque:
            return False, (
                f'Estoque insuficiente para "{item_origem.nome}"! '
                f'Disponível: {item_origem.estoque_formatado}.'
            )
        nome_limpo = limpar_nome_extremo(item_origem.nome)
        item_destino = destino_map.get(nome_limpo)
        if not item_destino:
            return False, (
                f'BLOQUEADO: O item "{item_origem.nome}" não foi encontrado na {loja_destino.nome} '
                'nem mesmo ignorando acentos. Importe a planilha na filial destino primeiro.'
            )
        preparados.append((item_origem, item_destino, qtd))

    dest_ids = sorted({d.id for _, d, _ in preparados})
    destino_por_id = {
        i.id: i
        for i in ItemEstoque.objects.filter(
            loja=loja_destino, pk__in=dest_ids
        ).select_for_update().order_by('pk')
    }
    if len(destino_por_id) != len(dest_ids):
        return False, 'Erro ao bloquear itens na filial destino.'

    for item_origem, item_destino_ref, qtd in preparados:
        item_destino = destino_por_id[item_destino_ref.id]
        item_origem.quantidade_estoque -= qtd
        item_origem.save()
        item_destino.quantidade_estoque += qtd
        item_destino.save()
        LogTransferenciaEstoque.objects.create(
            loja_origem=loja_origem,
            loja_destino=loja_destino,
            item_nome=item_origem.nome,
            quantidade=qtd,
            usuario=user,
        )

    return True, None


@login_required
def transferir_estoque_lote(request):
    loja_origem = check_loja(request)
    if not loja_origem:
        return redirect('admin:index')

    lojas_destino = lojas_destino_transferencia(request.user, loja_origem)
    itens = ItemEstoque.objects.filter(loja=loja_origem).order_by('nome')

    if request.method == 'POST':
        if not lojas_destino.exists():
            messages.error(request, 'Nenhuma filial destino disponível.')
            return redirect('transferir_estoque_lote')
        loja_destino_id = request.POST.get('loja_destino')
        loja_destino = get_object_or_404(Loja, id=loja_destino_id)
        if not loja_destino_e_permitida(request.user, loja_origem, loja_destino):
            messages.error(request, 'Filial destino não permitida para o seu usuário.')
            return redirect('transferir_estoque_lote')

        selecionados = request.POST.getlist('incluir')
        if not selecionados:
            messages.warning(request, 'Nenhum item foi selecionado.')
            return redirect('transferir_estoque_lote')

        linhas = []
        for sid in selecionados:
            try:
                item_id = int(sid)
            except (TypeError, ValueError):
                messages.error(request, 'Seleção de itens inválida.')
                return redirect('transferir_estoque_lote')
            qtd_raw = (request.POST.get(f'qtd_{item_id}') or '').strip().replace(',', '.')
            try:
                qtd = Decimal(qtd_raw)
            except Exception:
                messages.error(request, f'Quantidade inválida para o item ID {item_id}.')
                return redirect('transferir_estoque_lote')
            linhas.append((item_id, qtd))

        if linhas:
            acc = defaultdict(lambda: Decimal('0'))
            for item_id, qtd in linhas:
                acc[item_id] += qtd
            linhas = list(acc.items())

        try:
            with transaction.atomic():
                ok, err = _executar_transferencia_lote(
                    loja_origem, loja_destino, linhas, request.user
                )
        except Exception:
            messages.error(
                request,
                'Não foi possível concluir a transferência em lote. Tente novamente.',
            )
            return redirect('transferir_estoque_lote')

        if not ok:
            messages.error(request, err)
            return redirect('transferir_estoque_lote')

        n = len(linhas)
        registrar_log(
            request, 'TRANSFERIR',
            f'Transferência em lote: {n} item(ns) para {loja_destino.nome}',
            modelo='ItemEstoque', loja=loja_origem,
        )
        messages.success(
            request,
            f'{n} item(ns) transferido(s) com sucesso para {loja_destino.nome}.',
        )
        return redirect('lista_estoque')

    return render(
        request,
        'app_pdv/transferir_estoque_lote.html',
        {'itens': itens, 'lojas': lojas_destino},
    )


# -------------------------- Log de Transferências --------------------------------------

@login_required
def log_transferencias_estoque(request):
    loja = check_loja(request)
    if not loja:
        return redirect('admin:index')

    qs = LogTransferenciaEstoque.objects.select_related(
        'loja_origem', 'loja_destino', 'usuario'
    ).order_by('-data_transferencia')

    if not request.user.is_superuser:
        qs = qs.filter(Q(loja_origem=loja) | Q(loja_destino=loja))

    tipo = (request.GET.get('tipo') or 'TODAS').upper()
    if tipo == 'ENVIADAS':
        qs = qs.filter(loja_origem=loja)
    elif tipo == 'RECEBIDAS':
        qs = qs.filter(loja_destino=loja)

    q = (request.GET.get('q') or '').strip()
    if q:
        qs = qs.filter(item_nome__icontains=q)

    data_ini = (request.GET.get('data_ini') or '').strip()
    data_fim = (request.GET.get('data_fim') or '').strip()
    if data_ini:
        try:
            qs = qs.filter(data_transferencia__date__gte=date.fromisoformat(data_ini))
        except ValueError:
            messages.error(request, 'Data inicial inválida.')
    if data_fim:
        try:
            qs = qs.filter(data_transferencia__date__lte=date.fromisoformat(data_fim))
        except ValueError:
            messages.error(request, 'Data final inválida.')

    logs = qs[:500]

    return render(
        request,
        'app_pdv/log_transferencias_estoque.html',
        {
            'logs': logs,
            'tipo': tipo,
            'q': q,
            'data_ini': data_ini,
            'data_fim': data_fim,
        },
    )


# ---------------------- GESTÃO DE CATEGORIAS  --------------------------


@login_required
def lista_categorias(request):
    loja = check_loja(request)
    if not loja: return redirect('admin:index')
    
    if request.method == 'POST':
        form = CategoriaTransacaoForm(request.POST)
        if form.is_valid():
            categoria = form.save(commit=False)
            categoria.loja = loja
            categoria.save()
            messages.success(request, "Novo tipo adicionado com sucesso!")
            return redirect('lista_categorias')
    else:
        form = CategoriaTransacaoForm()
        
    categorias = CategoriaTransacao.objects.filter(loja=loja).order_by('nome')
    context = {
        'form': form,
        'categorias': categorias
    }
    return render(request, 'app_pdv/lista_categorias.html', context)

@login_required
def deletar_categoria(request, id):
    loja = check_loja(request)
    cat = get_object_or_404(CategoriaTransacao, pk=id, loja=loja)
    nome = cat.nome
    cid = cat.id
    cat.delete()
    registrar_log(
        request, 'EXCLUIR',
        f'Tipo de lançamento "{nome}" excluído',
        modelo='CategoriaTransacao', objeto_id=cid, loja=loja,
    )
    return redirect('lista_categorias')



# ------------------------- LANÇAR DESPESA/RECEITA NO CAIXA ---------------------------



@login_required
def adicionar_transacao(request):
    loja = check_loja(request)
    if not loja: return redirect('admin:index')
    
    if request.method == 'POST':
        # --- A MÁGICA ACONTECE AQUI: Passamos a loja para o form filtrar as categorias ---
        form = TransacaoForm(request.POST, loja=loja)
        if form.is_valid():
            transacao = form.save(commit=False)
            transacao.loja = loja
            
            # --- MÁGICA CONTÁBIL: AMARRAÇÃO DE GAVETA ---
            caixa_aberto = Caixa.objects.filter(loja=loja, status=True).first()
            
            if caixa_aberto and transacao.forma_pagamento == 'DINHEIRO' and transacao.data == date.today():
                transacao.caixa = caixa_aberto
                
            transacao.save()
            messages.success(request, "Lançamento salvo com sucesso!")
            return redirect('fluxo_caixa')
    else:
        # --- E AQUI: Passamos a loja quando a página apenas carrega vazia ---
        form = TransacaoForm(loja=loja)
        
    context = {
        'form': form,
        'titulo': 'Lançar Receita ou Despesa', 
        'botao': 'Salvar Lançamento'
    }
    return render(request, 'app_pdv/form_generico.html', context)



# ------------------------------------ CENTRAL DE RELATÓRIOS ---------------------------
@login_required
def excluir_transacao(request, id):
    if request.method != 'POST':
        return JsonResponse({'erro': 'Método inválido.'}, status=405)
    loja = check_loja(request)
    if not loja:
        return JsonResponse({'erro': 'Sem loja vinculada.'}, status=403)
    trans = get_object_or_404(Transacao, pk=id, loja=loja)
    descricao = f'Excluiu {trans.categoria.tipo if trans.categoria else "—"} #{trans.id}: {trans.descricao or "—"} — R$ {trans.valor}'
    trans_id = trans.id
    trans.delete()
    registrar_log(request, 'EXCLUIR', descricao, modelo='Transacao', objeto_id=trans_id, loja=loja)
    return JsonResponse({'sucesso': True})


@login_required
def central_logs(request):
    """Central de auditoria — disponível no menu (Relatórios)."""
    loja = check_loja(request)
    if not loja and not request.user.is_superuser:
        return redirect('admin:index')

    qs = LogAuditoria.objects.select_related('usuario', 'loja').all()
    if not request.user.is_superuser and loja:
        qs = qs.filter(loja=loja)

    acao = request.GET.get('acao', '')
    if acao:
        qs = qs.filter(acao=acao)
    busca = request.GET.get('q', '').strip()
    if busca:
        qs = qs.filter(Q(descricao__icontains=busca) | Q(usuario__username__icontains=busca))

    data_inicio = request.GET.get('data_inicio')
    data_fim = request.GET.get('data_fim')
    if data_inicio:
        qs = qs.filter(criado_em__date__gte=data_inicio)
    if data_fim:
        qs = qs.filter(criado_em__date__lte=data_fim)

    logs = qs[:500]
    return render(request, 'app_pdv/central_logs.html', {
        'logs': logs,
        'acao': acao,
        'busca': busca,
        'data_inicio': data_inicio or '',
        'data_fim': data_fim or '',
        'acoes': LogAuditoria.ACAO_CHOICES,
    })


@login_required
def relatorios(request):
    # 1. IDENTIFICA AS LOJAS DO USUÁRIO (Visão de Rede)
    if request.user.is_superuser:
        lojas_permitidas = Loja.objects.all()
    else:
        lojas_permitidas = request.user.lojas_gerenciadas.all()
        if not lojas_permitidas.exists():
            loja_unica = check_loja(request)
            if not loja_unica: return redirect('admin:index')
            lojas_permitidas = Loja.objects.filter(id=loja_unica.id)

    # 2. VERIFICA O QUE ELE SELECIONOU NO FILTRO DA TELA
    loja_selecionada_id = request.GET.get('loja_id', 'todas')
    
    if loja_selecionada_id != 'todas':
        lojas_alvo = lojas_permitidas.filter(id=loja_selecionada_id)
    else:
        lojas_alvo = lojas_permitidas

    # 3. CAPTURA AS DATAS E O TIPO DE RELATÓRIO
    data_inicio = request.GET.get('data_inicio', datetime.now().strftime('%Y-%m-%d'))
    data_fim = request.GET.get('data_fim', datetime.now().strftime('%Y-%m-%d'))
    tipo_relatorio = request.GET.get('tipo_relatorio', 'financeiro') 

    context = {
        'data_inicio': data_inicio,
        'data_fim': data_fim,
        'tipo_relatorio': tipo_relatorio,
        
        # Variáveis enviadas para o HTML montar o dropdown de lojas
        'lojas_permitidas': lojas_permitidas,
        'loja_selecionada_id': loja_selecionada_id,
        'mostrar_filtro_lojas': lojas_permitidas.count() > 1,
        'tem_cmv_pagamento': lojas_permitidas.filter(gerencia_pagamento_mercadorias=True).exists(),
    }

    # --- 1. RELATÓRIO FINANCEIRO ---
    if tipo_relatorio == 'financeiro':
        total_vendas = Venda.objects.filter(
            loja__in=lojas_alvo,
            data_venda__date__range=[data_inicio, data_fim], 
            status__in=STATUS_VENDA_FATURADA,
            eh_fiado=False,
            eh_cortesia=False,
        ).aggregate(Sum('total'))['total__sum'] or 0

        receitas_fiado = PagamentoFiado.objects.filter(
            loja__in=lojas_alvo,
            data_pagamento__date__range=[data_inicio, data_fim],
        ).aggregate(Sum('valor'))['valor__sum'] or 0

        transacoes = Transacao.objects.filter(loja__in=lojas_alvo, data__range=[data_inicio, data_fim]).select_related('categoria', 'loja')
        receitas_extras = transacoes.filter(categoria__tipo='RECEITA').aggregate(Sum('valor'))['valor__sum'] or 0
        despesas = transacoes.filter(categoria__tipo='DESPESA').aggregate(Sum('valor'))['valor__sum'] or 0

        custo_mercadorias = calcular_custo_mercadorias_periodo(lojas_alvo, data_inicio, data_fim)
        total_receitas = total_vendas + receitas_fiado + receitas_extras
        saldo_periodo = total_receitas - despesas - custo_mercadorias

        lista_transacoes = list(transacoes)
        for t in lista_transacoes:
            t.nome_forma_display = get_nome_forma_pagamento(t.loja, t.forma_pagamento)

        context['financeiro'] = {
            'vendas': total_vendas,
            'receitas_fiado': receitas_fiado,
            'receitas_extras': receitas_extras,
            'total_receitas': total_receitas,
            'despesas': despesas,
            'custo_mercadorias': custo_mercadorias,
            'saldo_periodo': saldo_periodo,
            'lista_transacoes': lista_transacoes
        }

    # --- 2. RELATÓRIO DE ORIGEM (APP x PDV) ---
    elif tipo_relatorio == 'origem':
        vendas_periodo = Venda.objects.filter(loja__in=lojas_alvo, data_venda__date__range=[data_inicio, data_fim], status__in=STATUS_VENDA_FATURADA)
        
        total_app = vendas_periodo.filter(origem='APP').aggregate(Sum('total'))['total__sum'] or 0
        total_pdv = vendas_periodo.filter(origem='PDV').aggregate(Sum('total'))['total__sum'] or 0

        context['dados_origem'] = {
            'total_app': total_app,
            'qtd_app': vendas_periodo.filter(origem='APP').count(),
            'total_pdv': total_pdv,
            'qtd_pdv': vendas_periodo.filter(origem='PDV').count(),
            'total_geral': total_app + total_pdv,
        }

    # --- 3. RELATÓRIO: FORMA DE PAGAMENTO ---
    elif tipo_relatorio == 'pagamento':
        vendas_periodo = Venda.objects.filter(loja__in=lojas_alvo, data_venda__date__range=[data_inicio, data_fim], status__in=STATUS_VENDA_FATURADA)
        multi_loja = lojas_alvo.count() > 1
        lista_pagamento, total_geral = montar_relatorio_pagamentos(lojas_alvo, vendas_periodo, multi_loja=multi_loja)

        context['dados_pagamento'] = {
            'lista': lista_pagamento,
            'total_geral': total_geral,
        }

    # --- 4. RELATÓRIO DE PRODUTOS ---
    elif tipo_relatorio == 'produtos':
        custo_efetivo = Coalesce(F('custo_unitario'), F('produto__preco_compra'), DECIMAL_ZERO)
        itens_vendidos = ItemVenda.objects.filter(
            venda__loja__in=lojas_alvo,
            venda__data_venda__date__range=[data_inicio, data_fim], venda__status__in=STATUS_VENDA_FATURADA
        ).values(
            'produto__nome_venda',
            'produto__item_estoque__unidade_medida',
        ).annotate(
            qtd_total=Sum('quantidade'),
            valor_total_vendido=Sum(F('quantidade') * F('preco_unitario'), output_field=DecimalField(max_digits=12, decimal_places=2)),
            custo_total=Sum(F('quantidade') * custo_efetivo, output_field=DecimalField(max_digits=12, decimal_places=2)),
        ).order_by('-valor_total_vendido')

        lista_produtos = []
        total_qtd_un = Decimal('0')
        total_qtd_kg = Decimal('0')
        total_custo = Decimal('0')
        total_venda = Decimal('0')
        for item in itens_vendidos:
            custo = item['custo_total'] or Decimal('0')
            venda_tot = item['valor_total_vendido'] or Decimal('0')
            qtd = item['qtd_total'] or Decimal('0')
            unidade = item.get('produto__item_estoque__unidade_medida') or 'UN'
            if unidade == 'UN':
                qtd_display = str(int(qtd))
                total_qtd_un += qtd
            else:
                qtd_display = f"{qtd:.3f}".replace('.', ',')
                total_qtd_kg += qtd
            lista_produtos.append({
                'nome': item['produto__nome_venda'],
                'qtd': qtd,
                'qtd_display': qtd_display,
                'unidade': unidade,
                'custo_total': custo,
                'venda_total': venda_tot,
                'lucro': venda_tot - custo,
            })
            total_custo += custo
            total_venda += venda_tot
        context['produtos'] = lista_produtos
        context['totais_produtos'] = {
            'qtd_un': int(total_qtd_un),
            'qtd_kg': total_qtd_kg,
            'tem_kg': total_qtd_kg > 0,
            'custo_total': total_custo,
            'venda_total': total_venda,
            'lucro': total_venda - total_custo,
        }

    # --- 5. RELATÓRIO DE CLIENTES ---
    elif tipo_relatorio == 'clientes':
        ranking = Venda.objects.filter(
            loja__in=lojas_alvo,
            data_venda__date__range=[data_inicio, data_fim], status__in=STATUS_VENDA_FATURADA, cliente__isnull=False 
        ).values('cliente__nome').annotate(
            total_gasto=Sum('total'), qtd_compras=Count('id')
        ).order_by('-total_gasto')
        context['clientes'] = ranking

    # --- 6. RELATÓRIO DE FECHAMENTOS ---
    elif tipo_relatorio == 'fechamentos':
        context['fechamentos'] = Caixa.objects.filter(loja__in=lojas_alvo, status=False).order_by('-data')

    # --- 7. RELATÓRIO DE ENTREGADORES ---
    elif tipo_relatorio == 'entregadores':
        vendas_base = Venda.objects.filter(loja__in=lojas_alvo, status_entrega='ENTREGUE', data_venda__date__range=[data_inicio, data_fim])
        ids_motoboys = vendas_base.values_list('entregador', flat=True).distinct()
        
        lista_agrupada = []
        total_geral = 0
        for user_id in ids_motoboys:
            if user_id:
                motoboy = User.objects.get(id=user_id)
                vendas_moto = vendas_base.filter(entregador=motoboy)
                total = vendas_moto.aggregate(Sum('taxa_entrega'))['taxa_entrega__sum'] or 0
                lista_agrupada.append({'motoboy': motoboy, 'vendas': vendas_moto, 'total_valor': total, 'quantidade': vendas_moto.count()})
                total_geral += total
        
        context['lista_agrupada'] = lista_agrupada
        context['total_geral_entregas'] = total_geral

    # --- 8. RELATÓRIO DE FIADO (PAGAMENTOS PENDENTES) ---
    elif tipo_relatorio == 'fiado':
        lojas_fiado = lojas_alvo.filter(usa_fiado=True)
        context['tem_fiado'] = lojas_fiado.exists()

        lista_fiado, totais = listar_vendas_fiado_abertas(
            lojas_fiado, data_inicio, data_fim, todas_datas=False,
        )
        context['fiado'] = {
            'lista': lista_fiado,
            'por_cliente': agrupar_fiado_por_cliente(lista_fiado),
            **totais,
        }

    # --- 8b. CENTRAL DE AGENDAMENTO FIADO ---
    elif tipo_relatorio == 'fiado_agendamento':
        lojas_fiado = lojas_alvo.filter(usa_fiado=True)
        context['tem_fiado'] = lojas_fiado.exists()

        lista_vendas, totais_vendas = listar_vendas_fiado_abertas(
            lojas_fiado, data_inicio=None, data_fim=None, todas_datas=True,
        )
        parcelas, totais_parcelas = listar_parcelas_agendadas(
            lojas_fiado, data_inicio, data_fim,
        )
        context['fiado_agendamento'] = {
            'vendas_abertas': lista_vendas,
            'totais_vendas': totais_vendas,
            'parcelas': parcelas,
            'totais_parcelas': totais_parcelas,
        }

    # --- 9. RELATÓRIO DE FIADO QUITADO (SALDO LIQUIDADO) ---
    elif tipo_relatorio == 'fiado_quitado':
        lojas_fiado = lojas_alvo.filter(usa_fiado=True)
        context['tem_fiado'] = lojas_fiado.exists()

        vendas_quitadas = Venda.objects.filter(
            loja__in=lojas_fiado,
            eh_fiado=True,
            status='FINALIZADO',
        ).annotate(
            data_quitacao=Max('pagamentos_fiado__data_pagamento'),
        ).filter(
            data_quitacao__date__range=[data_inicio, data_fim],
        ).select_related('cliente', 'loja').prefetch_related(
            'itens__produto__item_estoque', 'pagamentos_fiado'
        ).order_by('-data_quitacao')

        lista_quitado = []
        total_quitado = Decimal('0')
        total_recebido = Decimal('0')

        for venda in vendas_quitadas:
            itens_txt = []
            for item in venda.itens.all():
                qtd = item.quantidade
                if item.produto.item_estoque.unidade_medida == 'UN':
                    qtd_fmt = f"{int(qtd)}"
                else:
                    qtd_fmt = f"{qtd:.3f}".rstrip('0').rstrip('.')
                itens_txt.append(f"{qtd_fmt}x {item.produto.nome_venda}")

            pagamentos = []
            for pag in venda.pagamentos_fiado.all().order_by('data_pagamento'):
                pagamentos.append({
                    'data': localtime(pag.data_pagamento).strftime('%d/%m/%Y %H:%M'),
                    'valor': pag.valor,
                    'meio': pag.get_meio_liquidacao_display(),
                })

            pago = venda.valor_pago_fiado
            data_quitacao = venda.data_quitacao
            lista_quitado.append({
                'venda': venda,
                'cliente': venda.cliente.nome if venda.cliente else '—',
                'loja': venda.loja.nome,
                'data_venda': localtime(venda.data_venda).strftime('%d/%m/%Y %H:%M'),
                'data_quitacao': localtime(data_quitacao).strftime('%d/%m/%Y %H:%M') if data_quitacao else '—',
                'qtd_total': venda.qtd_itens_vendidos,
                'itens_resumo': ', '.join(itens_txt) if itens_txt else '—',
                'total': venda.total,
                'pago': pago,
                'pagamentos': pagamentos,
                'meio_final': venda.get_nome_meio_liquidacao(),
            })
            total_quitado += Decimal(str(venda.total or 0))
            total_recebido += pago

        context['fiado_quitado'] = {
            'lista': lista_quitado,
            'qtd_vendas': len(lista_quitado),
            'total_quitado': total_quitado,
            'total_recebido': total_recebido,
        }

    # --- 10. CMV / PAGAMENTO DE MERCADORIAS ---
    elif tipo_relatorio == 'cmv':
        lojas_cmv = lojas_alvo.filter(gerencia_pagamento_mercadorias=True)
        context['tem_cmv_pagamento'] = lojas_cmv.exists()
        cmv_parcela_status = (request.GET.get('cmv_parcela_status') or 'todos').strip()
        cmv_busca = (request.GET.get('cmv_busca') or '').strip()
        context['cmv_parcela_status'] = cmv_parcela_status
        context['cmv_busca'] = cmv_busca
        if lojas_cmv.exists():
            cmv_vendido = calcular_custo_mercadorias_periodo(lojas_cmv, data_inicio, data_fim)
            entradas_periodo = EntradaEstoque.objects.filter(
                loja__in=lojas_cmv,
                data_entrada__date__range=[data_inicio, data_fim],
            ).select_related('item', 'fornecedor', 'loja')
            total_compras = entradas_periodo.aggregate(Sum('valor_total'))['valor_total__sum'] or Decimal('0')
            pagamentos_periodo = PagamentoMercadoria.objects.filter(
                loja__in=lojas_cmv,
                data_pagamento__date__range=[data_inicio, data_fim],
            ).select_related('entrada__item', 'entrada__fornecedor')
            pago_periodo = pagamentos_periodo.aggregate(Sum('valor'))['valor__sum'] or Decimal('0')
            entradas_abertas = listar_entradas_abertas_cmv(lojas_cmv)
            total_a_pagar = sum((e['saldo_a_pagar'] for e in entradas_abertas), Decimal('0'))
            status_filtro = None if cmv_parcela_status in ('', 'todos') else cmv_parcela_status
            parcelas, totais_parcelas = listar_parcelas_mercadoria(
                lojas_cmv, data_inicio, data_fim,
                status=status_filtro,
                busca=cmv_busca,
            )
            context['cmv'] = {
                'cmv_vendido': cmv_vendido,
                'total_compras': total_compras,
                'pago_periodo': pago_periodo,
                'total_a_pagar': total_a_pagar,
                'entradas_abertas': entradas_abertas,
                'entradas_periodo': entradas_periodo.order_by('-data_entrada'),
                'pagamentos_periodo': pagamentos_periodo.order_by('-data_pagamento'),
                'parcelas': parcelas,
                'totais_parcelas': totais_parcelas,
            }

    return render(request, 'app_pdv/relatorios.html', context)


def _redirect_relatorio_fiado(request, tipo='fiado'):
    data_inicio = request.POST.get('data_inicio', request.GET.get('data_inicio', ''))
    data_fim = request.POST.get('data_fim', request.GET.get('data_fim', ''))
    loja_id = request.POST.get('loja_id', request.GET.get('loja_id', 'todas'))
    url = (
        f"{reverse('relatorios')}?tipo_relatorio={tipo}"
        f"&data_inicio={data_inicio}&data_fim={data_fim}&loja_id={loja_id}"
    )
    if tipo == 'cmv':
        cmv_status = request.POST.get('cmv_parcela_status', request.GET.get('cmv_parcela_status', 'todos'))
        cmv_busca = request.POST.get('cmv_busca', request.GET.get('cmv_busca', ''))
        url += f"&cmv_parcela_status={cmv_status}&cmv_busca={cmv_busca}"
    return redirect(url)


@login_required
@transaction.atomic
def registrar_pagamento_mercadoria(request, entrada_id):
    loja = check_loja(request)
    if not loja:
        return redirect('admin:index')
    if not getattr(loja, 'gerencia_pagamento_mercadorias', False):
        messages.error(request, 'Esta loja não gerencia pagamento de mercadorias.')
        return _redirect_relatorio_fiado(request, 'cmv')

    entrada = get_object_or_404(EntradaEstoque, pk=entrada_id, loja=loja)

    if request.method == 'POST':
        valor_str = (request.POST.get('valor') or '').replace(',', '.')
        meio = request.POST.get('meio_liquidacao', 'PIX')
        observacao = request.POST.get('observacao', '')
        try:
            valor = Decimal(valor_str)
            caixa_aberto = Caixa.objects.filter(loja=loja, status=True).first()
            entrada.registrar_pagamento(valor, meio, observacao, request.user, caixa=caixa_aberto)
            messages.success(
                request,
                f'Pagamento de R$ {valor:.2f} registrado. Saldo restante: R$ {entrada.saldo_a_pagar:.2f}',
            )
        except Exception as e:
            messages.error(request, str(e))

    return _redirect_relatorio_fiado(request, 'cmv')


@login_required
@transaction.atomic
def criar_parcelas_mercadoria_agendadas(request):
    loja = check_loja(request)
    if not loja or request.method != 'POST':
        return redirect('relatorios')
    if not getattr(loja, 'gerencia_pagamento_mercadorias', False):
        messages.error(request, 'Esta loja não gerencia pagamento de mercadorias.')
        return _redirect_relatorio_fiado(request, 'cmv')

    entrada_id = request.POST.get('entrada_id')
    entrada = get_object_or_404(
        EntradaEstoque, pk=entrada_id, loja=loja,
        status_pagamento__in=['PENDENTE', 'PARCIAL'],
    )

    valores = request.POST.getlist('parcela_valor')
    vencimentos = request.POST.getlist('parcela_vencimento')
    criadas = 0

    try:
        saldo_disp = saldo_agendavel_entrada(entrada)
        for val_str, ven_str in zip(valores, vencimentos):
            if not val_str or not ven_str:
                continue
            valor = Decimal(str(val_str).replace(',', '.'))
            if valor <= 0:
                continue
            if valor > saldo_disp:
                raise ValueError(
                    f'Parcela R$ {valor:.2f} excede saldo agendável R$ {saldo_disp:.2f}.'
                )
            data_venc = datetime.strptime(ven_str, '%Y-%m-%d').date()
            ParcelaMercadoriaAgendada.objects.create(
                loja=loja,
                entrada=entrada,
                valor=valor,
                data_vencimento=data_venc,
                criado_por=request.user,
            )
            saldo_disp -= valor
            criadas += 1

        if criadas:
            messages.success(
                request,
                f'{criadas} parcela(s) agendada(s) para entrada #{entrada.id} ({entrada.item.nome}).',
            )
        else:
            messages.warning(request, 'Informe ao menos uma parcela com valor e vencimento.')
    except Exception as e:
        messages.error(request, str(e))

    return _redirect_relatorio_fiado(request, 'cmv')


@login_required
@transaction.atomic
def cancelar_parcela_mercadoria(request, parcela_id):
    loja = check_loja(request)
    if not loja:
        return redirect('relatorios')
    if not getattr(loja, 'gerencia_pagamento_mercadorias', False):
        messages.error(request, 'Esta loja não gerencia pagamento de mercadorias.')
        return _redirect_relatorio_fiado(request, 'cmv')

    parcela = get_object_or_404(ParcelaMercadoriaAgendada, pk=parcela_id, loja=loja)
    if parcela.status != 'AGENDADO':
        messages.error(request, 'Só é possível cancelar parcelas agendadas.')
    else:
        parcela.status = 'CANCELADO'
        parcela.save(update_fields=['status'])
        messages.success(request, f'Parcela #{parcela.id} cancelada.')

    return _redirect_relatorio_fiado(request, 'cmv')


@login_required
@transaction.atomic
def editar_parcela_mercadoria(request, parcela_id):
    loja = check_loja(request)
    if not loja or request.method != 'POST':
        return redirect('relatorios')
    if not getattr(loja, 'gerencia_pagamento_mercadorias', False):
        messages.error(request, 'Esta loja não gerencia pagamento de mercadorias.')
        return _redirect_relatorio_fiado(request, 'cmv')

    parcela = get_object_or_404(
        ParcelaMercadoriaAgendada.objects.select_related('entrada'),
        pk=parcela_id, loja=loja,
    )
    if parcela.status != 'AGENDADO':
        messages.error(request, 'Só é possível editar parcelas agendadas.')
        return _redirect_relatorio_fiado(request, 'cmv')

    valor_str = (request.POST.get('valor') or '').replace(',', '.')
    venc_str = request.POST.get('data_vencimento') or ''
    try:
        valor = Decimal(valor_str).quantize(Decimal('0.01'))
        if valor <= 0:
            raise ValueError('Valor da parcela deve ser maior que zero.')
        data_venc = datetime.strptime(venc_str, '%Y-%m-%d').date()
        # Saldo agendável libera o valor atual desta parcela antes de revalidar.
        saldo_disp = saldo_agendavel_entrada(parcela.entrada) + Decimal(str(parcela.valor))
        if valor > saldo_disp:
            raise ValueError(
                f'Parcela R$ {valor:.2f} excede saldo agendável R$ {saldo_disp:.2f}.'
            )
        parcela.valor = valor
        parcela.data_vencimento = data_venc
        parcela.save(update_fields=['valor', 'data_vencimento'])
        messages.success(
            request,
            f'Parcela #{parcela.id} atualizada: R$ {valor:.2f} em {data_venc.strftime("%d/%m/%Y")}.',
        )
    except Exception as e:
        messages.error(request, str(e))

    return _redirect_relatorio_fiado(request, 'cmv')


@login_required
@transaction.atomic
def pagar_parcela_mercadoria(request, parcela_id):
    loja = check_loja(request)
    if not loja or request.method != 'POST':
        return redirect('relatorios')
    if not getattr(loja, 'gerencia_pagamento_mercadorias', False):
        messages.error(request, 'Esta loja não gerencia pagamento de mercadorias.')
        return _redirect_relatorio_fiado(request, 'cmv')

    parcela = get_object_or_404(
        ParcelaMercadoriaAgendada.objects.select_related('entrada'),
        pk=parcela_id, loja=loja, status='AGENDADO',
    )
    entrada = parcela.entrada
    meio = request.POST.get('meio_liquidacao', 'PIX')
    observacao = request.POST.get('observacao', '') or f'Parcela agendada #{parcela.id}'

    try:
        if parcela.valor > entrada.saldo_a_pagar:
            raise ValueError('Valor da parcela maior que o saldo a pagar da entrada.')
        caixa_aberto = Caixa.objects.filter(loja=loja, status=True).first()
        pag = entrada.registrar_pagamento(
            parcela.valor, meio, observacao, request.user, caixa=caixa_aberto,
        )
        parcela.status = 'PAGO'
        parcela.pagamento = pag
        parcela.save(update_fields=['status', 'pagamento'])
        messages.success(
            request,
            f'Parcela #{parcela.id} paga. Saldo restante: R$ {entrada.saldo_a_pagar:.2f}',
        )
    except Exception as e:
        messages.error(request, str(e))

    return _redirect_relatorio_fiado(request, 'cmv')


@login_required
@transaction.atomic
def registrar_pagamento_fiado(request, venda_id):
    loja = check_loja(request)
    if not loja:
        return redirect('admin:index')

    venda = get_object_or_404(Venda, pk=venda_id, loja=loja, eh_fiado=True, status='FIADO')

    if request.method == 'POST':
        valor_str = (request.POST.get('valor') or '').replace(',', '.')
        meio = request.POST.get('meio_liquidacao', 'DINHEIRO')
        observacao = request.POST.get('observacao', '')

        try:
            valor = Decimal(valor_str)
            caixa_aberto = Caixa.objects.filter(loja=loja, status=True).first()
            venda.registrar_pagamento_fiado(valor, meio, observacao, request.user, caixa=caixa_aberto)
            messages.success(request, f'Pagamento de R$ {valor:.2f} registrado. Saldo restante: R$ {venda.saldo_devedor:.2f}')
        except Exception as e:
            messages.error(request, str(e))

    tipo = request.POST.get('tipo_relatorio', request.GET.get('tipo_relatorio', 'fiado'))
    return _redirect_relatorio_fiado(request, tipo)


@login_required
@transaction.atomic
def registrar_pagamento_fiado_unificado(request):
    loja = check_loja(request)
    if not loja or request.method != 'POST':
        return redirect('relatorios')

    venda_ids = request.POST.getlist('venda_ids')
    if not venda_ids:
        messages.error(request, 'Selecione ao menos uma venda para receber.')
        return _redirect_relatorio_fiado(request, request.POST.get('tipo_relatorio', 'fiado'))

    vendas = list(
        Venda.objects.filter(
            pk__in=venda_ids, loja=loja, eh_fiado=True, status='FIADO',
        ).select_related('cliente').order_by('data_venda', 'id')
    )
    if not vendas:
        messages.error(request, 'Nenhuma venda fiado válida selecionada.')
        return _redirect_relatorio_fiado(request, request.POST.get('tipo_relatorio', 'fiado'))

    cliente_ids = {v.cliente_id for v in vendas if v.cliente_id}
    if len(cliente_ids) > 1:
        messages.error(request, 'Só é possível unificar parcelas do mesmo cliente.')
        return _redirect_relatorio_fiado(request, request.POST.get('tipo_relatorio', 'fiado'))

    valor_str = (request.POST.get('valor') or '').replace(',', '.')
    meio = request.POST.get('meio_liquidacao', 'DINHEIRO')
    observacao = request.POST.get('observacao', '')
    tipo = request.POST.get('tipo_relatorio', 'fiado')

    try:
        valor = Decimal(valor_str)
        caixa_aberto = Caixa.objects.filter(loja=loja, status=True).first()
        alocacoes = distribuir_pagamento_fiado(vendas, valor)
        for venda, parte in alocacoes:
            venda.registrar_pagamento_fiado(parte, meio, observacao, request.user, caixa=caixa_aberto)
        messages.success(
            request,
            f'Pagamento unificado de R$ {valor:.2f} registrado em {len(alocacoes)} venda(s).',
        )
    except Exception as e:
        messages.error(request, str(e))

    return _redirect_relatorio_fiado(request, tipo)


@login_required
@transaction.atomic
def criar_parcelas_fiado_agendadas(request):
    loja = check_loja(request)
    if not loja or request.method != 'POST':
        return redirect('relatorios')

    venda_id = request.POST.get('venda_id')
    venda = get_object_or_404(Venda, pk=venda_id, loja=loja, eh_fiado=True, status='FIADO')

    if not venda.cliente_id:
        messages.error(request, 'Venda sem cliente vinculado.')
        return _redirect_relatorio_fiado(request, 'fiado_agendamento')

    valores = request.POST.getlist('parcela_valor')
    vencimentos = request.POST.getlist('parcela_vencimento')
    criadas = 0

    try:
        saldo_disp = saldo_agendavel_venda(venda)
        for val_str, ven_str in zip(valores, vencimentos):
            if not val_str or not ven_str:
                continue
            valor = Decimal(str(val_str).replace(',', '.'))
            if valor <= 0:
                continue
            if valor > saldo_disp:
                raise ValueError(
                    f'Parcela R$ {valor:.2f} excede saldo agendável R$ {saldo_disp:.2f}.'
                )
            data_venc = datetime.strptime(ven_str, '%Y-%m-%d').date()
            ParcelaFiadoAgendada.objects.create(
                loja=loja,
                venda=venda,
                cliente=venda.cliente,
                valor=valor,
                data_vencimento=data_venc,
                criado_por=request.user,
            )
            saldo_disp -= valor
            criadas += 1

        if criadas:
            messages.success(request, f'{criadas} parcela(s) agendada(s) para venda #{venda.id}.')
        else:
            messages.warning(request, 'Informe ao menos uma parcela com valor e vencimento.')
    except Exception as e:
        messages.error(request, str(e))

    return _redirect_relatorio_fiado(request, 'fiado_agendamento')


@login_required
@transaction.atomic
def cancelar_parcela_fiado(request, parcela_id):
    loja = check_loja(request)
    if not loja:
        return redirect('relatorios')

    parcela = get_object_or_404(ParcelaFiadoAgendada, pk=parcela_id, loja=loja)
    if parcela.status != 'AGENDADO':
        messages.error(request, 'Só é possível cancelar parcelas agendadas.')
    else:
        parcela.status = 'CANCELADO'
        parcela.save(update_fields=['status'])
        messages.success(request, f'Parcela #{parcela.id} cancelada.')

    return _redirect_relatorio_fiado(request, 'fiado_agendamento')


@login_required
@transaction.atomic
def receber_parcela_fiado(request, parcela_id):
    loja = check_loja(request)
    if not loja or request.method != 'POST':
        return redirect('relatorios')

    parcela = get_object_or_404(
        ParcelaFiadoAgendada.objects.select_related('venda'),
        pk=parcela_id, loja=loja, status='AGENDADO',
    )
    venda = parcela.venda
    meio = request.POST.get('meio_liquidacao', 'DINHEIRO')
    observacao = request.POST.get('observacao', '') or f'Parcela agendada #{parcela.id}'

    try:
        if parcela.valor > venda.saldo_devedor:
            raise ValueError('Valor da parcela maior que o saldo devedor da venda.')
        caixa_aberto = Caixa.objects.filter(loja=loja, status=True).first()
        pag = venda.registrar_pagamento_fiado(
            parcela.valor, meio, observacao, request.user, caixa=caixa_aberto,
        )
        parcela.status = 'PAGO'
        parcela.pagamento = pag
        parcela.save(update_fields=['status', 'pagamento'])
        messages.success(request, f'Parcela #{parcela.id} recebida. Saldo restante: R$ {venda.saldo_devedor:.2f}')
    except Exception as e:
        messages.error(request, str(e))

    tipo = request.POST.get('tipo_relatorio', 'fiado_agendamento')
    return _redirect_relatorio_fiado(request, tipo)


@login_required
def api_criar_cliente_pdv(request):
    loja = check_loja(request)
    if not loja:
        return JsonResponse({'erro': 'Loja não encontrada.'}, status=400)

    if request.method != 'POST':
        return JsonResponse({'erro': 'Método inválido.'}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'erro': 'JSON inválido.'}, status=400)

    nome = (data.get('nome') or '').strip()
    if not nome:
        return JsonResponse({'erro': 'Nome do cliente é obrigatório.'}, status=400)

    cliente = Cliente.objects.create(
        loja=loja,
        nome=nome,
        whatsapp=(data.get('whatsapp') or '').strip() or None,
        telefone=(data.get('whatsapp') or '').strip() or None,
        endereco=(data.get('endereco') or '').strip() or None,
        bairro=(data.get('bairro') or '').strip() or None,
    )
    return JsonResponse({
        'id': cliente.id,
        'nome': cliente.nome,
        'whatsapp': cliente.whatsapp or '',
        'endereco': cliente.endereco or '',
        'bairro': cliente.bairro or '',
    })


@login_required
def ver_recibo_fechamento(request, id):
    loja = check_loja(request)
    caixa = get_object_or_404(Caixa, pk=id, loja=loja)

    vendas = vendas_turno_caixa(caixa)
    total_vendas = vendas.aggregate(Sum('total'))['total__sum'] or 0
    inicio_turno = caixa.data_hora_abertura or datetime.combine(caixa.data, datetime.min.time())
    fim_turno = caixa.data_hora_fechamento or timezone.now()
    pagamentos_fiado = PagamentoFiado.objects.filter(
        loja=loja,
        data_pagamento__gte=inicio_turno,
        data_pagamento__lte=fim_turno,
    )
    pagamentos_mercadoria = PagamentoMercadoria.objects.filter(
        loja=loja,
        data_pagamento__gte=inicio_turno,
        data_pagamento__lte=fim_turno,
    ).select_related('entrada__item', 'entrada__fornecedor')
    total_fiado = pagamentos_fiado.aggregate(Sum('valor'))['valor__sum'] or 0
    total_pag_mercadoria = pagamentos_mercadoria.aggregate(Sum('valor'))['valor__sum'] or 0
    dinheiro_vendas = calcular_entradas_gaveta(vendas, pagamentos_fiado, pagamentos_mercadoria)

    transacoes = Transacao.objects.filter(caixa=caixa)
    if not transacoes.exists():
        transacoes = Transacao.objects.filter(loja=loja, data=caixa.data)
    entradas = transacoes.filter(categoria__tipo='RECEITA').aggregate(Sum('valor'))['valor__sum'] or 0
    saidas = transacoes.filter(categoria__tipo='DESPESA').aggregate(Sum('valor'))['valor__sum'] or 0

    resumo_pgto = montar_resumo_liquidacao_loja(vendas, pagamentos_fiado, pagamentos_mercadoria)
    produtos_vendidos, produtos_por_grupo = agregar_produtos_vendas(vendas, loja)
    total_produtos_qtd = sum(p['qtd'] for p in produtos_vendidos)
    total_produtos_valor = sum(p['total'] for p in produtos_vendidos)

    data_fechamento = caixa.data_hora_fechamento or datetime.combine(caixa.data, datetime.min.time())

    context = {
        'caixa': caixa,
        'operador': request.user,
        'data_fechamento': data_fechamento,
        'total_vendas': total_vendas,
        'total_fiado': total_fiado,
        'total_pag_mercadoria': total_pag_mercadoria,
        'pagamentos_mercadoria': pagamentos_mercadoria,
        'dinheiro_vendas': dinheiro_vendas,
        'entradas': entradas,
        'saidas': saidas,
        'resumo_pgto': resumo_pgto,
        'produtos_vendidos': produtos_vendidos,
        'produtos_por_grupo': produtos_por_grupo,
        'divide_produtos_por_grupos': loja.divide_produtos_por_grupos,
        'total_produtos_qtd': total_produtos_qtd,
        'total_produtos_valor': total_produtos_valor,
    }
    return render(request, 'app_pdv/recibo_fechamento.html', context)


@login_required 
def relatorio_entregadores(request):
    loja = check_loja(request)
    if not loja: return redirect('admin:index')

    periodo = request.GET.get('periodo', 'hoje')
    motoboy_id = request.GET.get('motoboy') 
    
    hoje = date.today()
    filtro_data = {}
    
    if periodo == 'hoje':
        filtro_data['data_venda__date'] = hoje
    elif periodo == 'mes':
        filtro_data['data_venda__month'] = hoje.month
        filtro_data['data_venda__year'] = hoje.year

    vendas = Venda.objects.filter(loja=loja, status_entrega='ENTREGUE', **filtro_data)

    if motoboy_id:
        vendas = vendas.filter(entregador_id=motoboy_id)

    total_geral = vendas.aggregate(Sum('total'))['total__sum'] or 0
    quantidade = vendas.count()
    
    
    lista_motoboys = Motoboy.objects.filter(loja=loja)

    return render(request, 'relatorio_entregas.html', {
        'vendas': vendas,
        'total_geral': total_geral,
        'quantidade': quantidade,
        'lista_motoboys': lista_motoboys,
        'periodo_selecionado': periodo,
        'motoboy_selecionado': int(motoboy_id) if motoboy_id else None
    })

# --------------------------------- IMPORTÇÃO ---------------------------------

@login_required
def menu_importacao(request):
    form = ImportacaoForm()
    return render(request, 'app_pdv/importacao.html', {'form': form})

@login_required
def importar_clientes(request):
    loja = check_loja(request)
    if not loja: return redirect('admin:index')

    if request.method == 'POST':
        form = ImportacaoForm(request.POST, request.FILES)
        if form.is_valid():
            arquivo = request.FILES['arquivo_excel']
            try:
                df = pd.read_excel(arquivo, engine='openpyxl')
                df.columns = (df.columns.str.strip().str.lower()
                              .str.replace('ç', 'c').str.replace('ã', 'a')
                              .str.replace('é', 'e').str.replace('ó', 'o'))

                contador_criados = 0
                contador_atualizados = 0

                for index, row in df.iterrows():
                    nome_cliente = row.get('nome')
                    if not nome_cliente or pd.isna(nome_cliente):
                        continue

                    endereco = str(row.get('endereco', ''))
                    if endereco == 'nan':
                        endereco = ''

                    whatsapp = str(row.get('whatsapp', ''))
                    if whatsapp == 'nan':
                        whatsapp = ''

                    bairro = str(row.get('bairro', ''))
                    if bairro == 'nan':
                        bairro = ''

                    obj, created = Cliente.objects.update_or_create(
                        nome=nome_cliente,
                        loja=loja,
                        defaults={
                            'endereco': endereco,
                            'whatsapp': whatsapp,
                            'bairro': bairro or None,
                        }
                    )

                    if created:
                        contador_criados += 1
                    else:
                        contador_atualizados += 1

                messages.success(
                    request,
                    f"Sucesso! {contador_criados} clientes criados e {contador_atualizados} atualizados."
                )

            except Exception as e:
                messages.error(request, f"Erro ao processar arquivo: {str(e)}")

    return redirect('menu_importacao')




@login_required
@transaction.atomic
def importar_produtos(request):
    loja = check_loja(request)
    if not loja: return redirect('admin:index')

    if request.method == 'POST':
        form = ImportacaoForm(request.POST, request.FILES)
        if form.is_valid():
            arquivo = request.FILES['arquivo_excel']
            try:
                df = pd.read_excel(arquivo, engine='openpyxl')
                
                # Tratamento avançado de nomes de colunas
                df.columns = (df.columns.str.lower().str.strip()
                              .str.replace(' ', '_')
                              .str.replace('ç', 'c').str.replace('ã', 'a')
                              .str.replace('á', 'a').str.replace('à', 'a')
                              .str.replace('é', 'e').str.replace('ê', 'e')
                              .str.replace('í', 'i').str.replace('ó', 'o')
                              .str.replace('ô', 'o').str.replace('ú', 'u'))

                contador = 0
                
                def limpar_preco(valor):
                    if pd.isna(valor): return 0.0
                    if isinstance(valor, (int, float)): return float(valor)
                    valor = str(valor).replace('R$', '').replace(' ', '').replace('.', '').replace(',', '.')
                    try: return float(valor)
                    except: return 0.0

                for index, row in df.iterrows():
                    item_pai_nome = row.get('item_pai')
                    nome_venda = row.get('nome_venda')
                    
                    if pd.isna(item_pai_nome) or pd.isna(nome_venda): continue 
                    
                    item_pai_nome = str(item_pai_nome).strip()
                    nome_venda = str(nome_venda).strip()
                    
                    unidade = str(row.get('unidade', 'UN')).strip().upper()
                    if unidade not in ['UN', 'KG', 'L']: unidade = 'UN'

                    estoque_total = limpar_preco(row.get('estoque_total', 0))
                    qtd_baixa = limpar_preco(row.get('qtd_baixa', 1))
                    if qtd_baixa <= 0: qtd_baixa = 1 
                    
                    custo = limpar_preco(row.get('preco_custo', 0))
                    venda = limpar_preco(row.get('preco_venda', 0))

                    codigo_barras = str(row.get('codigo_barras', '') or '').strip()
                    if codigo_barras.lower() == 'nan':
                        codigo_barras = ''

                    grupo_nome = row.get('grupo')
                    grupo_obj = None
                    if pd.notna(grupo_nome) and str(grupo_nome).strip() and str(grupo_nome).strip().lower() != 'nan':
                        grupo_obj, _ = GrupoProduto.objects.get_or_create(
                            loja=loja,
                            nome=str(grupo_nome).strip(),
                        )

                    # --- NOVA LEITURA: VALIDADE E OBSERVAÇÃO ---
                    validade_raw = row.get('data_validade')
                    observacao_raw = row.get('observacao')
                    
                    data_val = None
                    if pd.notna(validade_raw) and str(validade_raw).strip() != '':
                        try:
                            # Converte a data do Excel para o formato que o banco de dados entende
                            data_val = pd.to_datetime(validade_raw).date()
                        except:
                            pass # Se a pessoa digitar lixo na data, ignora para não travar a importação
                            
                    obs_val = str(observacao_raw).strip() if pd.notna(observacao_raw) else ""
                    if obs_val == 'nan': obs_val = ""
                    # ---------------------------------------------
                    
                    # 1. Cria ou Encontra o Cofre (Item Pai) ATUALIZADO
                    item, created_item = ItemEstoque.objects.get_or_create(
                        nome=item_pai_nome, 
                        loja=loja,
                        defaults={
                            'unidade_medida': unidade,
                            'data_validade': data_val,  # Salva a data nova
                            'observacao': obs_val       # Salva a observação nova
                        }
                    )
                    
                    # Se o item já existia e a planilha tem data/obs nova, ele atualiza!
                    if not created_item:
                        mudou = False
                        if data_val: 
                            item.data_validade = data_val
                            mudou = True
                        if obs_val: 
                            item.observacao = obs_val
                            mudou = True
                        if mudou:
                            item.save()
                    
                    # Soma o estoque apenas se houver na planilha (evita somar infinito ao atualizar)
                    if estoque_total > 0:
                        # --- CORREÇÃO AQUI: Forçando ambos a serem Decimal antes da soma ---
                        estoque_atual = Decimal(str(item.quantidade_estoque))
                        estoque_novo = Decimal(str(estoque_total))
                        item.quantidade_estoque = estoque_atual + estoque_novo
                        item.save()

                    if codigo_barras:
                        conflito = Produto.objects.filter(
                            loja=loja, codigo_barras=codigo_barras
                        ).exclude(nome_venda=nome_venda, item_estoque=item).exists()
                        if conflito:
                            messages.warning(
                                request,
                                f"Código de barras '{codigo_barras}' já usado em outro produto "
                                f"(linha {index + 2}). Produto '{nome_venda}' importado sem o código."
                            )
                            codigo_barras = ''

                    defaults_produto = {
                        'quantidade_baixa': Decimal(str(qtd_baixa)),
                        'preco_compra': Decimal(str(custo)),
                        'preco_venda': Decimal(str(venda)),
                        'ativo': True,
                    }
                    if codigo_barras:
                        defaults_produto['codigo_barras'] = codigo_barras
                    if grupo_obj is not None:
                        defaults_produto['grupo'] = grupo_obj

                    # 2. Cria ou Atualiza o Produto da Prateleira
                    produto, created_prod = Produto.objects.update_or_create(
                        loja=loja,
                        nome_venda=nome_venda,
                        item_estoque=item,
                        defaults=defaults_produto,
                    )
                    if created_prod:
                        contador += 1
        
                if contador > 0:
                    messages.success(request, f"{contador} novos produtos criados com sucesso! Os estoques e preços foram sincronizados.")
                else:
                    messages.info(request, "Nenhum produto novo criado, mas os preços e estoques dos existentes foram atualizados.")

            except Exception as e:
                import traceback
                traceback.print_exc()
                messages.error(request, f"Erro ao processar arquivo. Verifique se usou a planilha modelo. Detalhe: {str(e)}")

    return redirect('menu_importacao')

@login_required
def baixar_modelo_excel(request, tipo):
    output = io.BytesIO()
    
    if tipo == 'clientes':
        df = pd.DataFrame({
            'Nome': ['João da Silva (Exemplo)'],
            'WhatsApp': ['21988887777'],
            'Endereco': ['Rua das Flores, 123 - Centro, RJ'],
            'Bairro': ['Centro'],
        })
        nome_arquivo = 'Modelo_Importacao_Clientes.xlsx'
        
    elif tipo == 'produtos':
        df = pd.DataFrame({
            'Item Pai': ['Special Dog', 'Special Dog', 'Coca Cola Lata'],
            'Unidade': ['KG', 'KG', 'UN'],
            'Estoque Total': [500, 0, 120],
            'Data Validade': ['2026-12-31', '', '2025-06-01'],
            'Observacao': ['Lote A1', '', 'Lote B2'],
            'Nome Venda': ['Special Dog Granel 1KG', 'Special Dog Saco 10KG', 'Coca Cola Lata Gelada'],
            'Codigo Barras': ['7891000100103', '', '7894900011517'],
            'Grupo': ['Ração', 'Ração', 'Bebidas'],
            'Qtd Baixa': [1, 10, 1],
            'Preco Custo': [5.00, 50.00, 2.50],
            'Preco Venda': [10.00, 95.00, 5.00],
        })
        nome_arquivo = 'Modelo_Importacao_Produtos.xlsx'
    else:
        return HttpResponse("Tipo inválido", status=400)

    # Gera o Excel usando o pandas e manda para o download
    writer = pd.ExcelWriter(output, engine='openpyxl')
    df.to_excel(writer, index=False, sheet_name='Planilha_Modelo')
    writer.close()
    output.seek(0)
    
    response = HttpResponse(output, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="{nome_arquivo}"'
    return response 


#--------------------------------------Vendedor------------------------------------------

@login_required
def cadastrar_vendedor(request):
    loja_atual = check_loja(request)
    if not loja_atual: return redirect('admin:index')

    # 1. SEGURANÇA: Define quais lojas o usuário atual pode ver na caixinha
    if request.user.is_superuser:
        lojas_permitidas = Loja.objects.all()
    else:
        lojas_permitidas = request.user.lojas_gerenciadas.all()
        if not lojas_permitidas.exists():
            lojas_permitidas = Loja.objects.filter(id=loja_atual.id)

    if request.method == 'POST':
        # 2. Passa as lojas permitidas para o Form
        form = CadastroVendedorForm(request.POST, lojas_permitidas=lojas_permitidas)
        if form.is_valid():
            user = form.save(commit=False)
            user.is_staff = False 
            user.save() # <-- Aqui o Signal age e cria o perfil vazio!
            
            # 3. A CARTADA FINAL: Pega a loja escolhida e atualiza o perfil
            loja_selecionada = form.cleaned_data.get('loja')
            if hasattr(user, 'perfil'):
                user.perfil.loja = loja_selecionada
                user.perfil.save()

            registrar_log(
                request, 'SENHA',
                f'Usuário {user.username} cadastrado na {loja_selecionada.nome}',
                modelo='User', objeto_id=user.id, loja=loja_selecionada,
            )
            messages.success(request, f"Usuário {user.first_name} cadastrado com sucesso na {loja_selecionada.nome}!")
            return redirect('lista_vendedores') 
        else:
            messages.error(request, "Erro ao cadastrar. Verifique os dados.")
    else:
        # Quando a página carrega pela primeira vez
        form = CadastroVendedorForm(lojas_permitidas=lojas_permitidas)

    return render(request, 'app_pdv/cadastrar_vendedor.html', {'form': form})

@login_required
def lista_vendedores(request):
    loja = check_loja(request)
    
    vendedores = User.objects.filter(perfil__loja=loja, is_superuser=False).order_by('first_name')
    return render(request, 'app_pdv/lista_vendedores.html', {'vendedores': vendedores})

@login_required
def gerenciar_permissoes(request, id):
    loja = check_loja(request)
    # Busca o usuário selecionado
    vendedor = get_object_or_404(User, id=id, perfil__loja=loja)
    
    if request.method == 'POST':
        # Atualiza o perfil desse vendedor
        form = PermissoesUsuarioForm(request.POST, instance=vendedor.perfil)
        if form.is_valid():
            form.save()
            registrar_log(
                request, 'SENHA',
                f'Permissões de {vendedor.username} atualizadas',
                modelo='User', objeto_id=vendedor.id, loja=loja,
            )
            messages.success(request, f"Permissões de {vendedor.first_name} atualizadas com sucesso!")
            return redirect('lista_vendedores')
    else:
        form = PermissoesUsuarioForm(instance=vendedor.perfil)
        
    return render(request, 'app_pdv/permissoes.html', {'form': form, 'vendedor': vendedor})

@login_required
def editar_vendedor(request, id):
    loja = check_loja(request)
    if not loja: return redirect('admin:index')
    
    # Busca o usuário garantindo que ele pertence à loja atual e não é o dono do sistema
    vendedor = get_object_or_404(User, id=id, perfil__loja=loja, is_superuser=False)

    if request.method == 'POST':
        form = EditarVendedorForm(request.POST, instance=vendedor)
        if form.is_valid():
            user = form.save(commit=False)
            
            # --- MÁGICA DA SENHA ---
            nova_senha = form.cleaned_data.get('senha')
            if nova_senha:
                user.set_password(nova_senha) # Criptografa e salva a nova senha
                
            user.save()
            detalhe = ' (senha alterada)' if nova_senha else ''
            registrar_log(
                request, 'SENHA',
                f'Dados do usuário {user.username} atualizados{detalhe}',
                modelo='User', objeto_id=user.id, loja=loja,
            )
            messages.success(request, f"Dados do usuário {user.first_name} atualizados com sucesso!")
            return redirect('lista_vendedores')
    else:
        form = EditarVendedorForm(instance=vendedor)

    # Reutilizamos o seu template genérico que já é bonito e funcional!
    return render(request, 'app_pdv/form_generico.html', {'form': form, 'titulo': 'Editar Usuário (Operador)'})

# ----------------------------- Entregas(MOTOBOY) ----------------------------------------------

@login_required
def lista_entregas(request):
    loja = check_loja(request)
    motoboys = Motoboy.objects.filter(loja=loja).order_by('-ativo', 'nome')
    motos = Moto.objects.filter(loja=loja).order_by('-ativa', 'modelo')
    return render(request, 'app_pdv/entregas.html', {'motoboys': motoboys, 'motos': motos})


@login_required
def cadastrar_motoboy(request):
    loja = check_loja(request)
    
    if request.method == 'POST':
        form = MotoboyForm(request.POST)
        if form.is_valid():
            motoboy = form.save(commit=False)
            motoboy.loja = loja 
            
            username_digitado = form.cleaned_data.get('username')
            senha_digitada = form.cleaned_data.get('senha')
            
            # Como a senha está required=False no form, exigimos ela aqui na criação
            if not senha_digitada:
                form.add_error('senha', "A senha é obrigatória para criar um novo motoboy.")
                return render(request, 'app_pdv/cadastrar_motoboy.html', {'form': form, 'titulo': 'Novo Entregador'})

            if User.objects.filter(username=username_digitado).exists():
                form.add_error('username', "Este usuário já está em uso.")
                return render(request, 'app_pdv/cadastrar_motoboy.html', {'form': form, 'titulo': 'Novo Entregador'})
            
            novo_user = User.objects.create_user(username=username_digitado, password=senha_digitada, first_name=motoboy.nome.split()[0])
            grupo_entregadores, _ = Group.objects.get_or_create(name='Entregadores')
            novo_user.groups.add(grupo_entregadores)
            
            perfil, _ = PerfilUsuario.objects.get_or_create(user=novo_user)
            perfil.loja = loja
            perfil.save()

            motoboy.user = novo_user
            motoboy.save()
            
            messages.success(request, f"Motoboy cadastrado! Login: {username_digitado}")
            return redirect('lista_entregas')
    else:
        form = MotoboyForm()
    
    return render(request, 'app_pdv/cadastrar_motoboy.html', {'form': form, 'titulo': 'Novo Entregador'})

@login_required
def editar_motoboy(request, id):
    loja = check_loja(request)
    motoboy = get_object_or_404(Motoboy, id=id, loja=loja)
    user_motoboy = motoboy.user

    if request.method == 'POST':
        form = MotoboyForm(request.POST, instance=motoboy)
        if form.is_valid():
            mb = form.save(commit=False)
            
            novo_username = form.cleaned_data.get('username')
            nova_senha = form.cleaned_data.get('senha')

            # Verifica se ele tentou mudar o username para um que já existe
            if user_motoboy and novo_username != user_motoboy.username and User.objects.filter(username=novo_username).exists():
                form.add_error('username', "Este usuário já está em uso.")
                return render(request, 'app_pdv/cadastrar_motoboy.html', {'form': form, 'titulo': 'Editar Entregador'})
            
            if user_motoboy:
                user_motoboy.username = novo_username
                # SE DIGITOU UMA SENHA NOVA, O SISTEMA REDEFINE
                if nova_senha: 
                    user_motoboy.set_password(nova_senha)
                user_motoboy.save()
            
            mb.save()
            messages.success(request, "Cadastro do motoboy atualizado com sucesso!")
            return redirect('lista_entregas')
    else:
        # Carrega o formulário já preenchido com o username atual
        form = MotoboyForm(instance=motoboy, initial={'username': user_motoboy.username if user_motoboy else ''})
    
    return render(request, 'app_pdv/cadastrar_motoboy.html', {'form': form, 'titulo': 'Editar Entregador'})

@login_required
def cadastrar_moto(request):
    loja = check_loja(request)
    if request.method == 'POST':
        form = MotoForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.loja = loja
            obj.save()
            messages.success(request, "Moto cadastrada com sucesso!")
            return redirect('lista_entregas')
    else:
        form = MotoForm()
    return render(request, 'app_pdv/cadastrar_moto.html', {'form': form, 'titulo': 'Nova Motocicleta'})

@login_required
def confirmar_recebimento_motoboy(request, venda_id):
    loja = check_loja(request)
    venda = get_object_or_404(Venda, id=venda_id, loja=loja)
    
    if venda.exige_conferencia_pagamento():
        venda.confirmar_conferencia_dinheiro(request.user)
        
    return redirect('lista_vendas')

# --------------------------------Area do Motoboy (APP FLUTTER)----------------------------------------------




def get_loja_api(user):
    return get_loja_usuario(user)


def get_loja_contexto(request):
    # =================================================================
    # BLINDAGEM SAAS: O TOKEN DO MOTOBOY MANDA MAIS QUE O APLICATIVO
    # =================================================================
    # 1. Se quem está chamando a API é um usuário logado (Motoboy), 
    # nós IGNORAMOS o que o App está pedindo e TRAVAMOS ele na loja do perfil dele!
    if request.user and request.user.is_authenticated:
        loja_do_usuario = get_loja_api(request.user)
        if loja_do_usuario:
            return loja_do_usuario
            
    # 2. Se for um visitante anônimo (ex: Aplicativo do Cliente final fazendo compras), 
    # aí sim ler a URL para saber de qual loja ele quer comprar.
    loja_id_app = request.GET.get('loja_id')
    if loja_id_app:
        try:
            return Loja.objects.get(id=loja_id_app)
        except Loja.DoesNotExist:
            pass
            
    return None


class EntregasDisponiveisView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            loja = get_loja_contexto(request) 
            if not loja: 
                return Response({'erro': 'Loja não identificada'}, status=403)

            if getattr(loja, 'usa_moveon', False) or not loja.monitorar_entrega:
                return Response([])

            # =========================================================
            # ESPIÃO SUPREMO - OLHANDO A ÚLTIMA VENDA DO BANCO
            # =========================================================
            print("\n--- INVESTIGAÇÃO SUPREMA ---")
            ultima_venda = Venda.objects.last()
            if ultima_venda:
                print(f"A ÚLTIMA VENDA CRIADA FOI O ID: {ultima_venda.id}")
                print(f"1. Pertence à Loja ID: {ultima_venda.loja_id} (O Motoboy está buscando a Loja {loja.id})")
                print(f"2. É para entrega? {ultima_venda.eh_entrega}")
                print(f"3. Já tem entregador? {'SIM' if ultima_venda.entregador else 'NÃO'}")
                print(f"4. Status da Venda: {ultima_venda.status}")
                print(f"5. Status da Entrega: {ultima_venda.status_entrega}")
            print("-----------------------------------------\n")
            # =========================================================
            
            vendas = Venda.objects.filter(
                loja=loja, 
                eh_entrega=True, 
                entregador__isnull=True, 
                status_entrega='PENDENTE' 
            ).filter(
                
                Q(status='EM_SEPARACAO') | Q(status='EM_PREPARACAO')
            ).order_by('-data_venda')
            
            dados = []
            for v in vendas:
                link_zap = None
                if v.cliente and v.cliente.telefone:
                    apenas_numeros = ''.join(filter(str.isdigit, str(v.cliente.telefone)))
                    if apenas_numeros:
                        link_zap = f"https://wa.me/55{apenas_numeros}"

                lista_itens = []
                if hasattr(v, 'itens'):
                    lista_itens = [f"{i.quantidade}x {i.produto.nome_venda}" for i in v.itens.all()]
                else:
                    lista_itens = ["Ver detalhes"]

                dados.append({
                    'id': v.id,
                    'cliente': "Cliente Avulso" if not v.cliente else v.cliente.nome,
                    'endereco': v.endereco_entrega or "Endereço não informado",
                    'valor': float(v.total),
                    'taxa': float(v.taxa_entrega),
                    'itens': lista_itens, 
                    'pagamento': get_nome_forma_pagamento(v.loja, v.forma_pagamento),
                    'troco_para': float(v.troco_para or 0),
                    'whatsapp_link': link_zap,
                    'status_texto': v.status
                })
                
            return Response(dados)
        except Exception as e:
            return Response([], status=200)

class AssumirEntregaView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, venda_id):
        loja = get_loja_contexto(request) 
        if not loja.monitorar_entrega:
            return Response({'erro': 'Esta loja finaliza entregas pela Torre de Controle.'}, status=400)

        try:
            venda = Venda.objects.get(id=venda_id, loja=loja)
            
            if venda.entregador is not None:
                return Response({'erro': 'Entrega já assumida!'}, status=400)
            
            venda.entregador = request.user
            
            
            venda.status_entrega = 'EM_ROTA' 
            
            
            venda.status = 'SAIU_ENTREGA' 
            
            venda.save()
            link_zap = notificar_cliente_saiu_entrega(venda)
            resp = {'mensagem': 'Boa viagem!'}
            if link_zap:
                resp['whatsapp_cliente_link'] = link_zap
            return Response(resp)
            
        except Venda.DoesNotExist:
            return Response({'erro': 'Venda não encontrada'}, status=404)


class DevolverEntregaView(APIView):
    """Devolve entrega assumida para a fila de disponíveis."""
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, venda_id):
        loja = get_loja_contexto(request)
        if not loja:
            return Response({'erro': 'Loja não identificada'}, status=403)
        if not loja.monitorar_entrega:
            return Response({'erro': 'Entregas gerenciadas pela Torre de Controle.'}, status=400)

        try:
            venda = Venda.objects.get(id=venda_id, loja=loja)
        except Venda.DoesNotExist:
            return Response({'erro': 'Venda não encontrada'}, status=404)

        if venda.entregador_id != request.user.id:
            return Response({'erro': 'Esta entrega não está com você.'}, status=403)
        if venda.status_entrega == 'ENTREGUE':
            return Response({'erro': 'Entrega já finalizada.'}, status=400)

        venda.entregador = None
        venda.status_entrega = 'PENDENTE'
        if venda.status == 'SAIU_ENTREGA':
            venda.status = 'EM_PREPARACAO'
        venda.save(update_fields=['entregador', 'status_entrega', 'status'])
        return Response({'mensagem': 'Entrega devolvida à fila.'})


import logging
logger = logging.getLogger(__name__)

class MinhasEntregasView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            loja = get_loja_contexto(request) 
            if not loja: return Response({'erro': 'Loja erro'}, status=403)

            vendas = Venda.objects.filter(entregador=request.user, loja=loja).order_by('-data_venda')
            
            dados = []
            for v in vendas:
                link_zap = None
                if v.cliente and v.cliente.telefone:
                    apenas_numeros = ''.join(filter(str.isdigit, str(v.cliente.telefone)))
                    if apenas_numeros:
                        link_zap = f"https://wa.me/55{apenas_numeros}"

                lista_itens = []
                if hasattr(v, 'itens'):
                    lista_itens = [f"{i.quantidade}x {i.produto.nome_venda}" for i in v.itens.all()]

                dados.append({
                    'id': v.id,
                    'cliente': v.cliente.nome if v.cliente else "Avulso", 
                    'endereco': v.endereco_entrega,
                    'status': v.status_entrega, 
                    'valor_recebido': float(v.taxa_entrega),
                    'data': localtime(v.data_venda).strftime('%d/%m/%Y %H:%M'),
                    'whatsapp_link': link_zap,
                    'pagamento': get_nome_forma_pagamento(v.loja, v.forma_pagamento),
                    'troco_para': float(v.troco_para or 0),
                    'valor': float(v.total), 
                    'itens': lista_itens
                })
                
            return Response(dados)
        except Exception as e:
            return Response({'erro': str(e)}, status=500)
    
def nao_eh_motoboy(user):
    eh_entregador = user.groups.filter(name='Entregadores').exists()
    return not eh_entregador


# ------------------------- ÁREA DA API (DEMAIS ENDPOINTS) ----------------------------

class CustomAuthToken(ObtainAuthToken):
    def post(self, request, *args, **kwargs):
        from rest_framework.authtoken.models import Token
        from rest_framework.exceptions import ValidationError
        from app_pdv.seguranca import (
            conta_congelada_user,
            conta_congelada_username,
            encerrar_outras_sessoes_web,
            invalidar_sessao_web,
            ip_bloqueado,
            limpar_falhas_apos_sucesso,
            minutos_restantes_bloqueio_ip,
            obter_ip_cliente,
            registrar_falha_login,
            registrar_token_ativo,
            invalidar_tokens_api,
            usuario_eh_superuser,
        )

        username = (request.data.get('username') or '').strip()
        serializer = self.serializer_class(data=request.data, context={'request': request})
        try:
            serializer.is_valid(raise_exception=True)
        except ValidationError:
            registrar_falha_login(request, username)
            if not usuario_eh_superuser(username):
                ip = obter_ip_cliente(request)
                if ip_bloqueado(ip):
                    mins = minutos_restantes_bloqueio_ip(ip)
                    return Response({
                        'erro': (
                            f'Muitas tentativas de login. IP bloqueado por {mins} minuto(s). '
                            'Contate o administrador se precisar de acesso imediato.'
                        ),
                        'bloqueio_ip': True,
                    }, status=429)
                if conta_congelada_username(username):
                    return Response({
                        'erro': (
                            'Conta congelada por segurança. '
                            'Solicite ao administrador do sistema para descongelar.'
                        ),
                        'conta_congelada': True,
                    }, status=403)
            return Response({'erro': 'Usuário ou senha inválidos.'}, status=400)

        user = serializer.validated_data['user']
        if conta_congelada_user(user):
            return Response(
                {'erro': 'Conta congelada. Solicite ao administrador do sistema.'},
                status=403,
            )

        if not user.is_superuser:
            from app_pdv.assinatura import (
                loja_do_usuario,
                loja_esta_bloqueada,
                payload_assinatura_bloqueada,
            )
            loja = loja_do_usuario(user)
            if loja and loja_esta_bloqueada(loja):
                return Response(payload_assinatura_bloqueada(loja), status=403)

        limpar_falhas_apos_sucesso(request, user)

        if not user.is_superuser:
            invalidar_tokens_api(user)
            invalidar_sessao_web(user)
            token = Token.objects.create(user=user)
            registrar_token_ativo(user, token.key)
            encerrar_outras_sessoes_web(user)
        else:
            token, _ = Token.objects.get_or_create(user=user)

        return Response({
            'token': token.key,
            'user_id': user.pk,
            'email': user.email,
            'nome': user.first_name or user.username,
            'is_superuser': user.is_superuser,
            'pode_gestor': usuario_pode_acessar_gestor(user),
        })
    

@api_view(['GET'])
@authentication_classes([TokenAuthentication]) 
@permission_classes([IsAuthenticated])
def api_listar_entregas(request):
    """
    Função legada ou secundária. 
    Se o app usar EntregasDisponiveisView, essa aqui pode ficar como backup.
    """
    loja = get_loja_contexto(request) 
    if not loja: return Response([])

    entregas = Venda.objects.filter(
        loja=loja,
        eh_entrega=True, 
        entregador=None
    ).filter(
        Q(status='EM_PREPARACAO') | Q(status='ABERTO') | Q(status='PENDENTE')
    ).order_by('-id')
    
    return Response(gerar_lista_dados(entregas))

@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def api_minhas_entregas(request):
    """
    Função legada ou secundária. 
    O app principal agora usa MinhasEntregasView (classe).
    """
    loja = get_loja_contexto(request) 
    minhas = Venda.objects.filter(entregador=request.user, loja=loja).order_by('-id')
    return Response(gerar_lista_dados(minhas))

# ----------------------- FUNÇÃO AJUDANTE ----------------------------------

def gerar_lista_dados(vendas_queryset):
    lista_dados = []
    for venda in vendas_queryset:
        itens_formatados = []
        try:
            for i in venda.itens.all():
                itens_formatados.append(f"{i.quantidade}x {i.produto.nome_venda}")
        except:
            itens_formatados = ["Erro ao Ler Itens"]
        
        if not itens_formatados:
            itens_formatados = ["Sem itens registrados"]

        link_zap = None
        telefone_visual = "Sem telefone"
        
        if venda.cliente and venda.cliente.telefone:
            telefone_bruto = str(venda.cliente.telefone)
            telefone_visual = telefone_bruto
            apenas_numeros = ''.join(filter(str.isdigit, telefone_bruto))
            if apenas_numeros:
                link_zap = f"https://wa.me/55{apenas_numeros}"

        endereco_final = venda.endereco_entrega
        if not endereco_final and venda.cliente:
            endereco_final = venda.cliente.endereco

        lista_dados.append({
            'id': venda.id,
            'cliente': venda.cliente.nome if venda.cliente else "Cliente Avulso",
            'endereco': endereco_final or "Endereço não informado",
            'valor': float(venda.total),
            'itens': itens_formatados,
            'status': venda.status_entrega,
            'pagamento': get_nome_forma_pagamento(venda.loja, venda.forma_pagamento), 
            'whatsapp_link': link_zap,
            'telefone_texto': telefone_visual,
            'troco_para': float(venda.troco_para or 0)
        })
    return lista_dados    
    
@api_view(['POST'])
@authentication_classes([TokenAuthentication]) 
@permission_classes([IsAuthenticated])
def api_assumir_entrega(request, venda_id):
    """
    Função usada nas URLs antigas. Se o urls.py apontar para AssumirEntregaView.as_view(),
    esta função não será chamada, mas mantemos atualizada por segurança.
    """
    loja = get_loja_contexto(request) 
    if not loja.monitorar_entrega:
        return Response({'erro': 'Esta loja finaliza entregas pela Torre de Controle.'}, status=400)

    try:
        venda = Venda.objects.get(id=venda_id, loja=loja)
    except Venda.DoesNotExist:
        return Response({'erro': 'Venda não encontrada'}, status=404)

    if venda.status == 'CANCELADO':
        return Response({'erro': 'Ops! A loja cancelou este pedido.'}, status=400)
    
    if venda.entregador is not None:
        return Response({'erro': 'Esta entrega já foi pega por outro motoboy!'}, status=400)

    venda.entregador = request.user
    venda.status_entrega = 'EM_ROTA'   
    venda.status = 'SAIU_ENTREGA'      
    venda.save()
    
    return Response({'sucesso': 'Entrega aceita! Boa corrida.'})  
    

@api_view(['POST'])
@authentication_classes([TokenAuthentication]) 
@permission_classes([IsAuthenticated])
def api_finalizar_entrega(request, venda_id):
    
    loja = get_loja_contexto(request) 
    try:
        venda = Venda.objects.get(id=venda_id, loja=loja)
    except Venda.DoesNotExist:
        return Response({'erro': 'Venda não encontrada'}, status=404)

    
    if venda.entregador != request.user:
        return Response({'erro': 'Você não é o dono desta entrega!'}, status=403)
    
    venda.status_entrega = 'ENTREGUE' 
    venda.status = 'FINALIZADO'  
    venda.save()
    
    link_zap = notificar_cliente_entrega_concluida(venda)
    resp = {'sucesso': 'Entrega finalizada com sucesso!'}
    if link_zap:
        resp['whatsapp_cliente_link'] = link_zap
    return Response(resp)

@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def api_meus_ganhos(request):
    
    loja = get_loja_contexto(request) 
    periodo = request.GET.get('periodo', 'hoje') 
    data_inicio_str = request.GET.get('inicio')
    data_fim_str = request.GET.get('fim')

    hoje = date.today()
    filtro_data = {}

    if periodo == 'hoje':
        filtro_data['data_venda__date'] = hoje
    elif periodo == 'semana':
        inicio_semana = hoje - timedelta(days=hoje.weekday()) 
        filtro_data['data_venda__date__gte'] = inicio_semana
    elif periodo == 'mes':
        filtro_data['data_venda__month'] = hoje.month
        filtro_data['data_venda__year'] = hoje.year
    elif periodo == 'intervalo' and data_inicio_str and data_fim_str:
        try:
            dt_ini = datetime.strptime(data_inicio_str, '%Y-%m-%d').date()
            dt_fim = datetime.strptime(data_fim_str, '%Y-%m-%d').date()
            filtro_data['data_venda__date__range'] = [dt_ini, dt_fim]
        except:
            return Response({'erro': 'Formato de data inválido'}, status=400)

    vendas = Venda.objects.filter(
        loja=loja,
        entregador=request.user, 
        status_entrega='ENTREGUE', 
        **filtro_data
    ).order_by('-id')

    total_ganho = sum(v.taxa_entrega for v in vendas)
    quantidade = vendas.count()

    historico = []
    for v in vendas:
        historico.append({
            'data': localtime(v.data_venda).strftime('%d/%m/%Y'),
            'cliente': v.cliente.nome if v.cliente else 'Avulso',
            'valor': float(v.taxa_entrega)
        })

    return Response({
        'total': float(total_ganho),
        'quantidade': quantidade,
        'historico': historico
    })

# -------------------------------- APP DO CLIENTE & TORRE ----------------------------

@login_required
def torre_controle(request):
    loja = check_loja(request)
    
    usa_moveon = getattr(loja, 'usa_moveon', False) if loja else False
    monitorar_entrega = getattr(loja, 'monitorar_entrega', True) if loja else True
    motoboys = []
    if loja and not monitorar_entrega:
        motoboys = list(Motoboy.objects.filter(loja=loja, ativo=True).values('id', 'nome'))
    
    return render(request, 'app_pdv/torre_controle.html', {
        'usa_moveon': usa_moveon,
        'monitorar_entrega': monitorar_entrega,
        'motoboys_json': json.dumps(motoboys),
    })


@login_required
def api_pedidos_torre(request):
    loja = check_loja(request)
    if not loja: return JsonResponse({'erro': 'Sem loja'}, status=403)

    pedidos = Venda.objects.filter(
        loja=loja,
        status__in=['PENDENTE', 'EM_PREPARACAO', 'SAIU_ENTREGA']
    ).select_related('cliente', 'entregador').order_by('data_venda') 

    lista_pedidos = []
    tem_novo_pedido = False

    for venda in pedidos:
        if venda.status == 'PENDENTE':
            tem_novo_pedido = True

        entregador_nome = None
        if venda.entregador:
            entregador_nome = venda.entregador.first_name or venda.entregador.username

        lista_pedidos.append({
            'id': venda.id,
            'cliente': venda.cliente.nome if venda.cliente else 'Cliente App',
            'total': float(venda.total),
            'status': venda.status,
            'origem': venda.origem,
            'itens': [f"{item.quantidade}x {item.produto.nome_venda}" for item in venda.itens.all()],
            'endereco': venda.endereco_entrega,
            'pagamento': get_nome_forma_pagamento(venda.loja, venda.forma_pagamento),
            'obs': venda.observacao or "",
            'entregador_nome': entregador_nome,
            'eh_entrega': venda.eh_entrega,
        })

    motoboys = []
    if not loja.monitorar_entrega:
        motoboys = list(Motoboy.objects.filter(loja=loja, ativo=True).values('id', 'nome'))

    return JsonResponse({
        'pedidos': lista_pedidos,
        'tocar_som': tem_novo_pedido,
        'monitorar_entrega': loja.monitorar_entrega,
        'motoboys': motoboys,
    })


@csrf_exempt
@login_required
def api_atualizar_status_pedido(request, venda_id):
    loja = check_loja(request)
    if request.method == 'POST':
        data = json.loads(request.body)
        novo_status = data.get('novo_status')
        motoboy_id = data.get('motoboy_id')
        
        venda = get_object_or_404(Venda, id=venda_id, loja=loja)
        venda.status = novo_status

        if not loja.monitorar_entrega and motoboy_id and novo_status in ('SAIU_ENTREGA', 'EM_PREPARACAO'):
            motoboy = Motoboy.objects.filter(id=motoboy_id, loja=loja, ativo=True).first()
            if motoboy and motoboy.user:
                venda.entregador = motoboy.user

        if novo_status == 'FINALIZADO':
            venda.status_entrega = 'ENTREGUE'

        venda.save()

        whatsapp_link = None
        if novo_status == 'SAIU_ENTREGA':
            whatsapp_link = notificar_cliente_saiu_entrega(venda)
        elif novo_status == 'FINALIZADO' and venda.eh_entrega:
            whatsapp_link = notificar_cliente_entrega_concluida(venda)
        
        # =================================================================
        # 2. O CÉREBRO DA INTEGRAÇÃO: O PDV IDENTIFICA A CONFIGURAÇÃO DA LOJA
        # =================================================================
        if novo_status in ['EM_PREPARACAO', 'SAIU_ENTREGA'] and loja.monitorar_entrega and getattr(loja, 'usa_moveon', False) and venda.eh_entrega:
            from transporte.models import Corrida # Importa o banco de dados do MoveON
            
            # Trava de segurança: Garante que não vai chamar 2 motoristas pro mesmo pacote
            if not Corrida.objects.filter(venda_pdv_id=venda.id).exists():
                
                # Resgata o WhatsApp (do cliente ou da loja) para o motorista poder avisar
                zap_contato = ""
                if venda.cliente and venda.cliente.whatsapp:
                    zap_contato = venda.cliente.whatsapp
                elif hasattr(loja, 'telefone'):
                    zap_contato = loja.telefone
                
                # CRIA A CORRIDA E FAZ O APP DO MOTORISTA APITAR!
                Corrida.objects.create(
                    venda_pdv_id=venda.id,
                    cliente_nome=f"Entrega: {loja.nome} (Para: {venda.cliente.nome if venda.cliente else 'Cliente Avulso'})",
                    cliente_whatsapp=zap_contato,
                    origem_texto=loja.nome, 
                    destino_texto=venda.endereco_entrega or "Endereço não informado",
                    valor_cobrado=venda.taxa_entrega, # A taxa cobrada no caixa vai pro motorista
                    status='SOLICITADO'
                )
        # =================================================================
        
        resp = {'sucesso': True}
        if whatsapp_link:
            resp['whatsapp_cliente_link'] = whatsapp_link
        return JsonResponse(resp)
    return JsonResponse({'erro': 'Método inválido'}, status=400)


def api_listar_produtos(request):
    
    
    loja_id = request.GET.get('loja_id', 1)
    try:
        loja = Loja.objects.get(id=loja_id)
    except Loja.DoesNotExist:
        return JsonResponse({'erro': 'Loja não encontrada'}, status=404)
    produtos = produtos_disponiveis_pdv(loja).filter(ativo=True)
    serializer = ProdutoCatalogoSerializer(produtos, many=True)
    return JsonResponse(serializer.data, safe=False)


def api_formas_pagamento(request):
    loja_id = request.GET.get('loja_id', 1)
    try:
        loja = Loja.objects.get(id=loja_id)
    except Loja.DoesNotExist:
        return JsonResponse({'erro': 'Loja não encontrada'}, status=404)

    # Garante criação de novas formas (ex.: CORTESIA) em lojas antigas
    if not FormaPagamentoLoja.objects.filter(loja=loja, codigo='CORTESIA').exists():
        criar_formas_pagamento_padrao(loja)

    formas = FormaPagamentoLoja.objects.filter(loja=loja, ativo=True).order_by('ordem', 'nome')
    dados = [{'codigo': f.codigo, 'nome': f.nome, 'cor': f.cor, 'icone': f.icone} for f in formas]
    return JsonResponse(dados, safe=False)


@csrf_exempt
@transaction.atomic
def api_criar_pedido(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            loja_id = data.get('loja_id', 1) 
            loja = Loja.objects.get(id=loja_id)

            cliente_nome = data.get('cliente_nome', 'Cliente App')
            telefone = data.get('telefone', '')
            endereco_novo = data.get('endereco', '')
            observacao_texto = data.get('obs', '')
            
            # PUXA A INFORMAÇÃO SE É ENTREGA OU RETIRADA
            eh_entrega = data.get('eh_entrega', True) 
            
            valor_troco = 0.00
            if 'Troco p/:' in observacao_texto:
                try:
                    partes = observacao_texto.split('R$')
                    if len(partes) > 1:
                        valor_limpo = partes[1].replace(')', '').strip()
                        valor_troco = float(valor_limpo)
                except:
                    valor_troco = 0.00

            if not loja.loja_aberta:
                return JsonResponse({'erro': 'LOJA FECHADA - PEDIDO REJEITADO'}, status=403)

            # Garante criação de novas formas (ex.: CORTESIA) em lojas antigas
            if not FormaPagamentoLoja.objects.filter(loja=loja, codigo='CORTESIA').exists():
                criar_formas_pagamento_padrao(loja)

            pagamento = data.get('pagamento')
            if not validar_forma_pagamento(loja, pagamento):
                return JsonResponse({'erro': 'Forma de pagamento inválida para esta loja.'}, status=400)

            meio_liquidacao = data.get('meio_liquidacao')
            if not meio_liquidacao and pagamento in ('DINHEIRO', 'PIX', 'CREDITO', 'DEBITO'):
                meio_liquidacao = pagamento
            elif not meio_liquidacao:
                meio_liquidacao = 'DINHEIRO' if valor_troco > 0 else 'PIX'
            if not validar_meio_liquidacao(meio_liquidacao):
                return JsonResponse({'erro': 'Meio de liquidação inválido.'}, status=400)

            # CORREÇÃO ANTI-ERRO 400 (DUPLICIDADE E PROTEÇÃO DE ENDEREÇO)
            cliente_obj = None
            if telefone:
                # Usa .first() para não quebrar se houver telefones duplicados no banco
                cliente_obj = Cliente.objects.filter(telefone=telefone, loja=loja).first()
                if not cliente_obj:
                    cliente_obj = Cliente.objects.create(
                        telefone=telefone, 
                        loja=loja,
                        nome=cliente_nome,
                        endereco=endereco_novo if eh_entrega else ""
                    )
                else:
                    cliente_obj.nome = cliente_nome
                    # Só atualiza o endereço no banco de dados se for uma entrega real
                    if eh_entrega and endereco_novo and endereco_novo != "Retirada na Loja":
                        cliente_obj.endereco = endereco_novo
                    cliente_obj.save()

            usar_fidelidade = data.get('usar_fidelidade', False)
            total_pedido = Decimal(str(data.get('total', 0)))
            obs_extra = observacao_texto

            if cliente_obj and usar_fidelidade and loja.fidelidade_ativa:
                subtotal = total_pedido - Decimal(str(data.get('taxa_entrega', 0) if eh_entrega else 0))
                desconto = calcular_desconto_fidelidade(cliente_obj, loja, subtotal, usar_promocao=True)
                if desconto > 0:
                    total_pedido -= desconto
                    obs_extra += f" | FIDELIDADE: promoção utilizada (-R$ {desconto:.2f})"
                    cliente_obj.promocao_fidelidade_ativa = False
                    cliente_obj.progresso_fidelidade = Decimal('0')
                    cliente_obj.save(update_fields=['promocao_fidelidade_ativa', 'progresso_fidelidade'])

            # CRIA A VENDA
            venda = Venda.objects.create(
                loja=loja, 
                cliente=cliente_obj,
                total=total_pedido,
                eh_entrega=eh_entrega, # <-- SALVANDO CORRETAMENTE
                taxa_entrega=data.get('taxa_entrega', 0.0),
                endereco_entrega=endereco_novo,
                forma_pagamento=pagamento,
                meio_liquidacao=meio_liquidacao,
                observacao=obs_extra,
                origem='APP',
                status='PENDENTE',
                troco_para=valor_troco if meio_liquidacao == 'DINHEIRO' else 0,
                conferencia_ok=(meio_liquidacao != 'DINHEIRO'),
            )

            itens_data = data.get('itens', [])
            for item in itens_data:
                produto = Produto.objects.select_related('item_estoque').get(id=item['id_produto'], loja=loja)
                err = validar_estoque_item_venda(loja, produto, item['quantidade'])
                if err:
                    return JsonResponse({'erro': err}, status=400)
            for item in itens_data:
                produto = Produto.objects.get(id=item['id_produto'], loja=loja)
                baixa_vazio = produto_baixa_apenas_vasilhame_vazio(produto)
                ItemVenda.objects.create(
                    venda=venda,
                    produto=produto,
                    quantidade=item['quantidade'],
                    preco_unitario=produto.preco_venda,
                    custo_unitario=custo_unitario_produto_venda(produto),
                    baixa_vasilhame_vazio=baixa_vazio,
                )

            venda.save()
            link_zap_empresa = notificar_novo_pedido_empresa(venda)
            resp = {'sucesso': True, 'pedido_id': venda.id}
            if link_zap_empresa:
                resp['whatsapp_empresa_link'] = link_zap_empresa
            return JsonResponse(resp, status=201)

        except Exception as e:
            # Imprime o erro exato no terminal do Django para facilitar futuras manutenções
            import traceback
            traceback.print_exc() 
            return JsonResponse({'erro': str(e)}, status=400)
            
    return JsonResponse({'erro': 'Método inválido'}, status=405)



def api_buscar_cliente(request):
    telefone = request.GET.get('telefone')
    loja_id = request.GET.get('loja_id', 1)

    if telefone:
        telefone_limpo = ''.join(filter(str.isdigit, telefone))
        cliente = Cliente.objects.filter(telefone=telefone, loja_id=loja_id).first()
        
        if cliente:
            return JsonResponse({
                'encontrou': True,
                'nome': cliente.nome,
                'endereco': cliente.endereco,
                'telefone': cliente.telefone,
                'bairro': cliente.bairro or '',
                'fidelidade': status_fidelidade_cliente(cliente, cliente.loja),
            })
            
    return JsonResponse({'encontrou': False})


def api_fidelidade_config(request):
    loja_id = request.GET.get('loja_id', 1)
    try:
        loja = Loja.objects.get(id=loja_id)
    except Loja.DoesNotExist:
        return JsonResponse({'erro': 'Loja não encontrada'}, status=404)
    cfg = obter_config_fidelidade(loja)
    if not cfg:
        return JsonResponse({'ativa': False})
    return JsonResponse(cfg)


@login_required
def api_fidelidade_cliente_pdv(request):
    loja = check_loja(request)
    if not loja:
        return JsonResponse({'erro': 'Sem loja'}, status=403)
    cliente_id = request.GET.get('cliente_id')
    if not cliente_id:
        return JsonResponse({'fidelidade': status_fidelidade_cliente(None, loja)})
    cliente = Cliente.objects.filter(id=cliente_id, loja=loja).first()
    return JsonResponse({'fidelidade': status_fidelidade_cliente(cliente, loja)})


def api_fidelidade_status(request):
    telefone = request.GET.get('telefone')
    loja_id = request.GET.get('loja_id', 1)
    if not telefone:
        return JsonResponse({'erro': 'Telefone obrigatório'}, status=400)
    try:
        loja = Loja.objects.get(id=loja_id)
    except Loja.DoesNotExist:
        return JsonResponse({'erro': 'Loja não encontrada'}, status=404)
    cliente = Cliente.objects.filter(telefone=telefone, loja=loja).first()
    if not cliente:
        return JsonResponse({'encontrou': False, 'fidelidade': status_fidelidade_cliente(None, loja)})
    return JsonResponse({
        'encontrou': True,
        'fidelidade': status_fidelidade_cliente(cliente, loja),
    })


def api_meus_pedidos(request):
    telefone = request.GET.get('telefone')
    loja_id = request.GET.get('loja_id', 1)

    if not telefone: return JsonResponse([], safe=False)

    vendas = Venda.objects.filter(cliente__telefone=telefone, loja_id=loja_id).order_by('-id')
    
    lista_pedidos = []
    for venda in vendas:
        itens_desc = []
        for item in venda.itens.all():
            itens_desc.append(f"{item.quantidade}x {item.produto.nome_venda}")
            
        lista_pedidos.append({
            'id': venda.id,
            'data': localtime(venda.data_venda).strftime('%d/%m/%Y %H:%M'),
            'total': float(venda.total),
            'status': venda.get_status_display(),
            'itens': itens_desc,
            'cor_status': venda.status 
        })
        
    return JsonResponse(lista_pedidos, safe=False)


@login_required
def api_conferir_venda(request, venda_id):
    loja = check_loja(request)
    if request.method == 'POST':
        venda = get_object_or_404(Venda, id=venda_id, loja=loja)
        if not venda.exige_conferencia_pagamento():
            return JsonResponse({'sucesso': False, 'erro': 'Esta venda não exige conferência de dinheiro.'}, status=400)
        venda.confirmar_conferencia_dinheiro(request.user)
        return JsonResponse({'sucesso': True})
    return JsonResponse({'sucesso': False, 'erro': 'Método inválido'})


def api_obter_taxa_entrega(request):
    
    loja_id = request.GET.get('loja_id', 1)
    loja = Loja.objects.filter(id=loja_id).first()
    taxa = float(loja.taxa_entrega_app) if loja else 5.00
    return JsonResponse({'taxa': taxa})


@login_required
@csrf_exempt
def definir_taxa_entrega(request):
    loja = check_loja(request)
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            nova_taxa = float(data.get('nova_taxa'))
            
            loja.taxa_entrega_app = nova_taxa
            loja.save()
            
            return JsonResponse({'sucesso': True})
        except Exception as e:
            return JsonResponse({'erro': str(e)}, status=400)
    return JsonResponse({'erro': 'Método inválido'}, status=400)


@csrf_exempt
@login_required
def api_toggle_loja(request):
    """
    Liga ou Desliga a loja.
    Chamado pelo botão na Torre de Controle.
    """
    loja = check_loja(request) 
    if not loja: 
        return JsonResponse({'erro': 'Loja não encontrada'}, status=403)
    
    if request.method == 'POST':
        
        loja.loja_aberta = not loja.loja_aberta
        loja.save()
        
        status_texto = "ABERTA" if loja.loja_aberta else "FECHADA"
        return JsonResponse({
            'sucesso': True, 
            'loja_aberta': loja.loja_aberta, 
            'msg': f'Sucesso! A loja agora está {status_texto}.'
        })
        
    
    return JsonResponse({'loja_aberta': loja.loja_aberta})

#----------------- Trafego Pg ------------------------

class ReceberLeadTrafficHub(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        dados = request.data
        loja_id = dados.get('saas_loja_id')
        
        if not loja_id:
            return Response({"erro": "ID da loja invalido"}, status=status.HTTP_400_BAD_REQUEST)

        loja_obj = get_object_or_404(Loja, id=loja_id)

        print(f"📦 Recebendo Lead para: {loja_obj.nome}")

        telefone = dados.get('telefone')
        
        # --- ATENÇÃO AQUI ---
        # Removi 'email' e 'observacoes' temporariamente para parar o erro.
        # Depois que você me mandar o seu models.py, a gente coloca os nomes certos.
        cliente, created = Cliente.objects.get_or_create(
            telefone=telefone,
            loja=loja_obj,
            defaults={
                'nome': dados.get('nome'),
                # 'email': dados.get('email'),  <-- COMENTEI POIS SEU SISTEMA NÃO TEM ESSE CAMPO
                # 'observacoes': ...            <-- COMENTEI TAMBÉM
            }
        )

        if created:
            msg = "Novo cliente cadastrado!"
        else:
            msg = "Cliente já existia."

        return Response({"status": "Sucesso", "detalhe": msg, "cliente_id": cliente.id}, status=status.HTTP_201_CREATED)
    

    #---------------------------- OUTRAS FUNÇÕES ----------------------------



def fazer_logout(request):
        if getattr(request, 'user', None) and request.user.is_authenticated:
            registrar_log(
                request, 'LOGOUT',
                f'Logout: {request.user.username}',
                modelo='User', objeto_id=request.user.id,
            )
        logout(request)
        return redirect('login')

def assinatura_bloqueada(request):
    """Renderiza a tela de bloqueio com opção de pagamento"""
    loja = None
    if hasattr(request.user, 'perfil') and request.user.perfil.loja:
        loja = request.user.perfil.loja
    
    context = {
        'loja': loja,
        'pix_code': "00020126580014br.gov.bcb.pix0136123e4567-e89b-12d3-a456-426614174000520400005303986540510.005802BR5913TRAFFICHUB SAAS6008BRASILIA62070503***6304E2CA", 
    }
    return render(request, 'app_pdv/bloqueio_pagamento.html', context)

@login_required
def minha_assinatura(request):
    loja = check_loja(request)
    if not loja: return redirect('dashboard')
    
    
    faturas = loja.faturas.all().order_by('-data_vencimento')
    
    context = {
        'loja': loja,
        'faturas': faturas,
        'dias_restantes': loja.dias_restantes()
    }
    return render(request, 'app_pdv/minha_assinatura.html', context)