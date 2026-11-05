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
            'municipio', 'uf', 'codigo_ibge', 'telefone',
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
        self.fields['unidade_tributavel'].help_text = (
            'GLP (ANP 210203001) usa KG na NF-e mesmo se a venda for por botijão (UN).'
        )
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
    produto_id = forms.ChoiceField(label='Produto', choices=[], required=False)
    quantidade = forms.DecimalField(
        min_value=Decimal('0.001'),
        initial=Decimal('1'),
        decimal_places=3,
        required=False,
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
        required=False,
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
    tributacao_nfe = forms.ChoiceField(
        label='Tributação',
        choices=[],
        initial='produto',
        widget=forms.Select(attrs={'class': 'form-control', 'id': 'id_tributacao_nfe'}),
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
        self._loja = loja
        from app_pdv.models import Produto

        from .natureza_service import choices_natureza_cfop
        from .nfe_catalog import (
            FINALIDADE_NFE,
            INDICADOR_IE_DESTINATARIO,
            MODALIDADE_FRETE_NFE,
            PERFIL_TRIBUTACAO_NFE,
            PRESENCA_COMPRADOR_NFE,
        )
        from .services import get_or_create_config

        nat_choices = choices_natureza_cfop(loja) if loja else []
        self.fields['natureza_cfop'].choices = [('', '— Selecione —')] + nat_choices
        self.fields['tributacao_nfe'].choices = PERFIL_TRIBUTACAO_NFE
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
                'indicador_ie_destinatario', 'modalidade_frete', 'tributacao_nfe',
            ):
                field.widget.attrs.setdefault('class', 'form-control')
        qs = Produto.objects.filter(loja=loja, ativo=True).order_by('nome_venda') if loja else Produto.objects.none()
        self.fields['produto_id'].choices = [('', '— Selecione —')] + [
            (str(p.id), p.nome_venda) for p in qs
        ]
        self.fields['produto_id'].widget.attrs.setdefault('class', 'form-control')
        initial = kwargs.get('initial') or {}
        data0 = getattr(self, 'data', None)
        cfop_ini = (data0.get('natureza_cfop') if data0 else None) or initial.get('natureza_cfop') or initial.get('cfop')
        if cfop_ini:
            cfop_ini = str(cfop_ini)
            existentes = {str(c[0]) for c in self.fields['natureza_cfop'].choices}
            if cfop_ini not in existentes:
                self.fields['natureza_cfop'].choices.append((cfop_ini, f'{cfop_ini} — (da nota)'))
        pid_ini = (data0.get('produto_id') if data0 else None) or initial.get('produto_id')
        if pid_ini and loja:
            existentes_p = {str(c[0]) for c in self.fields['produto_id'].choices}
            if str(pid_ini) not in existentes_p:
                from app_pdv.models import Produto as ProdutoModel
                prod = ProdutoModel.objects.filter(pk=int(pid_ini), loja=loja).first()
                if prod:
                    self.fields['produto_id'].choices.append((str(prod.id), prod.nome_venda))

    def clean(self):
        cleaned = super().clean()
        loja = self._loja
        cfop = (cleaned.get('natureza_cfop') or cleaned.get('cfop') or '').strip()
        if not cfop:
            raise forms.ValidationError('Selecione a natureza da operação (CFOP).')
        from .natureza_service import descricao_natureza_loja, tributacao_da_natureza

        cleaned['cfop'] = cfop
        cleaned['natureza_operacao'] = descricao_natureza_loja(loja, cfop) if loja else cfop
        if loja and (cleaned.get('tributacao_nfe') or 'produto') == 'produto':
            nat_trib = tributacao_da_natureza(loja, cfop)
            if nat_trib and nat_trib != 'produto':
                cleaned['tributacao_nfe'] = nat_trib
        cleaned['tributacao'] = cleaned.get('tributacao_nfe') or 'produto'
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

        from .nfe_catalog import cfop_exige_grupo_combustivel
        from .produto_fiscal import _quantidade_kg_monofasico

        if cfop_exige_grupo_combustivel(cfop):
            pid = cleaned.get('produto_id')
            if pid and loja:
                from app_pdv.models import Produto

                produto = Produto.objects.filter(pk=int(pid), loja=loja).first()
                if produto:
                    try:
                        df = produto.dados_fiscais
                    except Exception:
                        df = None
                    if not df or not (df.codigo_anp or '').strip():
                        raise forms.ValidationError(
                            'CFOP de combustível: cadastre código e descrição ANP no cadastro fiscal do produto.',
                        )
                    if not df.icms_aliquota_ad_rem or float(df.icms_aliquota_ad_rem) <= 0:
                        raise forms.ValidationError(
                            'CFOP de combustível: cadastre a alíquota ICMS ad rem (R$/kg) no produto — '
                            'obrigatória para CST 61 (monofásico retido).',
                        )
                    un = (df.unidade_tributavel or 'UN').lower()
                    peso_form = float(cleaned.get('peso_liquido') or 0)
                    q_kg = _quantidade_kg_monofasico(
                        produto,
                        quantidade=float(cleaned.get('quantidade') or 1),
                        unidade=un,
                        peso_liquido_nfe=peso_form or None,
                    )
                    if q_kg <= 0:
                        raise forms.ValidationError(
                            'Informe o peso líquido (kg) em Transportador/volumes ou cadastre o produto '
                            'com “kg” na descrição (ex.: GLP 13 kg).',
                        )
            trib = cleaned.get('tributacao_nfe') or 'produto'
            if trib in ('produto', 'csosn_102'):
                cleaned['tributacao_nfe'] = 'cst_61_combustivel'
            cleaned['tributacao'] = cleaned.get('tributacao_nfe') or 'cst_61_combustivel'
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
    """Provedor de emissão + credenciais ACBr API / ACBrLib."""

    acbr_lib_pfx_arquivo = forms.FileField(
        required=False,
        label='Certificado A1 (.pfx / .p12)',
        help_text='Obrigatório no modo ACBrLib. Arquivo fica só no servidor (volume media).',
        widget=forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': '.pfx,.p12'}),
    )

    class Meta:
        model = FiscalConfig
        fields = [
            'provedor_emissao', 'ambiente',
            'acbr_client_id', 'acbr_client_secret',
            'acbr_lib_pfx_senha',
        ]
        widgets = {
            'provedor_emissao': forms.Select(attrs={'class': 'form-control', 'id': 'id_provedor_emissao'}),
            'acbr_client_id': forms.TextInput(attrs={'class': 'form-control', 'autocomplete': 'off'}),
            'acbr_client_secret': forms.PasswordInput(render_value=False, attrs={'class': 'form-control', 'autocomplete': 'new-password'}),
            'acbr_lib_pfx_senha': forms.PasswordInput(render_value=False, attrs={'class': 'form-control', 'autocomplete': 'new-password'}),
            'ambiente': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['acbr_client_id'].label = 'Client ID'
        self.fields['acbr_client_secret'].label = 'Client Secret'
        self.fields['acbr_client_id'].required = False
        self.fields['acbr_client_secret'].required = False
        self.fields['acbr_lib_pfx_senha'].required = False
        self.fields['acbr_lib_pfx_senha'].label = 'Senha do certificado A1'
        self.fields['acbr_lib_pfx_senha'].help_text = 'Deixe em branco para manter a senha já salva.'
        self.fields['ambiente'].help_text = (
            'Homologação: SEFAZ homolog / ACBr API hom.acbr.api.br. '
            'Produção: SEFAZ produção / ACBr API prod.acbr.api.br.'
        )
        self.fields['acbr_client_id'].help_text = 'Client ID gerado no console da ACBr API (modo API).'
        self.fields['acbr_client_secret'].help_text = 'Client Secret da ACBr. Deixe em branco para manter o valor já salvo.'
        self.fields['provedor_emissao'].label = 'Provedor'
        self.fields['provedor_emissao'].choices = [
            ('api', 'ACBr API (OAuth HTTP)'),
            ('lib', 'ACBrLib Pro (SEFAZ direto)'),
        ]
        self.fields['provedor_emissao'].help_text = (
            'API usa Client ID/Secret. Lib usa certificado A1 (.pfx) neste formulário.'
        )

    def clean_acbr_client_secret(self):
        secret = (self.cleaned_data.get('acbr_client_secret') or '').strip()
        if secret:
            return secret
        if self.instance.pk and (self.instance.acbr_client_secret or '').strip():
            return self.instance.acbr_client_secret
        return ''

    def clean_acbr_lib_pfx_senha(self):
        senha = (self.cleaned_data.get('acbr_lib_pfx_senha') or '').strip()
        if senha:
            return senha
        if self.instance.pk and (self.instance.acbr_lib_pfx_senha or '').strip():
            return self.instance.acbr_lib_pfx_senha
        return ''


class EmitirLoteForm(forms.Form):
    tipo = forms.ChoiceField(
        choices=[
            ('nfce', 'NFC-e (65) — cupom consumidor'),
        ],
        initial='nfce',
        widget=forms.HiddenInput(),
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
        ],
        initial='nfce',
        widget=forms.HiddenInput(),
    )
    venda_id = forms.IntegerField(
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'ID da venda (obrigatório para NFC-e/NF-e)'}),
    )

    def clean(self):
        cleaned = super().clean()
        cleaned['tipo'] = 'nfce'
        if not cleaned.get('venda_id'):
            raise forms.ValidationError('Informe o ID da venda para emitir NFC-e.')
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


def _dec_post(valor, default='0'):
    raw = str(valor if valor not in (None, '') else default).strip().replace(',', '.')
    try:
        return Decimal(raw)
    except Exception:
        return Decimal(default)


def parse_itens_avulsa(post, loja):
    """Lê linhas item_* do POST. Se não houver lista, usa o produto único do formulário legado."""
    from app_pdv.models import Produto

    ids = [v for v in post.getlist('item_produto_id') if str(v).strip()]
    qtds = post.getlist('item_quantidade')
    precos = post.getlist('item_preco')
    descontos = post.getlist('item_desconto')
    acrescimos = post.getlist('item_acrescimo')
    if not ids:
        pid = str(post.get('produto_id') or '').strip()
        if pid:
            ids = [pid]
            qtds = [post.get('quantidade') or '1']
            precos = [post.get('preco_unitario') or '']
            descontos = [post.get('valor_desconto') or '0']
            acrescimos = [post.get('valor_acrescimo') or '0']
    itens = []
    for i, pid in enumerate(ids):
        if not str(pid).isdigit():
            continue
        produto = Produto.objects.filter(pk=int(pid), loja=loja, ativo=True).first()
        if not produto:
            raise forms.ValidationError(f'Produto inválido na linha {i + 1}.')
        qtd = _dec_post(qtds[i] if i < len(qtds) else '1', '1')
        if qtd <= 0:
            raise forms.ValidationError(f'Quantidade inválida na linha {i + 1}.')
        preco_raw = precos[i] if i < len(precos) else ''
        preco = _dec_post(preco_raw, '0') if str(preco_raw).strip() else (produto.preco_venda or Decimal('0'))
        if preco <= 0:
            raise forms.ValidationError(f'Preço inválido na linha {i + 1}.')
        itens.append({
            'produto': produto,
            'quantidade': float(qtd),
            'preco_unitario': float(preco),
            'valor_desconto': float(_dec_post(descontos[i] if i < len(descontos) else '0')),
            'valor_acrescimo': float(_dec_post(acrescimos[i] if i < len(acrescimos) else '0')),
        })
    if not itens:
        raise forms.ValidationError('Adicione ao menos um produto à nota.')
    return itens


def parse_pagamentos_avulsa(post, total):
    formas = [v for v in post.getlist('pag_forma') if str(v).strip()]
    valores = post.getlist('pag_valor')
    if not formas:
        forma = str(post.get('forma_pagamento') or '99').strip() or '99'
        return [{'forma_pagamento': forma, 'valor_pagamento': round(float(total), 2)}]
    pagamentos = []
    for i, forma in enumerate(formas):
        valor = float(_dec_post(valores[i] if i < len(valores) else '0'))
        if valor <= 0:
            continue
        pagamentos.append({
            'forma_pagamento': str(forma).zfill(2)[:2],
            'valor_pagamento': round(valor, 2),
        })
    if not pagamentos:
        raise forms.ValidationError('Informe ao menos uma forma de pagamento com valor.')
    return pagamentos


def total_itens_avulsa(itens):
    bruto = sum(i['quantidade'] * i['preco_unitario'] for i in itens)
    desc = sum(i.get('valor_desconto') or 0 for i in itens)
    acre = sum(i.get('valor_acrescimo') or 0 for i in itens)
    return round(max(bruto - desc + acre, 0.01), 2)


def dados_edicao_nfe(doc) -> dict:
    """Prefill do formulário NF-e (modelo 55) a partir do documento com erro."""
    payload = doc.payload_envio if isinstance(doc.payload_envio, dict) else {}
    snap = doc.snapshot_tributario or {}
    item = (payload.get('items') or [{}])[0]
    vols = payload.get('volumes') or []
    vol = vols[0] if vols else {}
    pag = (payload.get('formas_pagamento') or [{}])[0]
    cfop = ''.join(c for c in str(item.get('cfop') or '') if c.isdigit())[:4]
    trib = snap.get('tributacao') or 'produto'
    if str(item.get('icms_situacao_tributaria') or '') == '61' and trib == 'produto':
        trib = 'cst_61_combustivel'
    return {
        'natureza_cfop': cfop,
        'cfop': cfop,
        'tributacao_nfe': trib,
        'serie': str(doc.serie or payload.get('serie') or '1'),
        'finalidade_emissao': str(payload.get('finalidade_emissao') or '1'),
        'presenca_comprador': str(payload.get('presenca_comprador') or '1'),
        'produto_id': str(item.get('codigo_produto') or snap.get('produto_id') or doc.produto_avulso_id or ''),
        'quantidade': item.get('quantidade_comercial') or '1',
        'preco_unitario': item.get('valor_unitario_comercial') or '',
        'valor_desconto': item.get('valor_desconto') or payload.get('valor_desconto') or 0,
        'valor_acrescimo': item.get('valor_outras_despesas') or payload.get('valor_outras_despesas') or 0,
        'forma_pagamento': str(pag.get('forma_pagamento') or '99').zfill(2)[:2],
        'cnpj_destinatario': payload.get('cnpj_destinatario') or '',
        'cpf_destinatario': payload.get('cpf_destinatario') or '',
        'indicador_ie_destinatario': str(payload.get('indicador_inscricao_estadual_destinatario') or '9'),
        'inscricao_estadual_destinatario': payload.get('inscricao_estadual_destinatario') or '',
        'nome_destinatario': payload.get('nome_destinatario') or '',
        'cep': payload.get('cep_destinatario') or payload.get('cep') or '',
        'logradouro': payload.get('logradouro_destinatario') or payload.get('logradouro') or '',
        'numero': payload.get('numero_destinatario') or payload.get('numero') or '',
        'complemento': payload.get('complemento_destinatario') or payload.get('complemento') or '',
        'bairro': payload.get('bairro_destinatario') or payload.get('bairro') or '',
        'municipio': payload.get('municipio_destinatario') or payload.get('municipio') or '',
        'uf': payload.get('uf_destinatario') or payload.get('uf') or '',
        'codigo_municipio': payload.get('codigo_municipio_destinatario') or payload.get('codigo_municipio') or '',
        'modalidade_frete': str(payload.get('modalidade_frete') or '9'),
        'valor_frete': payload.get('valor_frete') or 0,
        'quantidade_volumes': vol.get('quantidade') or 0,
        'peso_bruto': vol.get('peso_bruto') or 0,
        'peso_liquido': vol.get('peso_liquido') or 0,
    }


def dados_edicao_avulsa(doc):
    """Monta itens/pagamentos/destinatário a partir do documento com erro."""
    payload = doc.payload_envio if isinstance(doc.payload_envio, dict) else {}
    snap = doc.snapshot_tributario or {}
    itens = []
    for linha in snap.get('itens') or []:
        itens.append({
            'produto_id': str(linha.get('produto_id') or ''),
            'quantidade': str(linha.get('quantidade') or '1'),
            'preco_unitario': str(linha.get('preco_unitario') or ''),
            'valor_desconto': str(linha.get('valor_desconto') or '0'),
            'valor_acrescimo': str(linha.get('valor_acrescimo') or '0'),
        })
    if not itens:
        item = (payload.get('items') or [{}])[0]
        itens.append({
            'produto_id': str(item.get('codigo_produto') or snap.get('produto_id') or doc.produto_avulso_id or ''),
            'quantidade': str(item.get('quantidade_comercial') or snap.get('quantidade') or '1'),
            'preco_unitario': str(item.get('valor_unitario_comercial') or snap.get('preco_unitario') or ''),
            'valor_desconto': str(item.get('valor_desconto') or payload.get('valor_desconto') or '0'),
            'valor_acrescimo': str(item.get('valor_outras_despesas') or payload.get('valor_outras_despesas') or '0'),
        })
    pagamentos = []
    for pag in payload.get('formas_pagamento') or snap.get('pagamentos') or []:
        pagamentos.append({
            'forma_pagamento': str(pag.get('forma_pagamento') or '99'),
            'valor_pagamento': str(pag.get('valor_pagamento') or pag.get('valor') or ''),
        })
    if not pagamentos:
        pagamentos.append({'forma_pagamento': '99', 'valor_pagamento': str(doc.valor_total or '')})
    return {
        'itens': itens,
        'pagamentos': pagamentos,
        'interestadual': payload.get('local_destino') == '2',
        'cpf_destinatario': payload.get('cpf_destinatario') or '',
        'cnpj_destinatario': payload.get('cnpj_destinatario') or '',
        'nome_destinatario': payload.get('nome_destinatario') or '',
    }
