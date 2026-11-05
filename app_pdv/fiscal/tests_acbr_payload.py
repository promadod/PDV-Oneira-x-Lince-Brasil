"""Pagamento da NFC-e no JSON da ACBr."""
from types import SimpleNamespace

from django.test import SimpleTestCase

from app_pdv.fiscal.acbr_payload import pedido_emissao


def _cfg():
    return SimpleNamespace(
        ambiente='homologacao',
        cnpj='12636948000117',
        codigo_ibge='3303500',
        uf='RJ',
        crt='1',
        razao_social='Loja',
    )


def _payload(forma):
    return {
        'cnpj_emitente': '12636948000117',
        'natureza_operacao': 'VENDA',
        'data_emissao': '2026-10-20T13:00:00-03:00',
        'items': [{
            'numero_item': 1,
            'codigo_produto': '1',
            'descricao': 'Item',
            'codigo_ncm': '08043000',
            'cfop': '5102',
            'unidade_comercial': 'UN',
            'quantidade_comercial': 1,
            'valor_unitario_comercial': 10,
            'valor_bruto': 10,
            'icms_origem': '0',
            'icms_situacao_tributaria': '102',
            'pis_situacao_tributaria': '07',
            'cofins_situacao_tributaria': '07',
        }],
        'formas_pagamento': [{'forma_pagamento': forma, 'valor_pagamento': 10}],
    }


class PagamentoAcbrTest(SimpleTestCase):
    def _det(self, forma):
        pedido = pedido_emissao(_cfg(), _payload(forma), tipo='nfce', ref='r', numero=1, serie=1)
        return pedido['infNFe']['pag']['detPag'][0]

    def test_dinheiro_nao_leva_grupo_de_cartao(self):
        det = self._det('01')
        self.assertEqual(det['tPag'], '01')
        self.assertNotIn('card', det)

    def test_credito_debito_e_pix_informam_pagamento_nao_integrado(self):
        for forma in ('03', '04', '17'):
            det = self._det(forma)
            self.assertEqual(det['tPag'], forma)
            self.assertEqual(det['card'], {'tpIntegra': 2})

    def test_outros_informa_descricao(self):
        det = self._det('99')
        self.assertEqual(det['xPag'], 'Outros')
        self.assertNotIn('card', det)

    def test_nfe_item_combustivel_grupo_comb_e_icms61(self):
        payload = _payload('01')
        payload['items'][0].update({
            'codigo_ncm': '27111910',
            'cfop': '5656',
            'descricao': 'GLP 13 kg',
            'valor_unitario_comercial': 85,
            'valor_bruto': 85,
            'icms_situacao_tributaria': '61',
            'combustivel_codigo_anp': '210203001',
            'combustivel_descricao_anp': 'GLP',
            'combustivel_sigla_uf': 'RJ',
            'combustivel_percentual_glp': 100,
            'icms_base_calculo_mono_retido': 13.0,
            'icms_aliquota_retido': 1.2196,
            'icms_valor_mono_retido': 15.85,
        })
        payload['formas_pagamento'][0]['valor_pagamento'] = 85
        pedido = pedido_emissao(_cfg(), payload, tipo='nfe', ref='r', numero=2, serie=1)
        prod = pedido['infNFe']['det'][0]['prod']
        comb = prod['comb']
        self.assertEqual(comb['cProdANP'], '210203001')
        self.assertEqual(comb['descANP'], 'GLP')
        self.assertEqual(comb['UFCons'], 'RJ')
        self.assertEqual(comb['pGLP'], 100.0)
        self.assertNotIn('origComb', comb)
        icms = pedido['infNFe']['det'][0]['imposto']['ICMS']
        self.assertEqual(icms['ICMS61']['CST'], '61')
        self.assertEqual(icms['ICMS61']['qBCMonoRet'], 13.0)
        self.assertEqual(icms['ICMS61']['adRemICMSRet'], 1.2196)
        self.assertEqual(icms['ICMS61']['vICMSMonoRet'], 15.85)
        self.assertEqual(pedido['infNFe']['total']['ICMSTot']['vICMSMonoRet'], 15.85)
        self.assertEqual(pedido['infNFe']['total']['ICMSTot']['qBCMonoRet'], 13.0)
        transporta = pedido['infNFe']['transp']['transporta']
        self.assertEqual(pedido['infNFe']['transp']['modFrete'], 0)
        self.assertEqual(transporta['CNPJ'], '12636948000117')
        self.assertEqual(transporta['xNome'], 'Loja')
        self.assertEqual(pedido['infNFe']['transp']['vol'][0]['pesoL'], 13.0)
