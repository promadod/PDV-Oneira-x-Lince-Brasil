from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from .models import (
    Loja, PerfilUsuario, Fornecedor, ItemEstoque, Produto, Cliente, GrupoProduto, ComponenteKit,
    Venda, ItemVenda, Caixa, EntradaEstoque, PrecoFornecedorItem, PagamentoFiado, LiquidacaoVenda,
    PagamentoMercadoria, ParcelaFiadoAgendada, ParcelaMercadoriaAgendada, BloqueioIPLogin,
    CategoriaTransacao, Transacao, Receita, Despesa, Moto, Motoboy, Rede,
    FormaPagamentoLoja, LogFechamentoEstoqueDiario
)
from .seguranca import descongelar_conta, liberar_ip

admin.site.site_header = "Magno Distribuidora - Administração"
admin.site.site_title = "Painel Administrativo"
admin.site.index_title = "Gerenciamento do Sistema"

# --- CONFIGURAÇÃO DE USUÁRIO E PERFIL (SAAS) ---
class PerfilUsuarioInline(admin.StackedInline):
    model = PerfilUsuario
    can_delete = False
    max_num = 1
    verbose_name_plural = 'Perfil do Usuário (Vincular Loja)'
    readonly_fields = ('congelada_em', 'tentativas_login_falhas', 'session_key_ativa', 'token_ativo')
    fieldsets = (
        (None, {
            'fields': ('loja', 'telefone'),
        }),
        ('Permissões', {
            'fields': (
                'perm_dashboard', 'perm_pdv', 'perm_caixa', 'perm_torre',
                'perm_estoque', 'perm_relatorios', 'perm_usuarios',
            ),
        }),
        ('Segurança', {
            'fields': (
                'conta_congelada', 'motivo_congelamento', 'congelada_em',
                'tentativas_login_falhas', 'session_key_ativa', 'token_ativo',
            ),
            'description': 'Desmarque "Conta congelada" e salve para liberar o usuário.',
        }),
    )

class UserAdmin(BaseUserAdmin):
    inlines = (PerfilUsuarioInline,)
    actions = ['descongelar_contas_selecionadas']

    def save_formset(self, request, form, formset, change):
        # Signal post_save já cria PerfilUsuario no add; evita 2º INSERT (UNIQUE user_id).
        if formset.model is PerfilUsuario:
            saved = []
            for f in formset.forms:
                if not getattr(f, 'cleaned_data', None) or f.cleaned_data.get('DELETE'):
                    continue
                perfil, _ = PerfilUsuario.objects.get_or_create(user=form.instance)
                for field_name, value in f.cleaned_data.items():
                    if field_name in ('id', 'user', 'DELETE'):
                        continue
                    if hasattr(perfil, field_name):
                        setattr(perfil, field_name, value)
                perfil.save()
                saved.append(perfil)
            # construct_change_message exige esses atributos após formset.save()
            formset.new_objects = saved if not change else []
            formset.changed_objects = [(obj, []) for obj in saved] if change else []
            formset.deleted_objects = []
            return
        super().save_formset(request, form, formset, change)

    @admin.action(description='Descongelar contas selecionadas (segurança)')
    def descongelar_contas_selecionadas(self, request, queryset):
        n = 0
        for user in queryset:
            if hasattr(user, 'perfil') and user.perfil.conta_congelada:
                descongelar_conta(user)
                n += 1
        self.message_user(request, f'{n} conta(s) descongelada(s).')

# Remove o admin de usuário padrão e adiciona com a Loja
admin.site.unregister(User)
admin.site.register(User, UserAdmin)


# --- HELPER PARA MULTI-LOJAS ---
class SaasAdmin(admin.ModelAdmin):
    """
    Classe auxiliar que adiciona a coluna 'Loja' na visualização
    apenas se o usuário for Superusuário (Dono do SaaS).
    """
    def get_list_display(self, request):
        defaults = list(super().get_list_display(request))
        
        if request.user.is_superuser and 'loja' not in defaults:
            return defaults + ['loja']
        return defaults

    def get_list_filter(self, request):
        defaults = list(super().get_list_filter(request))
        if request.user.is_superuser and 'loja' not in defaults:
            return defaults + ['loja']
        return defaults


# ---  MODELS ORIGINAIS (COM HERANÇA SAAS) ---

