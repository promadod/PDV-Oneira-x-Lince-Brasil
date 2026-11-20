from django import forms
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path, reverse
from .models import (
    Loja, PerfilUsuario, Fornecedor, ItemEstoque, Produto, Cliente, GrupoProduto, ComponenteKit,
    Venda, ItemVenda, Caixa, EntradaEstoque, PrecoFornecedorItem, PagamentoFiado, LiquidacaoVenda,
    PagamentoMercadoria, ParcelaFiadoAgendada, ParcelaMercadoriaAgendada, BloqueioIPLogin,
    CategoriaTransacao, Transacao, Receita, Despesa, Moto, Motoboy, Rede,
    FormaPagamentoLoja, LogFechamentoEstoqueDiario
)
from .fiscal.models import (
    FiscalConfig, DocumentoFiscal, RegraTributaria, FiscalWebhookLog, NFeRecebida,
    LoteEmissaoFiscal, LoteEmissaoFiscalItem, ProdutoDadosFiscais,
)
from .loja_piloto import (
    importar_produtos_da_piloto,
    opcoes_loja_piloto,
    produtos_da_piloto,
    resolver_loja_piloto_id,
)
from .seguranca import descongelar_conta, liberar_ip

admin.site.site_header = "Lince brasil sistemas - Administração"
admin.site.site_title = "Lince brasil sistemas"
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
                'perm_estoque', 'perm_relatorios', 'perm_usuarios', 'perm_fiscal',
                'perm_fiscal_config', 'perm_fiscal_telas', 'usuario_padrao_loja',
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

class LojaAdminForm(forms.ModelForm):
    importar_de_piloto = forms.ChoiceField(
        required=False,
        label='Importar produtos / parâmetros fiscais de',
        help_text=(
            'Opcional. Ao salvar uma loja nova, abre a tela para escolher quais produtos '
            'copiar da loja piloto (com CFOP, NCM etc. se existirem). CNPJ e certificado '
            'não são importados. Deixe em branco para cadastro normal.'
        ),
    )

    class Meta:
        model = Loja
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['importar_de_piloto'].choices = opcoes_loja_piloto()
        if self.instance and self.instance.pk:
            self.fields['importar_de_piloto'].widget = forms.HiddenInput()
            self.fields['importar_de_piloto'].required = False


