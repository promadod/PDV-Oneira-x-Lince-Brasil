from django.db import models
from django.db.models import Q
from django.contrib.auth.models import User
from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from datetime import date
from django.utils import timezone
from django.utils.text import slugify
from decimal import Decimal, ROUND_DOWN

# ------------------ OPÇÕES GERAIS (Status e Origem) ---------------
STATUS_VENDA_CHOICES = [
    ('ABERTO', 'Em Aberto (Balcão)'),
    ('FINALIZADO', 'Finalizado'),
    ('RETIRADO_NA_LOJA', 'Retirado na loja'),
    ('ORCAMENTO', 'Orçamento'),
    ('PENDENTE', 'Aguardando Aprovação'),   
    ('EM_PREPARACAO', 'Em Separação'),      
    ('SAIU_ENTREGA', 'Saiu para Entrega'),  
    ('CANCELADO', 'Cancelado/Recusado'),
    ('AGUARDANDO_FINALIZAR', 'Pausado / Finalizar Depois'),
    ('FIADO', 'Fiado (Pagamento Pendente)'),
]

ORIGEM_VENDA_CHOICES = [
    ('PDV', 'Balcão/Caixa'),
    ('APP', 'App Cliente'),
]

STATUS_ENTREGA_CHOICES = [
    ('PENDENTE', 'Aguardando Motoboy'),
    ('EM_ROTA', 'Saiu para Entrega'),
    ('ENTREGUE', 'Entregue Finalizado'),
]

FORMA_PGTO_CHOICES = [
    ('DINHEIRO', 'Dinheiro'), 
    ('CREDITO', 'Crédito'), 
    ('DEBITO', 'Débito'), 
    ('PIX', 'Pix')
]

MEIO_LIQUIDACAO_CHOICES = [
    ('DINHEIRO', 'Dinheiro'),
    ('PIX', 'Pix'),
    ('CREDITO', 'Cartão de Crédito'),
    ('DEBITO', 'Cartão de Débito'),
    ('CORTESIA', 'Cortesia'),
]

MEIO_LIQUIDACAO_VENDA_CHOICES = MEIO_LIQUIDACAO_CHOICES + [
    ('MISTO', 'Pagamento Dividido'),
]

MEIOS_LIQUIDACAO_PADRAO = [
    {'codigo': 'DINHEIRO', 'nome': 'Dinheiro', 'cor': '#28a745', 'icone': 'fa-money-bill-wave'},
    {'codigo': 'PIX', 'nome': 'Pix', 'cor': '#03dac6', 'icone': 'fa-qrcode'},
    {'codigo': 'CREDITO', 'nome': 'Cartão de Crédito', 'cor': '#29b6f6', 'icone': 'fa-credit-card'},
    {'codigo': 'DEBITO', 'nome': 'Cartão de Débito', 'cor': '#ff9800', 'icone': 'fa-wallet'},
    {'codigo': 'CORTESIA', 'nome': 'Cortesia', 'cor': '#9e9e9e', 'icone': 'fa-gift'},
]

FORMAS_PAGAMENTO_PADRAO = [
    {'codigo': 'DINHEIRO', 'nome': 'Dinheiro', 'cor': '#28a745', 'icone': 'fa-money-bill-wave', 'ordem': 1, 'exige_conferencia': True},
    {'codigo': 'PIX', 'nome': 'Pix', 'cor': '#03dac6', 'icone': 'fa-qrcode', 'ordem': 2, 'exige_conferencia': False},
    {'codigo': 'CREDITO', 'nome': 'Cartão de Crédito', 'cor': '#29b6f6', 'icone': 'fa-credit-card', 'ordem': 3, 'exige_conferencia': False},
    {'codigo': 'DEBITO', 'nome': 'Cartão de Débito', 'cor': '#ff9800', 'icone': 'fa-wallet', 'ordem': 4, 'exige_conferencia': False},
    {'codigo': 'CORTESIA', 'nome': 'Cortesia', 'cor': '#9e9e9e', 'icone': 'fa-gift', 'ordem': 99, 'exige_conferencia': False},
]

UNIDADE_MEDIDA_CHOICES = [
    ('UN', 'Unidade (Peça, Fardo, Saco Fechado)'),
    ('KG', 'Quilograma / Granel (KG)'),
    ('L', 'Litros (L)'),
]

# 1. -----------------------Lojas (SaaS)------------------------

class Rede(models.Model):
    nome = models.CharField(max_length=100, verbose_name="Nome da Rede/Franquia (Ex: The King)")
    slug = models.SlugField(unique=True, help_text="Nome para o link (ex: the-king)")
    logo = models.ImageField(upload_to='redes/', null=True, blank=True)
    ativa = models.BooleanField(default=True)

    def __str__(self):
        return self.nome

class Loja(models.Model):
    NOME_MARCA_PDV_MAX = 22

    # --- CAMPOS ORIGINAIS ---
    nome = models.CharField(max_length=100)
    gerente = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="lojas_gerenciadas")
    rede = models.ForeignKey(Rede, on_delete=models.SET_NULL, null=True, blank=True, related_name="unidades")
    nome_unidade = models.CharField(max_length=100, blank=True, null=True, help_text="Nome da filial para o cliente clicar. Ex: Botânico, Metrópoles")
    
    taxa_entrega_app = models.DecimalField(
        max_digits=10, decimal_places=2, default=5.00, verbose_name="Taxa de Entrega (App)"
    )
    taxa_entrega_pdv = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00, verbose_name="Taxa Padrão (PDV)"
    )
    
    ativo = models.BooleanField(default=True, verbose_name="Loja Ativa?")
    data_criacao = models.DateTimeField(auto_now_add=True)
    loja_aberta = models.BooleanField(default=True, verbose_name="Loja Aberta para Delivery")

    nome_marca_pdv = models.CharField(
        max_length=22,
        blank=True,
        default='',
        verbose_name='Nome exibido no menu lateral',
        help_text='Marca no topo do menu (máx. 22 caracteres). Clique no nome no sistema para alterar.',
    )
    cnpj = models.CharField(
        max_length=18,
        blank=True,
        default='',
        verbose_name='CNPJ',
        help_text='Exibido no rodapé do PDV. Ex: 00.000.000/0001-00',
    )

    # --- INTEGRAÇÃO MOVEON ---
    usa_moveon = models.BooleanField(
        default=False, 
        verbose_name="Utilizar frota terceirizada (MoveON)"
    )

    monitorar_entrega = models.BooleanField(
        default=True,
        verbose_name="Monitorar Entrega?",
        help_text="Sim: fluxo normal com app do motoboy (Em Separação → Em Rota → Finalizado). "
                   "Não: finaliza direto pela Torre de Controle, sem precisar do app."
    )

    trabalha_com_entregas = models.BooleanField(
        default=True,
        verbose_name="Trabalha com entregas?",
        help_text="Sim: vendas com cliente podem ir para entrega. "
                   "Não: vendas no PDV ficam como venda na loja (balcão), mesmo com cliente.",
    )

    impressao_automatica = models.BooleanField(
        default=False,
        verbose_name="Impressão automática ao finalizar venda?",
        help_text="Sim: ao finalizar venda no PDV, abre a impressão da nota fiscal.",
    )

    trabalha_com_leitor_codigo_barras = models.BooleanField(
        default=False,
        verbose_name="Trabalha com leitor de código de barras?",
        help_text="Ativo: na tela de vendas, leituras USB selecionam o produto automaticamente. "
                   "Cadastre o código de barras em cada produto.",
    )

    cobra_taxa_servico = models.BooleanField(
        default=False,
        verbose_name="Cobra taxa de serviço sobre a venda?",
        help_text="Ativo com 'Trabalha com entregas' desmarcado: aplica % sobre o consumo no PDV e na nota.",
    )
    taxa_servico_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=10.00,
        verbose_name="Taxa de serviço padrão (%)",
    )

    usa_fiado = models.BooleanField(
        default=False,
        verbose_name="Habilitar Vendas Fiado?",
        help_text="Ativa venda a prazo no PDV (ex.: depósito de gás). Lojas sem esta opção "
                   "continuam com o fluxo normal de pagamento integral."
    )

    controla_vasilhame_vazio = models.BooleanField(
        default=False,
        verbose_name="Controle de botijões/galões vazios?",
        help_text="Ao vender, incrementa vasilhame vazio do item. Na entrada de estoque, "
                   "consome vazios ao reabastecer. Exibe coluna 'Vazio' em /estoque/."
    )

    estoque_diario = models.BooleanField(
        default=False,
        verbose_name="Estoque diário (contagem manual)?",
        help_text="Permite editar cheios/vazios em /estoque/, registra abertura/fechamento do dia "
                   "e usa esses saldos no PDV. Requer 'Controle de botijões/galões vazios' ativo."
    )

    permite_pagamento_dividido = models.BooleanField(
        default=False,
        verbose_name="Permitir pagamento dividido?",
        help_text="Permite finalizar venda com 2 ou mais meios de liquidação (ex.: metade dinheiro, metade Pix)."
    )

    permite_venda_completa = models.BooleanField(
        default=False,
        verbose_name="Permitir venda de produto completo (gás+vasilhame)?",
        help_text="Depósitos: cliente sem vazio pode comprar produto cheio sem troca de vasilhame.",
    )

    divide_produtos_por_grupos = models.BooleanField(
        default=False,
        verbose_name="Dividir produtos por grupos?",
        help_text="Ativo: estoque e produtos organizados em grupos (ex.: Bebidas, Petiscos). "
                   "Recibo de fechamento de caixa agrupa as saídas por grupo.",
    )

    gerencia_pagamento_mercadorias = models.BooleanField(
        default=False,
        verbose_name="Gerenciar pagamento de mercadorias (CMV)?",
        help_text="Ativo: entradas consignadas ficam a pagar; baixas no relatório CMV "
                   "descontam o meio (Pix/Dinheiro etc.) no caixa do dia.",
    )

    # --- PLANO DE FIDELIDADE ---
    fidelidade_ativa = models.BooleanField(
        default=False,
        verbose_name="Ativar plano de fidelidade?",
    )
    FIDELIDADE_TIPO_META = [
        ('PRODUTOS', 'Por quantidade de produtos'),
        ('PONTOS', 'Por valor acumulado (pontos)'),
    ]
    fidelidade_tipo_meta = models.CharField(
        max_length=20, choices=FIDELIDADE_TIPO_META, default='PRODUTOS',
        verbose_name="Tipo de meta da promoção",
    )
    fidelidade_meta = models.DecimalField(
        max_digits=10, decimal_places=2, default=10,
        verbose_name="Meta para ativar promoção (qtd produtos ou pontos)",
    )
    fidelidade_desconto_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=5.00,
        verbose_name="Desconto da promoção (%)",
    )

    # --- WHATSAPP AUTOMÁTICO (SaaS) ---
    whatsapp_notificar_pedido = models.BooleanField(
        default=False,
        verbose_name="Notificar WhatsApp da empresa em novos pedidos?",
    )
    whatsapp_numero_empresa = models.CharField(
        max_length=20, blank=True, default='',
        verbose_name="WhatsApp da empresa (novos pedidos)",
    )
    whatsapp_msg_novo_pedido = models.TextField(
        blank=True, default='',
        verbose_name="Mensagem automática — novo pedido (empresa)",
        help_text="Placeholders: {pedido}, {cliente}, {telefone}, {whatsapp}, {endereco}, {pagamento}, {itens}, {total}, {obs}",
    )
    whatsapp_msg_saiu_entrega = models.TextField(
        blank=True, default='Olá {cliente}! Seu pedido #{pedido} saiu para entrega. Em breve chegaremos!',
        verbose_name="Mensagem — motoboy saiu para entrega (cliente)",
    )
    whatsapp_msg_entrega_concluida = models.TextField(
        blank=True, default='Olá {cliente}! Seu pedido #{pedido} foi entregue. Obrigado pela preferência!',
        verbose_name="Mensagem — entrega concluída (cliente)",
    )

    # --- CAMPANHAS DE CLIENTES ---
    msg_campanha_ativos = models.TextField(
        blank=True, default='',
        verbose_name="Mensagem para clientes ativos (30 dias)",
        help_text="Placeholders: {cliente}, {bairro}, {desconto}",
    )
    msg_campanha_inativos = models.TextField(
        blank=True, default='',
        verbose_name="Mensagem para clientes inativos (60+ dias)",
    )
    campanha_desconto_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=10.00,
        verbose_name="Desconto sugerido nas campanhas (%)",
    )

    # --- CAMPOS DO SAAS (ASSINATURA) ---
    STATUS_ASSINATURA = [
        ('ATIVO', 'Ativo - Acesso Liberado'),
        ('BLOQUEADO', 'Bloqueado - Pagamento Pendente'),
        ('CANCELADO', 'Cancelado'),
        ('GRATUITO', 'Período de Teste / Gratuito'),
    ]

    status_assinatura = models.CharField(
        max_length=20, choices=STATUS_ASSINATURA, default='ATIVO', verbose_name="Status da Assinatura"
    )
    
    data_vencimento = models.DateField(
        null=True, blank=True, help_text="Data limite para o próximo pagamento", verbose_name="Vencimento da Mensalidade"
    )
    
    valor_mensalidade = models.DecimalField(
        max_digits=10, decimal_places=2, default=99.90, verbose_name="Valor da Mensalidade"
    )
    
    # NOVO: Grace Period (Tolerância)
    dias_tolerancia = models.IntegerField(
        default=3, 
        help_text="Quantos dias a loja pode usar após o vencimento antes de bloquear total."
    )

    # NOVO: Rastreamento de Uso
    ultimo_acesso = models.DateTimeField(
        null=True, blank=True, 
        help_text="Data e hora da última interação de qualquer usuário desta loja."
    )
    
    link_pagamento_atual = models.URLField(blank=True, null=True, verbose_name="Link do Boleto/Pix")

    def __str__(self): 
        return self.nome

    def marca_pdv_exibicao(self):
        nome = (self.nome_marca_pdv or '').strip()
        return nome if nome else 'Oneira PDV'

    def get_formas_pagamento_ativas(self):
        return FormaPagamentoLoja.objects.filter(loja=self, ativo=True).order_by('ordem', 'nome')

    # --- MÉTODOS AUXILIARES DO SAAS (INSERIDOS AQUI) ---
    
    def dias_restantes(self):
        """Retorna quantos dias faltam para vencer. Se negativo, está vencido."""
        if not self.data_vencimento:
            return 0
        delta = self.data_vencimento - date.today()
        return delta.days

    def dias_atraso(self):
        """Retorna dias de atraso. Se negativo, ainda não venceu."""
        if not self.data_vencimento: return 0
        delta = date.today() - self.data_vencimento
        return delta.days

    def verificar_bloqueio(self):
        """
        Retorna TRUE se o sistema deve bloquear o acesso.
        Considera a data de vencimento + dias de tolerância.
        """
        if not self.data_vencimento:
            return False

        atraso = self.dias_atraso()
        
        # Se o atraso for maior que a tolerância, BLOQUEIA
        if atraso > self.dias_tolerancia:
            # Só altera status se ainda estiver como ATIVO
            if self.status_assinatura == 'ATIVO':
                self.status_assinatura = 'BLOQUEADO'
                self.save()
            return True
        
        # Se pagou (atraso negativo ou zero) e o status ainda ta bloqueado, desbloqueia
        if atraso <= 0 and self.status_assinatura == 'BLOQUEADO':
            self.status_assinatura = 'ATIVO'
            self.save()
             
        return False
        
    def registrar_acesso(self):
        """Chamado pelo Middleware para atualizar que a loja está viva"""
        self.ultimo_acesso = timezone.now()
        # update_fields é mais leve, atualiza só essa coluna
        self.save(update_fields=['ultimo_acesso'])


