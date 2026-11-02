"""Consulta CNPJ via worker ACBrLibConsultaCNPJ."""
from __future__ import annotations

import json
import re

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


def _digitos(value: str) -> str:
    return re.sub(r'\D', '', value or '')


def fmt_cnpj(value: str) -> str:
    d = _digitos(value)
    if len(d) == 14:
        return f'{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}'
    return value or ''


def fmt_cep(value: str) -> str:
    d = _digitos(value)
    if len(d) == 8:
        return f'{d[:5]}-{d[5:]}'
    return value or ''


def fmt_data(value: str) -> str:
    raw = (value or '').strip()
    if 'T' in raw:
        raw = raw.split('T', 1)[0]
    m = re.match(r'^(\d{4})-(\d{2})-(\d{2})', raw)
    if m:
        return f'{m.group(3)}/{m.group(2)}/{m.group(1)}'
    return value or ''


def fmt_capital(value) -> str:
    texto = str(value or '').strip()
    if not texto:
        return ''
    try:
        numero = float(texto.replace('.', '').replace(',', '.')) if ',' in texto and '.' in texto else float(texto.replace(',', '.'))
    except (TypeError, ValueError):
        return texto
    return f'R$ {numero:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def split_cnaes(texto: str) -> list[dict[str, str]]:
    raw = (texto or '').strip()
    if not raw:
        return []
    partes = re.split(r'[\n;]+|(?=\d{7}\s)', raw)
    itens: list[dict[str, str]] = []
    for parte in partes:
        parte = re.sub(r'\s+', ' ', parte).strip(' -')
        if not parte:
            continue
        m = re.match(r'^(\d{7})\s*(.*)$', parte)
        if m:
            itens.append({'codigo': m.group(1), 'descricao': m.group(2).strip()})
        else:
            itens.append({'codigo': '', 'descricao': parte})
    return itens


def _get(dados: dict, *chaves: str) -> str:
    for chave in chaves:
        val = dados.get(chave)
        if val is not None and str(val).strip():
            return str(val).strip()
    return ''


def montar_ficha(resultado: dict) -> dict:
    """Estrutura o retorno da Lib para o card da tela."""
    dados = {str(k): '' if v is None else str(v) for k, v in (resultado.get('dados') or {}).items()}
    usados = {
        'RazaoSocial', 'Fantasia', 'EmpresaTipo', 'Abertura', 'Situacao',
        'CapitalSocial', 'NaturezaJuridica', 'CNAE1', 'CNAE2', 'InscricaoEstadual',
        'Endereco', 'Numero', 'Complemento', 'Bairro', 'Cidade', 'UF', 'CEP',
        'Email', 'Telefone',
    }
    situacao = _get(dados, 'Situacao')
    situacao_up = situacao.upper()
    endereco_partes = [p for p in (
        _get(dados, 'Endereco'),
        _get(dados, 'Numero'),
        _get(dados, 'Complemento'),
    ) if p]
    cidade_uf = ' / '.join(p for p in (_get(dados, 'Cidade'), _get(dados, 'UF')) if p)
    extras = [
        (chave, chave, valor)
        for chave, valor in dados.items()
        if chave not in usados and str(valor).strip()
    ]
    return {
        'cnpj_fmt': fmt_cnpj(resultado.get('cnpj') or ''),
        'provedor_nome': resultado.get('provedor_nome') or '',
        'razao': _get(dados, 'RazaoSocial') or 'Empresa não identificada',
        'fantasia': _get(dados, 'Fantasia'),
        'tipo': _get(dados, 'EmpresaTipo'),
        'situacao': situacao or '—',
        'situacao_ok': situacao_up in ('ATIVA', 'ATIVO'),
        'abertura': fmt_data(_get(dados, 'Abertura')),
        'capital': fmt_capital(_get(dados, 'CapitalSocial')),
        'natureza': _get(dados, 'NaturezaJuridica'),
        'ie': _get(dados, 'InscricaoEstadual'),
        'logradouro': ', '.join(endereco_partes),
        'bairro': _get(dados, 'Bairro'),
        'cidade_uf': cidade_uf,
        'cep': fmt_cep(_get(dados, 'CEP')),
        'email': _get(dados, 'Email'),
        'telefone': _get(dados, 'Telefone'),
        'cnae_principal': (split_cnaes(_get(dados, 'CNAE1')) or [{'codigo': '', 'descricao': _get(dados, 'CNAE1')}])[0] if _get(dados, 'CNAE1') else None,
        'cnaes_secundarios': split_cnaes(_get(dados, 'CNAE2')),
        'extras': extras,
        'texto': resultado.get('texto') or '',
        'tem_endereco': bool(endereco_partes or _get(dados, 'Bairro') or cidade_uf or _get(dados, 'CEP')),
        'tem_contato': bool(_get(dados, 'Email') or _get(dados, 'Telefone')),
    }


def consultar(cnpj: str, provedor: int = 1) -> dict:
    return client_from_settings().consultar_cnpj(cnpj, provedor)


__all__ = [
    'AcbrLibError', 'CAMPOS', 'PROVEDORES', 'consultar', 'fmt_cnpj',
    'montar_ficha', 'parse_resposta', 'rotulos_dados', 'split_cnaes',
]
