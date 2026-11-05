"""Naturezas de operação (CFOP) por loja + importação do catálogo markdown."""
from __future__ import annotations

import re
from pathlib import Path

from django.conf import settings

from .models import NaturezaOperacaoFiscal
from .nfe_catalog import NATUREZAS_NFE_UNICAS, PERFIL_TRIBUTACAO_NFE


def _normalizar_cfop(valor: str) -> str:
    return ''.join(c for c in (valor or '') if c.isdigit())[:4]


def parse_catalogo_naturezas_md() -> list[tuple[str, str]]:
    """Lê catalogo_naturezas_cfop.md — pares (descrição, cfop)."""
    path = Path(settings.BASE_DIR) / 'catalogo_naturezas_cfop.md'
    if not path.is_file():
        return []
    texto = path.read_text(encoding='utf-8')
    pares: list[tuple[str, str]] = []
    for linha in texto.splitlines():
        if '|' not in linha or '---' in linha:
            continue
        cols = [c.strip() for c in linha.split('|') if c.strip()]
        if len(cols) < 2:
            continue
        cfop_raw = cols[-1]
        cfops = re.findall(r'\d[\d\.]{3,7}', cfop_raw)
        if not cfops:
            continue
        desc = cols[0]
        if desc.lower().startswith('natureza') or desc.lower().startswith('cfop'):
            continue
        for cf in cfops:
            cfop = _normalizar_cfop(cf)
            if len(cfop) == 4:
                pares.append((desc[:120], cfop))
    # dedupe by cfop+desc
    vistos = set()
    unicos = []
    for desc, cfop in pares:
        key = (cfop, desc)
        if key in vistos:
            continue
        vistos.add(key)
        unicos.append((desc, cfop))
    return unicos


def ensure_naturezas_padrao_loja(loja) -> None:
    """Garante naturezas iniciais (built-in + catálogo MD) na loja."""
    if NaturezaOperacaoFiscal.objects.filter(loja=loja).exists():
        return
    bulk = []
    for cfop, desc in NATUREZAS_NFE_UNICAS:
        bulk.append(NaturezaOperacaoFiscal(
            loja=loja, cfop=cfop, descricao=desc[:120], tributacao='produto', ativa=True,
        ))
    for desc, cfop in parse_catalogo_naturezas_md()[:400]:
        bulk.append(NaturezaOperacaoFiscal(
            loja=loja, cfop=cfop, descricao=desc[:120], tributacao='produto', ativa=True,
        ))
    # dedupe cfop+desc before insert
    seen = set()
    final = []
    for n in bulk:
        k = (n.cfop, n.descricao)
        if k in seen:
            continue
        seen.add(k)
        final.append(n)
    NaturezaOperacaoFiscal.objects.bulk_create(final, ignore_conflicts=True)


def choices_natureza_cfop(loja) -> list[tuple[str, str]]:
    ensure_naturezas_padrao_loja(loja)
    return [
        (n.cfop, f'{n.cfop} — {n.descricao}')
        for n in NaturezaOperacaoFiscal.objects.filter(loja=loja, ativa=True).order_by('cfop', 'descricao')
    ]


def descricao_natureza_loja(loja, cfop: str) -> str:
    cfop = _normalizar_cfop(cfop)
    obj = NaturezaOperacaoFiscal.objects.filter(loja=loja, cfop=cfop, ativa=True).first()
    if obj:
        return obj.descricao
    for c, desc in NATUREZAS_NFE_UNICAS:
        if c == cfop:
            return desc
    return f'Operação CFOP {cfop}'


def tributacao_da_natureza(loja, cfop: str) -> str:
    cfop = _normalizar_cfop(cfop)
    obj = NaturezaOperacaoFiscal.objects.filter(loja=loja, cfop=cfop, ativa=True).first()
    return obj.tributacao if obj else 'produto'


def criar_natureza_loja(loja, *, cfop: str, descricao: str, tributacao: str = 'produto'):
    cfop = _normalizar_cfop(cfop)
    if len(cfop) != 4:
        raise ValueError('CFOP inválido (4 dígitos).')
    descricao = (descricao or '').strip()[:120]
    if not descricao:
        raise ValueError('Descrição da natureza é obrigatória.')
    if tributacao not in dict(PERFIL_TRIBUTACAO_NFE):
        tributacao = 'produto'
    # NaturezaOperacaoFiscal.TRIBUTACAO_CHOICES usa subset compatível
    obj, _ = NaturezaOperacaoFiscal.objects.update_or_create(
        loja=loja,
        cfop=cfop,
        descricao=descricao,
        defaults={'tributacao': tributacao, 'ativa': True},
    )
    return obj