# --- NOVA TABELA: HISTÓRICO DE FATURAS ---
class Fatura(models.Model):
    loja = models.ForeignKey(Loja, on_delete=models.CASCADE, related_name='faturas')
    data_vencimento = models.DateField()
    valor = models.DecimalField(max_digits=10, decimal_places=2)
    pago = models.BooleanField(default=False)
    data_pagamento = models.DateField(null=True, blank=True)
    comprovante_url = models.URLField(null=True, blank=True, help_text="Link do comprovante ou PDF")
    
    def __str__(self):
        return f"Fatura {self.loja.nome} - {self.data_vencimento}"


class PerfilUsuario(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='perfil')
    loja = models.ForeignKey(Loja, on_delete=models.CASCADE, null=True, blank=True)
    telefone = models.CharField(max_length=20, null=True, blank=True)
    perm_dashboard = models.BooleanField(default=False, verbose_name="Acessar Dashboard (Faturamento)")
    perm_pdv = models.BooleanField(default=True, verbose_name="Acessar PDV (Vender)")
    perm_caixa = models.BooleanField(default=False, verbose_name="Gerenciar Caixa")
    perm_torre = models.BooleanField(default=False, verbose_name="Torre de Controle")
    perm_estoque = models.BooleanField(default=False, verbose_name="Modificar Estoque/Produtos")
    perm_relatorios = models.BooleanField(default=False, verbose_name="Ver Relatórios")
    perm_usuarios = models.BooleanField(default=False, verbose_name="Gerenciar Usuários")
    conta_congelada = models.BooleanField(
        default=False,
        verbose_name="Conta congelada",
        help_text="Bloqueia login até descongelar pelo Admin.",
    )
    motivo_congelamento = models.CharField(max_length=255, blank=True, default='')
    congelada_em = models.DateTimeField(null=True, blank=True)
    tentativas_login_falhas = models.PositiveIntegerField(default=0)
    session_key_ativa = models.CharField(max_length=40, null=True, blank=True)
    token_ativo = models.CharField(
        max_length=64, null=True, blank=True,
        verbose_name="Token API ativo (sessão única mobile)",
    )

    def __str__(self): return f"{self.user.username} - {self.loja}"


class BloqueioIPLogin(models.Model):
    """Rate limit de login por IP (5 falhas → bloqueio temporário)."""
    ip = models.GenericIPAddressField(unique=True)
    tentativas = models.PositiveIntegerField(default=0)
    bloqueado_ate = models.DateTimeField(null=True, blank=True)
    ultima_tentativa = models.DateTimeField(auto_now=True)
    ultimo_usuario_tentado = models.CharField(max_length=150, blank=True, default='')
    observacao = models.CharField(max_length=255, blank=True, default='')

    class Meta:
        verbose_name = 'Bloqueio de IP (login)'
        verbose_name_plural = 'Bloqueios de IP (login)'
        ordering = ['-ultima_tentativa']

    def __str__(self):
        return f"{self.ip} ({self.tentativas} tent.)"

    @property
    def esta_bloqueado(self):
        from django.utils import timezone
        return bool(self.bloqueado_ate and self.bloqueado_ate > timezone.now())

# --- SINAIS ---
@receiver(post_save, sender=User)
def criar_perfil_usuario(sender, instance, created, **kwargs):
    if created:
        PerfilUsuario.objects.get_or_create(user=instance)

@receiver(post_save, sender=User)
def salvar_perfil_usuario(sender, instance, **kwargs):
    if hasattr(instance, 'perfil'):
        instance.perfil.save()


# 2. ------------------------Fornecedores / Item ------------------------
class Fornecedor(models.Model):
    loja = models.ForeignKey(Loja, on_delete=models.CASCADE) 
    nome = models.CharField(max_length=100)
    contato = models.CharField(max_length=50)
    
    def __str__(self): return self.nome

class ItemEstoque(models.Model):
    loja = models.ForeignKey(Loja, on_delete=models.CASCADE) 
    nome = models.CharField(max_length=150, verbose_name="Nome do Item")
    quantidade_estoque = models.DecimalField(max_digits=10, decimal_places=3, default=0.000)
    quantidade_vazios = models.DecimalField(
        max_digits=10, decimal_places=3, default=0.000,
        verbose_name="Vasilhame vazio (botijões/galões)"
    )
    
    unidade_medida = models.CharField(max_length=2, choices=UNIDADE_MEDIDA_CHOICES, default='UN', verbose_name="Unidade de Medida")
    data_validade = models.DateField(null=True, blank=True, verbose_name="Data de Validade")
    observacao = models.CharField(max_length=255, null=True, blank=True, verbose_name="Lote / Observação")

    class Meta:
        ordering = ['nome'] 
        unique_together = ('loja', 'nome') 

    def __str__(self): return f"{self.nome} ({self.get_unidade_medida_display()})"
    
    @property
    def estoque_formatado(self):
        """Retorna o número limpo (sem decimais) para UN, ou com 3 casas para KG/L"""
        if self.unidade_medida == 'UN':
            # Converte para inteiro (tira o ,000) e adiciona 'UN'
            return f"{int(self.quantidade_estoque)} UN"
        else:
            # Mantém 3 casas decimais, troca ponto por vírgula e adiciona a sigla (KG ou L)
            valor = f"{self.quantidade_estoque:.3f}".replace('.', ',')
            return f"{valor} {self.unidade_medida}"

    @property
    def estoque_formatado_curto(self):
        """
        Formato para UI: remove zeros à direita em KG/L (sem mudar a precisão real no banco).
        Exemplos: 450,000 KG -> 450 KG | 427,500 KG -> 427,5 KG | 1,250 L -> 1,25 L
        """
        if self.unidade_medida == 'UN':
            return f"{int(self.quantidade_estoque)} UN"

        valor = f"{self.quantidade_estoque:.3f}".rstrip('0').rstrip('.')
        valor = valor.replace('.', ',')
        return f"{valor} {self.unidade_medida}"

    @property
    def vazios_formatado_curto(self):
        if self.unidade_medida == 'UN':
            return f"{int(self.quantidade_vazios)} UN"
        valor = f"{self.quantidade_vazios:.3f}".rstrip('0').rstrip('.')
        valor = valor.replace('.', ',')
        return f"{valor} {self.unidade_medida}"


