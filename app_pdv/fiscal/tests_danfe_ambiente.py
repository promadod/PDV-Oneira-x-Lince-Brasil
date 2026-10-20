"""DANFCE sem a faixa de ambiente."""
import re
import zlib

from django.test import SimpleTestCase

from app_pdv.fiscal.focus_arquivos import _classe_texto_danfe, ocultar_ambiente_danfe


def _pdf_com_faixa() -> bytes:
    conteudo = (
        'BT 10 100 Td (SEM VALOR FISCAL) Tj ET\n'
        'BT 10 90 Td (EMITIDA EM AMBIENTE DE HOMOLOGAÇÃO) Tj ET\n'
        'BT 10 70 Td (NOTA FISCAL EMITIDA) Tj ET\n'
        'BT 10 60 Td (EM AMBIENTE DE HO) Tj ET\n'
        'BT 10 40 Td (Via Consumidor) Tj ET\n'
    ).encode('latin-1')
    comp = zlib.compress(conteudo)
    miolo = (
        b'%PDF-1.3\n'
        b'4 0 obj\n'
        b'<</Filter /FlateDecode /Length ' + str(len(comp)).encode() + b'>>\n'
        b'stream\n' + comp + b'\nendstream\n'
        b'endobj\n'
        b'1 0 obj\n<</Type /Catalog>>\nendobj\n'
    )
    xref_pos = len(miolo)
    xref = (
        b'xref\n0 5\n'
        b'0000000000 65535 f \n'
        + f'{miolo.rfind(b"1 0 obj"):010d} 00000 n \n'.encode()
        + b'0000000000 65535 f \n'
        + b'0000000000 65535 f \n'
        + f'{miolo.find(b"4 0 obj"):010d} 00000 n \n'.encode()
        + b'trailer\n<<\n/Size 5\n/Root 1 0 R\n>>\nstartxref\n'
        + str(xref_pos).encode()
        + b'\n%%EOF'
    )
    return miolo + xref


class DanfeAmbienteTest(SimpleTestCase):
    def test_classifica_faixa_e_preserva_titulo(self):
        self.assertEqual(_classe_texto_danfe('SEM VALOR FISCAL'), 'banner')
        self.assertEqual(_classe_texto_danfe('EMITIDA EM AMBIENTE DE HOMOLOGAÇÃO'), 'banner')
        self.assertEqual(_classe_texto_danfe('NOTA FISCAL EMITIDA'), 'item')
        self.assertEqual(_classe_texto_danfe('Via Consumidor'), 'manter')
        self.assertEqual(_classe_texto_danfe('Nota Fiscal de Consumidor Eletronica'), 'manter')

    def test_pdf_troca_faixa_pelo_nome_do_produto(self):
        pdf = ocultar_ambiente_danfe(_pdf_com_faixa(), 'Absorvente Always Seca P')
        self.assertTrue(pdf.startswith(b'%PDF'))
        idx = pdf.rfind(b'\nxref\n')
        start = int(pdf[pdf.rfind(b'startxref\n') + len(b'startxref\n'):].split()[0])
        self.assertEqual(start, idx + 1)
        stream = re.search(rb'stream\n(.*?)\nendstream', pdf, re.S).group(1)
        texto = zlib.decompress(stream).decode('latin-1')
        self.assertNotIn('HOMOLOG', texto.upper())
        self.assertNotIn('SEM VALOR FISCAL', texto)
        self.assertIn('Absorvente Always', texto)
        self.assertIn('Seca P', texto)
        self.assertIn('Via Consumidor', texto)
