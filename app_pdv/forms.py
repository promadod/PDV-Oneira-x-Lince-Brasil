from django import forms
from decimal import Decimal
from .models import Produto, Cliente, Fornecedor, EntradaEstoque, Loja, ItemEstoque, CategoriaTransacao, Transacao, Motoboy, Moto, PerfilUsuario, GrupoProduto, ComponenteKit
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm

class ItemEstoqueForm(forms.ModelForm):
    class Meta:
        model = ItemEstoque
        fields = ['nome','unidade_medida','data_validade', 'observacao']
        widgets = {
            'nome': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: Ração Golden (Granel)'}),
            'unidade_medida': forms.Select(attrs={'class': 'form-control'}),
            'data_validade': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'observacao': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: Lote A123 / Fornecedor XPTO'}),
        }

# --- O ÚNICO QUE FOI ALTERADO (Adicionado o campo IMAGEM) ---
class ProdutoForm(forms.ModelForm):
    class Meta:
        model = Produto
        fields = [
            'eh_kit', 'item_estoque', 'nome_venda', 'imagem', 'quantidade_baixa',
            'preco_compra', 'preco_venda', 'fornecedor', 'grupo',
            'rastrear_recompra', 'vende_vasilhame_vazio',
            'usa_venda_completa', 'preco_venda_completo',
            'dias_recompra', 'mensagem_recompra', 'codigo_barras',
        ]
        
        labels = {
            'eh_kit': 'Produto kit / promoção?',
            'item_estoque': 'Item do Estoque (Pai)', 
            'nome_venda': 'Nome de Venda (Ex: Pack c/ 12)',
            'codigo_barras': 'Código de barras (leitor USB)',
            'imagem': 'Foto do Produto (Aparece no App)', 
            'quantidade_baixa': 'Qtd Itens neste Produto (Ex: 12)',
            'preco_compra': 'Custo Médio (atualizado pelas entradas de estoque)',
            'preco_venda': 'Preço de Venda (Deste pacote)',
            'fornecedor': 'Fornecedor',
            'grupo': 'Grupo do produto',
            'vende_vasilhame_vazio': 'Vende vasilhame vazio',
        }
        
        widgets = {
            'eh_kit': forms.CheckboxInput(attrs={'class': 'form-check-input', 'id': 'id_eh_kit'}),
            'item_estoque': forms.Select(attrs={'class': 'form-control select-search'}),
            'nome_venda': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: Coca Cola Fardo'}),
            'codigo_barras': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ex: 7891234567890',
                'autocomplete': 'off',
            }),
            'imagem': forms.FileInput(attrs={'class': 'form-control'}), 
            'quantidade_baixa': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.001', 'placeholder': '1 para avulso...'}),
            'preco_compra': forms.NumberInput(attrs={
                'class': 'form-control', 'step': '0.01',
                'title': 'Recalculado automaticamente ao abastecer estoque'
            }),
            'preco_venda': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'preco_venda_completo': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'fornecedor': forms.Select(attrs={'class': 'form-control select-search'}),
            'grupo': forms.Select(attrs={'class': 'form-control select-search'}),
            'vende_vasilhame_vazio': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'usa_venda_completa': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'rastrear_recompra': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        loja = kwargs.pop('loja', None)
        self.loja = loja
        super(ProdutoForm, self).__init__(*args, **kwargs)

        if not loja or not loja.trabalha_com_leitor_codigo_barras:
            self.fields.pop('codigo_barras', None)
        if not loja or not loja.permite_venda_completa:
            self.fields.pop('usa_venda_completa', None)
            self.fields.pop('preco_venda_completo', None)
        if not loja or not loja.controla_vasilhame_vazio:
            self.fields.pop('vende_vasilhame_vazio', None)
        if not loja or not loja.divide_produtos_por_grupos:
            self.fields.pop('grupo', None)

        if loja:
            if 'item_estoque' in self.fields:
                self.fields['item_estoque'].queryset = self.fields['item_estoque'].queryset.filter(loja=loja).order_by('nome')
                self.fields['item_estoque'].required = False
                self.fields['item_estoque'].empty_label = '— Selecione o item de estoque —'
            if 'fornecedor' in self.fields:
                self.fields['fornecedor'].queryset = self.fields['fornecedor'].queryset.filter(loja=loja).order_by('nome')
                self.fields['fornecedor'].required = False
            if 'grupo' in self.fields:
                self.fields['grupo'].queryset = GrupoProduto.objects.filter(loja=loja).order_by('ordem', 'nome')
                self.fields['grupo'].required = False
                self.fields['grupo'].empty_label = 'Sem grupo'
        for nome in ('preco_compra', 'preco_venda', 'preco_venda_completo', 'quantidade_baixa'):
            if nome in self.fields:
                self.fields[nome].required = False if nome == 'preco_venda_completo' else self.fields[nome].required

    def clean_codigo_barras(self):
        codigo = (self.cleaned_data.get('codigo_barras') or '').strip()
        if not codigo:
            return ''
        if self.loja:
            qs = Produto.objects.filter(loja=self.loja, codigo_barras=codigo)
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError('Já existe outro produto nesta loja com este código de barras.')
        return codigo

    def clean_grupo(self):
        grupo = self.cleaned_data.get('grupo')
        if grupo and self.loja and grupo.loja_id != self.loja.id:
            raise forms.ValidationError('Grupo inválido para esta loja.')
        return grupo

    def clean(self):
        cleaned = super().clean()
        eh_kit = cleaned.get('eh_kit')
        if eh_kit:
            cleaned['item_estoque'] = None
            cleaned['quantidade_baixa'] = Decimal('1')
            if 'vende_vasilhame_vazio' in self.fields:
                cleaned['vende_vasilhame_vazio'] = False
            if 'usa_venda_completa' in self.fields:
                cleaned['usa_venda_completa'] = False
            if 'preco_venda_completo' in self.fields:
                cleaned['preco_venda_completo'] = None
        elif not cleaned.get('item_estoque'):
            self.add_error('item_estoque', 'Obrigatório para produtos que não são kit. Selecione um item de estoque.')
        if cleaned.get('vende_vasilhame_vazio') and self.loja and not self.loja.controla_vasilhame_vazio:
            raise forms.ValidationError(
                'Venda de vasilhame vazio só está disponível para lojas com controle de vasilhame ativo.'
            )
        # Defaults numéricos quando vazios
        if cleaned.get('quantidade_baixa') in (None, ''):
            cleaned['quantidade_baixa'] = Decimal('1')
        if cleaned.get('preco_compra') in (None, ''):
            cleaned['preco_compra'] = Decimal('0')
        if cleaned.get('preco_venda') in (None, ''):
            cleaned['preco_venda'] = Decimal('0')
        return cleaned

