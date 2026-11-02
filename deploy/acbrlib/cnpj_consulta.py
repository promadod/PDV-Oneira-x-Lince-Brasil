"""Consulta CNPJ via ACBrLibConsultaCNPJ Pro (Console MT).

Roda em processo separado do worker NFe: as duas .so no mesmo processo
podem crashar no Linux.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from ctypes import CDLL, POINTER, byref, c_char_p, c_int, c_void_p, create_string_buffer
from pathlib import Path

SO_PATH = os.environ.get(
    'ACBR_LIB_CNPJ_SO',
    '/opt/acbrlib/Linux/CONSOLE-MT/libacbrconsultacnpj64.so',
)
WORK_ROOT = Path(os.environ.get('ACBR_LIB_WORK', '/var/acbrlib/work'))

PROVEDORES = {
    1: 'BrasilAPI',
    2: 'ReceitaWS',
    3: 'CNPJ.ws',
}


class ConsultaCnpjError(Exception):
    def __init__(self, message: str, code: int | None = None, detalhe: str = ''):
        super().__init__(message)
        self.code = code
        self.detalhe = detalhe


def _b(s: str | None) -> bytes:
    return (s or '').encode('utf-8')


def _load() -> CDLL:
    if not Path(SO_PATH).is_file():
        raise ConsultaCnpjError(f'SO ConsultaCNPJ não encontrada: {SO_PATH}')
    lib = CDLL(SO_PATH)
    lib.CNPJ_Inicializar.argtypes = [POINTER(c_void_p), c_char_p, c_char_p]
    lib.CNPJ_Inicializar.restype = c_int
    lib.CNPJ_Finalizar.argtypes = [c_void_p]
    lib.CNPJ_Finalizar.restype = c_int
    lib.CNPJ_ConfigGravarValor.argtypes = [c_void_p, c_char_p, c_char_p, c_char_p]
    lib.CNPJ_ConfigGravarValor.restype = c_int
    lib.CNPJ_ConfigGravar.argtypes = [c_void_p, c_char_p]
    lib.CNPJ_ConfigGravar.restype = c_int
    lib.CNPJ_UltimoRetorno.argtypes = [c_void_p, c_char_p, POINTER(c_int)]
    lib.CNPJ_UltimoRetorno.restype = c_int
    lib.CNPJ_Consultar.argtypes = [c_void_p, c_char_p, c_char_p, POINTER(c_int)]
    lib.CNPJ_Consultar.restype = c_int
    return lib


def _ultimo(lib: CDLL, handle: c_void_p) -> str:
    size = c_int(0)
    buf = create_string_buffer(1)
    lib.CNPJ_UltimoRetorno(handle, buf, byref(size))
    if size.value <= 0:
        return ''
    buf = create_string_buffer(size.value + 1)
    size = c_int(size.value + 1)
    lib.CNPJ_UltimoRetorno(handle, buf, byref(size))
    return buf.value.decode('utf-8', errors='replace')


def _check(lib: CDLL, handle: c_void_p, code: int, metodo: str) -> str:
    detalhe = _ultimo(lib, handle)
    if code != 0:
        raise ConsultaCnpjError(f'{metodo} falhou (código {code})', code=code, detalhe=detalhe)
    return detalhe


def _call_buffer(lib: CDLL, handle: c_void_p, metodo: str, call) -> str:
    size = c_int(0)
    buf = create_string_buffer(1)
    code = call(buf, size)
    if size.value > 1:
        buf = create_string_buffer(size.value + 1)
        size = c_int(size.value + 1)
        code = call(buf, size)
        texto = buf.value.decode('utf-8', errors='replace')
    else:
        texto = _ultimo(lib, handle)
    if code != 0:
        raise ConsultaCnpjError(f'{metodo} falhou (código {code})', code=code, detalhe=texto)
    return texto


def parse_resposta(texto: str) -> dict[str, str]:
    """Converte INI [Consulta] ou JSON da Lib em dict plano chave→valor."""
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


def consultar(cnpj: str, provedor: int = 1) -> dict:
    digits = ''.join(c for c in str(cnpj or '') if c.isdigit())
    if len(digits) != 14:
        raise ConsultaCnpjError('Informe um CNPJ com 14 dígitos.')
    try:
        provedor = int(provedor)
    except (TypeError, ValueError):
        provedor = 1
    if provedor not in PROVEDORES:
        provedor = 1

    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix='cnpj_', dir=str(WORK_ROOT)))
    lib = _load()
    handle = c_void_p()
    code = lib.CNPJ_Inicializar(byref(handle), _b(str(work / 'ACBrLib.ini')), _b(''))
    if code != 0:
        raise ConsultaCnpjError(f'CNPJ_Inicializar falhou (código {code})', code=code)
    try:
        lib.CNPJ_ConfigGravarValor(handle, _b('Principal'), _b('TipoResposta'), _b('2'))
        lib.CNPJ_ConfigGravarValor(handle, _b('Principal'), _b('CodificacaoResposta'), _b('0'))
        lib.CNPJ_ConfigGravarValor(handle, _b('Principal'), _b('LogNivel'), _b('2'))
        lib.CNPJ_ConfigGravarValor(handle, _b('Principal'), _b('LogPath'), _b(str(work)))
        lib.CNPJ_ConfigGravarValor(handle, _b('ConsultaCNPJ'), _b('Provedor'), _b(str(provedor)))
        lib.CNPJ_ConfigGravar(handle, _b(str(work / 'ACBrLib.ini')))
        texto = _call_buffer(
            lib, handle, 'CNPJ_Consultar',
            lambda buf, size: lib.CNPJ_Consultar(handle, _b(digits), buf, byref(size)),
        )
        return {
            'ok': True,
            'cnpj': digits,
            'provedor': provedor,
            'provedor_nome': PROVEDORES[provedor],
            'dados': parse_resposta(texto),
            'texto': texto,
        }
    finally:
        try:
            lib.CNPJ_Finalizar(handle)
        except Exception:
            pass
        import shutil
        shutil.rmtree(work, ignore_errors=True)


def main() -> int:
    cnpj = os.environ.get('CNPJ') or (sys.argv[1] if len(sys.argv) > 1 else '')
    provedor = os.environ.get('PROVEDOR') or (sys.argv[2] if len(sys.argv) > 2 else '1')
    try:
        print(json.dumps(consultar(cnpj, int(provedor or 1)), ensure_ascii=False))
        return 0
    except ConsultaCnpjError as exc:
        print(json.dumps({
            'ok': False,
            'erro': str(exc),
            'codigo': exc.code,
            'detalhe': exc.detalhe,
        }, ensure_ascii=False))
        return 1
    except Exception as exc:
        print(json.dumps({'ok': False, 'erro': str(exc)}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    sys.exit(main())
