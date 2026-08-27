from decimal import Decimal
from types import SimpleNamespace

from django.test import SimpleTestCase, TestCase

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

    def test_etiqueta_preco_ean_real_balanca(self):
        """EAN real da balança: prefixo 2 + PLU 194400 + total R$ 2,59."""
        ean = '2194400002592'
        dec = decodificar_ean13_balanca(
            ean,
            config={'prefixo': '2', 'plu_digitos': 6, 'variavel': 'PRECO'},
        )
        self.assertIsNotNone(dec)
        self.assertEqual(dec['plu'], '194400')
        self.assertEqual(dec['preco_total'], Decimal('2.59'))
        self.assertTrue(dec['dv_ok'])
        self.assertIn('194400', set(chaves_busca_plu('1944', 6)))
        qtd = quantidade_da_etiqueta(dec, preco_unitario='71.99')
        self.assertEqual(qtd, Decimal('0.036'))

    def test_chaves_plu_aceitam_com_e_sem_zeros(self):
        chaves = set(chaves_busca_plu('2030', 6))
        self.assertIn('2030', chaves)
        self.assertIn('002030', chaves)
        self.assertIn('203000', chaves)  # padding à direita (algumas balanças)
        self.assertIn('002030', set(chaves_busca_plu('002030', 6)))
        self.assertIn('194400', set(chaves_busca_plu('1944', 6)))
        self.assertIn('001944', set(chaves_busca_plu('1944', 6)))

    def test_csv_carga_apenas_kg(self):
        oregano = SimpleNamespace(
            pk=102030,
            id=102030,
            codigo_barras='102030',
            nome_venda='Oregano',
            preco_venda=Decimal('20.00'),
            item_estoque=SimpleNamespace(unidade_medida='KG'),
        )
        curry_sem_codigo = SimpleNamespace(
            pk=1944,
            id=1944,
            codigo_barras='',
            nome_venda='Curry',
            preco_venda=Decimal('45.00'),
            item_estoque=SimpleNamespace(unidade_medida='KG'),
        )
        gas_un = SimpleNamespace(
            pk=99,
            id=99,
            codigo_barras='405060',
            nome_venda='Gas 13 kg',
            preco_venda=Decimal('110.00'),
            item_estoque=SimpleNamespace(unidade_medida='UN'),
        )
        csv = gerar_csv_carga_balanca(
            [oregano, curry_sem_codigo, gas_un],
            loja=SimpleNamespace(
                trabalha_com_balanca_granel=True,
                balanca_ean_prefixo='2',
                balanca_plu_digitos=6,
                balanca_ean_variavel='PESO',
            ),
        )
        self.assertIn('102030;Oregano;20.00;P;KG', csv)
        self.assertIn('001944;Curry;45.00;P;KG', csv)
        self.assertNotIn('Gas 13 kg', csv)
        self.assertNotIn(';U;', csv)
        self.assertNotIn(';UN', csv)

    def test_nao_decodifica_ean_de_fabricante(self):
        self.assertIsNone(
            decodificar_ean13_balanca(
                '7891000100103',
                config={'prefixo': '2', 'plu_digitos': 6, 'variavel': 'PESO'},
            )
        )


class NormalizarCodigoBarrasExcelTests(SimpleTestCase):
    def test_float_sem_ponto_zero(self):
        from app_pdv.importacao_produtos import normalizar_codigo_barras_excel

        self.assertEqual(normalizar_codigo_barras_excel(7898908582765.0), '7898908582765')
        self.assertEqual(normalizar_codigo_barras_excel(7894900011517), '7894900011517')

    def test_string_com_ponto_zero(self):
        from app_pdv.importacao_produtos import normalizar_codigo_barras_excel

        self.assertEqual(normalizar_codigo_barras_excel('7898908582956.0'), '7898908582956')
        self.assertEqual(normalizar_codigo_barras_excel('nan'), '')

    def test_notacao_cientifica(self):
        from app_pdv.importacao_produtos import normalizar_codigo_barras_excel

        self.assertEqual(normalizar_codigo_barras_excel('7.894900011517E+12'), '7894900011517')
        self.assertEqual(normalizar_codigo_barras_excel(7.894900011517e12), '7894900011517')