# --- TODO O RESTO ABAIXO ESTÁ INTACTO CONFORME SEU CÓDIGO ---

class ClienteForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = ['nome', 'whatsapp', 'endereco', 'bairro']
        widgets = {
            'nome': forms.TextInput(attrs={'class': 'form-control'}),
            'whatsapp': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '(00) 00000-0000',
            }),
            'endereco': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'bairro': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: Botânico'}),
        }
        labels = {
            'whatsapp': 'WhatsApp',
        }

    def save(self, commit=True):
        obj = super().save(commit=False)
        # Mantém telefone legado sincronizado com o WhatsApp (campo único na prática).
        zap = (obj.whatsapp or '').strip()
        obj.whatsapp = zap or None
        obj.telefone = zap or None
        if commit:
            obj.save()
        return obj

class ConfigFidelidadeForm(forms.ModelForm):
    class Meta:
        model = Loja
        fields = [
            'fidelidade_ativa', 'fidelidade_tipo_meta', 'fidelidade_meta', 'fidelidade_desconto_pct',
        ]
        widgets = {
            'fidelidade_ativa': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'fidelidade_tipo_meta': forms.Select(attrs={'class': 'form-control'}),
            'fidelidade_meta': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'fidelidade_desconto_pct': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }

class ConfigWhatsAppForm(forms.ModelForm):
    class Meta:
        model = Loja
        fields = [
            'whatsapp_notificar_pedido', 'whatsapp_numero_empresa',
            'whatsapp_msg_novo_pedido', 'whatsapp_msg_saiu_entrega', 'whatsapp_msg_entrega_concluida',
            'msg_campanha_ativos', 'msg_campanha_inativos', 'campanha_desconto_pct',
        ]
        widgets = {
            'whatsapp_notificar_pedido': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'whatsapp_numero_empresa': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '21999999999'}),
            'whatsapp_msg_novo_pedido': forms.Textarea(attrs={'class': 'form-control', 'rows': 5}),
            'whatsapp_msg_saiu_entrega': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'whatsapp_msg_entrega_concluida': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'msg_campanha_ativos': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'msg_campanha_inativos': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'campanha_desconto_pct': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }

class FornecedorForm(forms.ModelForm):
    class Meta:
        model = Fornecedor
        fields = ['nome', 'contato']
        widgets = {
            'nome': forms.TextInput(attrs={'class': 'form-control'}),
            'contato': forms.TextInput(attrs={'class': 'form-control'}),
        }

class LojaForm(forms.ModelForm):
    class Meta:
        model = Loja
        fields = ['nome', 'gerente','usa_moveon']
        widgets = {
            'nome': forms.TextInput(attrs={'class': 'form-control'}),
            'gerente': forms.Select(attrs={'class': 'form-control'}),
            'usa_moveon': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

class EntradaEstoqueForm(forms.ModelForm):
    class Meta:
        model = EntradaEstoque
        fields = [
            'item', 'fornecedor', 'quantidade', 'preco_unitario_compra',
            'eh_consignado', 'observacao',
        ]
        labels = {
            'item': 'Item do Estoque',
            'fornecedor': 'Fornecedor',
            'quantidade': 'Quantidade',
            'preco_unitario_compra': 'Preço unitário de compra',
            'eh_consignado': 'Compra consignada (pagar depois)',
            'observacao': 'Observação (NF, lote, etc.)',
        }
        widgets = {
            'item': forms.Select(attrs={'class': 'form-control select-search', 'id': 'id_item_estoque'}),
            'fornecedor': forms.Select(attrs={'class': 'form-control select-search', 'id': 'id_fornecedor'}),
            'quantidade': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.001'}),
            'preco_unitario_compra': forms.NumberInput(attrs={
                'class': 'form-control', 'step': '0.01', 'id': 'id_preco_unitario'
            }),
            'eh_consignado': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
                'id': 'id_eh_consignado',
            }),
            'observacao': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Opcional (ex: NF de compra)'}),
        }

    def __init__(self, *args, **kwargs):
        loja = kwargs.pop('loja', None)
        super(EntradaEstoqueForm, self).__init__(*args, **kwargs)
        if loja:
            if 'item' in self.fields:
                self.fields['item'].queryset = self.fields['item'].queryset.filter(loja=loja).order_by('nome')
            if 'fornecedor' in self.fields:
                self.fields['fornecedor'].queryset = self.fields['fornecedor'].queryset.filter(loja=loja).order_by('nome')
                self.fields['fornecedor'].required = False
        self.fields['preco_unitario_compra'].required = False
        if not (loja and getattr(loja, 'gerencia_pagamento_mercadorias', False)):
            self.fields.pop('eh_consignado', None)

class CategoriaTransacaoForm(forms.ModelForm):
    class Meta:
        model = CategoriaTransacao
        fields = ['nome', 'tipo']
        widgets = {
            'nome': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: Conta de Luz'}),
            'tipo': forms.Select(attrs={'class': 'form-control'}),
        }

class TransacaoForm(forms.ModelForm):
    class Meta:
        model = Transacao
        fields = ['data', 'forma_pagamento','categoria', 'valor', 'descricao']
        widgets = {
            'data': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'forma_pagamento': forms.Select(attrs={'class': 'form-control'}),
            'categoria': forms.Select(attrs={'class': 'form-control select-search'}),
            'valor': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'descricao': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Detalhes (Opcional)'}),
        }

    def __init__(self, *args, **kwargs):
        loja = kwargs.pop('loja', None)
        super(TransacaoForm, self).__init__(*args, **kwargs)
        if loja and 'categoria' in self.fields:
            self.fields['categoria'].queryset = self.fields['categoria'].queryset.filter(loja=loja).order_by('nome')
        if loja and 'forma_pagamento' in self.fields:
            from .models import FormaPagamentoLoja, criar_formas_pagamento_padrao
            if not FormaPagamentoLoja.objects.filter(loja=loja).exists():
                criar_formas_pagamento_padrao(loja)
            formas = FormaPagamentoLoja.objects.filter(loja=loja, ativo=True).order_by('ordem', 'nome')
            self.fields['forma_pagamento'].widget = forms.Select(
                choices=[(f.codigo, f.nome) for f in formas],
                attrs={'class': 'form-control'}
            )