def baixar_produto_completo_item(item_estoque, quantidade):
    """Venda completa: baixa apenas cheios, sem incrementar vazios."""
    qtd = Decimal(str(quantidade))
    item_estoque.quantidade_estoque -= qtd
    item_estoque.save(update_fields=['quantidade_estoque'])


def devolver_produto_completo_item(item_estoque, quantidade):
    qtd = Decimal(str(quantidade))
    item_estoque.quantidade_estoque += qtd
    item_estoque.save(update_fields=['quantidade_estoque'])


def baixar_estoque_item(item_estoque, quantidade):
    """Baixa estoque cheio e, se a loja controla vasilhame, incrementa vazios."""
    qtd = Decimal(str(quantidade))
    item_estoque.quantidade_estoque -= qtd
    update_fields = ['quantidade_estoque']
    if item_estoque.loja.controla_vasilhame_vazio:
        item_estoque.quantidade_vazios += qtd
        update_fields.append('quantidade_vazios')
    item_estoque.save(update_fields=update_fields)


def devolver_estoque_item(item_estoque, quantidade):
    """Estorna baixa de estoque cheio e decrementa vazios quando aplicável."""
    qtd = Decimal(str(quantidade))
    item_estoque.quantidade_estoque += qtd
    update_fields = ['quantidade_estoque']
    if item_estoque.loja.controla_vasilhame_vazio:
        item_estoque.quantidade_vazios = max(Decimal('0'), item_estoque.quantidade_vazios - qtd)
        update_fields.append('quantidade_vazios')
    item_estoque.save(update_fields=update_fields)


def baixar_vasilhame_vazio_item(item_estoque, quantidade):
    """Baixa apenas o estoque de vasilhames vazios (venda de botijão/galão vazio)."""
    if not item_estoque.loja.controla_vasilhame_vazio:
        return
    qtd = Decimal(str(quantidade))
    item_estoque.quantidade_vazios = max(Decimal('0'), item_estoque.quantidade_vazios - qtd)
    item_estoque.save(update_fields=['quantidade_vazios'])


def devolver_vasilhame_vazio_item(item_estoque, quantidade):
    """Estorna baixa de vasilhame vazio."""
    if not item_estoque.loja.controla_vasilhame_vazio:
        return
    qtd = Decimal(str(quantidade))
    item_estoque.quantidade_vazios += qtd
    item_estoque.save(update_fields=['quantidade_vazios'])


def estoque_diario_ativo(loja):
    """Estoque diário híbrido: contagem manual + movimentação automática nas vendas."""
    return bool(getattr(loja, 'estoque_diario', False) and loja.controla_vasilhame_vazio)


def produtos_disponiveis_pdv(loja):
    """Produtos exibidos no PDV: cheios com estoque, vazios ou kits com componentes disponíveis."""
    qs = Produto.objects.filter(loja=loja).select_related('item_estoque').prefetch_related(
        'componentes_kit__item_estoque'
    )
    if loja.controla_vasilhame_vazio:
        base = qs.filter(
            Q(eh_kit=True) |
            Q(item_estoque__quantidade_estoque__gt=0) |
            Q(vende_vasilhame_vazio=True, item_estoque__quantidade_vazios__gt=0)
        )
    else:
        base = qs.filter(Q(eh_kit=True) | Q(item_estoque__quantidade_estoque__gt=0))

    disponiveis = []
    for produto in base:
        if produto.eh_kit:
            if validar_estoque_kit(produto, 1) is None:
                disponiveis.append(produto.pk)
        else:
            disponiveis.append(produto.pk)
    return qs.filter(pk__in=disponiveis)


def produto_baixa_apenas_vasilhame_vazio(produto):
    """
    True somente para produto dedicado à venda de vasilhame vazio.
    Exige par no mesmo item: outro produto com vende_vasilhame_vazio=False (cheio).
    Se só existir um produto marcado como vazio (ex.: Gas Super), trata como venda cheia.
    """
    if produto.eh_kit or not produto.item_estoque_id:
        return False
    loja = produto.item_estoque.loja
    if not (produto.vende_vasilhame_vazio and loja.controla_vasilhame_vazio):
        return False
    return Produto.objects.filter(
        item_estoque_id=produto.item_estoque_id,
        vende_vasilhame_vazio=False,
    ).exists()


def validar_estoque_item_venda(loja, produto, quantidade_vendida, venda_completa=False):
    """Retorna mensagem de erro se não houver estoque; None se OK."""
    if produto.eh_kit:
        return validar_estoque_kit(produto, quantidade_vendida)

    if not produto.item_estoque_id:
        return f'Produto "{produto.nome_venda}" sem item de estoque vinculado.'

    baixa = Decimal(str(quantidade_vendida)) * produto.quantidade_baixa
    item = produto.item_estoque
    if venda_completa and not produto_baixa_apenas_vasilhame_vazio(produto):
        if item.quantidade_estoque < baixa:
            return (
                f'Estoque insuficiente para venda completa de "{produto.nome_venda}". '
                f'Disponível: {item.quantidade_estoque}'
            )
    elif produto_baixa_apenas_vasilhame_vazio(produto):
        if item.quantidade_vazios < baixa:
            return (
                f'Estoque insuficiente de vasilhame vazio para "{produto.nome_venda}". '
                f'Disponível: {item.vazios_formatado_curto}'
            )
    elif item.quantidade_estoque < baixa:
        return (
            f'Estoque insuficiente para "{produto.nome_venda}". '
            f'Disponível: {item.quantidade_estoque}'
        )
    return None


def _item_baixa_vasilhame_vazio(item_venda):
    if getattr(item_venda, 'baixa_vasilhame_vazio', False):
        return True
    return produto_baixa_apenas_vasilhame_vazio(item_venda.produto)


def _item_venda_completa(item_venda):
    return bool(getattr(item_venda, 'venda_completa', False))


def aplicar_baixa_item_venda(item_venda, quantidade_baixa):
    produto = item_venda.produto
    if produto.eh_kit:
        aplicar_baixa_kit(produto, quantidade_baixa)
        return
    item = produto.item_estoque
    if _item_baixa_vasilhame_vazio(item_venda):
        baixar_vasilhame_vazio_item(item, quantidade_baixa)
    elif _item_venda_completa(item_venda):
        baixar_produto_completo_item(item, quantidade_baixa)
    else:
        baixar_estoque_item(item, quantidade_baixa)


def aplicar_devolucao_item_venda(item_venda, quantidade_baixa):
    produto = item_venda.produto
    if produto.eh_kit:
        aplicar_devolucao_kit(produto, quantidade_baixa)
        return
    item = produto.item_estoque
    if _item_baixa_vasilhame_vazio(item_venda):
        devolver_vasilhame_vazio_item(item, quantidade_baixa)
    elif _item_venda_completa(item_venda):
        devolver_produto_completo_item(item, quantidade_baixa)
    else:
        devolver_estoque_item(item, quantidade_baixa)


def ajustar_estoque_item_venda(item_venda, delta_quantidade_vendida):
    delta = Decimal(str(delta_quantidade_vendida))
    if delta == 0:
        return
    if item_venda.produto.eh_kit:
        alterar = abs(delta)
    else:
        alterar = abs(delta) * item_venda.produto.quantidade_baixa
    if delta > 0:
        aplicar_baixa_item_venda(item_venda, alterar)
    else:
        aplicar_devolucao_item_venda(item_venda, alterar)


def ajustar_estoque_item(item_estoque, delta_quantidade):
    """Ajuste por diferença de quantidade (delta positivo = mais baixa)."""
    delta = Decimal(str(delta_quantidade))
    if delta > 0:
        baixar_estoque_item(item_estoque, delta)
    elif delta < 0:
        devolver_estoque_item(item_estoque, abs(delta))

# 3. ---------------------------------------Produtos ----------------------------
class GrupoProduto(models.Model):
    loja = models.ForeignKey(Loja, on_delete=models.CASCADE, related_name='grupos_produto')
    nome = models.CharField(max_length=100)
    ordem = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = 'Grupo de Produto'
        verbose_name_plural = 'Grupos de Produto'
        ordering = ['ordem', 'nome']
        unique_together = ('loja', 'nome')

    def __str__(self):
        return self.nome


