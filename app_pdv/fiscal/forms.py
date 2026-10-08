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
            'email_envio_xml', 'email_contabilidade', 'whatsapp_contabilidade',
            'enviar_whatsapp_danfe',
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


FORMA_PAGAMENTO_FISCAL = [
    ('01', '01 — Dinheiro'),
    ('17', '17 — PIX'),
    ('03', '03 — Cartão crédito'),
    ('04', '04 — Cartão débito'),
    ('99', '99 — Outros'),
]


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
        choices=FORMA_PAGAMENTO_FISCAL,
        initial='99',
        widget=forms.Select(attrs={'class': 'form-control'}),
    )
    operacao_interestadual = forms.BooleanField(
        required=False,
        label='Operação interestadual (CFOP interestadual do produto)',
    )
    valor_desconto = forms.DecimalField(
        min_value=Decimal('0'),
        initial=Decimal('0'),
        decimal_places=2,
        required=False,
        label='Desconto (R$)',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
    )
    valor_acrescimo = forms.DecimalField(
        min_value=Decimal('0'),
        initial=Decimal('0'),
        decimal_places=2,
        required=False,
        label='Acréscimo (R$)',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
    )
    cpf_destinatario = forms.CharField(
        required=False,
        label='CPF do consumidor',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Opcional'}),
    )
    cnpj_destinatario = forms.CharField(
        required=False,
        label='CNPJ do consumidor',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Opcional'}),
    )
    nome_destinatario = forms.CharField(
        required=False,
        label='Nome / razão social na nota',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Substitui "Consumidor não identificado"'}),
    )

    def clean(self):
        cleaned = super().clean()
        cpf = ''.join(c for c in (cleaned.get('cpf_destinatario') or '') if c.isdigit())
        cnpj = ''.join(c for c in (cleaned.get('cnpj_destinatario') or '') if c.isdigit())
        if cpf and cnpj:
            raise forms.ValidationError('Informe apenas CPF ou CNPJ do destinatário, não ambos.')
        if cpf and len(cpf) != 11:
            raise forms.ValidationError('CPF inválido.')
        if cnpj and len(cnpj) != 14:
            raise forms.ValidationError('CNPJ inválido.')
        return cleaned

    def __init__(self, *args, loja=None, **kwargs):
        super().__init__(*args, **kwargs)
        from app_pdv.models import Produto
        qs = Produto.objects.filter(loja=loja, ativo=True).order_by('nome_venda') if loja else Produto.objects.none()
        produto_choices = [('', '— Selecione —')] + [
            (str(p.id), f'{p.nome_venda} (#{p.id})') for p in qs
        ]
        self.fields['produto_id'].choices = produto_choices
        self.fields['produto_id'].widget.attrs.setdefault('class', 'form-control')


class LoteAvulsoForm(forms.Form):
    produto_id = forms.ChoiceField(label='Produto', choices=[])
    quantidade_total = forms.DecimalField(
        min_value=Decimal('0.001'),
        decimal_places=3,
        label='Quantidade total',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.001'}),
    )
    quantidade_por_cupom = forms.DecimalField(
        min_value=Decimal('0.001'),
        decimal_places=3,
        initial=Decimal('1'),
        label='Quantidade por cupom',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.001'}),
    )
    preco_unitario = forms.DecimalField(
        min_value=Decimal('0.01'),
        decimal_places=2,
        required=False,
        label='Preço unitário (R$)',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
    )
    desconto_unitario = forms.DecimalField(
        min_value=Decimal('0'),
        initial=Decimal('0'),
        decimal_places=2,
        required=False,
        label='Desconto unitário (R$)',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
    )
    forma_pagamento = forms.ChoiceField(
        choices=FORMA_PAGAMENTO_FISCAL,
        initial='99',
        widget=forms.Select(attrs={'class': 'form-control'}),
    )

    def __init__(self, *args, loja=None, **kwargs):
        super().__init__(*args, **kwargs)
        from app_pdv.models import Produto
        qs = Produto.objects.filter(loja=loja, ativo=True).order_by('nome_venda') if loja else Produto.objects.none()
        self.fields['produto_id'].choices = [('', '— Selecione —')] + [
            (str(p.id), f'{p.nome_venda} (#{p.id})') for p in qs
        ]
        self.fields['produto_id'].widget.attrs.setdefault('class', 'form-control')


