"""Normaliza resposta da ACBrLib (JSON TipoResposta=2) para o formato interno."""
from __future__ import annotations

import re
from typing import Any


def _dig(obj: Any, *paths: str, default=''):
    if not isinstance(obj, dict):
        return default
    for path in paths:
        cur: Any = obj
        ok = True
        for part in path.split('.'):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                ok = False
                break
        if ok and cur not in (None, ''):
            return cur
    return default


def _buscar_chave(texto: str) -> str:
    m = re.search(r'\b(\d{44})\b', texto or '')
    return m.group(1) if m else ''


def _cstat_para_status(cstat: str) -> str:
    c = str(cstat or '').strip()
    if c in ('100', '150'):
        return 'autorizado'
    if c in ('110', '301', '302'):
        return 'denegado'
    if c in ('101', '135', '155'):
        return 'cancelado'
    if c:
        return 'erro_autorizacao'
    return 'erro'


def retorno_lib_para_interno(payload: dict, *, numero: int | None = None, serie: int | None = None) -> dict:
    """Converte POST /emitir do worker para o dict de _aplicar_retorno_focus."""
    if not isinstance(payload, dict):
        return {'status': 'erro', 'mensagem_sefaz': str(payload)}

    if payload.get('ok') is False:
        return {
            'status': 'erro',
            'mensagem_sefaz': str(payload.get('erro') or payload.get('detalhe') or 'Erro ACBrLib'),
            'status_sefaz': str(payload.get('codigo') or ''),
            'raw': payload,
        }

    resp = payload.get('resposta') if isinstance(payload.get('resposta'), dict) else {}
    texto = str(payload.get('texto') or '')

    # Formatos comuns do TipoResposta=2 (EnvRetorno / Retorno / raiz).
    cstat = str(_dig(
        resp,
        'EnvRetorno.cStat', 'cStat', 'Status.cStat', 'Retorno.cStat',
        'Envio.cStat', 'NFeRetorno.cStat',
        default='',
    ) or '')
    xmotivo = str(_dig(
        resp,
        'EnvRetorno.xMotivo', 'xMotivo', 'Status.xMotivo', 'Retorno.xMotivo',
        'Envio.xMotivo', 'NFeRetorno.xMotivo', 'mensagem',
        default='',
    ) or '')
    protocolo = str(_dig(
        resp,
        'EnvRetorno.nProt', 'nProt', 'Protocolo', 'Retorno.nProt',
        default='',
    ) or '')
    chave = str(_dig(
        resp,
        'EnvRetorno.chDFe', 'EnvRetorno.chNFe', 'chNFe', 'chDFe', 'Chave',
        'Retorno.chNFe',
        default='',
    ) or '')
    if not chave:
        chave = _buscar_chave(texto) or _buscar_chave(str(resp))

    if not cstat and isinstance(resp.get('raw'), str):
        m = re.search(r'"?cStat"?\s*[:=]\s*"?(\d+)"?', resp['raw'])
        if m:
            cstat = m.group(1)
        m2 = re.search(r'"?xMotivo"?\s*[:=]\s*"([^"]+)"', resp['raw'])
        if m2:
            xmotivo = m2.group(1)

    status = _cstat_para_status(cstat)
    if not cstat and payload.get('ok') and chave:
        status = 'autorizado'

    out = {
        'status': status,
        'numero': str(numero or _dig(resp, 'nNF', 'Numero', default='') or ''),
        'serie': str(serie or _dig(resp, 'serie', 'Serie', default='') or ''),
        'chave_nfe': chave,
        'chave': chave,
        'status_sefaz': cstat,
        'mensagem_sefaz': xmotivo or ('' if status == 'autorizado' else str(payload.get('detalhe') or '')),
        'protocolo': protocolo,
        'provedor': 'acbr_lib',
        'resposta_lib': resp,
    }
    if payload.get('caminho_xml'):
        out['caminho_xml_nota_fiscal'] = payload['caminho_xml']
        out['caminho_xml'] = payload['caminho_xml']
    if payload.get('caminho_pdf'):
        out['caminho_danfe'] = payload['caminho_pdf']
        out['caminho_pdf'] = payload['caminho_pdf']
    return out