class Produto(models.Model):
    loja = models.ForeignKey(Loja, on_delete=models.CASCADE) 
    item = models.OneToOneField(ItemEstoque, on_delete=models.CASCADE, related_name="produto_principal", null=True, blank=True)
    item_estoque = models.ForeignKey(
        ItemEstoque, on_delete=models.CASCADE, verbose_name="Item do Estoque",
        related_name="produtos_venda", null=True, blank=True,
    )
    grupo = models.ForeignKey(
        GrupoProduto, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='produtos', verbose_name='Grupo',
    )
    nome_venda = models.CharField(max_length=150, verbose_name="Nome na Venda (Ex: Pack, Promoção)")
    codigo_barras = models.CharField(
        max_length=50, blank=True, default='',
        verbose_name="Código de barras (EAN/GTIN)",
        help_text="Lido pelo leitor USB na tela de vendas (quando a loja usa leitor de código de barras).",
    )
    preco_compra = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, verbose_name="Preço de Custo (Unitário)")
    preco_venda = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    preco_venda_completo = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        verbose_name="Preço venda completa (cheio+vasilhame)",
        help_text="Opcional. Se vazio, usa preço cheio + produto vazio do mesmo item.",
    )
    quantidade_baixa = models.DecimalField(max_digits=10, decimal_places=3, default=1.000, verbose_name="Qtd retirada do estoque (ex: 12 p/ Pack, 1.5 p/ KG)")
    fornecedor = models.ForeignKey(Fornecedor, on_delete=models.SET_NULL, null=True, blank=True)
    imagem = models.ImageField(upload_to='produtos/', null=True, blank=True)
    ativo = models.BooleanField(default=True, verbose_name="Disponível no App?") 
    foto = models.ImageField(upload_to='produtos/', null=True, blank=True)
    vende_vasilhame_vazio = models.BooleanField(
        default=False,
        verbose_name="Vende vasilhame vazio",
        help_text="Produto de venda de botijão/galão vazio. Baixa apenas o estoque de vazios.",
    )
    rastrear_recompra = models.BooleanField(
        default=False,
        verbose_name="Rastrear recompra deste produto?",
        help_text="Exibe alerta no dashboard quando o cliente passar dos dias configurados sem comprar.",
    )
    usa_venda_completa = models.BooleanField(
        default=False,
        verbose_name="Venda completa (gás + vasilhame, sem troca)?",
        help_text="Baixa apenas estoque cheio, sem incrementar vazios. Use preço venda completa abaixo.",
    )
    dias_recompra = models.IntegerField(
        null=True, blank=True,
        verbose_name="Dias sem compra para alerta",
        help_text="Ex.: 5 para água, 30 para gás. Deixe vazio para não rastrear.",
    )
    mensagem_recompra = models.TextField(
        blank=True, default='Olá {cliente}, sua {produto} está acabando. Gostaria de fazer um novo pedido?',
        verbose_name="Mensagem WhatsApp de recompra",
        help_text="Placeholders: {cliente}, {produto}, {dias}",
    )
    eh_kit = models.BooleanField(
        default=False,
        verbose_name="Produto kit / promoção?",
        help_text="Ao vender, baixa automaticamente vários itens de estoque conforme os componentes do kit.",
    )

    def baixa_apenas_vasilhame_vazio(self):
        return produto_baixa_apenas_vasilhame_vazio(self)

    def estoque_kits_disponiveis(self):
        return estoque_disponivel_kit(self)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['loja', 'codigo_barras'],
                condition=~models.Q(codigo_barras=''),
                name='produto_codigo_barras_unico_por_loja',
            ),
        ]

    def __str__(self): return self.nome_venda


class ComponenteKit(models.Model):
    """Itens de estoque consumidos ao vender um produto kit/promoção."""
    produto_kit = models.ForeignKey(
        Produto, on_delete=models.CASCADE, related_name='componentes_kit',
        verbose_name='Produto kit',
    )
    item_estoque = models.ForeignKey(
        ItemEstoque, on_delete=models.CASCADE, related_name='kits_que_usam',
        verbose_name='Item de estoque',
    )
    quantidade = models.DecimalField(
        max_digits=10, decimal_places=3, default=1.000,
        verbose_name='Qtd por kit vendido',
    )
    ordem = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = 'Componente do kit'
        verbose_name_plural = 'Componentes do kit'
        ordering = ['ordem', 'id']
        unique_together = ('produto_kit', 'item_estoque')

    def __str__(self):
        return f'{self.quantidade}× {self.item_estoque.nome}'


def custo_medio_unitario_item_estoque(item_estoque):
    """Custo médio por unidade do item (a partir dos produtos de venda normais)."""
    custos = []
    for produto in Produto.objects.filter(item_estoque=item_estoque, eh_kit=False):
        qb = Decimal(str(produto.quantidade_baixa or 1))
        if qb <= 0:
            qb = Decimal('1')
        if produto.preco_compra:
            custos.append(Decimal(str(produto.preco_compra)) / qb)
    if custos:
        return (sum(custos) / len(custos)).quantize(Decimal('0.0001'))
    pf = PrecoFornecedorItem.objects.filter(item_estoque=item_estoque, ativo=True).first()
    if pf and pf.preco_compra:
        return Decimal(str(pf.preco_compra))
    return Decimal('0')


def recalcular_custo_kit(produto):
    if not produto.eh_kit:
        return
    total = Decimal('0')
    for comp in produto.componentes_kit.select_related('item_estoque'):
        total += comp.quantidade * custo_medio_unitario_item_estoque(comp.item_estoque)
    produto.preco_compra = total.quantize(Decimal('0.01'))
    produto.save(update_fields=['preco_compra'])


def estoque_disponivel_kit(produto):
    """Quantidade máxima de kits montáveis com o estoque atual dos componentes."""
    if not produto.eh_kit:
        return None
    componentes = list(produto.componentes_kit.select_related('item_estoque'))
    if not componentes:
        return Decimal('0')
    disponivel = None
    for comp in componentes:
        qtd_por_kit = Decimal(str(comp.quantidade))
        if qtd_por_kit <= 0:
            continue
        kits_possiveis = (
            comp.item_estoque.quantidade_estoque / qtd_por_kit
        ).to_integral_value(rounding=ROUND_DOWN)
        disponivel = kits_possiveis if disponivel is None else min(disponivel, kits_possiveis)
    return disponivel if disponivel is not None else Decimal('0')


def validar_estoque_kit(produto, quantidade_kits):
    """Valida estoque de todos os componentes. quantidade_kits = unidades do kit vendidas."""
    componentes = list(produto.componentes_kit.select_related('item_estoque'))
    if not componentes:
        return f'Kit "{produto.nome_venda}" não possui componentes cadastrados.'
    qtd_kits = Decimal(str(quantidade_kits))
    for comp in componentes:
        necessario = qtd_kits * comp.quantidade
        disp = comp.item_estoque.quantidade_estoque
        if disp < necessario:
            return (
                f'Estoque insuficiente para o kit "{produto.nome_venda}". '
                f'Item "{comp.item_estoque.nome}": necessário {necessario}, disponível {disp}.'
            )
    return None


def aplicar_baixa_kit(produto, quantidade_kits):
    qtd_kits = Decimal(str(quantidade_kits))
    for comp in produto.componentes_kit.select_related('item_estoque'):
        baixar_estoque_item(comp.item_estoque, qtd_kits * comp.quantidade)


def aplicar_devolucao_kit(produto, quantidade_kits):
    qtd_kits = Decimal(str(quantidade_kits))
    for comp in produto.componentes_kit.select_related('item_estoque'):
        devolver_estoque_item(comp.item_estoque, qtd_kits * comp.quantidade)


def custo_unitario_produto_venda(produto):
    if produto.eh_kit:
        total = Decimal('0')
        for comp in produto.componentes_kit.select_related('item_estoque'):
            total += comp.quantidade * custo_medio_unitario_item_estoque(comp.item_estoque)
        return total.quantize(Decimal('0.01'))
    return produto.preco_compra or Decimal('0')


class PrecoFornecedorItem(models.Model):
    loja = models.ForeignKey(Loja, on_delete=models.CASCADE)
    item_estoque = models.ForeignKey(
        ItemEstoque, on_delete=models.CASCADE, related_name='precos_fornecedor'
    )
    fornecedor = models.ForeignKey(
        Fornecedor, on_delete=models.CASCADE, related_name='precos_itens'
    )
    preco_compra = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00,
        verbose_name="Preço de custo (unitário do item)"
    )
    ativo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Preço por Fornecedor"
        verbose_name_plural = "Preços por Fornecedor"
        unique_together = ('item_estoque', 'fornecedor')
        ordering = ['fornecedor__nome']

    def __str__(self):
        return f"{self.item_estoque.nome} — {self.fornecedor.nome}: R$ {self.preco_compra}"


def recalcular_custo_medio_produtos(item_estoque, estoque_anterior, qtd_entrada, preco_unitario_entrada):
    """Atualiza preco_compra (custo médio ponderado) de todos os produtos do item."""
    preco_entrada = Decimal(str(preco_unitario_entrada or 0))
    qtd = Decimal(str(qtd_entrada or 0))
    estoque_ant = Decimal(str(estoque_anterior or 0))

    if preco_entrada <= 0 or qtd <= 0:
        return

    for produto in Produto.objects.filter(item_estoque=item_estoque):
        qb = Decimal(str(produto.quantidade_baixa or 1))
        if qb <= 0:
            qb = Decimal('1')

        if estoque_ant <= 0:
            custo_medio_item = preco_entrada
        else:
            custo_ant_item = Decimal(str(produto.preco_compra or 0)) / qb
            estoque_total = estoque_ant + qtd
            custo_medio_item = (estoque_ant * custo_ant_item + qtd * preco_entrada) / estoque_total

        produto.preco_compra = (custo_medio_item * qb).quantize(Decimal('0.01'))
        produto.save(update_fields=['preco_compra'])


# 4. -----------------------------Clientes-----------------------------------------
class Cliente(models.Model):
    loja = models.ForeignKey(Loja, on_delete=models.CASCADE) 
    nome = models.CharField(max_length=100)
    telefone = models.CharField(max_length=20, blank=True, null=True)
    whatsapp = models.CharField(max_length=20, blank=True, null=True)
    endereco = models.TextField(blank=True, null=True)
    bairro = models.CharField(max_length=100, blank=True, null=True, verbose_name="Bairro")
    pontos_fidelidade = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        verbose_name="Pontos de fidelidade acumulados",
    )
    progresso_fidelidade = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        verbose_name="Progresso até próxima promoção",
    )
    promocao_fidelidade_ativa = models.BooleanField(
        default=False,
        verbose_name="Promoção de fidelidade disponível?",
    )
    
    def __str__(self): return self.nome

    # --- ROBÔ INVISÍVEL: COPIA TELEFONE PARA WHATSAPP SE ESTIVER VAZIO ---
    def save(self, *args, **kwargs):
        if self.telefone and not self.whatsapp:
            self.whatsapp = self.telefone
        super(Cliente, self).save(*args, **kwargs)

