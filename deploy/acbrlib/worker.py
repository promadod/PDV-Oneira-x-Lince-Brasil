"""HTTP sidecar para ACBrLibNFe Console MT (ctypes)."""
from __future__ import annotations

import base64
import json
import logging
import os
import shutil
import tempfile
import threading
import time
import traceback
from ctypes import (
    CDLL,
    POINTER,
    byref,
    c_bool,
    c_char_p,
    c_int,
    c_void_p,
    create_string_buffer,
)
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger('acbrlib.worker')

SO_PATH = os.environ.get('ACBR_LIB_SO', '/opt/acbrlib/Linux/CONSOLE-MT/libacbrnfe64.so')
SCHEMAS_PATH = os.environ.get('ACBR_LIB_SCHEMAS', '/opt/acbrlib/Schemas/NFe')
SERVICOS_PATH = os.environ.get('ACBR_LIB_SERVICOS', '/opt/acbrlib/ACBrNFeServicos.ini')
WORK_ROOT = Path(os.environ.get('ACBR_LIB_WORK', '/var/acbrlib/work'))
# Demo ACBrLib: ~30 min por processo; reciclamos antes para evitar -999 "Demo expirou".
DEMO_MAX_SECONDS = int(os.environ.get('ACBR_LIB_DEMO_MAX_SECONDS', '1500') or '1500')

app = Flask(__name__)
_LOCK = threading.Lock()
_LIB: CDLL | None = None
_PROCESS_STARTED = time.monotonic()
_EXIT_SCHEDULED = False


class AcbrLibError(Exception):
    def __init__(self, message: str, code: int | None = None, detalhe: str = ''):
        super().__init__(message)
        self.code = code
        self.detalhe = detalhe


def _demo_expirou_texto(*parts: Any) -> bool:
    blob = ' '.join(str(p or '') for p in parts).lower()
    return 'demo' in blob and 'expirou' in blob


def _schedule_worker_exit(motivo: str) -> None:
    """Gunicorn sobe um worker novo; a Demo volta a valer por ~30 min."""
    global _EXIT_SCHEDULED
    if _EXIT_SCHEDULED:
        return
    _EXIT_SCHEDULED = True
    logger.warning('Reciclando worker ACBrLib (%s)', motivo)

    def _kill():
        time.sleep(0.4)
        os._exit(0)

    threading.Thread(target=_kill, daemon=True).start()


def _demo_precisa_reciclar() -> bool:
    return (time.monotonic() - _PROCESS_STARTED) >= max(60, DEMO_MAX_SECONDS)


def _b(s: str | None) -> bytes:
    return (s or '').encode('utf-8')


def _load_lib() -> CDLL:
    global _LIB
    if _LIB is not None:
        return _LIB
    if not Path(SO_PATH).is_file():
        raise AcbrLibError(f'SO não encontrada: {SO_PATH}')
    lib = CDLL(SO_PATH)

    lib.NFE_Inicializar.argtypes = [POINTER(c_void_p), c_char_p, c_char_p]
    lib.NFE_Inicializar.restype = c_int
    lib.NFE_Finalizar.argtypes = [c_void_p]
    lib.NFE_Finalizar.restype = c_int
    lib.NFE_ConfigGravarValor.argtypes = [c_void_p, c_char_p, c_char_p, c_char_p]
    lib.NFE_ConfigGravarValor.restype = c_int
    lib.NFE_ConfigGravar.argtypes = [c_void_p, c_char_p]
    lib.NFE_ConfigGravar.restype = c_int
    lib.NFE_UltimoRetorno.argtypes = [c_void_p, c_char_p, POINTER(c_int)]
    lib.NFE_UltimoRetorno.restype = c_int
    lib.NFE_LimparLista.argtypes = [c_void_p]
    lib.NFE_LimparLista.restype = c_int
    lib.NFE_CarregarINI.argtypes = [c_void_p, c_char_p]
    lib.NFE_CarregarINI.restype = c_int
    lib.NFE_Assinar.argtypes = [c_void_p]
    lib.NFE_Assinar.restype = c_int
    lib.NFE_Validar.argtypes = [c_void_p]
    lib.NFE_Validar.restype = c_int
    lib.NFE_StatusServico.argtypes = [c_void_p, c_char_p, POINTER(c_int)]
    lib.NFE_StatusServico.restype = c_int
    lib.NFE_Enviar.argtypes = [c_void_p, c_int, c_bool, c_bool, c_bool, c_char_p, POINTER(c_int)]
    lib.NFE_Enviar.restype = c_int

    for name, argtypes in (
        ('NFE_GravarXml', [c_void_p, c_int, c_char_p, c_char_p]),
        ('NFE_ObterXml', [c_void_p, c_int, c_char_p, POINTER(c_int)]),
        ('NFE_ImprimirPDF', [c_void_p]),
        ('NFE_Versao', [c_void_p, c_char_p, POINTER(c_int)]),
    ):
        if hasattr(lib, name):
            fn = getattr(lib, name)
            fn.argtypes = argtypes
            fn.restype = c_int

    _LIB = lib
    logger.info('ACBrLib carregada: %s', SO_PATH)
    return lib


