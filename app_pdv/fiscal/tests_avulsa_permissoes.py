from decimal import Decimal
from types import SimpleNamespace

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from app_pdv.fiscal.access import (
    TELAS_FISCAIS_KEYS,
    usuario_pode_config_fiscal,
    usuario_pode_tela_fiscal,
)
from app_pdv.fiscal.focus_payload import montar_payload_nfce_avulso
from app_pdv.fiscal.forms import parse_itens_avulsa, parse_pagamentos_avulsa, total_itens_avulsa
from app_pdv.fiscal.models import ProdutoDadosFiscais
from app_pdv.fiscal.produto_fiscal import replicar_dados_fiscais
from app_pdv.models import Loja, PerfilUsuario, Produto


def _cfg():
    return SimpleNamespace(cnpj='12636948000117')


class AvulsaPayloadTest(TestCase):
    def setUp(self):
        self.loja = Loja.objects.create(nome='loja-avulsa-fiscal', fiscal_habilitado=True, cnpj='12636948000117')
        self.p1 = Produto.objects.create(loja=self.loja, nome_venda='Gas 13kg', preco_venda=Decimal('110.00'))
        self.p2 = Produto.objects.create(loja=self.loja, nome_venda='Agua 20L', preco_venda=Decimal('12.00'))
        ProdutoDadosFiscais.objects.create(produto=self.p1, ncm='27111910', cfop_venda='5102')
        ProdutoDadosFiscais.objects.create(produto=self.p2, ncm='22011000', cfop_venda='5102')

    def test_payload_varios_produtos_e_pagamentos(self):
        payload = montar_payload_nfce_avulso(
            _cfg(), self.loja, self.p1,
            quantidade=1, preco_unitario=110,
            itens=[
                {'produto': self.p1, 'quantidade': 1, 'preco_unitario': 110, 'valor_desconto': 0, 'valor_acrescimo': 0},
                {'produto': self.p2, 'quantidade': 2, 'preco_unitario': 12, 'valor_desconto': 2, 'valor_acrescimo': 0},
            ],
            pagamentos=[
                {'forma_pagamento': '01', 'valor_pagamento': 100},
                {'forma_pagamento': '17', 'valor_pagamento': 32},
            ],
        )
        self.assertEqual(len(payload['items']), 2)
        self.assertEqual(payload['items'][1]['valor_desconto'], 2)
        self.assertEqual(len(payload['formas_pagamento']), 2)
        self.assertEqual(payload['formas_pagamento'][1]['forma_pagamento'], '17')
        self.assertEqual(payload['valor_desconto'], 2)

    def test_soma_pagamento_divergente_rejeita(self):
        with self.assertRaises(ValueError):
            montar_payload_nfce_avulso(
                _cfg(), self.loja, self.p1,
                quantidade=1, preco_unitario=10,
                pagamentos=[{'forma_pagamento': '01', 'valor_pagamento': 5}],
            )


class ParseAvulsaTest(TestCase):
    def setUp(self):
        self.loja = Loja.objects.create(nome='loja-parse-avulsa', fiscal_habilitado=True)
        self.p1 = Produto.objects.create(loja=self.loja, nome_venda='Item A', preco_venda=Decimal('10.00'))

    def test_parse_listas_e_total(self):
        from django.http import QueryDict
        post = QueryDict(mutable=True)
        post.setlist('item_produto_id', [str(self.p1.id), str(self.p1.id)])
        post.setlist('item_quantidade', ['1', '2'])
        post.setlist('item_preco', ['10', '10'])
        post.setlist('item_desconto', ['0', '0'])
        post.setlist('item_acrescimo', ['0', '0'])
        post.setlist('pag_forma', ['01', '17'])
        post.setlist('pag_valor', ['20', '10'])
        itens = parse_itens_avulsa(post, self.loja)
        self.assertEqual(len(itens), 2)
        total = total_itens_avulsa(itens)
        self.assertEqual(total, 30)
        pags = parse_pagamentos_avulsa(post, total)
        self.assertEqual(len(pags), 2)


