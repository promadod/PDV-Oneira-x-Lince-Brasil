from django.contrib.admin.models import ADDITION, CHANGE, LogEntry
from django.contrib.admin.sites import site as admin_site
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from app_pdv.loja_usuario import (
    PERMISSOES_USUARIO_PADRAO_LOJA,
    SENHA_PADRAO_NOVA_LOJA,
    username_from_loja_nome,
)
from app_pdv.models import Loja, LogAuditoria, PerfilUsuario


class AdminTituloTests(TestCase):
    def test_cabecalho_lince_brasil(self):
        self.assertEqual(admin_site.site_header, 'Lince brasil sistemas - Administração')
        self.assertNotIn('Magno', admin_site.site_header)


class UsuarioPadraoLojaTests(TestCase):
    def test_username_igual_ao_nome_simples(self):
        self.assertEqual(username_from_loja_nome('multimarcas'), 'multimarcas')

    def test_nome_composto_junta_sem_hifen(self):
        self.assertEqual(username_from_loja_nome('shop 10'), 'shop10')
        self.assertEqual(username_from_loja_nome('Loja Centro'), 'lojacentro')

    def test_criar_loja_gera_usuario_com_permissoes(self):
        loja = Loja.objects.create(nome='multimarcas')
        user = User.objects.get(username='multimarcas')
        self.assertTrue(user.check_password(SENHA_PADRAO_NOVA_LOJA))
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        perfil = PerfilUsuario.objects.get(user=user)
        self.assertEqual(perfil.loja_id, loja.id)
        for campo, valor in PERMISSOES_USUARIO_PADRAO_LOJA.items():
            self.assertTrue(getattr(perfil, campo), msg=campo)
        loja.refresh_from_db()
        self.assertEqual(loja.gerente_id, user.id)

    def test_nome_com_espaco_gera_username_junto(self):
        loja = Loja.objects.create(nome='shop 10')
        user = User.objects.get(username='shop10')
        self.assertEqual(user.perfil.loja_id, loja.id)

    def test_username_duplicado_recebe_sufixo(self):
        Loja.objects.create(nome='multimarcas')
        loja2 = Loja.objects.create(nome='multimarcas')
        self.assertTrue(User.objects.filter(username='multimarcas-2').exists())
        self.assertEqual(
            User.objects.get(username='multimarcas-2').perfil.loja_id,
            loja2.id,
        )


class LogDjangoAdminTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('gestor', 'g@x.com', 'x')
        self.loja = Loja.objects.create(nome='loja-log')

    def test_log_entry_aparece_na_central(self):
        LogEntry.objects.create(
            user=self.admin,
            content_type=ContentType.objects.get_for_model(Loja),
            object_id=str(self.loja.pk),
            object_repr=str(self.loja),
            action_flag=ADDITION,
            change_message='Added.',
        )
        log = LogAuditoria.objects.filter(acao='ADMIN').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.usuario_id, self.admin.id)
        self.assertEqual(log.loja_id, self.loja.id)
        self.assertIn('Django Admin', log.descricao)
        self.assertIn('Loja', log.descricao)

    def test_alteracao_admin_tambem_registra(self):
        LogEntry.objects.create(
            user=self.admin,
            content_type=ContentType.objects.get_for_model(Loja),
            object_id=str(self.loja.pk),
            object_repr=str(self.loja),
            action_flag=CHANGE,
            change_message='Changed nome.',
        )
        log = LogAuditoria.objects.filter(acao='ADMIN', objeto_id=self.loja.id).order_by('-id').first()
        self.assertIsNotNone(log)
        self.assertIn('alterou', log.descricao)