@admin.register(Loja)
class LojaAdmin(admin.ModelAdmin):
    list_display = ('id', 'nome', 'gerente', 'ativo', 'usa_fiado', 'permite_pagamento_dividido', 'controla_vasilhame_vazio', 'estoque_diario', 'gerencia_pagamento_mercadorias', 'monitorar_entrega', 'trabalha_com_entregas', 'trabalha_com_leitor_codigo_barras', 'trabalha_com_balanca_granel', 'impressao_automatica', 'data_criacao')
    list_filter = ('ativo', 'monitorar_entrega', 'trabalha_com_entregas', 'trabalha_com_leitor_codigo_barras', 'trabalha_com_balanca_granel', 'impressao_automatica', 'usa_fiado', 'permite_pagamento_dividido', 'controla_vasilhame_vazio', 'estoque_diario', 'gerencia_pagamento_mercadorias')
    fieldsets = (
        (None, {
            'fields': ('nome', 'cnpj', 'gerente', 'rede', 'nome_unidade', 'ativo', 'loja_aberta')
        }),
        ('Entregas', {
            'fields': ('taxa_entrega_app', 'taxa_entrega_pdv', 'trabalha_com_entregas', 'monitorar_entrega', 'usa_moveon')
        }),
        ('PDV', {
            'fields': (
                'nome_marca_pdv', 'impressao_automatica',
                'trabalha_com_leitor_codigo_barras', 'trabalha_com_balanca_granel',
                'balanca_ean_prefixo', 'balanca_plu_digitos', 'balanca_ean_variavel',
                'cobra_taxa_servico', 'taxa_servico_pct',
            ),
            'description': 'Taxa de serviço só vale com "Trabalha com entregas" desmarcado.',
        }),
        ('Depósito / Fiado', {
            'fields': ('usa_fiado', 'permite_pagamento_dividido', 'controla_vasilhame_vazio', 'estoque_diario', 'permite_venda_completa', 'divide_produtos_por_grupos', 'gerencia_pagamento_mercadorias'),
            'description': 'Habilite fiado para venda a prazo. Estoque diário exige controle de vasilhame ativo. CMV controla pagamentos de compras consignadas.',
        }),
        ('Fidelidade', {
            'fields': ('fidelidade_ativa', 'fidelidade_tipo_meta', 'fidelidade_meta', 'fidelidade_desconto_pct'),
        }),
        ('Assinatura SaaS', {
            'fields': ('status_assinatura', 'data_vencimento', 'valor_mensalidade',
                       'dias_tolerancia', 'ultimo_acesso', 'link_pagamento_atual'),
            'classes': ('collapse',),
        }),
    )


@admin.register(FormaPagamentoLoja)
class FormaPagamentoLojaAdmin(SaasAdmin):
    list_display = ('nome', 'codigo', 'exige_conferencia', 'cor', 'ativo', 'eh_sistema', 'ordem')
    list_filter = ('ativo', 'eh_sistema', 'exige_conferencia')
    list_editable = ('ativo', 'ordem', 'exige_conferencia')
    search_fields = ('nome', 'codigo')
    readonly_fields = ('eh_sistema',)

    def has_delete_permission(self, request, obj=None):
        if obj and obj.eh_sistema:
            return False
        return super().has_delete_permission(request, obj)


@admin.register(Fornecedor)
class FornecedorAdmin(SaasAdmin):
    list_display = ('id', 'nome', 'contato')
    search_fields = ('nome', 'contato')


@admin.register(ItemEstoque)
class ItemEstoqueAdmin(SaasAdmin):

    list_display = (
        'id', 'nome', 'unidade_medida',
        'quantidade_estoque', 'quantidade_vazios', 'status_estoque',
    )
    list_editable = ('quantidade_estoque', 'quantidade_vazios')
    search_fields = ('nome',)
    list_filter = ('unidade_medida',)
    list_per_page = 50
    readonly_fields = ('id',)
    actions = [
        'zerar_apenas_cheios',
        'zerar_apenas_vazios',
        'zerar_cheios_e_vazios',
    ]

    @admin.display(description='Situação')
    def status_estoque(self, obj):
        if obj.quantidade_estoque <= 10:
            return "⚠️ Baixo"
        return "✅ Normal"

    @admin.action(description='Zerar apenas CHEIOS (quantidade em estoque)')
    def zerar_apenas_cheios(self, request, queryset):
        n = queryset.update(quantidade_estoque=0)
        self.message_user(
            request,
            f'{n} item(ns): quantidade de cheios zerada. Vazios não foram alterados. Itens mantidos.',
        )

    @admin.action(description='Zerar apenas VAZIOS (vasilhame)')
    def zerar_apenas_vazios(self, request, queryset):
        n = queryset.update(quantidade_vazios=0)
        self.message_user(
            request,
            f'{n} item(ns): quantidade de vazios zerada. Cheios não foram alterados. Itens mantidos.',
        )

    @admin.action(description='Zerar CHEIOS e VAZIOS (estoque completo)')
    def zerar_cheios_e_vazios(self, request, queryset):
        n = queryset.update(quantidade_estoque=0, quantidade_vazios=0)
        self.message_user(
            request,
            f'{n} item(ns): cheios e vazios zerados. Cadastro dos itens mantido.',
        )


