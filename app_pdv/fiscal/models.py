from django.conf import settings
from django.db import models
from django.contrib.auth.models import User


class FiscalConfig(models.Model):
    """Pilar 1 — Configurações fiscais da empresa + credenciais Focus."""
    AMBIENTE_CHOICES = [
        ('homologacao', 'Homologação'),
        ('producao', 'Produção'),
    ]
    CRT_CHOICES = [
        ('1', '1 — Simples Nacional'),
        ('2', '2 — Simples Nacional (excesso sublimite)'),
        ('3', '3 — Regime Normal'),
        ('4', '4 — MEI'),
    ]

    loja = models.OneToOneField('app_pdv.Loja', on_delete=models.CASCADE, related_name='fiscal_config')
    razao_social = models.CharField(max_length=200, blank=True, default='')
    nome_fantasia = models.CharField(max_length=200, blank=True, default='')
    cnpj = models.CharField(max_length=18, blank=True, default='')
    inscricao_estadual = models.CharField(max_length=20, blank=True, default='', verbose_name='IE')
    inscricao_municipal = models.CharField(max_length=20, blank=True, default='', verbose_name='IM')
    cnae = models.CharField(max_length=10, blank=True, default='')
    crt = models.CharField(max_length=1, choices=CRT_CHOICES, default='1', verbose_name='CRT')

    logradouro = models.CharField(max_length=200, blank=True, default='')
    numero = models.CharField(max_length=20, blank=True, default='')
    complemento = models.CharField(max_length=100, blank=True, default='')
    bairro = models.CharField(max_length=100, blank=True, default='')
    cep = models.CharField(max_length=10, blank=True, default='')
    municipio = models.CharField(max_length=100, blank=True, default='')
    uf = models.CharField(max_length=2, blank=True, default='')
    codigo_ibge = models.CharField(max_length=7, blank=True, default='', verbose_name='Código IBGE município')

    ambiente = models.CharField(max_length=20, choices=AMBIENTE_CHOICES, default='homologacao')
    focus_token = models.CharField(
        max_length=255, blank=True, default='',
        verbose_name='Token Focus NFe',
        help_text='Token da empresa na Focus (Basic Auth). Armazenado apenas no servidor.',
    )
    focus_empresa_id = models.CharField(max_length=64, blank=True, default='', verbose_name='ID empresa Focus')
    certificado_status = models.CharField(
        max_length=40, blank=True, default='nao_enviado',
        help_text='nao_enviado | valido | expirado | erro',
    )
    certificado_validade = models.DateField(null=True, blank=True)
    certificado_obs = models.CharField(max_length=255, blank=True, default='')

    serie_nfe = models.PositiveIntegerField(default=1)
    serie_nfce = models.PositiveIntegerField(default=1)
    serie_nfse = models.PositiveIntegerField(default=1)
    proximo_numero_nfe = models.PositiveIntegerField(default=1)
    proximo_numero_nfce = models.PositiveIntegerField(default=1)
    proximo_numero_nfse = models.PositiveIntegerField(default=1)

    csc_id = models.CharField(max_length=10, blank=True, default='', verbose_name='CSC ID (NFC-e)')
    csc_token = models.CharField(max_length=64, blank=True, default='', verbose_name='CSC Token (NFC-e)')

    emite_nfe = models.BooleanField(default=True, verbose_name='Emitir NF-e (55)')
    emite_nfce = models.BooleanField(default=True, verbose_name='Emitir NFC-e (65)')
    emite_nfse = models.BooleanField(default=False, verbose_name='Emitir NFS-e')
    emite_nfse_nacional = models.BooleanField(default=False, verbose_name='Emitir NFS-e Nacional')

    # Pilar 7 — contingência
    contingencia_ativa = models.BooleanField(default=False)
    contingencia_tipo = models.CharField(
        max_length=30, blank=True, default='',
        help_text='Ex.: offline, SVCAN, SVCRS',
    )
    contingencia_inicio = models.DateTimeField(null=True, blank=True)
    contingencia_motivo = models.CharField(max_length=255, blank=True, default='')

    webhook_url_configurada = models.URLField(blank=True, default='')
    email_envio_xml = models.EmailField(blank=True, default='', verbose_name='E-mail para envio de XML/DANFE')
    enviar_whatsapp_danfe = models.BooleanField(default=False)

    atualizado_em = models.DateTimeField(auto_now=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Configuração fiscal'
        verbose_name_plural = 'Configurações fiscais'

    def __str__(self):
        return f'Fiscal {self.loja_id} — {self.cnpj or self.razao_social or "sem CNPJ"}'

    @property
    def focus_base_url(self):
        if self.ambiente == 'producao':
            return getattr(settings, 'FOCUS_NFE_API_BASE_PRODUCAO', 'https://api.focusnfe.com.br/v2')
        return getattr(settings, 'FOCUS_NFE_API_BASE_HOMOLOGACAO', 'https://homologacao.focusnfe.com.br/v2')


class ProdutoDadosFiscais(models.Model):
    """Dados fiscais do produto (NCM, origem, serviço)."""
    ORIGEM_CHOICES = [
        ('0', '0 — Nacional'),
        ('1', '1 — Estrangeira (importação direta)'),
        ('2', '2 — Estrangeira (adquirida no mercado interno)'),
        ('3', '3 — Nacional (conteúdo importação > 40%)'),
        ('4', '4 — Nacional (produção conforme PPB)'),
        ('5', '5 — Nacional (conteúdo importação ≤ 40%)'),
        ('6', '6 — Estrangeira (importação direta sem similar)'),
        ('7', '7 — Estrangeira (mercado interno sem similar)'),
        ('8', '8 — Nacional (conteúdo importação > 70%)'),
    ]
    TIPO_CHOICES = [
        ('produto', 'Produto (mercadoria)'),
        ('servico', 'Serviço'),
    ]

    produto = models.OneToOneField(
        'app_pdv.Produto', on_delete=models.CASCADE, related_name='dados_fiscais',
    )
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES, default='produto')
    ncm = models.CharField(max_length=10, blank=True, default='')
    cest = models.CharField(max_length=9, blank=True, default='')
    origem = models.CharField(max_length=1, choices=ORIGEM_CHOICES, default='0')
    unidade_tributavel = models.CharField(max_length=10, blank=True, default='UN')
    codigo_servico = models.CharField(
        max_length=20, blank=True, default='',
        verbose_name='Código serviço (LC 116 / municipal)',
    )
    descricao_servico = models.CharField(max_length=255, blank=True, default='')
    # Pilar 9 — reforma (extensível)
    nbs = models.CharField(max_length=20, blank=True, default='', verbose_name='NBS (reforma)')
    codigo_class_trib = models.CharField(max_length=20, blank=True, default='', verbose_name='cClassTrib')

    class Meta:
        verbose_name = 'Dados fiscais do produto'
        verbose_name_plural = 'Dados fiscais dos produtos'

    def __str__(self):
        return f'{self.produto_id} NCM {self.ncm or "—"}'