# 4b. ---------------------- Formas de Pagamento por Loja (SaaS) ----------------------
class FormaPagamentoLoja(models.Model):
    loja = models.ForeignKey(Loja, on_delete=models.CASCADE, related_name='formas_pagamento')
    nome = models.CharField(max_length=50, verbose_name="Nome exibido")
    codigo = models.SlugField(max_length=30, verbose_name="Código interno")
    cor = models.CharField(max_length=7, default='#9c27b0', verbose_name="Cor (hex)")
    icone = models.CharField(max_length=50, default='fa-wallet', verbose_name="Ícone FontAwesome")
    eh_sistema = models.BooleanField(default=False, verbose_name="Forma padrão do sistema?")
    exige_conferencia = models.BooleanField(
        default=False,
        verbose_name="Exige conferência de troco?",
        help_text="Se marcado, exibe campo de troco na venda e botão 'Receber' no histórico."
    )
    ativo = models.BooleanField(default=True)
    ordem = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Forma de Pagamento"
        verbose_name_plural = "Formas de Pagamento"
        unique_together = ('loja', 'codigo')
        ordering = ['ordem', 'nome']

    def __str__(self):
        return f"{self.nome} ({self.loja.nome})"

    def save(self, *args, **kwargs):
        if not self.codigo:
            self.codigo = slugify(self.nome).replace('-', '_')[:30]
        super().save(*args, **kwargs)


def criar_formas_pagamento_padrao(loja):
    for padrao in FORMAS_PAGAMENTO_PADRAO:
        FormaPagamentoLoja.objects.get_or_create(
            loja=loja,
            codigo=padrao['codigo'],
            defaults={
                'nome': padrao['nome'],
                'cor': padrao['cor'],
                'icone': padrao['icone'],
                'ordem': padrao['ordem'],
                'eh_sistema': True,
                'exige_conferencia': padrao.get('exige_conferencia', False),
                'ativo': True,
            }
        )


def get_nome_forma_pagamento(loja, codigo):
    if not codigo:
        return 'Não informado'
    forma = FormaPagamentoLoja.objects.filter(loja=loja, codigo=codigo).first()
    if forma:
        return forma.nome
    return dict(FORMA_PGTO_CHOICES).get(codigo, codigo)


def validar_forma_pagamento(loja, codigo):
    if not codigo:
        return False
    return FormaPagamentoLoja.objects.filter(loja=loja, codigo=codigo, ativo=True).exists()


def forma_exige_conferencia(loja, codigo):
    if not codigo:
        return False
    forma = FormaPagamentoLoja.objects.filter(loja=loja, codigo=codigo).first()
    if forma:
        return forma.exige_conferencia
    return codigo.upper() == 'DINHEIRO'


def validar_meio_liquidacao(codigo):
    return codigo in dict(MEIO_LIQUIDACAO_CHOICES)


def get_nome_meio_liquidacao(codigo):
    if not codigo:
        return 'Não informado'
    return dict(MEIO_LIQUIDACAO_VENDA_CHOICES).get(codigo, codigo)


def validar_liquidacoes_payload(total_venda, liquidacoes, exige_multiplo=False):
    """Valida lista de parcelas [{meio_liquidacao, valor, troco_para?}]."""
    if not liquidacoes:
        return 'Informe ao menos uma forma de pagamento.'
    if exige_multiplo and len(liquidacoes) < 2:
        return 'Pagamento dividido exige ao menos 2 formas de liquidação.'

    total_venda = Decimal(str(total_venda or 0))
    soma = Decimal('0')
    meios_usados = set()

    for item in liquidacoes:
        meio = item.get('meio_liquidacao')
        if not validar_meio_liquidacao(meio):
            return f'Meio de liquidação inválido: {meio}'
        if meio in meios_usados:
            return 'Não repita o mesmo meio de liquidação na mesma venda.'
        meios_usados.add(meio)

        try:
            valor = Decimal(str(item.get('valor', 0) or 0))
        except Exception:
            return 'Valor de parcela inválido.'
        if valor <= 0:
            return 'Cada parcela deve ter valor maior que zero.'
        soma += valor

    if abs(soma - total_venda) > Decimal('0.01'):
        return f'Soma das parcelas (R$ {soma:.2f}) difere do total da venda (R$ {total_venda:.2f}).'
    return None


def persistir_liquidacoes_venda(venda, liquidacoes, caixa=None, usuario=None):
    """Substitui parcelas da venda e sincroniza campos-resumo em Venda."""
    venda.liquidacoes.all().delete()
    tem_dinheiro = False

    for item in liquidacoes:
        meio = item['meio_liquidacao']
        valor = Decimal(str(item['valor']))
        troco = item.get('troco_para')
        troco_decimal = None
        if meio == 'DINHEIRO' and troco not in (None, '', 0, '0', '0.00'):
            troco_decimal = Decimal(str(troco))
            tem_dinheiro = True
        elif meio == 'DINHEIRO':
            tem_dinheiro = True

        conferencia_ok = meio != 'DINHEIRO'
        LiquidacaoVenda.objects.create(
            loja=venda.loja,
            venda=venda,
            valor=valor,
            meio_liquidacao=meio,
            troco_para=troco_decimal,
            conferencia_ok=conferencia_ok,
            registrado_por=usuario,
            caixa=caixa,
        )

    dividido = len(liquidacoes) > 1
    venda.pagamento_dividido = dividido
    if dividido:
        venda.meio_liquidacao = 'MISTO'
        venda.troco_para = None
    else:
        unica = liquidacoes[0]
        venda.meio_liquidacao = unica['meio_liquidacao']
        venda.troco_para = (
            Decimal(str(unica['troco_para'])) if unica['meio_liquidacao'] == 'DINHEIRO' and unica.get('troco_para') else None
        )

    if tem_dinheiro:
        pendente = venda.liquidacoes.filter(meio_liquidacao='DINHEIRO', conferencia_ok=False).exists()
        venda.conferencia_ok = not pendente
    else:
        venda.conferencia_ok = True

    venda.save(update_fields=['pagamento_dividido', 'meio_liquidacao', 'troco_para', 'conferencia_ok'])
    return venda


def _totais_liquidacao_por_meio(vendas_qs, pagamentos_fiado_qs=None):
    from django.db.models import Sum

    totais = {m['codigo']: Decimal('0') for m in MEIOS_LIQUIDACAO_PADRAO}
    venda_ids = list(vendas_qs.values_list('id', flat=True))

    if venda_ids:
        for row in LiquidacaoVenda.objects.filter(venda_id__in=venda_ids).values('meio_liquidacao').annotate(
            total=Sum('valor')
        ):
            codigo = row['meio_liquidacao']
            if codigo in totais:
                totais[codigo] += row['total'] or Decimal('0')

        vendas_com_parcelas = LiquidacaoVenda.objects.filter(
            venda_id__in=venda_ids
        ).values_list('venda_id', flat=True).distinct()
        legacy = vendas_qs.exclude(id__in=vendas_com_parcelas).exclude(meio_liquidacao='MISTO')
        for meio in MEIOS_LIQUIDACAO_PADRAO:
            codigo = meio['codigo']
            leg = legacy.filter(meio_liquidacao=codigo).aggregate(Sum('total'))['total__sum'] or 0
            totais[codigo] += leg

    if pagamentos_fiado_qs is not None:
        for row in pagamentos_fiado_qs.values('meio_liquidacao').annotate(total=Sum('valor')):
            codigo = row['meio_liquidacao']
            if codigo in totais:
                totais[codigo] += row['total'] or Decimal('0')

    return totais


def montar_resumo_liquidacao_loja(vendas_qs, pagamentos_fiado_qs=None, pagamentos_mercadoria_qs=None):
    totais = _totais_liquidacao_por_meio(vendas_qs, pagamentos_fiado_qs)
    if pagamentos_mercadoria_qs is not None:
        from django.db.models import Sum
        for meio in MEIOS_LIQUIDACAO_PADRAO:
            codigo = meio['codigo']
            saida = pagamentos_mercadoria_qs.filter(
                meio_liquidacao=codigo
            ).aggregate(Sum('valor'))['valor__sum'] or Decimal('0')
            totais[codigo] = totais.get(codigo, Decimal('0')) - Decimal(str(saida))
    return [
        {
            'nome': meio['nome'],
            'codigo': meio['codigo'],
            'cor': meio['cor'],
            'icone': meio['icone'],
            'total': totais.get(meio['codigo'], Decimal('0')),
        }
        for meio in MEIOS_LIQUIDACAO_PADRAO
    ]


def calcular_entradas_gaveta(vendas_qs, pagamentos_fiado_qs=None, pagamentos_mercadoria_qs=None):
    from django.db.models import Sum

    venda_ids = list(vendas_qs.values_list('id', flat=True))
    dinheiro = Decimal('0')

    if venda_ids:
        dinheiro += LiquidacaoVenda.objects.filter(
            venda_id__in=venda_ids,
            meio_liquidacao='DINHEIRO',
            conferencia_ok=True,
        ).aggregate(Sum('valor'))['valor__sum'] or Decimal('0')

        vendas_com_parcelas = LiquidacaoVenda.objects.filter(
            venda_id__in=venda_ids
        ).values_list('venda_id', flat=True).distinct()
        dinheiro += vendas_qs.filter(
            meio_liquidacao='DINHEIRO',
            conferencia_ok=True,
        ).exclude(id__in=vendas_com_parcelas).aggregate(Sum('total'))['total__sum'] or Decimal('0')

    if pagamentos_fiado_qs is not None:
        dinheiro += pagamentos_fiado_qs.filter(
            meio_liquidacao='DINHEIRO'
        ).aggregate(Sum('valor'))['valor__sum'] or Decimal('0')

    if pagamentos_mercadoria_qs is not None:
        dinheiro -= pagamentos_mercadoria_qs.filter(
            meio_liquidacao='DINHEIRO'
        ).aggregate(Sum('valor'))['valor__sum'] or Decimal('0')

    return dinheiro


def _adicionar_valor_bucket(buckets, key, forma, multi_loja, valor, qtd=0):
    if key not in buckets:
        nome = forma.nome
        if multi_loja and not forma.eh_sistema:
            nome = f"{forma.nome} ({forma.loja.nome})"
        buckets[key] = {
            'nome': nome,
            'cor': forma.cor,
            'icone': forma.icone,
            'codigo': forma.codigo,
            'total': Decimal('0'),
            'qtd': 0,
        }
    buckets[key]['total'] += valor
    buckets[key]['qtd'] += qtd


def _ref_forma_pagamento_venda(venda, formas_map, meio_liquidacao=None):
    """Prioriza tipo de lançamento avulso/customizado sobre meio de liquidação padrão."""
    lid = venda.loja_id
    fp = venda.forma_pagamento
    if fp:
        ref_fp = formas_map.get((lid, fp))
        if ref_fp:
            _, forma = ref_fp
            if not forma.eh_sistema:
                return ref_fp
    if meio_liquidacao:
        ref_ml = formas_map.get((lid, meio_liquidacao))
        if ref_ml:
            return ref_ml
    if fp:
        return formas_map.get((lid, fp))
    return None


