"""Consulta CNPJ via worker ACBrLibConsultaCNPJ."""
from __future__ import annotations

import json

from .acbr_lib_client import AcbrLibError, client_from_settings

PROVEDORES = (
    (1, 'BrasilAPI'),
    (2, 'ReceitaWS'),
    (3, 'CNPJ.ws'),
)

# Ordem de exibição; o restante da resposta entra depois, na ordem original.
CAMPOS = (
    ('RazaoSocial', 'Razão social'),
    ('Fantasia', 'Nome fantasia'),
    ('EmpresaTipo', 'Tipo'),
    ('Abertura', 'Abertura'),
    ('Situacao', 'Situação'),
    ('CapitalSocial', 'Capital social'),
    ('NaturezaJuridica', 'Natureza jurídica'),
    ('CNAE1', 'CNAE principal'),
    ('CNAE2', 'CNAE secundário'),
    ('InscricaoEstadual', 'Inscrição estadual'),
    ('Endereco', 'Endereço'),
    ('Numero', 'Número'),
    ('Complemento', 'Complemento'),
    ('Bairro', 'Bairro'),
    ('Cidade', 'Cidade'),
    ('UF', 'UF'),
    ('CEP', 'CEP'),
    ('Email', 'E-mail'),
    ('Telefone', 'Telefone'),
)


def parse_resposta(texto: str) -> dict[str, str]:
    """Converte INI [Consulta] ou JSON da Lib em dict plano."""
    texto = (texto or '').strip()
    if not texto:
        return {}
    if texto.startswith('{'):
        try:
            data = json.loads(texto)
        except json.JSONDecodeError:
            data = {}
        if isinstance(data, dict):
            bloco = data.get('Consulta') if isinstance(data.get('Consulta'), dict) else data
            return {str(k): '' if v is None else str(v) for k, v in bloco.items()}
    dados: dict[str, str] = {}
    secao = ''
    for linha in texto.splitlines():
        raw = linha.strip()
        if not raw or raw.startswith(';'):
            continue
        if raw.startswith('[') and raw.endswith(']'):
            secao = raw[1:-1].strip()
            continue
        if '=' not in raw:
            continue
        chave, _, valor = raw.partition('=')
        chave, valor = chave.strip(), valor.strip()
        if secao and secao.lower() != 'consulta':
            chave = f'{secao}.{chave}'
        dados[chave] = valor
    return dados


def rotulos_dados(dados: dict) -> list[tuple[str, str, str]]:
    """[(chave, rótulo, valor)] com campos conhecidos primeiro e o restante depois."""
    dados = {str(k): '' if v is None else str(v) for k, v in (dados or {}).items()}
    vistos = set()
    linhas: list[tuple[str, str, str]] = []
    for chave, rotulo in CAMPOS:
        if chave in dados:
            linhas.append((chave, rotulo, dados[chave]))
            vistos.add(chave)
    for chave, valor in dados.items():
        if chave not in vistos:
            linhas.append((chave, chave, valor))
    return linhas


def consultar(cnpj: str, provedor: int = 1) -> dict:
    return client_from_settings().consultar_cnpj(cnpj, provedor)


__all__ = ['AcbrLibError', 'CAMPOS', 'PROVEDORES', 'consultar', 'parse_resposta', 'rotulos_dados']
