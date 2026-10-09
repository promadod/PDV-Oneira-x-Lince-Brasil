"""Reemissão NF-e — payload legado deve ganhar CST 61."""
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from app_pdv.fiscal.focus_payload import reenriquecer_payload_nfe_reemissao


class ReemissaoNfeMonofasicoTest(SimpleTestCase):
    @patch('app_pdv.models.Produto.objects.filter')
    @patch('app_pdv.fiscal.produto_fiscal.resolver_regra', return_value=None)
    def test_payload_legado_csosn102_vai_para_cst61(self, _regra, produto_filter):
        loja = MagicMock(pk=1)
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
        produto = MagicMock(pk=5, nome_venda='GLP 13 kg', dados_fiscais=dados)
        produto_filter.return_value.select_related.return_value.first.return_value = produto

        payload_antigo = {
            'natureza_operacao': 'Venda combustivel',
            'uf_destinatario': 'RJ',
            'indicador_inscricao_estadual_destinatario': '9',
            'items': [{
                'numero_item': '1',
                'codigo_produto': '5',
                'cfop': '5656',
                'icms_situacao_tributaria': '102',
                'combustivel_codigo_anp': '210203001',
                'quantidade_comercial': 1,
                'valor_unitario_comercial': 110,
                'valor_bruto': 110,
            }],
            'volumes': [{'quantidade': 1, 'peso_liquido': 13.0, 'peso_bruto': 27.0}],
        }
        novo = reenriquecer_payload_nfe_reemissao(loja, payload_antigo)
        item = novo['items'][0]
        self.assertEqual(item['icms_situacao_tributaria'], '61')
        self.assertEqual(item['icms_base_calculo_mono_retido'], 13.0)