def montar_resumo_pagamentos_loja(loja, vendas_qs):
    formas = FormaPagamentoLoja.objects.filter(loja=loja, ativo=True).order_by('ordem', 'nome')
    buckets = {}
    formas_map = {(f.loja_id, f.codigo): (f.codigo, f) for f in formas}

    for venda in vendas_qs.select_related('loja').prefetch_related('liquidacoes'):
        if venda.liquidacoes.exists():
            for liq in venda.liquidacoes.all():
                ref = _ref_forma_pagamento_venda(venda, formas_map, liq.meio_liquidacao)
                if ref:
                    key, forma = ref
                    _adicionar_valor_bucket(buckets, key, forma, False, liq.valor)
        else:
            ref = _ref_forma_pagamento_venda(venda, formas_map)
            if ref:
                key, forma = ref
                _adicionar_valor_bucket(buckets, key, forma, False, venda.total or 0)

    return [
        {
            'nome': buckets[k]['nome'],
            'codigo': buckets[k]['codigo'],
            'cor': buckets[k]['cor'],
            'icone': buckets[k]['icone'],
            'total': buckets[k]['total'],
        }
        for k in buckets
    ]


def montar_relatorio_pagamentos(lojas_alvo, vendas_periodo, multi_loja=False):
    formas = FormaPagamentoLoja.objects.filter(loja__in=lojas_alvo, ativo=True).order_by('ordem', 'nome')
    buckets = {}
    formas_map = {}
    for forma in formas:
        key = forma.codigo if (forma.eh_sistema or not multi_loja) else f"{forma.loja_id}_{forma.codigo}"
        formas_map[(forma.loja_id, forma.codigo)] = (key, forma)
        if key not in buckets:
            _adicionar_valor_bucket(buckets, key, forma, multi_loja, Decimal('0'))

    vendas = vendas_periodo.select_related('loja').prefetch_related('liquidacoes')
    for venda in vendas:
        if venda.liquidacoes.exists():
            for liq in venda.liquidacoes.all():
                ref = _ref_forma_pagamento_venda(venda, formas_map, liq.meio_liquidacao)
                if ref:
                    key, forma = ref
                    _adicionar_valor_bucket(buckets, key, forma, multi_loja, liq.valor, qtd=1)
        else:
            ref = _ref_forma_pagamento_venda(venda, formas_map)
            if ref:
                key, forma = ref
                _adicionar_valor_bucket(buckets, key, forma, multi_loja, venda.total or 0, qtd=1)

    lista = list(buckets.values())
    total_geral = sum(item['total'] for item in lista)
    return lista, total_geral


# 5. ---------------------------Vendas e Itens-------------------------------------
class Venda(models.Model):
    loja = models.ForeignKey(Loja, on_delete=models.CASCADE) 
    cliente = models.ForeignKey(Cliente, on_delete=models.SET_NULL, null=True)
    vendedor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True) 
    data_venda = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_VENDA_CHOICES, default='ABERTO')
    origem = models.CharField(max_length=10, choices=ORIGEM_VENDA_CHOICES, default='PDV')
    observacao = models.TextField(blank=True, null=True, verbose_name="Obs do Pedido") 
    forma_pagamento = models.CharField(max_length=30, blank=True, null=True, verbose_name="Tipo de Lançamento")
    meio_liquidacao = models.CharField(
        max_length=20,
        choices=MEIO_LIQUIDACAO_VENDA_CHOICES,
        blank=True,
        null=True,
        verbose_name="Meio de Liquidação",
    )
    pagamento_dividido = models.BooleanField(default=False, verbose_name="Pagamento dividido?")
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    eh_entrega = models.BooleanField(default=False, verbose_name="É Entrega?")
    endereco_entrega = models.TextField(blank=True, null=True)
    taxa_entrega = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    taxa_servico_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=0.00,
        verbose_name="Taxa de serviço (%) aplicada",
    )
    taxa_servico = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00,
        verbose_name="Valor taxa de serviço (R$)",
    )
    troco_para = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    conferencia_ok = models.BooleanField(default=False)
    quem_recebeu = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="recebimentos_caixa")
    status_entrega = models.CharField(max_length=20, choices=STATUS_ENTREGA_CHOICES, default='PENDENTE')
    entregador = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="entregas_realizadas")
    eh_fiado = models.BooleanField(default=False, verbose_name="Venda Fiado?")
    eh_cortesia = models.BooleanField(default=False, verbose_name="Venda Cortesia?")
    eh_avaria = models.BooleanField(default=False, verbose_name="Venda Avaria?")
    desconto_fidelidade = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        verbose_name="Desconto fidelidade aplicado",
    )

    def __str__(self):
        return f"Venda #{self.id} - {self.get_status_display()}"

    def get_nome_forma_pagamento(self):
        return get_nome_forma_pagamento(self.loja, self.forma_pagamento)

    def exige_conferencia_pagamento(self):
        if self.liquidacoes.filter(meio_liquidacao='DINHEIRO', conferencia_ok=False).exists():
            return True
        if self.liquidacoes.exists():
            return False
        return self.meio_liquidacao == 'DINHEIRO' and not self.conferencia_ok

    def confirmar_conferencia_dinheiro(self, usuario):
        """Marca parcelas em dinheiro (ou venda legada) como conferidas."""
        parcelas = self.liquidacoes.filter(meio_liquidacao='DINHEIRO', conferencia_ok=False)
        if parcelas.exists():
            parcelas.update(conferencia_ok=True)
            pendente = self.liquidacoes.filter(meio_liquidacao='DINHEIRO', conferencia_ok=False).exists()
            self.conferencia_ok = not pendente
        elif self.meio_liquidacao == 'DINHEIRO':
            self.conferencia_ok = True
        else:
            return False
        self.quem_recebeu = usuario
        self.save(update_fields=['conferencia_ok', 'quem_recebeu'])
        return True

    def get_nome_meio_liquidacao(self):
        return get_nome_meio_liquidacao(self.meio_liquidacao)

    def get_resumo_liquidacao_display(self):
        parcelas = list(self.liquidacoes.all())
        if len(parcelas) > 1:
            partes = []
            for p in parcelas:
                partes.append(f"{get_nome_meio_liquidacao(p.meio_liquidacao)} R$ {p.valor:.2f}")
            return ' + '.join(partes)
        if len(parcelas) == 1:
            return get_nome_meio_liquidacao(parcelas[0].meio_liquidacao)
        return self.get_nome_meio_liquidacao()

    @property
    def valor_pago_fiado(self):
        from django.db.models import Sum
        return self.pagamentos_fiado.aggregate(Sum('valor'))['valor__sum'] or Decimal('0')

    @property
    def saldo_devedor(self):
        return max(Decimal(str(self.total or 0)) - self.valor_pago_fiado, Decimal('0'))

    @property
    def qtd_itens_vendidos(self):
        from django.db.models import Sum
        return self.itens.aggregate(Sum('quantidade'))['quantidade__sum'] or Decimal('0')

    def registrar_pagamento_fiado(self, valor, meio_liquidacao=None, observacao='', usuario=None, caixa=None):
        valor = Decimal(str(valor or 0))
        if valor <= 0:
            raise ValueError('Valor do pagamento deve ser maior que zero.')
        if valor > self.saldo_devedor:
            raise ValueError('Valor maior que o saldo devedor.')
        pagamento = PagamentoFiado.objects.create(
            loja=self.loja,
            venda=self,
            valor=valor,
            meio_liquidacao=meio_liquidacao or 'DINHEIRO',
            observacao=observacao,
            registrado_por=usuario,
            caixa=caixa,
        )
        if self.saldo_devedor <= 0:
            self.status = 'FINALIZADO'
            if meio_liquidacao:
                self.meio_liquidacao = meio_liquidacao
            self.save(update_fields=['status', 'meio_liquidacao'])
        return pagamento


class PagamentoFiado(models.Model):
    loja = models.ForeignKey(Loja, on_delete=models.CASCADE)
    venda = models.ForeignKey('Venda', on_delete=models.CASCADE, related_name='pagamentos_fiado')
    valor = models.DecimalField(max_digits=10, decimal_places=2)
    data_pagamento = models.DateTimeField(auto_now_add=True)
    meio_liquidacao = models.CharField(
        max_length=20, choices=MEIO_LIQUIDACAO_CHOICES, default='DINHEIRO',
        verbose_name="Meio de liquidação"
    )
    observacao = models.CharField(max_length=200, blank=True, null=True)
    registrado_por = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='pagamentos_fiado_registrados'
    )
    caixa = models.ForeignKey(
        'Caixa', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='pagamentos_fiado', verbose_name='Turno de caixa'
    )

    class Meta:
        verbose_name = "Pagamento Fiado"
        verbose_name_plural = "Pagamentos Fiado"
        ordering = ['-data_pagamento']

    def __str__(self):
        return f"R$ {self.valor} — Venda #{self.venda_id}"


class ParcelaFiadoAgendada(models.Model):
    """Parcela de recebimento agendada para saldo devedor de venda fiado."""

    STATUS_CHOICES = [
        ('AGENDADO', 'Agendado'),
        ('PAGO', 'Pago'),
        ('CANCELADO', 'Cancelado'),
    ]

    loja = models.ForeignKey(Loja, on_delete=models.CASCADE)
    venda = models.ForeignKey(
        'Venda', on_delete=models.CASCADE, related_name='parcelas_fiado_agendadas',
    )
    cliente = models.ForeignKey(
        Cliente, on_delete=models.CASCADE, related_name='parcelas_fiado_agendadas',
    )
    valor = models.DecimalField(max_digits=10, decimal_places=2)
    data_vencimento = models.DateField(verbose_name='Vencimento')
    data_entrada = models.DateTimeField(auto_now_add=True, verbose_name='Data de agendamento')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='AGENDADO')
    pagamento = models.ForeignKey(
        PagamentoFiado, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='parcela_agendada',
    )
    observacao = models.CharField(max_length=200, blank=True, null=True)
    criado_por = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='parcelas_fiado_criadas',
    )

    class Meta:
        verbose_name = 'Parcela Fiado Agendada'
        verbose_name_plural = 'Parcelas Fiado Agendadas'
        ordering = ['data_vencimento', 'id']

    def __str__(self):
        return f"Parcela #{self.id} — Venda #{self.venda_id} — R$ {self.valor}"

    @property
    def esta_atrasada(self):
        if self.status != 'AGENDADO':
            return False
        return self.data_vencimento < timezone.localdate()