class ContabilidadePeriodoForm(forms.Form):
    mes_referencia = forms.CharField(
        label='Mês de referência',
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'month'}),
    )
    email_destino = forms.EmailField(
        required=False,
        label='E-mail da contabilidade',
        widget=forms.EmailInput(attrs={'class': 'form-control'}),
    )
    whatsapp_destino = forms.CharField(
        required=False,
        label='WhatsApp da contabilidade',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '5511999999999'}),
    )


class EmitirNFeForm(forms.Form):
    natureza_cfop = forms.ChoiceField(
        label='Natureza da operação',
        choices=[],
        widget=forms.Select(attrs={'class': 'form-control', 'id': 'id_natureza_cfop'}),
    )
    cfop = forms.CharField(
        label='CFOP',
        widget=forms.TextInput(attrs={'class': 'form-control', 'id': 'id_cfop', 'readonly': 'readonly'}),
    )
    serie = forms.CharField(
        label='Série',
        widget=forms.Select(attrs={'class': 'form-control'}),
    )
    finalidade_emissao = forms.ChoiceField(
        choices=[],
        initial='1',
        widget=forms.Select(attrs={'class': 'form-control'}),
    )
    produto_id = forms.ChoiceField(label='Produto', choices=[])
    quantidade = forms.DecimalField(min_value=Decimal('0.001'), decimal_places=3, initial=Decimal('1'))
    preco_unitario = forms.DecimalField(min_value=Decimal('0.01'), decimal_places=2, required=False)
    valor_desconto = forms.DecimalField(min_value=Decimal('0'), initial=Decimal('0'), decimal_places=2, required=False)
    valor_acrescimo = forms.DecimalField(min_value=Decimal('0'), initial=Decimal('0'), decimal_places=2, required=False)
    presenca_comprador = forms.ChoiceField(
        label='Presença do comprador',
        choices=[],
        initial='1',
        widget=forms.Select(attrs={'class': 'form-control'}),
    )
    forma_pagamento = forms.ChoiceField(
        choices=FORMA_PAGAMENTO_FISCAL,
        initial='99',
        widget=forms.Select(attrs={'class': 'form-control'}),
    )
    cnpj_destinatario = forms.CharField(
        required=False,
        label='CNPJ destinatário',
        widget=forms.TextInput(attrs={'class': 'form-control', 'id': 'id_cnpj_destinatario'}),
    )
    cpf_destinatario = forms.CharField(
        required=False,
        label='CPF destinatário',
        widget=forms.TextInput(attrs={'class': 'form-control', 'id': 'id_cpf_destinatario'}),
    )
    indicador_ie_destinatario = forms.ChoiceField(
        label='Indicador IE (destinatário)',
        choices=[],
        initial='9',
        widget=forms.Select(attrs={'class': 'form-control', 'id': 'id_indicador_ie_destinatario'}),
    )
    inscricao_estadual_destinatario = forms.CharField(
        required=False,
        label='Inscrição Estadual (IE)',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'id': 'id_inscricao_estadual_destinatario',
            'placeholder': 'Somente números — obrigatório se contribuinte ICMS',
        }),
    )
    nome_destinatario = forms.CharField(
        label='Nome / razão social *',
        widget=forms.TextInput(attrs={'class': 'form-control', 'id': 'id_nome_destinatario', 'list': 'lista_clientes_nfe'}),
    )
    cep = forms.CharField(
        label='CEP *',
        widget=forms.TextInput(attrs={'class': 'form-control', 'id': 'id_cep', 'placeholder': '00000-000'}),
    )
    logradouro = forms.CharField(
        label='Logradouro *',
        widget=forms.TextInput(attrs={'class': 'form-control', 'id': 'id_logradouro'}),
    )
    numero = forms.CharField(
        label='Número *',
        widget=forms.TextInput(attrs={'class': 'form-control', 'id': 'id_numero'}),
    )
    complemento = forms.CharField(
        required=False,
        label='Complemento',
        widget=forms.TextInput(attrs={'class': 'form-control', 'id': 'id_complemento'}),
    )
    bairro = forms.CharField(
        label='Bairro *',
        widget=forms.TextInput(attrs={'class': 'form-control', 'id': 'id_bairro'}),
    )
    municipio = forms.CharField(
        label='Município *',
        widget=forms.TextInput(attrs={'class': 'form-control', 'id': 'id_municipio'}),
    )
    uf = forms.CharField(
        label='UF *',
        max_length=2,
        widget=forms.TextInput(attrs={'class': 'form-control', 'maxlength': '2', 'id': 'id_uf'}),
    )
    codigo_municipio = forms.CharField(
        required=False,
        widget=forms.HiddenInput(attrs={'id': 'id_codigo_municipio'}),
    )
    modalidade_frete = forms.ChoiceField(
        label='Frete por conta',
        choices=[],
        initial='9',
        widget=forms.Select(attrs={'class': 'form-control', 'id': 'id_modalidade_frete'}),
    )
    valor_frete = forms.DecimalField(
        required=False,
        min_value=Decimal('0'),
        initial=Decimal('0'),
        decimal_places=2,
        label='Valor do frete (R$)',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'id': 'id_valor_frete'}),
    )
    quantidade_volumes = forms.IntegerField(
        required=False,
        min_value=0,
        initial=0,
        label='Quantidade de volumes',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'id': 'id_quantidade_volumes'}),
    )
    peso_bruto = forms.DecimalField(
        required=False,
        min_value=Decimal('0'),
        initial=Decimal('0'),
        decimal_places=3,
        label='Peso bruto (kg)',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.001', 'id': 'id_peso_bruto'}),
    )
    peso_liquido = forms.DecimalField(
        required=False,
        min_value=Decimal('0'),
        initial=Decimal('0'),
        decimal_places=3,
        label='Peso líquido (kg)',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.001', 'id': 'id_peso_liquido'}),
    )

    def __init__(self, *args, loja=None, **kwargs):
        super().__init__(*args, **kwargs)
        from app_pdv.models import Produto

        from .nfe_catalog import (
            FINALIDADE_NFE,
            INDICADOR_IE_DESTINATARIO,
            MODALIDADE_FRETE_NFE,
            NATUREZAS_NFE_UNICAS,
            PRESENCA_COMPRADOR_NFE,
        )
        from .services import get_or_create_config

        self.fields['natureza_cfop'].choices = [('', '— Selecione —')] + [
            (cfop, f'{cfop} — {desc}') for cfop, desc in NATUREZAS_NFE_UNICAS
        ]
        self.fields['finalidade_emissao'].choices = FINALIDADE_NFE
        self.fields['presenca_comprador'].choices = PRESENCA_COMPRADOR_NFE
        self.fields['indicador_ie_destinatario'].choices = INDICADOR_IE_DESTINATARIO
        self.fields['modalidade_frete'].choices = MODALIDADE_FRETE_NFE
        cfg = get_or_create_config(loja) if loja else None
        serie = str(cfg.serie_nfe if cfg else 1)
        self.fields['serie'].widget = forms.Select(
            attrs={'class': 'form-control'},
            choices=[(str(s), str(s)) for s in range(1, 100)],
        )
        self.fields['serie'].initial = serie

        for name, field in self.fields.items():
            if name not in (
                'finalidade_emissao', 'forma_pagamento', 'presenca_comprador',
                'produto_id', 'natureza_cfop', 'serie', 'codigo_municipio',
                'indicador_ie_destinatario', 'modalidade_frete',
            ):
                field.widget.attrs.setdefault('class', 'form-control')
        qs = Produto.objects.filter(loja=loja, ativo=True).order_by('nome_venda') if loja else Produto.objects.none()
        self.fields['produto_id'].choices = [('', '— Selecione —')] + [
            (str(p.id), p.nome_venda) for p in qs
        ]
        self.fields['produto_id'].widget.attrs.setdefault('class', 'form-control')

    def clean(self):
        cleaned = super().clean()
        cfop = (cleaned.get('natureza_cfop') or cleaned.get('cfop') or '').strip()
        if not cfop:
            raise forms.ValidationError('Selecione a natureza da operação (CFOP).')
        from .nfe_catalog import natureza_por_cfop

        cleaned['cfop'] = cfop
        cleaned['natureza_operacao'] = natureza_por_cfop(cfop)
        cpf = ''.join(c for c in (cleaned.get('cpf_destinatario') or '') if c.isdigit())
        cnpj = ''.join(c for c in (cleaned.get('cnpj_destinatario') or '') if c.isdigit())
        if cpf and cnpj:
            raise forms.ValidationError('Informe apenas CPF ou CNPJ do destinatário, não ambos.')
        if not cpf and not cnpj:
            raise forms.ValidationError('Informe CPF ou CNPJ do destinatário.')
        if cnpj and len(cnpj) != 14:
            raise forms.ValidationError('CNPJ destinatário inválido.')
        if cpf and len(cpf) != 11:
            raise forms.ValidationError('CPF destinatário inválido.')
        if cpf:
            cleaned['indicador_ie_destinatario'] = '9'
            cleaned['inscricao_estadual_destinatario'] = ''
        if cnpj:
            ind = str(cleaned.get('indicador_ie_destinatario') or '9')
            ie = ''.join(c for c in (cleaned.get('inscricao_estadual_destinatario') or '') if c.isdigit())
            if ind == '1' and not ie:
                raise forms.ValidationError(
                    'Informe a IE do destinatário ou altere o indicador para isento / não contribuinte.',
                )
            cleaned['inscricao_estadual_destinatario'] = ie
        if not (cleaned.get('nome_destinatario') or '').strip():
            raise forms.ValidationError('Nome do destinatário é obrigatório.')
        cep = ''.join(c for c in (cleaned.get('cep') or '') if c.isdigit())
        if len(cep) != 8:
            raise forms.ValidationError('CEP inválido (8 dígitos).')
        cleaned['cep'] = cep
        uf = (cleaned.get('uf') or '').strip().upper()
        if len(uf) != 2:
            raise forms.ValidationError('UF inválida.')
        cleaned['uf'] = uf
        for campo, rotulo in (
            ('logradouro', 'Logradouro'),
            ('numero', 'Número'),
            ('bairro', 'Bairro'),
            ('municipio', 'Município'),
        ):
            if not (cleaned.get(campo) or '').strip():
                raise forms.ValidationError(f'{rotulo} do destinatário é obrigatório.')
        ibge = ''.join(c for c in (cleaned.get('codigo_municipio') or '') if c.isdigit())
        if ibge:
            cleaned['codigo_municipio'] = ibge
        return cleaned


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
    """Credenciais e ambiente da API fiscal (Basic Auth — token como usuário, senha vazia)."""

    class Meta:
        model = FiscalConfig
        fields = ['ambiente', 'focus_token', 'focus_empresa_id', 'webhook_url_configurada']
        widgets = {
            'focus_token': forms.PasswordInput(render_value=True, attrs={'class': 'form-control', 'autocomplete': 'off'}),
            'ambiente': forms.Select(attrs={'class': 'form-control'}),
            'focus_empresa_id': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Opcional — ID da empresa no provedor'}),
            'webhook_url_configurada': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://seu-dominio/api/fiscal/webhooks/focus/'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['focus_token'].label = 'Token da API fiscal'
        self.fields['focus_empresa_id'].label = 'ID empresa (provedor)'
        self.fields['ambiente'].help_text = 'Homologação para testes; produção gera documentos com validade fiscal.'
        self.fields['focus_token'].help_text = 'Token alfanumérico da loja (HTTP Basic, senha em branco).'
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