class RegraTributaria(models.Model):
    """Pilar 2 — Matriz de impostos (CFOP, CST/CSOSN, alíquotas)."""
    loja = models.ForeignKey('app_pdv.Loja', on_delete=models.CASCADE, related_name='regras_tributarias')
    nome = models.CharField(max_length=120)
    ativa = models.BooleanField(default=True)
    ncm = models.CharField(max_length=10, blank=True, default='', help_text='Vazio = regra geral da loja')
    uf_destino = models.CharField(max_length=2, blank=True, default='', help_text='Vazio = qualquer UF')
    operacao = models.CharField(
        max_length=30, default='venda',
        help_text='venda | devolucao | transferencia | servico',
    )
    cfop = models.CharField(max_length=5, default='5102')
    csosn = models.CharField(max_length=4, blank=True, default='102', verbose_name='CSOSN (Simples)')
    cst_icms = models.CharField(max_length=3, blank=True, default='', verbose_name='CST ICMS')
    cst_pis = models.CharField(max_length=2, blank=True, default='49')
    cst_cofins = models.CharField(max_length=2, blank=True, default='49')
    aliquota_icms = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    aliquota_pis = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    aliquota_cofins = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    aliquota_iss = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    # Pilar 9
    aliquota_ibs = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    aliquota_cbs = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    observacao = models.CharField(max_length=255, blank=True, default='')
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Regra tributária'
        verbose_name_plural = 'Regras tributárias'
        ordering = ['nome']

    def __str__(self):
        return f'{self.nome} ({self.cfop})'


