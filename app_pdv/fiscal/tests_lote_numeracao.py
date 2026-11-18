"""Emissão em lote: não reutilizar nNF após falha de conexão / SEFAZ 539."""
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from app_pdv.fiscal.models import DocumentoFiscal, FiscalConfig, ProdutoDadosFiscais
from app_pdv.fiscal.services import (
    _eh_duplicidade_chave_diferente,
    _reservar_proximo_numero,
    emitir_documento,
    processar_lote_emissao,
)
from app_pdv.models import ItemVenda, Loja, PerfilUsuario, Produto, Venda


class ReservarNumeroTest(TestCase):
    def setUp(self):
        self.loja = Loja.objects.create(nome='loja-lote-num', fiscal_habilitado=True, cnpj='49747180000169')
        self.cfg = FiscalConfig.objects.create(
            loja=self.loja,
            cnpj='49747180000169',
            proximo_numero_nfce=4,
            serie_nfce=2,
            provedor_emissao='lib',
        )

    def test_reservar_consome_numero_imediatamente(self):
        cfg, numero, serie = _reservar_proximo_numero(self.cfg, 'nfce')
        self.assertEqual(numero, 4)
        self.assertEqual(serie, 2)
        cfg.refresh_from_db()
        self.assertEqual(cfg.proximo_numero_nfce, 5)

    def test_eh_duplicidade_539(self):
        self.assertTrue(_eh_duplicidade_chave_diferente({
            'status_sefaz': '539',
            'mensagem_sefaz': 'Duplicidade de NF-e, com diferença na Chave de Acesso',
        }))
        self.assertFalse(_eh_duplicidade_chave_diferente({'status_sefaz': '704'}))


@override_settings(ACBR_LIB_ENABLED=True)
class LoteNumeracaoTest(TestCase):
    def setUp(self):
        self.loja = Loja.objects.create(nome='loja-lote-emit', fiscal_habilitado=True, cnpj='49747180000169')
        self.cfg = FiscalConfig.objects.create(
            loja=self.loja,
            cnpj='49747180000169',
            razao_social='LOJA',
            nome_fantasia='LOJA',
            inscricao_estadual='123',
            logradouro='Rua A',
            numero='1',
            bairro='Centro',
            municipio='Rio',
            uf='RJ',
            cep='20040020',
            codigo_ibge='3304557',
            crt='1',
            ambiente='homologacao',
            emite_nfce=True,
            serie_nfce=2,
            proximo_numero_nfce=4,
            provedor_emissao='lib',
            acbr_lib_pfx_path='fiscal/certs/1/cert.pfx',
            csc_id='000001',
            csc_token='token-teste',
        )
        self.user = User.objects.create_user('op-lote', password='x')
        perfil, _ = PerfilUsuario.objects.get_or_create(user=self.user)
        perfil.loja = self.loja
        perfil.perm_fiscal = True
        perfil.save()
        self.produto = Produto.objects.create(
            loja=self.loja, nome_venda='P13', preco_venda=Decimal('90'),
            quantidade_baixa=Decimal('1'),
        )
        ProdutoDadosFiscais.objects.create(
            produto=self.produto, ncm='27111910', cfop_venda='5102', csosn='102',
        )
        self.v1 = Venda.objects.create(loja=self.loja, status='FINALIZADO', total=Decimal('100'))
        self.v2 = Venda.objects.create(loja=self.loja, status='FINALIZADO', total=Decimal('90'))
        # bulk_create evita signal de estoque no setUp do teste fiscal.
        ItemVenda.objects.bulk_create([
            ItemVenda(venda=self.v1, produto=self.produto, quantidade=Decimal('1'), preco_unitario=Decimal('100')),
            ItemVenda(venda=self.v2, produto=self.produto, quantidade=Decimal('1'), preco_unitario=Decimal('90')),
        ])

    @patch('app_pdv.fiscal.acbr_lib_client.salvar_arquivos_lib', return_value={})
    @patch('app_pdv.fiscal.acbr_lib_client.AcbrLibClient')
    @patch('app_pdv.fiscal.acbr_lib_client.acbr_lib_habilitada', return_value=True)
    def test_falha_conexao_nao_reutiliza_numero_na_proxima_venda(self, _hab, mock_client_cls, _arq):
        from app_pdv.fiscal.acbr_lib_client import AcbrLibError

        client = MagicMock()
        mock_client_cls.return_value = client
        client.emitir.side_effect = [
            AcbrLibError('NFE_Enviar falhou (código -10): Erro HTTP: 0'),
            {
                'ok': True,
                'resposta': {
                    'EnvRetorno': {
                        'cStat': '100',
                        'xMotivo': 'Autorizado',
                        'chNFe': '33' + '0' * 42,
                        'nProt': '1',
                    },
                },
                'xml_b64': '',
                'pdf_b64': '',
            },
        ]

        lote = processar_lote_emissao(
            self.loja, self.user, tipo='nfce',
            vendas=[self.v1, self.v2],
            filtros_meta={'pular_ja_emitidas': True},
        )
        self.cfg.refresh_from_db()
        self.assertEqual(lote.total_erro, 1)
        self.assertEqual(lote.total_autorizado, 1)
        # 1ª venda consumiu nNF=4 (falha); 2ª usou nNF=5 e autorizou.
        self.assertEqual(self.cfg.proximo_numero_nfce, 6)
        docs = list(DocumentoFiscal.objects.filter(loja=self.loja, tipo='nfce').order_by('id'))
        self.assertEqual(len(docs), 2)
        self.assertEqual(docs[0].numero, '4')
        self.assertEqual(docs[0].status, 'erro')
        self.assertEqual(docs[1].numero, '5')
        self.assertEqual(docs[1].status, 'autorizado')
        self.assertEqual(client.emitir.call_count, 2)

    @patch('app_pdv.fiscal.acbr_lib_client.salvar_arquivos_lib', return_value={})
    @patch('app_pdv.fiscal.acbr_lib_client.AcbrLibClient')
    @patch('app_pdv.fiscal.acbr_lib_client.acbr_lib_habilitada', return_value=True)
    def test_539_tenta_proximo_numero_automaticamente(self, _hab, mock_client_cls, _arq):
        client = MagicMock()
        mock_client_cls.return_value = client
        client.emitir.side_effect = [
            {
                'ok': True,
                'resposta': {
                    'Envio': {
                        'CStat': 539,
                        'XMotivo': 'Rejeicao: Duplicidade de NF-e, com diferença na Chave de Acesso',
                    },
                },
            },
            {
                'ok': True,
                'resposta': {
                    'EnvRetorno': {
                        'cStat': '100',
                        'xMotivo': 'Autorizado',
                        'chNFe': '33' + '1' * 42,
                        'nProt': '2',
                    },
                },
                'xml_b64': '',
                'pdf_b64': '',
            },
        ]
        doc = emitir_documento(self.loja, self.user, tipo='nfce', venda=self.v1)
        self.cfg.refresh_from_db()
        self.assertEqual(doc.status, 'autorizado')
        self.assertEqual(doc.numero, '5')
        self.assertEqual(self.cfg.proximo_numero_nfce, 6)
        self.assertEqual(client.emitir.call_count, 2)
