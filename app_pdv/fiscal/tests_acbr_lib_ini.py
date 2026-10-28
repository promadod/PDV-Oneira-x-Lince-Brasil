from django.test import SimpleTestCase

from app_pdv.fiscal.acbr_lib_ini import montar_ini_nfe
from app_pdv.fiscal.acbr_lib_retorno import retorno_lib_para_interno


class _Cfg:
    ambiente = 'homologacao'
    cnpj = '12345678000199'
    codigo_ibge = '3304557'
    uf = 'RJ'
    crt = '1'
    razao_social = 'LOJA TESTE'
    nome_fantasia = 'TESTE'
    inscricao_estadual = '123'
    inscricao_municipal = ''
    cnae = ''
    logradouro = 'Rua A'
    numero = '10'
    complemento = ''
    bairro = 'Centro'
    cep = '20040020'
    municipio = 'Rio de Janeiro'
    csc_id = '1'
    csc_token = 'abc'


class AcbrLibIniTests(SimpleTestCase):
    def test_montar_ini_nfce_basico(self):
        payload = {
            'natureza_operacao': 'VENDA',
            'items': [{
                'codigo_produto': '1',
                'descricao': 'GAS',
                'codigo_ncm': '27111910',
                'cfop': '5102',
                'quantidade_comercial': 1,
                'valor_unitario_comercial': 100,
                'valor_bruto': 100,
                'icms_origem': '0',
                'icms_situacao_tributaria': '102',
                'pis_situacao_tributaria': '49',
                'cofins_situacao_tributaria': '49',
            }],
            'formas_pagamento': [{'forma_pagamento': '01', 'valor_pagamento': 100}],
        }
        ini = montar_ini_nfe(_Cfg(), payload, tipo='nfce', numero=1, serie=1)
        self.assertIn('[Identificacao]', ini)
        self.assertIn('mod=65', ini)
        self.assertIn('tpAmb=2', ini)
        self.assertIn('NOTA FISCAL EMITIDA EM AMBIENTE DE HOMOLOGACAO', ini)
        self.assertIn('[Produto001]', ini)
        self.assertIn('[pag001]', ini)
        self.assertIn('vNF=100.00', ini)

    def test_retorno_autorizado(self):
        interno = retorno_lib_para_interno({
            'ok': True,
            'resposta': {'EnvRetorno': {'cStat': '100', 'xMotivo': 'Autorizado', 'chNFe': '33' + '0' * 42, 'nProt': '1'}},
            'texto': '',
            'caminho_xml': 'fiscal/lib/1/x.xml',
        }, numero=7, serie=1)
        self.assertEqual(interno['status'], 'autorizado')
        self.assertEqual(interno['numero'], '7')
        self.assertEqual(interno['status_sefaz'], '100')
        self.assertTrue(interno['chave_nfe'].startswith('33'))