@admin.register(Loja)
class LojaAdmin(admin.ModelAdmin):
    form = LojaAdminForm
    list_display = (
        'id', 'nome', 'segmento', 'loja_piloto', 'gerente', 'ativo', 'fiscal_habilitado',
        'usa_fiado', 'permite_pagamento_dividido', 'controla_vasilhame_vazio', 'estoque_diario',
        'gerencia_pagamento_mercadorias', 'conferencia_dinheiro_habilitada', 'monitorar_entrega',
        'trabalha_com_entregas', 'trabalha_com_leitor_codigo_barras', 'trabalha_com_balanca_granel',
        'impressao_automatica', 'data_criacao',
    )
    list_filter = (
        'ativo', 'segmento', 'loja_piloto', 'fiscal_habilitado', 'monitorar_entrega',
        'trabalha_com_entregas', 'trabalha_com_leitor_codigo_barras', 'trabalha_com_balanca_granel',
        'impressao_automatica', 'usa_fiado', 'permite_pagamento_dividido', 'controla_vasilhame_vazio',
        'estoque_diario', 'gerencia_pagamento_mercadorias', 'conferencia_dinheiro_habilitada',
    )
    fieldsets = (
        (None, {
            'fields': (
                'nome', 'cnpj', 'gerente', 'rede', 'nome_unidade', 'ativo', 'loja_aberta',
                'segmento', 'loja_piloto', 'importar_de_piloto',
                'fiscal_habilitado', 'assistente_habilitado',
            ),
            'description': (
                'Segmento + loja piloto: ao criar, você pode importar produtos e parâmetros '
                'fiscais de uma loja piloto do mesmo segmento. Cadastro fiscal (CNPJ/certificado) '
                'permanece manual.'
            ),
        }),
        ('Entregas', {
            'fields': ('taxa_entrega_app', 'taxa_entrega_pdv', 'trabalha_com_entregas', 'monitorar_entrega', 'usa_moveon')
        }),
        ('PDV', {
            'fields': (
                'nome_marca_pdv', 'impressao_automatica',
                'conferencia_dinheiro_habilitada',
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

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                'importar-produtos-piloto/',
                self.admin_site.admin_view(self.importar_produtos_piloto_view),
                name='app_pdv_loja_importar_produtos_piloto',
            ),
        ]
        return custom + urls

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        if obj is not None:
            # Select de importação só no cadastro de loja nova.
            ajustados = []
            for name, opts in fieldsets:
                fields = tuple(f for f in opts.get('fields', ()) if f != 'importar_de_piloto')
                ajustados.append((name, {**opts, 'fields': fields}))
            return ajustados
        return fieldsets

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if change:
            return
        from .loja_usuario import SENHA_PADRAO_NOVA_LOJA
        user = getattr(obj, '_usuario_padrao', None)
        if user:
            self.message_user(
                request,
                f'Usuário "{user.username}" criado para esta loja '
                f'(senha padrão: {SENHA_PADRAO_NOVA_LOJA}). Oriente a troca no primeiro acesso.',
            )
        piloto_id = resolver_loja_piloto_id(
            segmento=getattr(obj, 'segmento', '') or '',
            loja_piloto_id=form.cleaned_data.get('importar_de_piloto') if form else None,
        )
        obj._piloto_import_id = piloto_id

    def response_add(self, request, obj, post_url_continue=None):
        piloto_id = getattr(obj, '_piloto_import_id', None)
        if piloto_id and request.user.is_superuser:
            url = reverse('admin:app_pdv_loja_importar_produtos_piloto')
            return redirect(f'{url}?loja={obj.pk}&piloto={piloto_id}')
        return super().response_add(request, obj, post_url_continue=post_url_continue)

    def importar_produtos_piloto_view(self, request):
        if not request.user.is_superuser:
            messages.error(request, 'Apenas superusuários podem importar produtos da loja piloto.')
            return redirect('admin:app_pdv_loja_changelist')

        loja = get_object_or_404(Loja, pk=request.GET.get('loja') or request.POST.get('loja'))
        piloto = get_object_or_404(Loja, pk=request.GET.get('piloto') or request.POST.get('piloto'))
        if loja.pk == piloto.pk:
            messages.error(request, 'Loja destino e piloto não podem ser a mesma.')
            return redirect('admin:app_pdv_loja_change', loja.pk)

        produtos = list(produtos_da_piloto(piloto))
        fiscais_ids = set(
            ProdutoDadosFiscais.objects.filter(produto_id__in=[p.pk for p in produtos])
            .exclude(ncm='')
            .values_list('produto_id', flat=True)
        )

        if request.method == 'POST':
            selecionados = request.POST.getlist('produto_ids')
            resultado = importar_produtos_da_piloto(loja, piloto, selecionados)
            for aviso in resultado.avisos:
                messages.warning(request, aviso)
            if resultado.produtos_criados:
                messages.success(
                    request,
                    (
                        f'{resultado.produtos_criados} produto(s) importado(s) de "{piloto.nome}" '
                        f'para "{loja.nome}". '
                        f'{resultado.fiscais_copiados} com parâmetros fiscais, '
                        f'{resultado.itens_estoque_criados} item(ns) de estoque (zerados).'
                    ),
                )
            else:
                messages.info(request, 'Nenhum produto foi importado.')
            return redirect('admin:app_pdv_loja_change', loja.pk)

        context = {
            **self.admin_site.each_context(request),
            'title': f'Importar produtos da loja piloto — {piloto.nome}',
            'loja': loja,
            'piloto': piloto,
            'produtos': produtos,
            'fiscais_ids': fiscais_ids,
            'opts': self.model._meta,
            'has_view_permission': True,
        }
        return render(request, 'admin/app_pdv/loja/importar_produtos_piloto.html', context)


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
@admin.register(FiscalConfig)
class FiscalConfigAdmin(SaasAdmin):
    list_display = ('loja', 'cnpj', 'ambiente', 'emite_nfce', 'emite_nfe', 'contingencia_ativa')
    list_filter = ('ambiente', 'contingencia_ativa')


@admin.register(DocumentoFiscal)
class DocumentoFiscalAdmin(SaasAdmin):
    list_display = ('ref', 'tipo', 'status', 'numero', 'valor_total', 'loja', 'criado_em')
    list_filter = ('tipo', 'status')
    search_fields = ('ref', 'chave_acesso', 'numero')


@admin.register(RegraTributaria)
class RegraTributariaAdmin(SaasAdmin):
    list_display = ('nome', 'cfop', 'csosn', 'ncm', 'ativa', 'loja')


@admin.register(FiscalWebhookLog)
class FiscalWebhookLogAdmin(SaasAdmin):
    list_display = ('criado_em', 'evento', 'ref', 'status_recebido', 'processado', 'loja')
    readonly_fields = ('criado_em',)


@admin.register(NFeRecebida)
class NFeRecebidaAdmin(SaasAdmin):
    list_display = ('chave_acesso', 'nome_emitente', 'valor_total', 'situacao', 'manifestacao', 'loja')


@admin.register(LoteEmissaoFiscal)
class LoteEmissaoFiscalAdmin(SaasAdmin):
    list_display = (
        'id', 'loja', 'tipo', 'status', 'total_autorizado', 'total_erro', 'total_solicitado', 'criado_em',
    )
    list_filter = ('tipo', 'status')
    readonly_fields = ('criado_em', 'finalizado_em')


@admin.register(LoteEmissaoFiscalItem)
class LoteEmissaoFiscalItemAdmin(SaasAdmin):
    list_display = ('lote', 'venda', 'status', 'documento', 'criado_em')
    list_filter = ('status',)
