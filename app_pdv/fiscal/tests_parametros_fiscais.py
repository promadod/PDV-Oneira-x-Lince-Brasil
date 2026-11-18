"""Trava de emissão sem parâmetros fiscais cadastrados."""
from decimal import Decimal
from types import SimpleNamespace

from django.http import QueryDict
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from app_pdv.fiscal.forms import parse_itens_avulsa
from app_pdv.fiscal.models import ProdutoDadosFiscais
from app_pdv.fiscal.produto_fiscal import (
    MSG_SEM_PARAMETROS_FISCAIS,
    garantir_produto_com_parametros_fiscais,
    montar_item_focus_json,
    produto_tem_parametros_fiscais,
)
from django.contrib.auth.models import User

from app_pdv.models import Loja, PerfilUsuario, Produto


class ProdutoTemParametrosFiscaisTest(SimpleTestCase):
    def test_sem_dados_fiscais(self):
        class ProdutoSemDados:
            pk = 2
            nome_venda = 'X'

            @property
            def dados_fiscais(self):
                raise ProdutoDadosFiscais.DoesNotExist

        self.assertFalse(produto_tem_parametros_fiscais(ProdutoSemDados()))

    def test_linha_vazia_nao_conta(self):
        dados = SimpleNamespace(
            ncm='', cest='', cfop_venda='', cfop_interestadual='', csosn='', cst_icms='',
            cst_pis='', cst_cofins='', codigo_beneficio_fiscal='', codigo_anp='',
            descricao_anp='', codigo_servico='', descricao_servico='', nbs='',
            codigo_class_trib='', cst_ibs_cbs='',
            aliquota_icms=0, aliquota_pis=0, aliquota_cofins=0, icms_aliquota_ad_rem=0,
            origem='0', unidade_tributavel='UN', tipo='produto',
        )
        self.assertFalse(produto_tem_parametros_fiscais(SimpleNamespace(pk=1), dados))

    def test_ncm_zerado_nao_conta(self):
        dados = SimpleNamespace(
            ncm='00000000', cest='', cfop_venda='', cfop_interestadual='', csosn='', cst_icms='',
            cst_pis='', cst_cofins='', codigo_beneficio_fiscal='', codigo_anp='',
            descricao_anp='', codigo_servico='', descricao_servico='', nbs='',
            codigo_class_trib='', cst_ibs_cbs='',
            aliquota_icms=0, aliquota_pis=0, aliquota_cofins=0, icms_aliquota_ad_rem=0,
        )
        self.assertFalse(produto_tem_parametros_fiscais(SimpleNamespace(pk=1), dados))

    def test_apenas_cfop_libera(self):
        dados = SimpleNamespace(
            ncm='', cest='', cfop_venda='5102', cfop_interestadual='', csosn='', cst_icms='',
            cst_pis='', cst_cofins='', codigo_beneficio_fiscal='', codigo_anp='',
            descricao_anp='', codigo_servico='', descricao_servico='', nbs='',
            codigo_class_trib='', cst_ibs_cbs='',
            aliquota_icms=0, aliquota_pis=0, aliquota_cofins=0, icms_aliquota_ad_rem=0,
        )
        self.assertTrue(produto_tem_parametros_fiscais(SimpleNamespace(pk=1), dados))

    def test_apenas_csosn_ou_cst_libera(self):
        base = dict(
            ncm='', cest='', cfop_venda='', cfop_interestadual='', csosn='', cst_icms='',
            cst_pis='', cst_cofins='', codigo_beneficio_fiscal='', codigo_anp='',
            descricao_anp='', codigo_servico='', descricao_servico='', nbs='',
            codigo_class_trib='', cst_ibs_cbs='',
            aliquota_icms=0, aliquota_pis=0, aliquota_cofins=0, icms_aliquota_ad_rem=0,
        )
        self.assertTrue(produto_tem_parametros_fiscais(
            SimpleNamespace(pk=1), SimpleNamespace(**{**base, 'csosn': '102'}),
        ))
        self.assertTrue(produto_tem_parametros_fiscais(
            SimpleNamespace(pk=1), SimpleNamespace(**{**base, 'cst_pis': '49'}),
        ))


class BloqueioEmissaoParametrosTest(TestCase):
    def setUp(self):
        self.loja = Loja.objects.create(nome='loja-param-fiscal', fiscal_habilitado=True)
        self.sem = Produto.objects.create(loja=self.loja, nome_venda='bombom sem fiscal', preco_venda=Decimal('10'))
        self.com = Produto.objects.create(loja=self.loja, nome_venda='bombom ok', preco_venda=Decimal('10'))
        ProdutoDadosFiscais.objects.create(produto=self.com, ncm='18069000', cfop_venda='5102', csosn='102')
        # Linha vazia (como bombom garoto #3725)
        ProdutoDadosFiscais.objects.create(produto=self.sem)

    def test_garantir_bloqueia_sem_parametro(self):
        with self.assertRaises(ValueError) as ctx:
            garantir_produto_com_parametros_fiscais(self.sem)
        self.assertIn('ERRO', str(ctx.exception))
        self.assertIn('parâmetros fiscais', str(ctx.exception))

    def test_montar_item_bloqueia(self):
        with self.assertRaises(ValueError):
            montar_item_focus_json(self.loja, self.sem, quantidade=1, preco_unitario=10)

    def test_montar_item_permite_parcial(self):
        item = montar_item_focus_json(self.loja, self.com, quantidade=1, preco_unitario=10)
        self.assertEqual(item['codigo_ncm'], '18069000')
        self.assertEqual(item['cfop'], '5102')

    def test_parse_itens_avulsa_bloqueia(self):
        post = QueryDict(mutable=True)
        post.setlist('item_produto_id', [str(self.sem.id)])
        post.setlist('item_quantidade', ['1'])
        post.setlist('item_preco', ['10'])
        post.setlist('item_desconto', ['0'])
        post.setlist('item_acrescimo', ['0'])
        with self.assertRaises(Exception) as ctx:
            parse_itens_avulsa(post, self.loja)
        self.assertIn('parâmetros fiscais', str(ctx.exception))

    def test_avulsa_json_marca_tem_fiscal(self):
        user = User.objects.create_user('op-param', password='x')
        perfil, _ = PerfilUsuario.objects.get_or_create(user=user)
        perfil.loja = self.loja
        perfil.perm_fiscal = True
        perfil.perm_fiscal_telas = ['avulsa', 'produtos', 'nfe']
        perfil.save()
        self.client.login(username='op-param', password='x')
        resp = self.client.get(reverse('fiscal_emitir_avulsa'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'modal-fiscal-erro')
        self.assertContains(resp, MSG_SEM_PARAMETROS_FISCAIS.split(':')[0])
        self.assertContains(resp, f'"id": {self.sem.id}')
        self.assertContains(resp, '"tem_fiscal": false')
        self.assertContains(resp, f'"id": {self.com.id}')
        self.assertContains(resp, '"tem_fiscal": true')
