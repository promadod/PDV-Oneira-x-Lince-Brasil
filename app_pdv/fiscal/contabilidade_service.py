"""Pacote contábil — ZIP com XMLs/PDFs autorizados no período."""
from __future__ import annotations

import io
import zipfile
from datetime import date

import requests
from django.core.mail import EmailMessage
from django.utils import timezone

from .focus_arquivos import url_pdf_documento, url_xml_documento
from .models import DocumentoFiscal, FiscalConfig


def documentos_contabilidade_periodo(loja, *, ano: int, mes: int):
    inicio = date(ano, mes, 1)
    if mes == 12:
        fim = date(ano + 1, 1, 1)
    else:
        fim = date(ano, mes + 1, 1)
    return DocumentoFiscal.objects.filter(
        loja=loja,
        status='autorizado',
        criado_em__date__gte=inicio,
        criado_em__date__lt=fim,
    ).order_by('criado_em')


def resumo_contabilidade(loja, *, ano: int, mes: int) -> dict:
    qs = documentos_contabilidade_periodo(loja, ano=ano, mes=mes)
    total = qs.count()
    cancelados = DocumentoFiscal.objects.filter(
        loja=loja,
        status='cancelado',
        criado_em__year=ano,
        criado_em__month=mes,
    ).count()
    erros = DocumentoFiscal.objects.filter(
        loja=loja,
        status='erro',
        criado_em__year=ano,
        criado_em__month=mes,
    ).count()
    return {
        'autorizados': total,
        'cancelados': cancelados,
        'inutilizados': 0,
        'erros': erros,
        'total_pacote': total,
    }


def _baixar_arquivo(cfg: FiscalConfig, url: str) -> bytes | None:
    if not url or not cfg.focus_token:
        return None
    try:
        resp = requests.get(
            url,
            auth=(cfg.focus_token.strip(), ''),
            timeout=90,
        )
        if resp.status_code == 200:
            return resp.content
    except requests.RequestException:
        return None
    return None


def montar_zip_contabilidade(loja, cfg: FiscalConfig, *, ano: int, mes: int) -> tuple[bytes, str]:
    docs = list(documentos_contabilidade_periodo(loja, ano=ano, mes=mes))
    buf = io.BytesIO()
    incluidos = 0
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        linhas = []
        for doc in docs:
            chave = doc.chave_acesso or doc.ref
            linhas.append(
                f'{doc.get_tipo_display()} nº {doc.numero} — R$ {doc.valor_total} — {chave}',
            )
            xml_url = url_xml_documento(cfg, doc)
            pdf_url = url_pdf_documento(cfg, doc)
            xml_bytes = _baixar_arquivo(cfg, xml_url)
            if xml_bytes:
                nome = f'XML/{chave or doc.ref}.xml'
                zf.writestr(nome, xml_bytes)
                incluidos += 1
            pdf_bytes = _baixar_arquivo(cfg, pdf_url)
            if pdf_bytes:
                nome_pdf = f'PDF/{chave or doc.ref}.pdf'
                zf.writestr(nome_pdf, pdf_bytes)
                incluidos += 1
        zf.writestr(
            'LISTAGEM.txt',
            '\n'.join(linhas) or 'Nenhum documento autorizado no período.',
        )
    nome_zip = f'contabilidade_{loja.id}_{ano}{mes:02d}.zip'
    return buf.getvalue(), nome_zip


def enviar_zip_por_email(destino: str, assunto: str, corpo: str, zip_bytes: bytes, nome_arquivo: str):
    msg = EmailMessage(
        subject=assunto,
        body=corpo,
        to=[destino],
    )
    msg.attach(nome_arquivo, zip_bytes, 'application/zip')
    msg.send(fail_silently=False)
