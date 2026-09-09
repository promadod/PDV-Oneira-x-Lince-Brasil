"""Serviços de emissão / tributação / webhooks."""
from __future__ import annotations

import uuid
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .focus_client import FocusNFeError, client_from_config
from .models import (
    DocumentoFiscal,
    DocumentoFiscalEvento,
    FiscalConfig,
    FiscalWebhookLog,
    ProdutoDadosFiscais,
    RegraTributaria,
)


def get_or_create_config(loja) -> FiscalConfig:
    cfg, _ = FiscalConfig.objects.get_or_create(
        loja=loja,
        defaults={
            'cnpj': (loja.cnpj or '').strip(),
            'nome_fantasia': loja.marca_pdv_exibicao() if hasattr(loja, 'marca_pdv_exibicao') else loja.nome,
            'razao_social': loja.nome,
        },
    )
    return cfg


def resolver_regra(loja, ncm='', uf_destino='', operacao='venda') -> RegraTributaria | None:
    qs = RegraTributaria.objects.filter(loja=loja, ativa=True, operacao=operacao)
    if ncm:
        especifica = qs.filter(ncm=ncm).first()
        if especifica:
            if not especifica.uf_destino or especifica.uf_destino.upper() == (uf_destino or '').upper():
                return especifica
    if uf_destino:
        por_uf = qs.filter(ncm='', uf_destino__iexact=uf_destino).first()
        if por_uf:
            return por_uf
    return qs.filter(ncm='', uf_destino='').first()


def montar_snapshot_itens(loja, venda) -> dict:
    itens = []
    from app_pdv.models import ItemVenda
    for item in ItemVenda.objects.filter(venda=venda).select_related('produto'):
        dados = None
        try:
            dados = item.produto.dados_fiscais
        except ProdutoDadosFiscais.DoesNotExist:
            dados = None
        ncm = dados.ncm if dados else ''
        regra = resolver_regra(loja, ncm=ncm, operacao='venda')
        itens.append({
            'produto_id': item.produto_id,
            'nome': item.produto.nome_venda,
            'quantidade': str(item.quantidade),
            'preco_unitario': str(item.preco_unitario),
            'ncm': ncm,
            'cfop': regra.cfop if regra else '5102',
            'csosn': regra.csosn if regra else '102',
            'cst_icms': regra.cst_icms if regra else '',
            'origem': dados.origem if dados else '0',
            'aliquota_icms': str(regra.aliquota_icms) if regra else '0',
            'aliquota_pis': str(regra.aliquota_pis) if regra else '0',
            'aliquota_cofins': str(regra.aliquota_cofins) if regra else '0',
            'aliquota_ibs': str(regra.aliquota_ibs) if regra else '0',
            'aliquota_cbs': str(regra.aliquota_cbs) if regra else '0',
        })
    return {'itens': itens, 'total': str(venda.total)}


def _nova_ref(loja, tipo: str, venda_id=None) -> str:
    suffix = uuid.uuid4().hex[:10]
    base = f'{loja.id}-{tipo}-{venda_id or 0}-{suffix}'
    return base[:64]


def _endpoint_tipo(tipo: str) -> str:
    return {
        'nfe': 'nfe',
        'nfce': 'nfce',
        'nfse': 'nfse',
        'nfse_nacional': 'nfse',
    }.get(tipo, 'nfce')


@transaction.atomic
def emitir_documento(loja, usuario, *, tipo='nfce', venda=None, payload_extra=None):
    cfg = get_or_create_config(loja)
    if not cfg.focus_token:
        raise FocusNFeError('Configure o token Focus NFe em Configurações Fiscais.')

    if tipo == 'nfe' and not cfg.emite_nfe:
        raise FocusNFeError('Emissão de NF-e desabilitada nesta loja.')
    if tipo == 'nfce' and not cfg.emite_nfce:
        raise FocusNFeError('Emissão de NFC-e desabilitada nesta loja.')
    if tipo.startswith('nfse') and not (cfg.emite_nfse or cfg.emite_nfse_nacional):
        raise FocusNFeError('Emissão de NFS-e desabilitada nesta loja.')

    snapshot = montar_snapshot_itens(loja, venda) if venda else {'itens': []}
    valor = Decimal(str(venda.total)) if venda else Decimal('0')
    ref = _nova_ref(loja, tipo, getattr(venda, 'id', None))

    payload = {
        'cnpj_emitente': ''.join(c for c in (cfg.cnpj or '') if c.isdigit()),
        'nome_emitente': cfg.razao_social or loja.nome,
        'valor_total': float(valor),
        'itens': snapshot.get('itens', []),
        'ambiente': cfg.ambiente,
    }
    if cfg.contingencia_ativa:
        payload['em_contingencia'] = True
        payload['contingencia_tipo'] = cfg.contingencia_tipo
    if payload_extra:
        payload.update(payload_extra)

    serie_map = {
        'nfe': cfg.serie_nfe,
        'nfce': cfg.serie_nfce,
        'nfse': cfg.serie_nfse,
        'nfse_nacional': cfg.serie_nfse,
    }
    doc = DocumentoFiscal.objects.create(
        loja=loja,
        venda=venda,
        tipo=tipo,
        ref=ref,
        status='processando',
        valor_total=valor,
        serie=str(serie_map.get(tipo, 1)),
        payload_envio=payload,
        snapshot_tributario=snapshot,
        em_contingencia=cfg.contingencia_ativa,
        criado_por=usuario if getattr(usuario, 'is_authenticated', False) else None,
    )
    DocumentoFiscalEvento.objects.create(
        documento=doc, tipo='envio', descricao='Documento enviado para Focus NFe', payload=payload,
    )

    client = client_from_config(cfg)
    endpoint = _endpoint_tipo(tipo)
    try:
        if endpoint == 'nfe':
            retorno = client.emitir_nfe(ref, payload)
        elif endpoint == 'nfse':
            retorno = client.emitir_nfse(ref, payload)
        else:
            retorno = client.emitir_nfce(ref, payload)
    except FocusNFeError as exc:
        doc.status = 'erro'
        doc.mensagem_sefaz = str(exc)
        doc.payload_retorno = exc.payload
        doc.save(update_fields=['status', 'mensagem_sefaz', 'payload_retorno', 'atualizado_em'])
        DocumentoFiscalEvento.objects.create(
            documento=doc, tipo='erro', descricao=str(exc), payload=exc.payload,
        )
        raise

    _aplicar_retorno_focus(doc, retorno)
    return doc