@admin.register(GrupoProduto)
class GrupoProdutoAdmin(SaasAdmin):
    list_display = ('nome', 'loja', 'ordem')
    list_filter = ('loja',)
    search_fields = ('nome',)
    ordering = ('loja', 'ordem', 'nome')


@admin.register(ComponenteKit)
class ComponenteKitAdmin(SaasAdmin):
    list_display = ('produto_kit', 'item_estoque', 'quantidade', 'ordem')
    list_filter = ('produto_kit__loja',)
    search_fields = ('produto_kit__nome_venda', 'item_estoque__nome')


@admin.register(Produto)
class ProdutoAdmin(SaasAdmin):
    
    list_display = ('id', 'nome_venda', 'preco_compra', 'preco_venda', 'lucro_unidade', 'eh_kit', 'vende_vasilhame_vazio', 'fornecedor')
    search_fields = ('nome_venda', 'codigo_barras')
    list_filter = ('fornecedor', 'vende_vasilhame_vazio')
    list_editable = ('preco_venda',)
    readonly_fields = ('id',) 
    
    @admin.display(description='Lucro Unit.')
    def lucro_unidade(self, obj):
        return f"R$ {obj.preco_venda - obj.preco_compra:.2f}"


@admin.register(PrecoFornecedorItem)
class PrecoFornecedorItemAdmin(SaasAdmin):
    list_display = ('item_estoque', 'fornecedor', 'preco_compra', 'ativo')
    list_filter = ('ativo',)
    search_fields = ('item_estoque__nome', 'fornecedor__nome')


@admin.register(PagamentoFiado)
class PagamentoFiadoAdmin(SaasAdmin):
    list_display = ('venda', 'valor', 'meio_liquidacao', 'data_pagamento', 'registrado_por')
    list_filter = ('meio_liquidacao', 'data_pagamento')
    search_fields = ('venda__id', 'venda__cliente__nome')


@admin.register(ParcelaFiadoAgendada)
class ParcelaFiadoAgendadaAdmin(SaasAdmin):
    list_display = ('id', 'venda', 'cliente', 'valor', 'data_vencimento', 'status', 'data_entrada')
    list_filter = ('status', 'data_vencimento', 'loja')
    search_fields = ('cliente__nome', 'venda__id')


@admin.register(LiquidacaoVenda)
class LiquidacaoVendaAdmin(SaasAdmin):
    list_display = ('venda', 'valor', 'meio_liquidacao', 'conferencia_ok', 'data_liquidacao', 'registrado_por')
    list_filter = ('meio_liquidacao', 'conferencia_ok', 'data_liquidacao')
    search_fields = ('venda__id', 'venda__cliente__nome')
    readonly_fields = ('data_liquidacao',)


@admin.register(Cliente)
class ClienteAdmin(SaasAdmin):
    list_display = ('id', 'nome', 'whatsapp', 'telefone')
    search_fields = ('nome', 'whatsapp', 'telefone')


# --- VENDAS ---
class ItemVendaInline(admin.TabularInline):
    model = ItemVenda
    extra = 0
    readonly_fields = ('total_item',)
    
    def total_item(self, obj):
        return f"R$ {obj.quantidade * obj.preco_unitario:.2f}"


@admin.register(EntradaEstoque)
class EntradaEstoqueAdmin(SaasAdmin):
    list_display = (
        'id', 'item', 'fornecedor', 'quantidade', 'preco_unitario_compra',
        'eh_consignado', 'valor_total', 'valor_pago', 'status_pagamento', 'data_entrada',
    )
    list_filter = ('data_entrada', 'eh_consignado', 'status_pagamento')
    search_fields = ('item__nome',)


@admin.register(PagamentoMercadoria)
class PagamentoMercadoriaAdmin(SaasAdmin):
    list_display = ('id', 'entrada', 'valor', 'meio_liquidacao', 'data_pagamento', 'caixa', 'loja')
    list_filter = ('meio_liquidacao', 'data_pagamento')
    search_fields = ('entrada__item__nome',)


