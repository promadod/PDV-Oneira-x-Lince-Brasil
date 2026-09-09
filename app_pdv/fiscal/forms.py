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
            'municipio', 'uf', 'codigo_ibge', 'ambiente', 'focus_token', 'focus_empresa_id',
            'serie_nfe', 'serie_nfce', 'serie_nfse',
            'proximo_numero_nfe', 'proximo_numero_nfce', 'proximo_numero_nfse',
            'csc_id', 'csc_token',
            'emite_nfe', 'emite_nfce', 'emite_nfse', 'emite_nfse_nacional',
            'email_envio_xml', 'enviar_whatsapp_danfe',
            'webhook_url_configurada',
        ]
        widgets = {
            'focus_token': forms.PasswordInput(render_value=True, attrs={'class': 'form-control', 'autocomplete': 'off'}),
            'csc_token': forms.PasswordInput(render_value=True, attrs={'class': 'form-control', 'autocomplete': 'off'}),
            'crt': forms.Select(attrs={'class': 'form-control'}),
            'ambiente': forms.Select(attrs={'class': 'form-control'}),
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
            'codigo_servico', 'descricao_servico', 'nbs', 'codigo_class_trib',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'form-control')


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
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'ID da venda (opcional)'}),
    )


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