class ImportacaoProdutosTests(TestCase):
    def setUp(self):
        from django.contrib.auth.models import User

        from app_pdv.models import Loja

        self.loja = Loja.objects.create(nome='Loja Import Test')
        self.user = User.objects.create_user(username='importador', password='x')

    def _df_goiabada(self, estoque=10):
        import pandas as pd

        return pd.DataFrame([{
            'item_pai': 'goiabada cascao doces tradicao 250g',
            'unidade': 'UN',
            'estoque_total': estoque,
            'nome_venda': 'Goiabada cascao D. tradicao 250g',
            'codigo_barras': '7898917764060',
            'qtd_baixa': 1,
            'preco_custo': 4.35,
            'preco_venda': 10.99,
        }])

    def test_importacao_somar_acumula_estoque(self):
        from app_pdv.importacao_produtos import MODO_SOMAR, executar_importacao_produtos, normalizar_colunas_dataframe
        from app_pdv.models import ItemEstoque

        df = normalizar_colunas_dataframe(self._df_goiabada(10))
        executar_importacao_produtos(self.loja, self.user, df, 'a.xlsx', MODO_SOMAR)
        executar_importacao_produtos(self.loja, self.user, df, 'a.xlsx', MODO_SOMAR)
        item = ItemEstoque.objects.get(loja=self.loja, nome='goiabada cascao doces tradicao 250g')
        self.assertEqual(item.quantidade_estoque, Decimal('20'))

    def test_importacao_substituir_nao_acumula(self):
        from app_pdv.importacao_produtos import MODO_SUBSTITUIR, executar_importacao_produtos, normalizar_colunas_dataframe
        from app_pdv.models import ItemEstoque

        df = normalizar_colunas_dataframe(self._df_goiabada(10))
        executar_importacao_produtos(self.loja, self.user, df, 'a.xlsx', MODO_SUBSTITUIR)
        executar_importacao_produtos(self.loja, self.user, df, 'b.xlsx', MODO_SUBSTITUIR)
        item = ItemEstoque.objects.get(loja=self.loja, nome='goiabada cascao doces tradicao 250g')
        self.assertEqual(item.quantidade_estoque, Decimal('10'))

    def test_reverter_importacao_restaura_estoque(self):
        from app_pdv.importacao_produtos import (
            MODO_SOMAR,
            executar_importacao_produtos,
            normalizar_colunas_dataframe,
            reverter_importacao_produtos,
        )
        from app_pdv.models import ImportacaoProdutosLog, ItemEstoque, Produto

        df = normalizar_colunas_dataframe(self._df_goiabada(10))
        log, _ = executar_importacao_produtos(self.loja, self.user, df, 'c.xlsx', MODO_SOMAR)
        self.assertEqual(Produto.objects.filter(loja=self.loja).count(), 1)
        item = ItemEstoque.objects.get(pk=log.itens_snapshot.first().item_estoque_id)
        self.assertEqual(item.quantidade_estoque, Decimal('10'))

        log2, _ = executar_importacao_produtos(self.loja, self.user, df, 'd.xlsx', MODO_SOMAR)
        item.refresh_from_db()
        self.assertEqual(item.quantidade_estoque, Decimal('20'))

        out = reverter_importacao_produtos(
            ImportacaoProdutosLog.objects.get(pk=log2.id), self.user,
        )
        self.assertTrue(out.ok)
        item.refresh_from_db()
        self.assertEqual(item.quantidade_estoque, Decimal('10'))

        out = reverter_importacao_produtos(
            ImportacaoProdutosLog.objects.get(pk=log.id), self.user,
        )
        self.assertTrue(out.ok)
        self.assertFalse(ItemEstoque.objects.filter(loja=self.loja).exists())
        self.assertFalse(Produto.objects.filter(loja=self.loja).exists())
