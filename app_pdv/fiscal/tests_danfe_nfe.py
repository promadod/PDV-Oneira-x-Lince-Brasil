from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from app_pdv.fiscal.danfe_nfe_pdf import montar_danfe_nfe_pdf, regenerar_pdf_nfe_de_xml

_XML_NFE = b'''<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe">
  <NFe>
    <infNFe Id="NFe33261149747180000169550020000000071691768806">
      <ide>
        <mod>55</mod><nNF>7</nNF><serie>2</serie><tpNF>1</tpNF>
        <natOp>Venda de combustivel</natOp>
        <dhEmi>2026-11-05T11:00:00-03:00</dhEmi>
      </ide>
      <emit>
        <CNPJ>49747180000169</CNPJ><xNome>LOJA TESTE</xNome><IE>123</IE>
        <enderEmit><xLgr>Rua A</xLgr><nro>10</nro><xBairro>Centro</xBairro>
        <xMun>Rio de Janeiro</xMun><UF>RJ</UF><fone>21999999999</fone></enderEmit>
      </emit>
      <dest>
        <CPF>12345678901</CPF><xNome>CLIENTE TESTE</xNome>
        <enderDest><xLgr>Rua B</xLgr><nro>1</nro><xBairro>Centro</xBairro>
        <xMun>Rio de Janeiro</xMun><UF>RJ</UF><CEP>20040020</CEP></enderDest>
      </dest>
      <det nItem="1">
        <prod>
          <cProd>3718</cProd><xProd>P13</xProd><NCM>27111910</NCM>
          <CFOP>5656</CFOP><uCom>UN</uCom><qCom>1.0000</qCom>
          <vUnCom>85.00</vUnCom><vProd>85.00</vProd><uTrib>KG</uTrib>
          <qTrib>13.0000</qTrib><vUnTrib>6.5384615385</vUnTrib>
        </prod>
        <imposto><ICMS><ICMS61><orig>0</orig><CST>61</CST>
          <qBCMonoRet>13.0000</qBCMonoRet><adRemICMSRet>1.2196</adRemICMSRet>
          <vICMSMonoRet>15.85</vICMSMonoRet></ICMS61></ICMS></imposto>
      </det>
      <total><ICMSTot>
        <vBC>0.00</vBC><vICMS>0.00</vICMS><vBCST>0.00</vBCST><vST>0.00</vST>
        <vProd>85.00</vProd><vFrete>0.00</vFrete><vSeg>0.00</vSeg><vDesc>0.00</vDesc>
        <vIPI>0.00</vIPI><vPIS>0.00</vPIS><vCOFINS>0.00</vCOFINS><vOutro>0.00</vOutro>
        <vNF>85.00</vNF><qBCMonoRet>13.0000</qBCMonoRet><vICMSMonoRet>15.85</vICMSMonoRet>
      </ICMSTot></total>
      <transp><modFrete>9</modFrete></transp>
      <pag><detPag><tPag>01</tPag><vPag>85.00</vPag></detPag></pag>
    </infNFe>
  </NFe>
  <protNFe><infProt><nProt>333260001031095</nProt>
    <dhRecbto>2026-11-05T11:05:00-03:00</dhRecbto></infProt></protNFe>
</nfeProc>
'''


class DanfeNfeA4Tests(SimpleTestCase):
    def test_pdf_a4_nao_e_bobina_nfce(self):
        pdf = montar_danfe_nfe_pdf(_XML_NFE)
        self.assertTrue(pdf.startswith(b'%PDF'))
        self.assertIn(b'DANFE', pdf)
        self.assertNotIn(b'DANFE NFC-e', pdf)
        self.assertGreater(len(pdf), 1000)
        self.assertIn(b'VALOR TOTAL DA NOTA', pdf)
        self.assertIn(b'RECEBEMOS DE', pdf)
        self.assertIn(b'DESTINAT', pdf)
        self.assertIn(b'/MediaBox', pdf)
        self.assertIn(b'595.27', pdf)

    def test_regenera_somente_modelo_55(self):
        with TemporaryDirectory() as tmp:
            xml = Path(tmp) / 'n.xml'
            pdf = Path(tmp) / 'n.pdf'
            xml.write_bytes(_XML_NFE.replace(b'<mod>55</mod>', b'<mod>65</mod>'))
            self.assertFalse(regenerar_pdf_nfe_de_xml(xml, pdf))
            xml.write_bytes(_XML_NFE)
            self.assertTrue(regenerar_pdf_nfe_de_xml(xml, pdf))
            self.assertTrue(pdf.is_file())
            self.assertTrue(pdf.read_bytes().startswith(b'%PDF'))