def _ultimo_retorno(lib: CDLL, handle: c_void_p) -> str:
    size = c_int(0)
    buf = create_string_buffer(1)
    lib.NFE_UltimoRetorno(handle, buf, byref(size))
    if size.value <= 0:
        return ''
    buf = create_string_buffer(size.value + 1)
    size = c_int(size.value + 1)
    lib.NFE_UltimoRetorno(handle, buf, byref(size))
    return buf.value.decode('utf-8', errors='replace')


def _check(lib: CDLL, handle: c_void_p, code: int, metodo: str) -> str:
    detalhe = _ultimo_retorno(lib, handle)
    if code != 0:
        raise AcbrLibError(f'{metodo} falhou (código {code})', code=code, detalhe=detalhe)
    return detalhe


def _call_buffer(lib: CDLL, handle: c_void_p, metodo: str, call) -> tuple[int, str]:
    size = c_int(0)
    buf = create_string_buffer(1)
    code = call(buf, size)
    if size.value > 1:
        buf = create_string_buffer(size.value + 1)
        size = c_int(size.value + 1)
        code = call(buf, size)
        texto = buf.value.decode('utf-8', errors='replace')
    else:
        texto = _ultimo_retorno(lib, handle)
    if code != 0:
        raise AcbrLibError(f'{metodo} falhou (código {code})', code=code, detalhe=texto)
    return code, texto


def _cfg(lib: CDLL, handle: c_void_p, sessao: str, chave: str, valor: str) -> None:
    code = lib.NFE_ConfigGravarValor(handle, _b(sessao), _b(chave), _b(str(valor)))
    _check(lib, handle, code, f'ConfigGravarValor[{sessao}.{chave}]')


