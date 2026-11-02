from django.test import SimpleTestCase

from app_pdv.fiscal.acbr_cnpj import parse_resposta, rotulos_dados
from app_pdv.fiscal.danfe_nfce_pdf import _eh_frase_homolog, _descricao_item, montar_danfe_nfce_pdf
from xml.etree import ElementTree as ET


class ConsultaCnpjParseTests(SimpleTestCase):
    def test_parse_ini_consulta(self):
        texto = (
            '[Consulta]\n'
            'RazaoSocial=Sacolao da Cris\n'
            'Fantasia=SACOLAO\n'
            'Cidade=NOVA IGUACU\n'
            'UF=RJ\n'
        )
        dados = parse_resposta(texto)
        self.assertEqual(dados['RazaoSocial'], 'Sacolao da Cris')
        self.assertEqual(dados['UF'], 'RJ')
        linhas = rotulos_dados(dados)
        chaves = [c for c, _, _ in linhas]
        self.assertEqual(chaves[:2], ['RazaoSocial', 'Fantasia'])

    def test_parse_json_consulta(self):
        dados = parse_resposta('{"Consulta": {"Situacao": "ATIVA", "CEP": "26200-000"}}')
        self.assertEqual(dados['Situacao'], 'ATIVA')


class DanfeHomologTests(SimpleTestCase):
    def test_omite_frase_homologacao(self):
        self.assertTrue(_eh_frase_homolog('NOTA FISCAL EMITIDA EM AMBIENTE DE HOMOLOGACAO - SEM VALOR FISCAL'))
        self.assertTrue(_eh_frase_homolog('EMITIDA EM AMBIENTE DE HOMOLOGAÇÃO'))
        self.assertFalse(_eh_frase_homolog('Algodão Hidrófilo'))

    def test_usa_infadprod_quando_xprod_e_homolog(self):
        ns = 'http://www.portalfiscal.inf.br/nfe'
        xml = f'''<det xmlns="{ns}" nItem="1">
            <prod><xProd>NOTA FISCAL EMITIDA EM AMBIENTE DE HOMOLOGACAO - SEM VALOR FISCAL</xProd></prod>
            <infAdProd>Algodao Hidrofilo</infAdProd>
        </det>'''
        det = ET.fromstring(xml)
        prod = det.find(f'{{{ns}}}prod')
        self.assertEqual(_descricao_item(det, prod), 'Algodao Hidrofilo')

    def test_pdf_sem_frases_homolog(self):
        xml = b'''<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe">
  <NFe><infNFe Id="NFe33261112636948000117650010000000321611801600">
    <ide><mod>65</mod><nNF>32</nNF><serie>1</serie><dhEmi>2026-11-02T13:33:00-03:00</dhEmi><tpAmb>2</tpAmb><tpEmis>1</tpEmis></ide>
    <emit><CNPJ>12636948000117</CNPJ><xNome>Sacolao da Cris</xNome><IE>1</IE>
      <enderEmit><xLgr>Rua</xLgr><nro>1</nro><xBairro>B</xBairro><xMun>Cidade</xMun><UF>RJ</UF></enderEmit>
    </emit>
    <det nItem="1"><prod><cProd>1</cProd><xProd>NOTA FISCAL EMITIDA EM AMBIENTE DE HOMOLOGACAO - SEM VALOR FISCAL</xProd>
      <qCom>1</qCom><uCom>UN</uCom><vUnCom>5.50</vUnCom><vProd>5.50</vProd></prod>
      <infAdProd>Algodao Hidrofilo</infAdProd></det>
    <total><ICMSTot><vProd>5.50</vProd><vNF>5.50</vNF><vDesc>0</vDesc><vFrete>0</vFrete><vOutro>0</vOutro></ICMSTot></total>
    <pag><detPag><tPag>01</tPag><vPag>5.50</vPag></detPag></pag>
  </infNFe></NFe>
</nfeProc>'''
        pdf = montar_danfe_nfce_pdf(xml)
        self.assertTrue(pdf.startswith(b'%PDF'))
        self.assertNotIn('EMITIDA EM AMBIENTE DE HOMOLOG'.encode('latin-1'), pdf)
        self.assertNotIn(b'NOTA FISCAL EMITIDA EM AMBIENTE DE HOMOLOGACAO', pdf)
        self.assertIn(b'Algodao Hidrofilo', pdf)