class ArquivoLibSemTokenTests(SimpleTestCase):
    def test_xml_local_nao_exige_token_focus(self):
        from app_pdv.fiscal.focus_arquivos import obter_conteudo_documento

        with TemporaryDirectory() as tmp:
            xml = Path(tmp) / 'fiscal' / 'lib' / '1' / 'nota.xml'
            xml.parent.mkdir(parents=True)
            xml.write_bytes(_XML_NFE)
            cfg = SimpleNamespace(focus_token='', provedor_emissao='lib', ambiente='homologacao', focus_base_url='')
            doc = MagicMock()
            doc.tipo = 'nfe'
            doc.caminho_xml = 'fiscal/lib/1/nota.xml'
            doc.caminho_pdf = ''
            doc.chave_acesso = '33261149747180000169550020000000071691768806'
            doc.ref = 'r'
            doc.payload_envio = {}
            doc.produto_avulso = None
            with patch('django.conf.settings.MEDIA_ROOT', tmp):
                conteudo, ctype, fname = obter_conteudo_documento(cfg, doc, formato='xml', refresh=False)
            self.assertTrue(conteudo.startswith(b'<?xml') or b'<nfeProc' in conteudo)
            self.assertIn('xml', ctype)
            self.assertTrue(fname.endswith('.xml'))

    def test_pdf_nfe_gera_a4_a_partir_do_xml(self):
        from app_pdv.fiscal.focus_arquivos import obter_conteudo_documento

        with TemporaryDirectory() as tmp:
            xml = Path(tmp) / 'fiscal' / 'lib' / '1' / 'nota.xml'
            xml.parent.mkdir(parents=True)
            xml.write_bytes(_XML_NFE)
            cfg = SimpleNamespace(focus_token='', provedor_emissao='lib', ambiente='homologacao', focus_base_url='')
            doc = MagicMock()
            doc.tipo = 'nfe'
            doc.caminho_xml = 'fiscal/lib/1/nota.xml'
            doc.caminho_pdf = ''
            doc.chave_acesso = '3326'
            doc.ref = 'r'
            doc.payload_envio = {}
            doc.produto_avulso = None
            with patch('django.conf.settings.MEDIA_ROOT', tmp):
                conteudo, ctype, fname = obter_conteudo_documento(cfg, doc, formato='pdf', refresh=False)
            self.assertTrue(conteudo.startswith(b'%PDF'))
            self.assertEqual(ctype, 'application/pdf')
            self.assertTrue(fname.endswith('.pdf'))
            self.assertNotIn(b'DANFE NFC-e', conteudo)
            self.assertIn(b'DANFE', conteudo)

    def test_xml_encontrado_pela_chave_sem_caminho(self):
        from app_pdv.fiscal.focus_arquivos import obter_conteudo_documento

        chave = '33261149747180000169550020000000071691768806'
        with TemporaryDirectory() as tmp:
            xml = Path(tmp) / 'fiscal' / 'lib' / '16' / f'{chave}.xml'
            xml.parent.mkdir(parents=True)
            xml.write_bytes(_XML_NFE)
            cfg = SimpleNamespace(focus_token='', provedor_emissao='lib', ambiente='homologacao', focus_base_url='')
            doc = MagicMock()
            doc.tipo = 'nfe'
            doc.caminho_xml = ''
            doc.caminho_pdf = ''
            doc.chave_acesso = chave
            doc.loja_id = 16
            doc.ref = 'r'
            doc.payload_envio = {}
            doc.produto_avulso = None
            with patch('django.conf.settings.MEDIA_ROOT', tmp):
                xml_bytes, ctype, fname = obter_conteudo_documento(cfg, doc, formato='xml', refresh=False)
                pdf_bytes, pdf_ctype, pdf_name = obter_conteudo_documento(cfg, doc, formato='pdf', refresh=False)
            self.assertTrue(xml_bytes.startswith(b'<?xml') or b'<nfeProc' in xml_bytes)
            self.assertIn('xml', ctype)
            self.assertTrue(fname.endswith('.xml'))
            self.assertTrue(pdf_bytes.startswith(b'%PDF'))
            self.assertEqual(pdf_ctype, 'application/pdf')
            self.assertTrue(pdf_name.endswith('.pdf'))
            self.assertNotIn(b'DANFE NFC-e', pdf_bytes)