class ReplicarParametrosFiscaisTest(TestCase):
    def setUp(self):
        self.loja = Loja.objects.create(nome='loja-replica-fiscal', fiscal_habilitado=True)
        self.origem = Produto.objects.create(loja=self.loja, nome_venda='Origem', preco_venda=Decimal('1'))
        self.dest = Produto.objects.create(loja=self.loja, nome_venda='Destino', preco_venda=Decimal('1'))
        self.dados_o = ProdutoDadosFiscais.objects.create(
            produto=self.origem, ncm='22011000', cfop_venda='5102', csosn='102', codigo_anp='210203001',
        )
        self.dados_d = ProdutoDadosFiscais.objects.create(produto=self.dest)

    def test_replica_ncm_cfop_anp(self):
        n = replicar_dados_fiscais(self.dados_o, [self.dados_d])
        self.assertEqual(n, 1)
        self.dados_d.refresh_from_db()
        self.assertEqual(self.dados_d.ncm, '22011000')
        self.assertEqual(self.dados_d.cfop_venda, '5102')
        self.assertEqual(self.dados_d.codigo_anp, '210203001')


class PermissoesFiscaisTest(TestCase):
    def setUp(self):
        self.loja = Loja.objects.create(nome='loja-perm-fiscal', fiscal_habilitado=True)
        self.root = User.objects.create_superuser('rootf', 'r@x.com', 'x')
        self.op = User.objects.create_user('op-fiscal', password='x')
        perfil, _ = PerfilUsuario.objects.get_or_create(user=self.op)
        perfil.loja = self.loja
        perfil.perm_fiscal = True
        perfil.perm_fiscal_config = False
        perfil.usuario_padrao_loja = False
        perfil.perm_fiscal_telas = ['produtos', 'avulsa']
        perfil.save()
        self.perfil = perfil
        self.op = User.objects.select_related('perfil').get(pk=self.op.pk)

    def test_config_restrita(self):
        self.assertFalse(usuario_pode_config_fiscal(self.op, self.loja))
        self.assertTrue(usuario_pode_config_fiscal(self.root, self.loja))
        self.assertTrue(usuario_pode_tela_fiscal(self.op, 'fiscal_produtos', self.loja))
        self.assertFalse(usuario_pode_tela_fiscal(self.op, 'fiscal_config', self.loja))
        self.assertFalse(usuario_pode_tela_fiscal(self.op, 'fiscal_documentos', self.loja))

    def test_usuario_padrao_tem_config(self):
        self.perfil.usuario_padrao_loja = True
        self.perfil.save(update_fields=['usuario_padrao_loja'])
        self.op = User.objects.select_related('perfil').get(pk=self.op.pk)
        self.assertTrue(usuario_pode_config_fiscal(self.op, self.loja))
        self.assertTrue(usuario_pode_tela_fiscal(self.op, 'fiscal_focus', self.loja))
        self.assertTrue(usuario_pode_tela_fiscal(self.op, 'fiscal_documentos', self.loja))

    def test_pagina_produtos_mostra_replicar(self):
        self.client.login(username='op-fiscal', password='x')
        resp = self.client.get(reverse('fiscal_produtos'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Replicar parâmetros fiscais')

    def test_documentos_erro_tem_botao_editar(self):
        from app_pdv.fiscal.models import DocumentoFiscal
        DocumentoFiscal.objects.create(
            loja=self.loja, tipo='nfce', ref='t-err-1', status='erro', valor_total=Decimal('10'),
        )
        self.perfil.perm_fiscal_telas = ['produtos', 'avulsa', 'documentos']
        self.perfil.save(update_fields=['perm_fiscal_telas'])
        self.client.login(username='op-fiscal', password='x')
        resp = self.client.get(reverse('fiscal_documentos'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Editar')

    def test_config_bloqueada_para_operador(self):
        self.client.login(username='op-fiscal', password='x')
        resp = self.client.get(reverse('fiscal_config'))
        self.assertEqual(resp.status_code, 302)