def _aplicar_config(lib: CDLL, handle: c_void_p, cfg: dict, work: Path) -> None:
    out = work / 'out'
    out.mkdir(parents=True, exist_ok=True)
    pdf = work / 'pdf'
    pdf.mkdir(parents=True, exist_ok=True)

    _cfg(lib, handle, 'Principal', 'TipoResposta', '2')
    # Respostas em UTF-8; o INI da nota é gravado em CP1252 (compatível com a Lib ANSI).
    _cfg(lib, handle, 'Principal', 'CodificacaoResposta', '0')
    _cfg(lib, handle, 'Principal', 'LogNivel', str(cfg.get('log_nivel', '2')))
    _cfg(lib, handle, 'Principal', 'LogPath', str(work))

    _cfg(lib, handle, 'DFe', 'SSLCryptLib', str(cfg.get('ssl_crypt', '1')))
    _cfg(lib, handle, 'DFe', 'SSLHttpLib', str(cfg.get('ssl_http', '3')))
    _cfg(lib, handle, 'DFe', 'SSLXmlSignLib', str(cfg.get('ssl_xml', '4')))
    _cfg(lib, handle, 'DFe', 'UF', (cfg.get('uf') or 'RJ').upper()[:2])
    # tzManual: sem isso a Lib usa /etc/localtime (UTC no Debian) e grava dhEmi+00:00 → SEFAZ 704.
    _cfg(lib, handle, 'DFe', 'TimeZone.Modo', str(cfg.get('tz_modo', '2')))
    _cfg(lib, handle, 'DFe', 'TimeZone.Str', str(cfg.get('tz_str') or '-03:00'))
    pfx = cfg.get('pfx_path') or ''
    if pfx:
        _cfg(lib, handle, 'DFe', 'ArquivoPFX', pfx)
    if cfg.get('pfx_senha') is not None:
        _cfg(lib, handle, 'DFe', 'Senha', str(cfg.get('pfx_senha') or ''))

    ambiente = 1 if (cfg.get('ambiente') or 'homologacao') != 'producao' else 0
    modelo = 1 if (cfg.get('modelo') or '65') in (65, '65', 1, '1') else 0
    _cfg(lib, handle, 'NFe', 'Ambiente', str(ambiente))
    _cfg(lib, handle, 'NFe', 'FormaEmissao', str(cfg.get('forma_emissao', '0')))
    _cfg(lib, handle, 'NFe', 'ModeloDF', str(modelo))
    _cfg(lib, handle, 'NFe', 'VersaoDF', str(cfg.get('versao_df', '3')))
    _cfg(lib, handle, 'NFe', 'SSLType', str(cfg.get('ssl_type', '5')))
    # Mantém ç/ã/õ no XML e no DANFE (API já envia acentuado).
    _cfg(lib, handle, 'NFe', 'RetirarAcentos', '0')
    _cfg(lib, handle, 'NFe', 'PathSchemas', cfg.get('schemas_path') or SCHEMAS_PATH)
    _cfg(lib, handle, 'NFe', 'PathSalvar', str(out))
    _cfg(lib, handle, 'NFe', 'PathNFe', str(out))
    _cfg(lib, handle, 'NFe', 'SepararPorCNPJ', '0')
    if Path(SERVICOS_PATH).is_file():
        _cfg(lib, handle, 'NFe', 'IniServicos', SERVICOS_PATH)

    if modelo == 1:
        if cfg.get('csc_id'):
            _cfg(lib, handle, 'NFe', 'IdCSC', str(cfg['csc_id']))
        if cfg.get('csc_token'):
            _cfg(lib, handle, 'NFe', 'CSC', str(cfg['csc_token']))

    _cfg(lib, handle, 'DANFE', 'PathPDF', str(pdf))
    # Rodapé do PDF nativo: sessão [Sistema], não [DANFE] (DANFE.Sistema não existe nesta Lib).
    # O DANFE final é regenerado no Django sem o texto Demo.
    try:
        _cfg(lib, handle, 'Sistema', 'Nome', str(cfg.get('sistema') or 'Oneira PDV'))
    except AcbrLibError as exc:
        logger.warning('Sistema.Nome ignorado: %s %s', exc, exc.detalhe)
    lib.NFE_ConfigGravar(handle, _b(str(work / 'ACBrLib.ini')))


def _session(cfg: dict):
    lib = _load_lib()
    work = Path(tempfile.mkdtemp(prefix='acbr_', dir=str(WORK_ROOT)))
    handle = c_void_p()
    code = lib.NFE_Inicializar(byref(handle), _b(str(work / 'ACBrLib.ini')), _b(''))
    if code != 0:
        shutil.rmtree(work, ignore_errors=True)
        raise AcbrLibError(f'NFE_Inicializar falhou (código {code})', code=code)
    try:
        _aplicar_config(lib, handle, cfg, work)
        yield lib, handle, work
    finally:
        try:
            lib.NFE_Finalizar(handle)
        except Exception:
            logger.exception('NFE_Finalizar')
        shutil.rmtree(work, ignore_errors=True)