def total_parcelas_agendadas_venda(venda):
    from django.db.models import Sum
    return venda.parcelas_fiado_agendadas.filter(status='AGENDADO').aggregate(
        total=Sum('valor')
    )['total'] or Decimal('0')


def saldo_agendavel_venda(venda):
    return max(venda.saldo_devedor - total_parcelas_agendadas_venda(venda), Decimal('0'))


class LiquidacaoVenda(models.Model):
    loja = models.ForeignKey(Loja, on_delete=models.CASCADE)
    venda = models.ForeignKey('Venda', on_delete=models.CASCADE, related_name='liquidacoes')
    valor = models.DecimalField(max_digits=10, decimal_places=2)
    meio_liquidacao = models.CharField(
        max_length=20, choices=MEIO_LIQUIDACAO_CHOICES, default='DINHEIRO',
        verbose_name="Meio de liquidação",
    )
    troco_para = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    conferencia_ok = models.BooleanField(default=False)
    data_liquidacao = models.DateTimeField(auto_now_add=True)
    registrado_por = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='liquidacoes_venda_registradas'
    )
    caixa = models.ForeignKey(
        'Caixa', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='liquidacoes_venda', verbose_name='Turno de caixa',
    )

    class Meta:
        verbose_name = "Liquidação de Venda"
        verbose_name_plural = "Liquidações de Venda"
        ordering = ['id']

    def __str__(self):
        return f"R$ {self.valor} ({self.get_meio_liquidacao_display()}) — Venda #{self.venda_id}"


class ItemVenda(models.Model):
    venda = models.ForeignKey(Venda, on_delete=models.CASCADE, related_name="itens") 
    produto = models.ForeignKey(Produto, on_delete=models.CASCADE)
    quantidade = models.DecimalField(max_digits=10, decimal_places=3, default=1.000)
    preco_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    custo_unitario = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00,
        verbose_name="Custo unitário (snapshot na venda)"
    )
    baixa_vasilhame_vazio = models.BooleanField(
        default=False,
        verbose_name="Baixa de vasilhame vazio",
        help_text="Snapshot: esta linha deduziu estoque de vazios, não de cheios.",
    )
    venda_completa = models.BooleanField(
        default=False,
        verbose_name="Venda completa (sem troca de vasilhame)",
    )

    # A FUNÇÃO DEF SAVE() FOI REMOVIDA DAQUI PARA O BEM DO SEU SISTEMA. 
    # ELA FOI SUBSTITUIDA PELOS SIGNALS LÁ NO FINAL DO ARQUIVO.

# 6. ----------------------------------Caixa---------------------------------
class Caixa(models.Model):
    loja = models.ForeignKey(Loja, on_delete=models.CASCADE)
    data = models.DateField(auto_now_add=True) 
    data_hora_abertura = models.DateTimeField(null=True, blank=True)
    data_hora_fechamento = models.DateTimeField(null=True, blank=True)
    saldo_inicial = models.DecimalField(max_digits=10, decimal_places=2)
    saldo_final = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    status = models.BooleanField(default=True) 

    def __str__(self):
        return f"Caixa {self.id} - {self.loja.nome}" 

# 7. ----------------------------------Estoque -------------------------------
class EntradaEstoque(models.Model):
    STATUS_PAGAMENTO_CHOICES = [
        ('QUITADO', 'Quitado'),
        ('PENDENTE', 'A pagar'),
        ('PARCIAL', 'Pago parcial'),
    ]

    loja = models.ForeignKey(Loja, on_delete=models.CASCADE)
    item = models.ForeignKey(ItemEstoque, on_delete=models.CASCADE)
    fornecedor = models.ForeignKey(
        Fornecedor, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name="Fornecedor"
    )
    quantidade = models.DecimalField(max_digits=10, decimal_places=3, default=0.000)
    preco_unitario_compra = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        verbose_name="Preço unitário de compra"
    )
    data_entrada = models.DateTimeField(auto_now_add=True)
    observacao = models.CharField(max_length=200, blank=True, null=True)
    eh_consignado = models.BooleanField(
        default=False,
        verbose_name="Compra consignada (pagar depois)?",
        help_text="Se marcado e a loja gerencia CMV, a entrada fica a pagar até as baixas.",
    )
    valor_total = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        verbose_name="Valor total da compra",
    )
    valor_pago = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        verbose_name="Valor já pago",
    )
    status_pagamento = models.CharField(
        max_length=10, choices=STATUS_PAGAMENTO_CHOICES, default='QUITADO',
        verbose_name="Status do pagamento",
    )

    @property
    def saldo_a_pagar(self):
        saldo = Decimal(str(self.valor_total or 0)) - Decimal(str(self.valor_pago or 0))
        return saldo if saldo > 0 else Decimal('0')

    def recalcular_status_pagamento(self):
        total = Decimal(str(self.valor_total or 0))
        pago = Decimal(str(self.valor_pago or 0))
        if total <= 0 or pago >= total:
            self.status_pagamento = 'QUITADO'
            if pago > total:
                self.valor_pago = total
        elif pago > 0:
            self.status_pagamento = 'PARCIAL'
        else:
            self.status_pagamento = 'PENDENTE'

    def save(self, *args, **kwargs):
        if not self.pk:
            qtd = Decimal(str(self.quantidade or 0))
            preco = Decimal(str(self.preco_unitario_compra or 0))
            self.valor_total = (qtd * preco).quantize(Decimal('0.01'))
            loja = self.loja
            if getattr(loja, 'gerencia_pagamento_mercadorias', False) and self.eh_consignado:
                self.valor_pago = Decimal('0')
                self.status_pagamento = 'PENDENTE' if self.valor_total > 0 else 'QUITADO'
            else:
                self.valor_pago = self.valor_total
                self.status_pagamento = 'QUITADO'
                self.eh_consignado = False

            estoque_anterior = self.item.quantidade_estoque
            vazios_antes = self.item.quantidade_vazios
            self.item.quantidade_estoque += self.quantidade
            update_fields = ['quantidade_estoque']
            if self.item.loja.controla_vasilhame_vazio and self.quantidade > 0:
                consumir = min(vazios_antes, self.quantidade)
                self.item.quantidade_vazios = vazios_antes - consumir
                update_fields.append('quantidade_vazios')
            self.item.save(update_fields=update_fields)
            super().save(*args, **kwargs)
            if self.preco_unitario_compra:
                recalcular_custo_medio_produtos(
                    self.item, estoque_anterior, self.quantidade, self.preco_unitario_compra
                )
        else:
            super().save(*args, **kwargs)

    def registrar_pagamento(self, valor, meio_liquidacao='PIX', observacao='', usuario=None, caixa=None):
        valor = Decimal(str(valor or 0)).quantize(Decimal('0.01'))
        if valor <= 0:
            raise ValueError('Valor do pagamento deve ser maior que zero.')
        saldo = self.saldo_a_pagar
        if valor > saldo:
            raise ValueError(f'Valor maior que o saldo a pagar (R$ {saldo:.2f}).')
        if not validar_meio_liquidacao(meio_liquidacao):
            raise ValueError('Meio de pagamento inválido.')
        pagamento = PagamentoMercadoria.objects.create(
            loja=self.loja,
            entrada=self,
            valor=valor,
            meio_liquidacao=meio_liquidacao,
            observacao=observacao or '',
            registrado_por=usuario,
            caixa=caixa,
        )
        self.valor_pago = (Decimal(str(self.valor_pago or 0)) + valor).quantize(Decimal('0.01'))
        self.recalcular_status_pagamento()
        self.save(update_fields=['valor_pago', 'status_pagamento'])
        return pagamento

    def __str__(self):
        return f"{self.item.nome} - +{self.quantidade}"


class PagamentoMercadoria(models.Model):
    """Baixa de pagamento de entrada de estoque (consignado / a pagar)."""
    loja = models.ForeignKey(Loja, on_delete=models.CASCADE, related_name='pagamentos_mercadoria')
    entrada = models.ForeignKey(
        EntradaEstoque, on_delete=models.CASCADE, related_name='pagamentos'
    )
    valor = models.DecimalField(max_digits=12, decimal_places=2)
    meio_liquidacao = models.CharField(
        max_length=20, choices=MEIO_LIQUIDACAO_CHOICES, default='PIX',
        verbose_name="Meio de pagamento",
    )
    data_pagamento = models.DateTimeField(default=timezone.now)
    observacao = models.CharField(max_length=200, blank=True, default='')
    registrado_por = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='pagamentos_mercadoria',
    )
    caixa = models.ForeignKey(
        'Caixa', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='pagamentos_mercadoria', verbose_name='Turno de caixa',
    )

    class Meta:
        verbose_name = 'Pagamento de mercadoria'
        verbose_name_plural = 'Pagamentos de mercadorias'
        ordering = ['-data_pagamento']

    def __str__(self):
        return f"R$ {self.valor} — {self.entrada.item.nome} ({self.meio_liquidacao})"


class ParcelaMercadoriaAgendada(models.Model):
    """Parcela de pagamento agendada para saldo a pagar de entrada consignada."""

    STATUS_CHOICES = [
        ('AGENDADO', 'Agendado'),
        ('PAGO', 'Pago'),
        ('CANCELADO', 'Cancelado'),
    ]

    loja = models.ForeignKey(Loja, on_delete=models.CASCADE)
    entrada = models.ForeignKey(
        EntradaEstoque, on_delete=models.CASCADE, related_name='parcelas_agendadas',
    )
    valor = models.DecimalField(max_digits=12, decimal_places=2)
    data_vencimento = models.DateField(verbose_name='Vencimento')
    data_entrada = models.DateTimeField(auto_now_add=True, verbose_name='Data de agendamento')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='AGENDADO')
    pagamento = models.ForeignKey(
        PagamentoMercadoria, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='parcela_agendada',
    )
    observacao = models.CharField(max_length=200, blank=True, default='')
    criado_por = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='parcelas_mercadoria_criadas',
    )

    class Meta:
        verbose_name = 'Parcela mercadoria agendada'
        verbose_name_plural = 'Parcelas mercadoria agendadas'
        ordering = ['data_vencimento', 'id']

    def __str__(self):
        return f"Parcela #{self.id} — Entrada #{self.entrada_id} — R$ {self.valor}"

    @property
    def esta_atrasada(self):
        if self.status != 'AGENDADO':
            return False
        return self.data_vencimento < timezone.localdate()


def total_parcelas_agendadas_entrada(entrada):
    from django.db.models import Sum
    return entrada.parcelas_agendadas.filter(status='AGENDADO').aggregate(
        total=Sum('valor')
    )['total'] or Decimal('0')


def saldo_agendavel_entrada(entrada):
    return max(entrada.saldo_a_pagar - total_parcelas_agendadas_entrada(entrada), Decimal('0'))


class LogTransferenciaEstoque(models.Model):
    loja_origem = models.ForeignKey(Loja, on_delete=models.CASCADE, related_name='transferencias_enviadas')
    loja_destino = models.ForeignKey(Loja, on_delete=models.CASCADE, related_name='transferencias_recebidas')
    item_nome = models.CharField(max_length=150, verbose_name="Item Transferido")
    quantidade = models.DecimalField(max_digits=10, decimal_places=3)
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name="Operador")
    data_transferencia = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Log de Transferência"
        verbose_name_plural = "Logs de Transferência"
        ordering = ['-data_transferencia']

    def __str__(self):
        return f"{self.quantidade}x {self.item_nome} ({self.loja_origem.nome} -> {self.loja_destino.nome})"


class LogFechamentoEstoqueDiario(models.Model):
    TIPO_CHOICES = [
        ('ABERTURA', 'Abertura do dia'),
        ('FECHAMENTO', 'Fechamento do dia'),
    ]

    loja = models.ForeignKey(Loja, on_delete=models.CASCADE, related_name='logs_estoque_diario')
    item_estoque = models.ForeignKey(
        ItemEstoque, on_delete=models.CASCADE, related_name='logs_fechamento_diario'
    )
    data_referencia = models.DateField(verbose_name="Data de referência")
    tipo = models.CharField(max_length=12, choices=TIPO_CHOICES)
    quantidade_cheios = models.DecimalField(max_digits=10, decimal_places=3, default=0)
    quantidade_vazios = models.DecimalField(max_digits=10, decimal_places=3, default=0)
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    registrado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Log de estoque diário"
        verbose_name_plural = "Logs de estoque diário"
        ordering = ['-registrado_em', 'item_estoque__nome']
        indexes = [
            models.Index(fields=['loja', 'data_referencia', 'tipo']),
        ]

    def __str__(self):
        return (
            f"{self.get_tipo_display()} — {self.item_estoque.nome} "
            f"({self.data_referencia})"
        )

# 8. ------------------------------- Relatorios --------------------------------
class CategoriaTransacao(models.Model):
    loja = models.ForeignKey(Loja, on_delete=models.CASCADE) 
    TIPO_CHOICES = [('RECEITA', 'Receita/Entrada'), ('DESPESA', 'Despesa/Saída')]
    nome = models.CharField(max_length=100)
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES)
    
    def __str__(self): return f"{self.nome} ({self.get_tipo_display()})"

class Transacao(models.Model):
    loja = models.ForeignKey(Loja, on_delete=models.CASCADE)
    categoria = models.ForeignKey(CategoriaTransacao, on_delete=models.SET_NULL, null=True)
    valor = models.DecimalField(max_digits=10, decimal_places=2)
    data = models.DateField(default=timezone.now, verbose_name="Data do Lançamento")
    descricao = models.CharField(max_length=200, blank=True, null=True)
    caixa = models.ForeignKey('Caixa', on_delete=models.SET_NULL, null=True, blank=True, related_name='transacoes_caixa')

    forma_pagamento = models.CharField(
        max_length=30,
        default='DINHEIRO',
        verbose_name="Forma de Pagamento"
    )
    
    def __str__(self): return f"R$ {self.valor} - {self.categoria}"

class Receita(Transacao):
    class Meta:
        proxy = True
        verbose_name = "Receita / Entrada"
        verbose_name_plural = "Receitas"

class Despesa(Transacao):
    class Meta:
        proxy = True
        verbose_name = "Despesa / Saída"
        verbose_name_plural = "Despesas"

#9.---------------------------- Motoboy / Entregas-----------------------------

class LogAuditoria(models.Model):
    ACAO_CHOICES = [
        ('CRIAR', 'Criou'),
        ('EDITAR', 'Editou'),
        ('EXCLUIR', 'Excluiu'),
        ('LOGIN', 'Login'),
        ('LOGOUT', 'Logout'),
        ('TRANSFERIR', 'Transferiu estoque'),
        ('VENDA', 'Venda'),
        ('CAIXA', 'Caixa'),
        ('ESTOQUE', 'Estoque'),
        ('SENHA', 'Senha / usuário'),
        ('CONFIG', 'Configuração'),
        ('OUTRO', 'Outro'),
    ]
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='logs_auditoria')
    loja = models.ForeignKey(Loja, on_delete=models.SET_NULL, null=True, blank=True)
    acao = models.CharField(max_length=20, choices=ACAO_CHOICES, default='OUTRO')
    modelo = models.CharField(max_length=80, blank=True, default='')
    objeto_id = models.PositiveIntegerField(null=True, blank=True)
    descricao = models.TextField()
    ip = models.GenericIPAddressField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Log de auditoria'
        verbose_name_plural = 'Logs de auditoria'
        ordering = ['-criado_em']

    def __str__(self):
        user = self.usuario.username if self.usuario else '—'
        return f"#{self.id} {user} — {self.get_acao_display()} — {self.criado_em:%d/%m/%Y %H:%M}"


class Motoboy(models.Model):
    loja = models.ForeignKey(Loja, on_delete=models.CASCADE)
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True, related_name='motoboy_perfil')
    nome = models.CharField(max_length=100)
    cpf = models.CharField(max_length=14, unique=True, verbose_name="CPF")
    telefone = models.CharField(max_length=20, verbose_name="WhatsApp/Telefone")
    ativo = models.BooleanField(default=True)
    data_cadastro = models.DateTimeField(auto_now_add=True)

    def __str__(self): return self.nome

class Moto(models.Model):
    loja = models.ForeignKey(Loja, on_delete=models.CASCADE) 
    modelo = models.CharField(max_length=50, help_text="Ex: Honda CG 160")
    placa = models.CharField(max_length=10) 
    cor = models.CharField(max_length=20)
    ativa = models.BooleanField(default=True)

    def __str__(self): return f"{self.modelo} - {self.placa}"


# ==============================================================================
# 🚀 MOTOR DE ESTOQUE INTELIGENTE (SIGNALS) - A ARQUITETURA DEFINITIVA
# ==============================================================================

# Quais status configuram que o produto SAIU da prateleira?
STATUS_COMPROMETIDOS = [
    'FINALIZADO', 'RETIRADO_NA_LOJA', 'PENDENTE', 'EM_PREPARACAO', 'SAIU_ENTREGA', 'FIADO',
]
# Vendas concluídas para faturamento / relatórios / CMV (sem entregas em aberto)
STATUS_VENDA_FATURADA = ['FINALIZADO', 'RETIRADO_NA_LOJA']
# Liquidação no caixa ao concluir (inclui entrega em preparação)
STATUS_GERA_LIQUIDACAO = ['FINALIZADO', 'RETIRADO_NA_LOJA', 'EM_PREPARACAO']

@receiver(pre_save, sender=Venda)
def blindagem_status_venda(sender, instance, **kwargs):
    """Observa se a venda mudou de status (Ex: Cancelamento) e estorna sozinho"""
    if instance.pk:
        try:
            venda_antiga = Venda.objects.get(pk=instance.pk)
            # Se estava FINALIZADA/PENDENTE e foi para CANCELADA (Devolve Estoque)
            if venda_antiga.status in STATUS_COMPROMETIDOS and instance.status not in STATUS_COMPROMETIDOS:
                for item in instance.itens.all():
                    qtd_decimal = Decimal(str(item.quantidade))
                    if item.produto.eh_kit:
                        devolver = qtd_decimal
                    else:
                        devolver = qtd_decimal * item.produto.quantidade_baixa
                    aplicar_devolucao_item_venda(item, devolver)

            elif venda_antiga.status not in STATUS_COMPROMETIDOS and instance.status in STATUS_COMPROMETIDOS:
                for item in instance.itens.all():
                    qtd_decimal = Decimal(str(item.quantidade))
                    if item.produto.eh_kit:
                        baixar = qtd_decimal
                    else:
                        baixar = qtd_decimal * item.produto.quantidade_baixa
                    aplicar_baixa_item_venda(item, baixar)
        except Venda.DoesNotExist:
            pass

@receiver(post_save, sender=ItemVenda)
def blindagem_novo_item(sender, instance, created, **kwargs):
    """Toda vez que nascer um item em uma venda válida, deduz do estoque"""
    if created and instance.venda.status in STATUS_COMPROMETIDOS:
        qtd_decimal = Decimal(str(instance.quantidade))
        if instance.produto.eh_kit:
            baixar = qtd_decimal
        else:
            baixar = qtd_decimal * instance.produto.quantidade_baixa
        aplicar_baixa_item_venda(instance, baixar)

@receiver(pre_save, sender=ItemVenda)
def blindagem_edicao_item(sender, instance, **kwargs):
    """Se o gerente for no admin e mudar a quantidade de 2 pra 5, o sistema deduz a diferença"""
    if instance.pk and getattr(instance, 'venda', None) and instance.venda.status in STATUS_COMPROMETIDOS:
        item_antigo = ItemVenda.objects.get(pk=instance.pk)
        diferenca = Decimal(str(instance.quantidade)) - Decimal(str(item_antigo.quantidade))
        if diferenca != 0:
            ajustar_estoque_item_venda(instance, diferenca)

@receiver(post_save, sender=Loja)
def criar_formas_pagamento_nova_loja(sender, instance, created, **kwargs):
    if created:
        criar_formas_pagamento_padrao(instance)


@receiver(post_delete, sender=ItemVenda)
def blindagem_exclusao_item(sender, instance, **kwargs):
    """Se um item for deletado do carrinho, devolve para a prateleira"""
    # Só estorna se a venda ainda estava ativa. Se for cancelada, a blindagem da Venda já cuidou disso.
    if getattr(instance, 'venda', None) and instance.venda.status in STATUS_COMPROMETIDOS:
        qtd_decimal = Decimal(str(instance.quantidade))
        if instance.produto.eh_kit:
            devolver = qtd_decimal
        else:
            devolver = qtd_decimal * instance.produto.quantidade_baixa
        aplicar_devolucao_item_venda(instance, devolver)


@receiver(post_save, sender=Venda)
def processar_fidelidade_ao_finalizar(sender, instance, created, **kwargs):
    if instance.status in ('FINALIZADO', 'RETIRADO_NA_LOJA') and instance.cliente_id:
        from .fidelidade_service import registrar_progresso_fidelidade
        registrar_progresso_fidelidade(instance)