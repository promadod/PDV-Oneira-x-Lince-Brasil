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