def _ler_arquivos(pasta: Path, extensoes: tuple[str, ...]) -> list[Path]:
    if not pasta.is_dir():
        return []
    arquivos: list[Path] = []
    for p in pasta.rglob('*'):
        if p.is_file() and p.suffix.lower() in extensoes:
            arquivos.append(p)
    return sorted(arquivos, key=lambda x: x.stat().st_mtime, reverse=True)


def _b64_file(path: Path | None) -> str:
    if not path or not path.is_file():
        return ''
    return base64.b64encode(path.read_bytes()).decode('ascii')


def _parse_jsonish(texto: str) -> Any:
    texto = (texto or '').strip()
    if not texto:
        return {}
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        return {'raw': texto}


def status_servico(cfg: dict) -> dict:
    with _LOCK:
        for lib, handle, _work in _session(cfg):
            code, texto = _call_buffer(
                lib, handle, 'NFE_StatusServico',
                lambda buf, size: lib.NFE_StatusServico(handle, buf, byref(size)),
            )
            return {'ok': True, 'codigo': code, 'resposta': _parse_jsonish(texto), 'texto': texto}


def _gravar_ini_nota(path: Path, ini_conteudo: str) -> None:
    """XML NFe/Assinar exige UTF-8. Com LANG=C.UTF-8 a Lib lê o INI corretamente (sem mojibake)."""
    path.write_text(ini_conteudo or '', encoding='utf-8')


def emitir(cfg: dict, ini_conteudo: str) -> dict:
    if not (ini_conteudo or '').strip():
        raise AcbrLibError('INI da nota vazio')
    with _LOCK:
        for lib, handle, work in _session(cfg):
            ini_path = work / 'nota.ini'
            _gravar_ini_nota(ini_path, ini_conteudo)
            _check(lib, handle, lib.NFE_LimparLista(handle), 'NFE_LimparLista')
            # Prefere conteúdo INI em UTF-8 (evita path + codepage do SO).
            # Fallback: arquivo se a Lib rejeitar o buffer.
            code_ini = lib.NFE_CarregarINI(handle, _b(ini_conteudo))
            if code_ini != 0:
                logger.warning(
                    'NFE_CarregarINI(conteúdo) código %s — tentando arquivo: %s',
                    code_ini, _ultimo_retorno(lib, handle),
                )
                _check(lib, handle, lib.NFE_CarregarINI(handle, _b(str(ini_path))), 'NFE_CarregarINI')
            _check(lib, handle, lib.NFE_Assinar(handle), 'NFE_Assinar')
            try:
                _check(lib, handle, lib.NFE_Validar(handle), 'NFE_Validar')
            except AcbrLibError as exc:
                # Algumas UFs/homolog rejeitam validação local; segue para envio se Assinar ok.
                logger.warning('NFE_Validar: %s %s', exc, exc.detalhe)

            if hasattr(lib, 'NFE_GravarXml'):
                _check(lib, handle, lib.NFE_GravarXml(handle, 0, _b(''), _b('')), 'NFE_GravarXml')

            code, texto = _call_buffer(
                lib, handle, 'NFE_Enviar',
                lambda buf, size: lib.NFE_Enviar(
                    handle, c_int(1), c_bool(False), c_bool(True), c_bool(False), buf, byref(size),
                ),
            )
            resposta = _parse_jsonish(texto)

            xml_b64 = ''
            if hasattr(lib, 'NFE_ObterXml'):
                try:
                    _, xml_txt = _call_buffer(
                        lib, handle, 'NFE_ObterXml',
                        lambda buf, size: lib.NFE_ObterXml(handle, 0, buf, byref(size)),
                    )
                    if xml_txt.strip().startswith('<'):
                        xml_b64 = base64.b64encode(xml_txt.encode('utf-8')).decode('ascii')
                except AcbrLibError:
                    logger.warning('NFE_ObterXml indisponível ou falhou')

            xmls = _ler_arquivos(work / 'out', ('.xml',))
            if not xml_b64 and xmls:
                xml_b64 = _b64_file(xmls[0])

            pdf_b64 = ''
            if hasattr(lib, 'NFE_ImprimirPDF'):
                try:
                    _check(lib, handle, lib.NFE_ImprimirPDF(handle), 'NFE_ImprimirPDF')
                    pdfs = _ler_arquivos(work / 'pdf', ('.pdf',))
                    if pdfs:
                        pdf_b64 = _b64_file(pdfs[0])
                except AcbrLibError as exc:
                    logger.warning('PDF: %s %s', exc, exc.detalhe)

            return {
                'ok': True,
                'codigo': code,
                'resposta': resposta,
                'texto': texto,
                'xml_b64': xml_b64,
                'pdf_b64': pdf_b64,
            }


