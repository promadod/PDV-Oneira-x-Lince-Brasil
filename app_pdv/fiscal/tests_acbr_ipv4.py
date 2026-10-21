"""Chamadas da ACBr ficam em IPv4."""
import socket
from unittest.mock import patch

from django.test import SimpleTestCase

from app_pdv.fiscal.acbr_client import _IPv4HTTPSConnection


class AcbrIPv4Test(SimpleTestCase):
    def test_abre_conexao_no_endereco_ipv4(self):
        familias = []

        def fake_getaddrinfo(host, port, family, socktype):
            familias.append((host, family))
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('104.20.31.148', port))]

        with (
            patch('app_pdv.fiscal.acbr_client.socket.getaddrinfo', fake_getaddrinfo),
            patch('app_pdv.fiscal.acbr_client.urllib3_connection.create_connection', return_value=object()) as criar,
        ):
            conn = _IPv4HTTPSConnection(host='auth.acbr.api.br', port=443, timeout=5)
            conn._new_conn()

        self.assertEqual(familias, [('auth.acbr.api.br', socket.AF_INET)])
        self.assertEqual(criar.call_args.args[0], ('104.20.31.148', 443))
