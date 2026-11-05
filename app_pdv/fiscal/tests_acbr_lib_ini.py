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
    telefone = '21994495071'
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
        self.assertIn('Fone=21994495071', ini)
        self.assertIn('infAdProd=GAS', ini)
        self.assertNotIn('[Combustivel001]', ini)

    def test_montar_ini_nfe_grupo_combustivel_cst61(self):
        payload = {
            'natureza_operacao': 'Venda de combustivel',
            'items': [{
                'codigo_produto': '1',
                'descricao': 'GLP 13 kg',
                'codigo_ncm': '27111910',
                'cfop': '5656',
                'quantidade_comercial': 1,
                'valor_unitario_comercial': 85,
                'valor_bruto': 85,
                'icms_origem': '0',
                'icms_situacao_tributaria': '61',
                'pis_situacao_tributaria': '49',
                'cofins_situacao_tributaria': '49',
                'combustivel_codigo_anp': '210203001',
                'combustivel_descricao_anp': 'GLP',
                'combustivel_sigla_uf': 'RJ',
                'combustivel_percentual_glp': 100,
                'unidade_comercial': 'UN',
                'unidade_tributavel': 'KG',
                'quantidade_tributavel': 13.0,
                'valor_unitario_tributavel': 85 / 13,
                'icms_base_calculo_mono_retido': 13.0,
                'icms_aliquota_retido': 1.2196,
                'icms_valor_mono_retido': 15.85,
            }],
            'formas_pagamento': [{'forma_pagamento': '01', 'valor_pagamento': 85}],
        }
        ini = montar_ini_nfe(_Cfg(), payload, tipo='nfe', numero=2, serie=1)
        self.assertIn('mod=55', ini)
        self.assertIn('[Combustivel001]', ini)
        self.assertIn('uTrib=KG', ini)
        self.assertIn('qTrib=13', ini)
        self.assertIn('cProdANP=210203001', ini)
        self.assertIn('descANP=GLP', ini)
        self.assertIn('UFCons=RJ', ini)
        self.assertIn('pGLP=100.0000', ini)
        self.assertIn('pGNn=0.0000', ini)
        self.assertIn('pGNi=0.0000', ini)
        self.assertIn('vPart=85.00', ini)
        self.assertIn('CST=61', ini)
        self.assertIn('qBCMonoRet=13', ini)
        self.assertGreaterEqual(ini.count('qBCMonoRet=13'), 2)
        self.assertRegex(ini, r'\[Total\][\s\S]*qBCMonoRet=13')
        self.assertRegex(ini, r'\[Total\][\s\S]*vICMSMonoRet=15.85')
        self.assertIn('adRemICMSRet=1.2196', ini)
        self.assertIn('vICMSMonoRet=15.85', ini)
        self.assertNotIn('[origComb', ini)
        self.assertIn('[Transportador]', ini)
        self.assertIn('modFrete=0', ini)
        self.assertIn('CNPJCPF=12345678000199', ini)
        self.assertIn('xNome=LOJA TESTE', ini)
        self.assertIn('[Volume001]', ini)
        self.assertIn('pesoL=13.000', ini)

    def test_combustivel_nao_envia_transporta_com_mod_frete_9(self):
        payload = {
            'natureza_operacao': 'Venda de combustivel',
            'modalidade_frete': '9',
            'items': [{
                'codigo_produto': '1',
                'descricao': 'GLP 13 kg',
                'codigo_ncm': '27111910',
                'cfop': '5656',
                'quantidade_comercial': 1,
                'valor_unitario_comercial': 85,
                'valor_bruto': 85,
                'icms_origem': '0',
                'icms_situacao_tributaria': '61',
                'pis_situacao_tributaria': '49',
                'cofins_situacao_tributaria': '49',
                'combustivel_codigo_anp': '210203001',
                'combustivel_descricao_anp': 'GLP',
                'combustivel_sigla_uf': 'RJ',
                'icms_base_calculo_mono_retido': 13.0,
            }],
            'formas_pagamento': [{'forma_pagamento': '01', 'valor_pagamento': 85}],
        }
        ini = montar_ini_nfe(_Cfg(), payload, tipo='nfe', numero=11, serie=1)
        self.assertIn('modFrete=0', ini)
        self.assertNotRegex(ini, r'\[Transportador\][^\[]*modFrete=9')
        self.assertIn('CNPJCPF=12345678000199', ini)

    def test_montar_ini_nfe_origcomb_quando_gn(self):
        payload = {
            'natureza_operacao': 'Venda de combustivel',
            'items': [{
                'codigo_produto': '1',
                'descricao': 'GLP 13 kg',
                'codigo_ncm': '27111910',
                'cfop': '5656',
                'quantidade_comercial': 1,
                'valor_unitario_comercial': 85,
                'valor_bruto': 85,
                'icms_origem': '0',
                'icms_situacao_tributaria': '61',
                'pis_situacao_tributaria': '49',
                'cofins_situacao_tributaria': '49',
                'combustivel_codigo_anp': '210203001',
                'combustivel_descricao_anp': 'GLP',
                'combustivel_sigla_uf': 'RJ',
                'combustivel_percentual_glp': 100,
                'combustivel_percentual_gas_natural_nacional': 70,
                'combustivel_percentual_gas_natural_importado': 30,
                'origens_combustivel': [
                    {'indicador_importacao': '0', 'uf_origem': '33', 'percentual_originario_uf': 100.0},
                    {'indicador_importacao': '1', 'uf_origem': '33', 'percentual_originario_uf': 100.0},
                ],
                'icms_base_calculo_mono_retido': 13.0,
                'icms_aliquota_retido': 1.2196,
                'icms_valor_mono_retido': 15.85,
            }],
            'formas_pagamento': [{'forma_pagamento': '01', 'valor_pagamento': 85}],
        }
        ini = montar_ini_nfe(_Cfg(), payload, tipo='nfe', numero=2, serie=1)
        self.assertIn('[origComb00101]', ini)
        self.assertIn('[origComb00102]', ini)
        self.assertIn('indImport=0', ini)
        self.assertIn('indImport=1', ini)
        self.assertIn('cUFOrig=33', ini)
        self.assertIn('pGNn=70.0000', ini)
        self.assertIn('pGNi=30.0000', ini)

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

    def test_retorno_rejeicao_envio_maiusculo(self):
        interno = retorno_lib_para_interno({
            'ok': True,
            'resposta': {
                'Envio': {
                    'CStat': 704,
                    'XMotivo': 'Rejeicao: NFC-e com Data-Hora de emissão atrasada',
                },
            },
        }, numero=21, serie=1)
        self.assertEqual(interno['status'], 'erro_autorizacao')
        self.assertEqual(interno['status_sefaz'], '704')
        self.assertIn('atrasada', interno['mensagem_sefaz'])

    def test_retorno_duplicidade_204_com_protocolo(self):
        chave = '33261012636948000117650010000000261914987130'
        interno = retorno_lib_para_interno({
            'ok': True,
            'resposta': {
                'Envio': {
                    'CStat': 204,
                    'XMotivo': 'Rejeicao: Duplicidade de NF-e',
                    'Msg': 'Rejeicao: Duplicidade de NF-e',
                    'NFe26': {
                        'cStat': 100,
                        'chDFe': chave,
                        'nProt': '333260002801509',
                        'xMotivo': 'Autorizado o uso da NF-e',
                    },
                },
            },
        }, numero=26, serie=1)
        self.assertEqual(interno['status'], 'autorizado')
        self.assertEqual(interno['status_sefaz'], '100')
        self.assertEqual(interno['protocolo'], '333260002801509')
        self.assertEqual(interno['chave_nfe'], chave)
        self.assertIn('Autorizado', interno['mensagem_sefaz'])