class ImportacaoForm(forms.Form):
    arquivo_excel = forms.FileField(label="Selecione o arquivo Excel (.xlsx)", widget=forms.FileInput(attrs={'class': 'form-control', 'accept': '.xlsx'}))

class CadastroVendedorForm(UserCreationForm):
    first_name = forms.CharField(label="Nome", max_length=30, required=True, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: Ana'}))
    last_name = forms.CharField(label="Sobrenome", max_length=30, required=True, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: Souza'}))
    username = forms.CharField(label="Usuário (Login)", max_length=30, required=True, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: anasouza'}))
    email = forms.EmailField(label="E-mail (Opcional)", required=False, widget=forms.EmailInput(attrs={'class': 'form-control'}))

    # --- NOVO CAMPO: SELEÇÃO DE FILIAL ---
    loja = forms.ModelChoiceField(
        queryset=Loja.objects.none(), # Começa vazio e a view preenche por segurança
        label="Vincular a qual Filial/Loja?",
        required=True,
        widget=forms.Select(attrs={'class': 'form-control select-search'})
    )

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email']

    # --- MÁGICA: Recebe a lista de lojas autorizadas da View ---
    def __init__(self, *args, **kwargs):
        lojas_permitidas = kwargs.pop('lojas_permitidas', None)
        super(CadastroVendedorForm, self).__init__(*args, **kwargs)
        if lojas_permitidas is not None:
            self.fields['loja'].queryset = lojas_permitidas

class EditarVendedorForm(forms.ModelForm):
    senha = forms.CharField(
        label="Nova Senha", 
        required=False, 
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Preencha APENAS se quiser mudar a senha'})
    )
    first_name = forms.CharField(label="Nome", max_length=30, required=True, widget=forms.TextInput(attrs={'class': 'form-control'}))
    last_name = forms.CharField(label="Sobrenome", max_length=30, required=True, widget=forms.TextInput(attrs={'class': 'form-control'}))
    username = forms.CharField(label="Usuário (Login)", max_length=30, required=True, widget=forms.TextInput(attrs={'class': 'form-control'}))
    email = forms.EmailField(label="E-mail (Opcional)", required=False, widget=forms.EmailInput(attrs={'class': 'form-control'}))

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'username', 'email']

class MotoboyForm(forms.ModelForm):
    username = forms.CharField(label="Usuário (Login no App)", max_length=30, required=True, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: joao.entregas'}))
    senha = forms.CharField(label="Senha do App", required=False, widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Preencha APENAS se quiser mudar a senha'}))
    
    ativo = forms.TypedChoiceField(
        label="Status do Entregador",
        choices=[('True', 'Ativo (Liberado para trabalhar)'), ('False', 'Inativo (Bloqueado)')],
        coerce=lambda x: x == 'True', 
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    class Meta:
        model = Motoboy
        fields = ['nome', 'cpf', 'telefone', 'ativo']
        widgets = {
            'nome': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nome completo'}),
            'cpf': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '000.000.000-00'}),
            'telefone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '(XX) 9XXXX-XXXX'}),
        }

class MotoForm(forms.ModelForm):
    class Meta:
        model = Moto
        fields = ['modelo', 'placa', 'cor']
        widgets = {
            'modelo': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: Fan 160'}),
            'placa': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'ABC-1234'}),
            'cor': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: Vermelha'}),
        }

class PermissoesUsuarioForm(forms.ModelForm):
    class Meta:
        model = PerfilUsuario
        fields = ['perm_dashboard','perm_pdv', 'perm_caixa', 'perm_torre', 'perm_estoque', 'perm_relatorios', 'perm_usuarios']
        widgets = {
            'perm_dashboard': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'perm_pdv': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'perm_caixa': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'perm_torre': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'perm_estoque': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'perm_relatorios': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'perm_usuarios': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }