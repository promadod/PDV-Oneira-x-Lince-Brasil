from decimal import Decimal

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from app_pdv.fiscal.models import ProdutoDadosFiscais
from app_pdv.loja_piloto import (
    PILOTO_PADRAO_POR_SEGMENTO,
    importar_produtos_da_piloto,
    resolver_loja_piloto_id,
)
from app_pdv.models import ItemEstoque, Loja, Produto


class ResolverPilotoTests(TestCase):
    def test_segmento_mercadinho_usa_id_15(self):
        self.assertEqual(resolver_loja_piloto_id(segmento='mercadinho'), 15)
        self.assertEqual(PILOTO_PADRAO_POR_SEGMENTO['mercadinho'], 15)

    def test_segmento_gas_usa_id_16(self):
        self.assertEqual(resolver_loja_piloto_id(segmento='revenda_gas'), 16)

    def test_select_explicito_tem_prioridade(self):
        self.assertEqual(
            resolver_loja_piloto_id(segmento='mercadinho', loja_piloto_id='99'),
            99,
        )

    def test_sem_segmento_nao_importa(self):
        self.assertIsNone(resolver_loja_piloto_id(segmento=''))


class ImportarProdutosPilotoTests(TestCase):
    def setUp(self):
        self.piloto = Loja.objects.create(
            nome='Piloto Gas', segmento='revenda_gas', loja_piloto=True,
        )
        self.destino = Loja.objects.create(nome='Nova Loja Gas')
        self.item = ItemEstoque.objects.create(
            loja=self.piloto, nome='P13', unidade_medida='UN', quantidade_estoque=10,
        )
        self.produto = Produto.objects.create(
            loja=self.piloto,
            item_estoque=self.item,
            nome_venda='Gás P13',
            preco_venda=Decimal('120.00'),
            preco_compra=Decimal('90.00'),
            ativo=True,
        )
        ProdutoDadosFiscais.objects.create(
            produto=self.produto,
            ncm='27111910',
            cfop_venda='5655',
            csosn='102',
            codigo_anp='210203001',
        )

    def test_importa_produto_e_fiscal_com_estoque_zerado(self):
        resultado = importar_produtos_da_piloto(
            self.destino, self.piloto, [self.produto.id],
        )
        self.assertEqual(resultado.produtos_criados, 1)
        self.assertEqual(resultado.fiscais_copiados, 1)
        self.assertEqual(resultado.itens_estoque_criados, 1)

        novo = Produto.objects.get(loja=self.destino, nome_venda='Gás P13')
        self.assertEqual(novo.preco_venda, Decimal('120.00'))
        self.assertEqual(novo.item_estoque.quantidade_estoque, 0)
        self.assertEqual(novo.dados_fiscais.ncm, '27111910')
        self.assertEqual(novo.dados_fiscais.cfop_venda, '5655')
        self.assertEqual(novo.dados_fiscais.codigo_anp, '210203001')

    def test_sem_selecao_nao_cria(self):
        resultado = importar_produtos_da_piloto(self.destino, self.piloto, [])
        self.assertEqual(resultado.produtos_criados, 0)
        self.assertFalse(Produto.objects.filter(loja=self.destino).exists())


class AdminImportarPilotoFlowTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('root', 'r@x.com', 'x')
        self.client = Client()
        self.client.force_login(self.admin)
        self.piloto = Loja.objects.create(
            nome='Massini Test', segmento='revenda_gas', loja_piloto=True,
        )
        item = ItemEstoque.objects.create(loja=self.piloto, nome='P45', unidade_medida='UN')
        self.produto = Produto.objects.create(
            loja=self.piloto, item_estoque=item, nome_venda='Gás P45',
            preco_venda=Decimal('200'), ativo=True,
        )
        ProdutoDadosFiscais.objects.create(produto=self.produto, ncm='27111910', cfop_venda='5655')

    def test_criar_loja_com_segmento_redireciona_para_importacao(self):
        url = reverse('admin:app_pdv_loja_add')
        payload = {
            'nome': 'Nova Revenda',
            'gerente': self.admin.id,
            'segmento': 'revenda_gas',
            'importar_de_piloto': str(self.piloto.id),
            'ativo': 'on',
            'loja_aberta': 'on',
            'taxa_entrega_app': '5.00',
            'taxa_entrega_pdv': '0.00',
            'status_assinatura': 'ATIVO',
            'valor_mensalidade': '99.90',
            'dias_tolerancia': '3',
            'taxa_servico_pct': '10.00',
            'balanca_ean_prefixo': '2',
            'balanca_plu_digitos': '6',
            'balanca_ean_variavel': 'PESO',
            'fidelidade_tipo_meta': 'PRODUTOS',
            'fidelidade_meta': '10',
            'fidelidade_desconto_pct': '5.00',
            'campanha_desconto_pct': '10.00',
            'conferencia_dinheiro_habilitada': 'on',
            'monitorar_entrega': 'on',
            'trabalha_com_entregas': 'on',
            '_save': 'Salvar',
        }
        resp = self.client.post(url, payload)
        if resp.status_code != 302:
            form = resp.context.get('adminform').form if resp.context else None
            self.fail(f'Admin add falhou ({resp.status_code}): {getattr(form, "errors", resp.content[:500])}')
        loja = Loja.objects.get(nome='Nova Revenda')
        self.assertIn('importar-produtos-piloto', resp.url)
        self.assertIn(f'loja={loja.id}', resp.url)
        self.assertIn(f'piloto={self.piloto.id}', resp.url)

    def test_post_importacao_copia_produtos(self):
        destino = Loja.objects.create(nome='Destino Import')
        url = reverse('admin:app_pdv_loja_importar_produtos_piloto')
        resp = self.client.post(
            f'{url}?loja={destino.id}&piloto={self.piloto.id}',
            {
                'loja': destino.id,
                'piloto': self.piloto.id,
                'produto_ids': [self.produto.id],
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Produto.objects.filter(loja=destino, nome_venda='Gás P45').exists())
        novo = Produto.objects.get(loja=destino, nome_venda='Gás P45')
        self.assertEqual(novo.dados_fiscais.ncm, '27111910')