def _aplicar_retorno_focus(doc: DocumentoFiscal, retorno: dict):
    if not isinstance(retorno, dict):
        retorno = {'raw': retorno}
    doc.payload_retorno = retorno
    status = (retorno.get('status') or '').lower()
    mapping = {
        'autorizado': 'autorizado',
        'autorizada': 'autorizado',
        'processando_autorizacao': 'processando',
        'erro_autorizacao': 'erro',
        'erro': 'erro',
        'cancelado': 'cancelado',
        'denegado': 'denegado',
    }
    if status in mapping:
        doc.status = mapping[status]
    doc.numero = str(retorno.get('numero') or doc.numero or '')
    doc.serie = str(retorno.get('serie') or doc.serie or '')
    doc.chave_acesso = str(retorno.get('chave_nfe') or retorno.get('chave') or doc.chave_acesso or '')
    doc.protocolo = str(retorno.get('protocolo') or doc.protocolo or '')
    doc.status_sefaz = str(retorno.get('status_sefaz') or '')
    doc.mensagem_sefaz = str(retorno.get('mensagem_sefaz') or retorno.get('mensagem') or '')
    caminho_xml = retorno.get('caminho_xml_nota_fiscal') or retorno.get('caminho_xml') or ''
    caminho_pdf = retorno.get('caminho_danfe') or retorno.get('caminho_pdf') or ''
    doc.caminho_xml = str(caminho_xml)
    doc.caminho_pdf = str(caminho_pdf)
    if caminho_xml and str(caminho_xml).startswith('http'):
        doc.url_xml = str(caminho_xml)
    if caminho_pdf and str(caminho_pdf).startswith('http'):
        doc.url_pdf = str(caminho_pdf)
    doc.save()
    DocumentoFiscalEvento.objects.create(
        documento=doc, tipo='retorno_focus', descricao=f'Status: {doc.status}', payload=retorno,
    )


def cancelar_documento(doc: DocumentoFiscal, justificativa: str):
    cfg = get_or_create_config(doc.loja)
    client = client_from_config(cfg)
    endpoint = _endpoint_tipo(doc.tipo)
    retorno = client.cancelar(endpoint, doc.ref, justificativa)
    doc.status = 'cancelado'
    doc.cancelado_em = timezone.now()
    doc.motivo_cancelamento = justificativa
    doc.payload_retorno = retorno if isinstance(retorno, dict) else {'raw': retorno}
    doc.save()
    DocumentoFiscalEvento.objects.create(
        documento=doc, tipo='cancelamento', descricao=justificativa, payload=doc.payload_retorno,
    )
    return doc


def carta_correcao_documento(doc: DocumentoFiscal, texto: str):
    if doc.tipo != 'nfe':
        raise FocusNFeError('Carta de correção disponível apenas para NF-e.')
    cfg = get_or_create_config(doc.loja)
    client = client_from_config(cfg)
    retorno = client.carta_correcao(doc.ref, texto)
    doc.carta_correcao = texto
    doc.carta_correcao_em = timezone.now()
    doc.save(update_fields=['carta_correcao', 'carta_correcao_em', 'atualizado_em'])
    DocumentoFiscalEvento.objects.create(
        documento=doc, tipo='carta_correcao', descricao=texto, payload=retorno if isinstance(retorno, dict) else {},
    )
    return doc


def processar_webhook(payload: dict, headers: dict | None = None, loja=None):
    ref = str(payload.get('ref') or '')
    status = str(payload.get('status') or '')
    evento = str(payload.get('event') or payload.get('evento') or 'nfe')
    doc = None
    if ref:
        qs = DocumentoFiscal.objects.filter(ref=ref)
        if loja:
            qs = qs.filter(loja=loja)
        doc = qs.select_related('loja').first()
        if doc and not loja:
            loja = doc.loja

    log = FiscalWebhookLog.objects.create(
        loja=loja,
        documento=doc,
        evento=evento,
        ref=ref,
        status_recebido=status,
        payload=payload,
        headers=headers or {},
    )
    if doc:
        try:
            _aplicar_retorno_focus(doc, payload)
            log.processado = True
            log.save(update_fields=['processado'])
        except Exception as exc:
            log.erro = str(exc)
            log.save(update_fields=['erro'])
    else:
        log.erro = 'Documento não encontrado para a ref informada.'
        log.save(update_fields=['erro'])
    return log