@app.get('/health')
def health():
    so_ok = Path(SO_PATH).is_file()
    schemas_ok = Path(SCHEMAS_PATH).is_dir()
    info: dict[str, Any] = {
        'ok': so_ok and schemas_ok,
        'so': SO_PATH,
        'so_ok': so_ok,
        'schemas': SCHEMAS_PATH,
        'schemas_ok': schemas_ok,
        'openssl_conf': os.environ.get('OPENSSL_CONF', ''),
    }
    if so_ok:
        try:
            _load_lib()
            info['lib_loaded'] = True
        except Exception as exc:
            info['ok'] = False
            info['lib_loaded'] = False
            info['erro'] = str(exc)
    status = 200 if info['ok'] else 503
    return jsonify(info), status


def _resposta_demo_recycle():
    _schedule_worker_exit('limite Demo ~30min')
    return jsonify({
        'ok': False,
        'erro': 'demo_recycle',
        'codigo': -999,
        'detalhe': (
            'ACBrLib Demo atingiu o limite de ~30 minutos neste processo. '
            'O worker está reiniciando; tente de novo em alguns segundos '
            '(ou use a SO Pro, sem esse limite).'
        ),
    }), 503


@app.post('/status')
def api_status():
    if _demo_precisa_reciclar():
        return _resposta_demo_recycle()
    body = request.get_json(silent=True) or {}
    cfg = body.get('config') or body
    try:
        WORK_ROOT.mkdir(parents=True, exist_ok=True)
        return jsonify(status_servico(cfg))
    except AcbrLibError as exc:
        if _demo_expirou_texto(exc, exc.detalhe):
            _schedule_worker_exit('Demo expirou no StatusServico')
            return jsonify({
                'ok': False, 'erro': 'demo_expired', 'codigo': exc.code,
                'detalhe': exc.detalhe or str(exc),
            }), 503
        return jsonify({
            'ok': False, 'erro': str(exc), 'codigo': exc.code, 'detalhe': exc.detalhe,
        }), 400
    except Exception as exc:
        logger.exception('status')
        return jsonify({'ok': False, 'erro': str(exc), 'trace': traceback.format_exc()}), 500


@app.post('/emitir')
def api_emitir():
    if _demo_precisa_reciclar():
        return _resposta_demo_recycle()
    body = request.get_json(silent=True) or {}
    cfg = body.get('config') or {}
    ini = body.get('ini') or ''
    try:
        WORK_ROOT.mkdir(parents=True, exist_ok=True)
        return jsonify(emitir(cfg, ini))
    except AcbrLibError as exc:
        if _demo_expirou_texto(exc, exc.detalhe):
            _schedule_worker_exit('Demo expirou no Enviar')
            return jsonify({
                'ok': False, 'erro': 'demo_expired', 'codigo': exc.code,
                'detalhe': (
                    'O Demo da ACBrLibNFe expirou neste processo (limite ~30 min). '
                    'Worker reiniciando — reemitir em alguns segundos. '
                    'Para produção contínua, substitua a SO pela versão Pro.'
                ),
            }), 503
        return jsonify({
            'ok': False, 'erro': str(exc), 'codigo': exc.code, 'detalhe': exc.detalhe,
        }), 400
    except Exception as exc:
        logger.exception('emitir')
        return jsonify({'ok': False, 'erro': str(exc), 'trace': traceback.format_exc()}), 500


if __name__ == '__main__':
    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', '8091')), debug=False)
