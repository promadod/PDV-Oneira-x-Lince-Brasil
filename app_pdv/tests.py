from decimal import Decimal
from types import SimpleNamespace

from django.test import SimpleTestCase

from app_pdv.balanca import (
    chaves_busca_plu,
    decodificar_ean13_balanca,
    ean13_digito_verificador,
    gerar_csv_carga_balanca,
    montar_ean13_etiqueta,
    quantidade_da_etiqueta,
)


class EtiquetaBalancaTests(SimpleTestCase):
    def test_ean13_dv_conhecido(self):
        self.assertEqual(ean13_digito_verificador('789100010010'), '3')

    def test_etiqueta_peso_plu_6_digitos(self):
        ean = montar_ean13_etiqueta(
            '102030',
            peso_kg='0.500',
            config={'prefixo': '2', 'plu_digitos': 6, 'variavel': 'PESO'},
        )
        self.assertEqual(len(ean), 13)
        self.assertTrue(ean.startswith('2102030'))
        dec = decodificar_ean13_balanca(
            ean,
            config={'prefixo': '2', 'plu_digitos': 6, 'variavel': 'PESO'},
        )
        self.assertIsNotNone(dec)
        self.assertEqual(dec['plu'], '102030')
        self.assertEqual(dec['quantidade'], Decimal('0.500'))
        self.assertTrue(dec['dv_ok'])

    def test_etiqueta_preco_define_quantidade_pelo_preco_kg(self):
        ean = montar_ean13_etiqueta(
            '102030',
            preco_total='10.00',
            config={'prefixo': '2', 'plu_digitos': 6, 'variavel': 'PRECO'},
        )
        dec = decodificar_ean13_balanca(
            ean,
            config={'prefixo': '2', 'plu_digitos': 6, 'variavel': 'PRECO'},
        )
        qtd = quantidade_da_etiqueta(dec, preco_unitario='20.00')
        self.assertEqual(qtd, Decimal('0.500'))

    def test_chaves_plu_aceitam_com_e_sem_zeros(self):
        chaves = set(chaves_busca_plu('2030', 6))
        self.assertIn('2030', chaves)
        self.assertIn('002030', chaves)
        self.assertIn('002030', set(chaves_busca_plu('002030', 6)))

    def test_csv_carga_so_granel_com_codigo(self):
        oregano = SimpleNamespace(
            codigo_barras='102030',
            nome_venda='Oregano',
            preco_venda=Decimal('20.00'),
            item_estoque=SimpleNamespace(unidade_medida='KG'),
        )
        lata = SimpleNamespace(
            codigo_barras='7894900011517',
            nome_venda='Refrigerante',
            preco_venda=Decimal('5.00'),
            item_estoque=SimpleNamespace(unidade_medida='UN'),
        )
        csv = gerar_csv_carga_balanca(
            [oregano, lata],
            loja=SimpleNamespace(
                trabalha_com_balanca_granel=True,
                balanca_ean_prefixo='2',
                balanca_plu_digitos=6,
                balanca_ean_variavel='PESO',
            ),
        )
        self.assertIn('102030;Oregano;20.00;P;KG', csv)
        self.assertNotIn('7894900011517', csv)

    def test_nao_decodifica_ean_de_fabricante(self):
        self.assertIsNone(
            decodificar_ean13_balanca(
                '7891000100103',
                config={'prefixo': '2', 'plu_digitos': 6, 'variavel': 'PESO'},
            )
        )
