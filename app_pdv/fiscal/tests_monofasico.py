"""Testes — ICMS monofásico combustível (CST 61) no JSON Focus."""
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from app_pdv.fiscal.produto_fiscal import montar_item_focus_json


class MonofasicoCombustivelTest(SimpleTestCase):
    @patch('app_pdv.fiscal.produto_fiscal.resolver_regra', return_value=None)
    def test_item_cst61_com_grupo_retido(self, _regra):
        loja = MagicMock(pk=1)
        produto = MagicMock()
        produto.pk = 1
        produto.nome_venda = 'GLP 13 kg'
        dados = MagicMock()
        dados.ncm = '27111910'
        dados.cfop_venda = '5656'
        dados.csosn = '102'
        dados.cst_icms = ''
        dados.cst_pis = '49'
        dados.cst_cofins = '49'
        dados.aliquota_icms = 0
        dados.aliquota_pis = 0
        dados.aliquota_cofins = 0
        dados.origem = '0'
        dados.unidade_tributavel = 'UN'
        dados.codigo_beneficio_fiscal = ''
        dados.codigo_class_trib = ''
        dados.cst_ibs_cbs = ''
        dados.codigo_anp = '210203001'
        dados.descricao_anp = 'GLP'
        dados.icms_aliquota_ad_rem = Decimal('1.2196')
        dados.pct_glp = Decimal('100')
        dados.pct_gn_nacional = 0
        dados.pct_gn_importado = 0
        produto.dados_fiscais = dados

        item = montar_item_focus_json(
            loja, produto,
            quantidade=1,
            preco_unitario=110.0,
            cfop_override='5656',
            uf_consumo='RJ',
            peso_liquido_kg=13.0,
            forcar_monofasico_combustivel=True,
        )
        self.assertEqual(item['icms_situacao_tributaria'], '61')
        self.assertEqual(item['icms_base_calculo_mono_retido'], 13.0)
        self.assertEqual(item['icms_aliquota_retido'], 1.2196)
        self.assertEqual(item['icms_valor_mono_retido'], 15.85)
        self.assertIn('combustivel_codigo_anp', item)
        self.assertIn('origens_combustivel', item)