class DocumentoFiscal(models.Model):
    """Pilares 3/5/6/7/8 — Documento emitido (NF-e, NFC-e, NFS-e)."""
    TIPO_CHOICES = [
        ('nfe', 'NF-e (55)'),
        ('nfce', 'NFC-e (65)'),
        ('nfse', 'NFS-e'),
        ('nfse_nacional', 'NFS-e Nacional'),
    ]
    STATUS_CHOICES = [
        ('rascunho', 'Rascunho'),
        ('processando', 'Processando'),
        ('autorizado', 'Autorizado'),
        ('erro', 'Erro'),
        ('cancelado', 'Cancelado'),
        ('denegado', 'Denegado'),
        ('inutilizado', 'Inutilizado'),
        ('contingencia', 'Contingência'),
    ]

    loja = models.ForeignKey('app_pdv.Loja', on_delete=models.CASCADE, related_name='documentos_fiscais')
    venda = models.ForeignKey(
        'app_pdv.Venda', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='documentos_fiscais',
    )
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default='nfce')
    ref = models.CharField(max_length=64, verbose_name='Referência Focus (única)')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='rascunho')
    numero = models.CharField(max_length=20, blank=True, default='')
    serie = models.CharField(max_length=10, blank=True, default='')
    chave_acesso = models.CharField(max_length=50, blank=True, default='')
    protocolo = models.CharField(max_length=50, blank=True, default='')
    status_sefaz = models.CharField(max_length=10, blank=True, default='')
    mensagem_sefaz = models.TextField(blank=True, default='')
    valor_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    caminho_xml = models.CharField(max_length=500, blank=True, default='')
    caminho_pdf = models.CharField(max_length=500, blank=True, default='')
    url_xml = models.URLField(blank=True, default='')
    url_pdf = models.URLField(blank=True, default='')

    payload_envio = models.JSONField(default=dict, blank=True)
    payload_retorno = models.JSONField(default=dict, blank=True)
    snapshot_tributario = models.JSONField(default=dict, blank=True)

    em_contingencia = models.BooleanField(default=False)
    cancelado_em = models.DateTimeField(null=True, blank=True)
    motivo_cancelamento = models.CharField(max_length=255, blank=True, default='')
    carta_correcao = models.TextField(blank=True, default='')
    carta_correcao_em = models.DateTimeField(null=True, blank=True)

    criado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Documento fiscal'
        verbose_name_plural = 'Documentos fiscais'
        ordering = ['-criado_em']
        constraints = [
            models.UniqueConstraint(fields=['loja', 'ref'], name='fiscal_doc_unico_loja_ref'),
        ]
        indexes = [
            models.Index(fields=['loja', 'status', '-criado_em'], name='fiscal_doc_loja_status_idx'),
            models.Index(fields=['chave_acesso'], name='fiscal_doc_chave_idx'),
        ]

    def __str__(self):
        return f'{self.get_tipo_display()} {self.numero or self.ref} [{self.status}]'