@admin.register(ParcelaMercadoriaAgendada)
class ParcelaMercadoriaAgendadaAdmin(SaasAdmin):
    list_display = ('id', 'entrada', 'valor', 'data_vencimento', 'status', 'data_entrada', 'loja')
    list_filter = ('status', 'data_vencimento', 'loja')
    search_fields = ('entrada__item__nome', 'entrada__id')


@admin.register(Venda)
class VendaAdmin(SaasAdmin):
    list_display = ('id', 'cliente_nome', 'total', 'status', 'eh_fiado', 'forma_pagamento', 'meio_liquidacao', 'data_venda')
    
    list_filter = ('status', 'eh_fiado', 'forma_pagamento', 'meio_liquidacao', 'data_venda', 'loja')
    search_fields = ('cliente__nome', 'id')
    inlines = [ItemVendaInline]
    date_hierarchy = 'data_venda'
    
    @admin.display(description='Cliente')
    def cliente_nome(self, obj):
        return obj.cliente.nome if obj.cliente else "Consumidor Final"


@admin.register(Caixa)
class CaixaAdmin(SaasAdmin):
    list_display = ('id', 'data', 'saldo_inicial', 'saldo_final', 'status', 'loja')
    list_filter = ('status', 'data')


@admin.register(CategoriaTransacao)
class CategoriaTransacaoAdmin(SaasAdmin):
    list_display = ('id', 'nome', 'tipo_formatado')
    list_filter = ('tipo',)

    @admin.display(description='Tipo')
    def tipo_formatado(self, obj):
        return "🟢 Receita" if obj.tipo == 'RECEITA' else "🔴 Despesa"


@admin.register(Receita)
class ReceitaAdmin(SaasAdmin):
    list_display = ('id', 'descricao', 'valor', 'categoria', 'data', 'loja')
    list_filter = ('data', 'categoria')
    search_fields = ('descricao',)
    date_hierarchy = 'data'
    
    def get_queryset(self, request):
        return super().get_queryset(request).filter(categoria__tipo='RECEITA')
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "categoria":
            kwargs["queryset"] = CategoriaTransacao.objects.filter(tipo='RECEITA')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Despesa)
class DespesaAdmin(SaasAdmin):
    list_display = ('id', 'descricao', 'valor', 'categoria', 'data', 'loja')
    list_filter = ('data', 'categoria')
    search_fields = ('descricao',)
    date_hierarchy = 'data'
    
    def get_queryset(self, request):
        return super().get_queryset(request).filter(categoria__tipo='DESPESA')
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "categoria":
            kwargs["queryset"] = CategoriaTransacao.objects.filter(tipo='DESPESA')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Transacao)
class TransacaoGeralAdmin(SaasAdmin):
    list_display = ('id', 'descricao', 'valor_formatado', 'categoria', 'data')
    list_filter = ('categoria__tipo', 'data')
    
    @admin.display(description='Valor')
    def valor_formatado(self, obj):
        
        cor = "green" if obj.categoria and obj.categoria.tipo == 'RECEITA' else "red"
        return f"R$ {obj.valor}"

@admin.register(Rede)
class RedeAdmin(admin.ModelAdmin):
    list_display = ('nome', 'slug', 'ativa')
    prepopulated_fields = {'slug': ('nome',)}

admin.site.register(Moto, SaasAdmin)
admin.site.register(Motoboy, SaasAdmin)


@admin.register(LogFechamentoEstoqueDiario)
class LogFechamentoEstoqueDiarioAdmin(SaasAdmin):
    list_display = ('data_referencia', 'tipo', 'item_estoque', 'quantidade_cheios', 'quantidade_vazios', 'usuario', 'registrado_em')
    list_filter = ('tipo', 'data_referencia')
    search_fields = ('item_estoque__nome',)
    readonly_fields = ('registrado_em',)


@admin.register(BloqueioIPLogin)
class BloqueioIPLoginAdmin(admin.ModelAdmin):
    list_display = (
        'ip', 'tentativas', 'bloqueado_ate', 'esta_bloqueado_display',
        'ultimo_usuario_tentado', 'ultima_tentativa',
    )
    list_filter = ('bloqueado_ate',)
    search_fields = ('ip', 'ultimo_usuario_tentado')
    readonly_fields = ('ultima_tentativa',)
    actions = ['liberar_ips_selecionados']

    @admin.display(boolean=True, description='Bloqueado agora')
    def esta_bloqueado_display(self, obj):
        return obj.esta_bloqueado

    @admin.action(description='Liberar IP imediatamente (desbloquear login)')
    def liberar_ips_selecionados(self, request, queryset):
        for reg in queryset:
            liberar_ip(reg.ip)
        self.message_user(request, f'{queryset.count()} IP(s) liberado(s).')