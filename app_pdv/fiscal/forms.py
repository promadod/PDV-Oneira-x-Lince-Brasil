from decimal import Decimal

from django import forms

from .models import (
    FiscalConfig,
    InutilizacaoNumeracao,
    NFeRecebida,
    ProdutoDadosFiscais,
    RegraTributaria,
)


class FiscalConfigForm(forms.ModelForm):
    class Meta:
        model = FiscalConfig
        fields = [
            'razao_social', 'nome_fantasia', 'cnpj', 'inscricao_estadual', 'inscricao_municipal',
            'cnae', 'crt', 'logradouro', 'numero', 'complemento', 'bairro', 'cep',
            'municipio', 'uf', 'codigo_ibge',
            'serie_nfe', 'serie_nfce', 'serie_nfse',
            'proximo_numero_nfe', 'proximo_numero_nfce', 'proximo_numero_nfse',
            'csc_id', 'csc_token',
            'emite_nfe', 'emite_nfce', 'emite_nfse', 'emite_nfse_nacional',
            'email_envio_xml', 'enviar_whatsapp_danfe',
        ]
        widgets = {
            'csc_token': forms.PasswordInput(render_value=True, attrs={'class': 'form-control', 'autocomplete': 'off'}),
            'crt': forms.Select(attrs={'class': 'form-control'}),
            'uf': forms.TextInput(attrs={'class': 'form-control', 'maxlength': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if name in ('emite_nfe', 'emite_nfce', 'emite_nfse', 'emite_nfse_nacional', 'enviar_whatsapp_danfe'):
                field.widget.attrs.setdefault('class', 'form-check-input')
            else:
                field.widget.attrs.setdefault('class', 'form-control')


class RegraTributariaForm(forms.ModelForm):
    class Meta:
        model = RegraTributaria
        fields = [
            'nome', 'ativa', 'ncm', 'uf_destino', 'operacao', 'cfop', 'csosn', 'cst_icms',
            'cst_pis', 'cst_cofins', 'aliquota_icms', 'aliquota_pis', 'aliquota_cofins',
            'aliquota_iss', 'aliquota_ibs', 'aliquota_cbs', 'observacao',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if name == 'ativa':
                field.widget.attrs.setdefault('class', 'form-check-input')
            else:
                field.widget.attrs.setdefault('class', 'form-control')


class ProdutoDadosFiscaisForm(forms.ModelForm):
    class Meta:
        model = ProdutoDadosFiscais
        fields = [
            'tipo', 'ncm', 'cest', 'origem', 'unidade_tributavel',
            'cfop_venda', 'cfop_interestadual', 'codigo_beneficio_fiscal',
            'csosn', 'cst_icms', 'cst_pis', 'cst_cofins',
            'aliquota_icms', 'aliquota_pis', 'aliquota_cofins',
            'cst_ibs_cbs', 'codigo_class_trib', 'nbs',
            'codigo_servico', 'descricao_servico',
            'codigo_anp', 'descricao_anp', 'icms_aliquota_ad_rem',
            'pct_glp', 'pct_gn_nacional', 'pct_gn_importado',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'form-control')


class EmitirAvulsaForm(forms.Form):
    produto_id = forms.ChoiceField(label='Produto', choices=[])
    quantidade = forms.DecimalField(
        min_value=Decimal('0.001'),
        initial=Decimal('1'),
        decimal_places=3,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.001'}),
    )
    preco_unitario = forms.DecimalField(
        min_value=Decimal('0.01'),
        decimal_places=2,
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        label='Preço unitário (R$)',
        help_text='Se vazio, usa o preço de venda do produto.',
    )
    forma_pagamento = forms.ChoiceField(
        choices=[
            ('01', '01 — Dinheiro'),
            ('17', '17 — PIX'),
            ('03', '03 — Cartão crédito'),
            ('04', '04 — Cartão débito'),
            ('99', '99 — Outros'),
        ],
        initial='99',
        widget=forms.Select(attrs={'class': 'form-control'}),
    )
    operacao_interestadual = forms.BooleanField(
        required=False,
        label='Operação interestadual (CFOP interestadual do produto)',
    )

    def __init__(self, *args, loja=None, **kwargs):
        super().__init__(*args, **kwargs)
        from app_pdv.models import Produto
        qs = Produto.objects.filter(loja=loja, ativo=True).order_by('nome_venda') if loja else Produto.objects.none()
        self.fields['produto_id'].widget = forms.Select(
            choices=[('', '— Selecione —')] + [(p.id, f'{p.nome_venda} (#{p.id})') for p in qs],
            attrs={'class': 'form-control'},
        )


class ContingenciaForm(forms.ModelForm):
    class Meta:
        model = FiscalConfig
        fields = ['contingencia_ativa', 'contingencia_tipo', 'contingencia_motivo']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['contingencia_ativa'].widget.attrs.setdefault('class', 'form-check-input')
        self.fields['contingencia_tipo'].widget.attrs.setdefault('class', 'form-control')
        self.fields['contingencia_motivo'].widget.attrs.setdefault('class', 'form-control')


class InutilizacaoForm(forms.ModelForm):
    class Meta:
        model = InutilizacaoNumeracao
        fields = ['modelo', 'serie', 'numero_inicial', 'numero_final', 'justificativa']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'form-control')


class ManifestacaoForm(forms.Form):
    manifestacao = forms.ChoiceField(
        choices=[
            ('ciencia', 'Ciência da operação'),
            ('confirmacao', 'Confirmação da operação'),
            ('desconhecimento', 'Desconhecimento'),
            ('nao_realizada', 'Operação não realizada'),
        ],
        widget=forms.Select(attrs={'class': 'form-control'}),
    )


class FocusIntegracaoForm(forms.ModelForm):
    """Credenciais e ambiente da API Focus NFe (Basic Auth — token como usuário, senha vazia)."""

    class Meta:
        model = FiscalConfig
        fields = ['ambiente', 'focus_token', 'focus_empresa_id', 'webhook_url_configurada']
        widgets = {
            'focus_token': forms.PasswordInput(render_value=True, attrs={'class': 'form-control', 'autocomplete': 'off'}),
            'ambiente': forms.Select(attrs={'class': 'form-control'}),
            'focus_empresa_id': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Opcional — painel Focus / API empresas'}),
            'webhook_url_configurada': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://seu-dominio/api/fiscal/webhooks/focus/'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['ambiente'].help_text = 'Homologação para testes; produção gera documentos com validade fiscal.'
        self.fields['focus_token'].help_text = 'Token alfanumérico da empresa na Focus (HTTP Basic, senha em branco).'
        self.fields['focus_token'].required = False

    def clean_focus_token(self):
        token = (self.cleaned_data.get('focus_token') or '').strip()
        if token:
            return token
        if self.instance.pk and (self.instance.focus_token or '').strip():
            return self.instance.focus_token
        raise forms.ValidationError('Informe o token Focus NFe.')


class EmitirLoteForm(forms.Form):
    tipo = forms.ChoiceField(
        choices=[
            ('nfce', 'NFC-e (65) — cupom consumidor'),
            ('nfe', 'NF-e (55)'),
        ],
        initial='nfce',
        widget=forms.Select(attrs={'class': 'form-control'}),
    )
    data_de = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        label='Vendas de',
    )
    data_ate = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        label='Vendas até',
    )
    venda_ids_texto = forms.CharField(
        required=False,
        label='IDs das vendas (opcional)',
        help_text='Separados por vírgula ou espaço. Se informado, ignora o filtro por data.',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Ex.: 1201, 1202, 1203',
        }),
    )
    pular_ja_emitidas = forms.BooleanField(
        required=False,
        initial=True,
        label='Pular vendas que já possuem documento autorizado ou em processamento',
    )

    def clean(self):
        cleaned = super().clean()
        texto = (cleaned.get('venda_ids_texto') or '').strip()
        ids = []
        if texto:
            import re
            for part in re.split(r'[,\s;]+', texto):
                part = part.strip().lstrip('#')
                if part.isdigit():
                    ids.append(int(part))
            if not ids:
                raise forms.ValidationError('Informe IDs numéricos válidos ou use o filtro por data.')
            cleaned['venda_ids_parsed'] = ids
        else:
            if not cleaned.get('data_de') or not cleaned.get('data_ate'):
                raise forms.ValidationError('Informe o período (de/até) ou a lista de IDs das vendas.')
            if cleaned['data_de'] > cleaned['data_ate']:
                raise forms.ValidationError('A data inicial não pode ser posterior à data final.')
            cleaned['venda_ids_parsed'] = None
        return cleaned


class EmitirDocumentoForm(forms.Form):
    tipo = forms.ChoiceField(
        choices=[
            ('nfce', 'NFC-e (65) — cupom consumidor'),
            ('nfe', 'NF-e (55)'),
            ('nfse', 'NFS-e'),
            ('nfse_nacional', 'NFS-e Nacional'),
        ],
        widget=forms.Select(attrs={'class': 'form-control'}),
    )
    venda_id = forms.IntegerField(
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'ID da venda (obrigatório para NFC-e/NF-e)'}),
    )

    def clean(self):
        cleaned = super().clean()
        tipo = cleaned.get('tipo')
        venda_id = cleaned.get('venda_id')
        if tipo in ('nfce', 'nfe') and not venda_id:
            raise forms.ValidationError('Informe o ID da venda para emitir NFC-e ou NF-e com payload Focus completo.')
        return cleaned


class CartaCorrecaoForm(forms.Form):
    correcao = forms.CharField(
        min_length=15, max_length=1000,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
        label='Texto da carta de correção',
    )


class CancelarDocumentoForm(forms.Form):
    justificativa = forms.CharField(
        min_length=15, max_length=255,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
    )