class DocumentoFiscalEvento(models.Model):
    documento = models.ForeignKey(DocumentoFiscal, on_delete=models.CASCADE, related_name='eventos')
    tipo = models.CharField(max_length=40)
    descricao = models.TextField(blank=True, default='')
    payload = models.JSONField(default=dict, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-criado_em']


class LoteEmissaoFiscal(models.Model):
    """Emissão fiscal em lote (SaaS — várias vendas de uma loja)."""
    STATUS_LOTE = [
        ('processando', 'Processando'),
        ('concluido', 'Concluído'),
        ('parcial', 'Parcial (com erros)'),
        ('vazio', 'Nenhuma venda processada'),
    ]
    loja = models.ForeignKey('app_pdv.Loja', on_delete=models.CASCADE, related_name='lotes_emissao_fiscal')
    tipo = models.CharField(max_length=20, choices=DocumentoFiscal.TIPO_CHOICES, default='nfce')
    status = models.CharField(max_length=20, choices=STATUS_LOTE, default='processando')
    data_venda_de = models.DateField(null=True, blank=True)
    data_venda_ate = models.DateField(null=True, blank=True)
    pular_ja_emitidas = models.BooleanField(default=True)
    total_solicitado = models.PositiveIntegerField(default=0)
    total_autorizado = models.PositiveIntegerField(default=0)
    total_erro = models.PositiveIntegerField(default=0)
    total_ignorado = models.PositiveIntegerField(default=0)
    observacao = models.CharField(max_length=255, blank=True, default='')
    criado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    finalizado_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-criado_em']
        verbose_name = 'Lote de emissão fiscal'
        verbose_name_plural = 'Lotes de emissão fiscal'

    def __str__(self):
        return f'Lote #{self.pk} — {self.get_tipo_display()} ({self.criado_em:%d/%m/%Y %H:%M})'


class LoteEmissaoFiscalItem(models.Model):
    STATUS_ITEM = [
        ('pendente', 'Pendente'),
        ('autorizado', 'Autorizado'),
        ('processando', 'Processando'),
        ('erro', 'Erro'),
        ('ignorado', 'Ignorado'),
    ]
    lote = models.ForeignKey(LoteEmissaoFiscal, on_delete=models.CASCADE, related_name='itens')
    venda = models.ForeignKey('app_pdv.Venda', on_delete=models.CASCADE, related_name='lote_emissao_itens')
    documento = models.ForeignKey(
        DocumentoFiscal, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='lote_emissao_itens',
    )
    status = models.CharField(max_length=20, choices=STATUS_ITEM, default='pendente')
    mensagem = models.TextField(blank=True, default='')
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']
        constraints = [
            models.UniqueConstraint(fields=['lote', 'venda'], name='fiscal_lote_item_venda_unica'),
        ]


class FiscalWebhookLog(models.Model):
    """Pilar 4 — Logs de callbacks Focus."""
    loja = models.ForeignKey(
        'app_pdv.Loja', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='fiscal_webhooks',
    )
    documento = models.ForeignKey(
        DocumentoFiscal, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='webhook_logs',
    )
    evento = models.CharField(max_length=40, blank=True, default='')
    ref = models.CharField(max_length=64, blank=True, default='')
    status_recebido = models.CharField(max_length=40, blank=True, default='')
    payload = models.JSONField(default=dict, blank=True)
    headers = models.JSONField(default=dict, blank=True)
    processado = models.BooleanField(default=False)
    erro = models.TextField(blank=True, default='')
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-criado_em']
        verbose_name = 'Log de webhook fiscal'


class InutilizacaoNumeracao(models.Model):
    """Pilar 6 — Inutilização de faixa."""
    loja = models.ForeignKey('app_pdv.Loja', on_delete=models.CASCADE, related_name='inutilizacoes_fiscais')
    modelo = models.CharField(max_length=10, default='65', help_text='55=NF-e, 65=NFC-e')
    serie = models.PositiveIntegerField(default=1)
    numero_inicial = models.PositiveIntegerField()
    numero_final = models.PositiveIntegerField()
    justificativa = models.CharField(max_length=255)
    ref = models.CharField(max_length=64, blank=True, default='')
    status = models.CharField(max_length=30, default='pendente')
    protocolo = models.CharField(max_length=50, blank=True, default='')
    mensagem = models.TextField(blank=True, default='')
    criado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-criado_em']


class NFeRecebida(models.Model):
    """Pilar 10 — Manifestação / NF-e de entrada."""
    loja = models.ForeignKey('app_pdv.Loja', on_delete=models.CASCADE, related_name='nfe_recebidas')
    chave_acesso = models.CharField(max_length=50)
    cnpj_emitente = models.CharField(max_length=18, blank=True, default='')
    nome_emitente = models.CharField(max_length=200, blank=True, default='')
    valor_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    data_emissao = models.DateTimeField(null=True, blank=True)
    situacao = models.CharField(max_length=40, blank=True, default='pendente')
    manifestacao = models.CharField(
        max_length=40, blank=True, default='',
        help_text='ciencia | confirmacao | desconhecimento | nao_realizada',
    )
    manifestacao_em = models.DateTimeField(null=True, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-criado_em']
        constraints = [
            models.UniqueConstraint(
                fields=['loja', 'chave_acesso'],
                name='fiscal_nfe_recebida_unica',
            ),
        ]

    def __str__(self):
        return self.chave_acesso
