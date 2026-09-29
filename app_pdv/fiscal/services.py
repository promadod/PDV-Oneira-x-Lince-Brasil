"""Serviços de emissão / tributação / webhooks."""
from __future__ import annotations

import uuid
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .focus_client import FocusNFeError, client_from_config
from .focus_payload import montar_payload_emissao
from .models import (
    DocumentoFiscal,
    DocumentoFiscalEvento,
    FiscalConfig,
    FiscalWebhookLog,
    LoteEmissaoFiscal,
    LoteEmissaoFiscalItem,
    ProdutoDadosFiscais,
    RegraTributaria,
)

LOTE_EMISSAO_MAX_VENDAS = 50
_STATUS_VENDA_FATURADA = ('FINALIZADO', 'RETIRADO_NA_LOJA')
_DOC_BLOQUEIA_REEMISSAO = ('autorizado', 'processando')


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

    try:
        payload = montar_payload_emissao(cfg, loja, tipo=tipo, venda=venda)
    except ValueError as exc:
        raise FocusNFeError(str(exc)) from exc
    params_extra = {}
    if cfg.contingencia_ativa and tipo == 'nfce':
        params_extra['forma_emissao'] = 'offline'
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
            retorno = client.emitir_nfe(ref, payload, query_params=params_extra or None)
        elif endpoint == 'nfse':
            retorno = client.emitir_nfse(ref, payload, query_params=params_extra or None)
        else:
            retorno = client.emitir_nfce(ref, payload, query_params=params_extra or None)
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


def testar_conexao_focus(cfg: FiscalConfig) -> dict:
    if not cfg.focus_token:
        raise FocusNFeError('Informe o token Focus NFe antes de testar.')
    client = client_from_config(cfg)
    data = client.testar_autenticacao()
    hooks = data if isinstance(data, list) else data.get('hooks', data)
    qtd = len(hooks) if isinstance(hooks, list) else 0
    return {
        'ok': True,
        'ambiente': cfg.ambiente,
        'base_url': cfg.focus_base_url,
        'gatilhos_cadastrados': qtd,
        'resposta': data,
    }


def url_webhook_sistema(request) -> str:
    from django.urls import reverse

    path = reverse('fiscal_webhook_focus')
    return request.build_absolute_uri(path)


def registrar_gatilhos_focus(cfg: FiscalConfig, webhook_url: str, eventos: list[str] | None = None) -> list[dict]:
    if not cfg.focus_token:
        raise FocusNFeError('Configure o token Focus NFe.')
    if not webhook_url:
        raise FocusNFeError('Informe a URL pública do webhook.')
    cnpj = ''.join(c for c in (cfg.cnpj or '') if c.isdigit())
    if len(cnpj) != 14:
        raise FocusNFeError('CNPJ da loja é obrigatório para cadastrar gatilhos na Focus.')

    eventos = eventos or ['nfe', 'nfce_contingencia', 'inutilizacao']
    client = client_from_config(cfg)
    criados = []
    for event in eventos:
        body = {'event': event, 'url': webhook_url, 'cnpj': cnpj}
        try:
            ret = client.cadastrar_webhook(body)
            criados.append({'event': event, 'ok': True, 'retorno': ret})
        except FocusNFeError as exc:
            criados.append({'event': event, 'ok': False, 'erro': str(exc)})
    cfg.webhook_url_configurada = webhook_url
    cfg.save(update_fields=['webhook_url_configurada', 'atualizado_em'])
    return criados


def venda_ja_tem_documento_tipo(venda, tipo: str) -> bool:
    return DocumentoFiscal.objects.filter(
        venda=venda, tipo=tipo, status__in=_DOC_BLOQUEIA_REEMISSAO,
    ).exists()


def buscar_vendas_elegiveis_lote(
    loja,
    *,
    tipo: str,
    data_de=None,
    data_ate=None,
    venda_ids=None,
    pular_ja_emitidas=True,
    limite=LOTE_EMISSAO_MAX_VENDAS,
):
    """Vendas finalizadas, com itens, opcionalmente sem documento do mesmo tipo."""
    from app_pdv.models import ItemVenda, Venda

    qs = Venda.objects.filter(loja=loja, status__in=_STATUS_VENDA_FATURADA)
    qs = qs.filter(itens__isnull=False).distinct()
    if data_de:
        qs = qs.filter(data_venda__date__gte=data_de)
    if data_ate:
        qs = qs.filter(data_venda__date__lte=data_ate)
    if venda_ids:
        qs = qs.filter(pk__in=venda_ids)
    qs = qs.order_by('data_venda', 'id')
    elegiveis = []
    for venda in qs[: limite * 3]:
        if len(elegiveis) >= limite:
            break
        if not ItemVenda.objects.filter(venda=venda).exists():
            continue
        if pular_ja_emitidas and venda_ja_tem_documento_tipo(venda, tipo):
            continue
        elegiveis.append(venda)
    return elegiveis


def processar_lote_emissao(loja, usuario, *, tipo, vendas, filtros_meta=None):
    """Emite documentos sequencialmente; persiste lote e itens para auditoria SaaS."""
    filtros_meta = filtros_meta or {}
    lote = LoteEmissaoFiscal.objects.create(
        loja=loja,
        tipo=tipo,
        status='processando',
        data_venda_de=filtros_meta.get('data_de'),
        data_venda_ate=filtros_meta.get('data_ate'),
        pular_ja_emitidas=filtros_meta.get('pular_ja_emitidas', True),
        total_solicitado=len(vendas),
        criado_por=usuario if getattr(usuario, 'is_authenticated', False) else None,
        observacao=filtros_meta.get('observacao', '')[:255],
    )
    if not vendas:
        lote.status = 'vazio'
        lote.finalizado_em = timezone.now()
        lote.save(update_fields=['status', 'finalizado_em'])
        return lote

    for venda in vendas:
        if venda.loja_id != loja.id:
            LoteEmissaoFiscalItem.objects.create(
                lote=lote, venda=venda, status='ignorado',
                mensagem='Venda de outra loja.',
            )
            lote.total_ignorado += 1
            continue
        if lote.pular_ja_emitidas and venda_ja_tem_documento_tipo(venda, tipo):
            LoteEmissaoFiscalItem.objects.create(
                lote=lote, venda=venda, status='ignorado',
                mensagem='Já existe documento autorizado ou em processamento para este tipo.',
            )
            lote.total_ignorado += 1
            continue
        item = LoteEmissaoFiscalItem.objects.create(lote=lote, venda=venda, status='pendente')
        try:
            doc = emitir_documento(loja, usuario, tipo=tipo, venda=venda)
            item.documento = doc
            if doc.status == 'autorizado':
                item.status = 'autorizado'
                lote.total_autorizado += 1
            elif doc.status == 'processando':
                item.status = 'processando'
            else:
                item.status = 'erro'
                item.mensagem = doc.mensagem_sefaz or doc.status
                lote.total_erro += 1
            item.save(update_fields=['documento', 'status', 'mensagem'])
        except FocusNFeError as exc:
            item.status = 'erro'
            item.mensagem = str(exc)
            item.save(update_fields=['status', 'mensagem'])
            lote.total_erro += 1

    if lote.total_autorizado + lote.total_erro + lote.total_ignorado == 0:
        lote.status = 'vazio'
    elif lote.total_erro == 0:
        lote.status = 'concluido'
    elif lote.total_autorizado == 0 and lote.total_erro > 0:
        lote.status = 'parcial'
    else:
        lote.status = 'parcial'
    lote.finalizado_em = timezone.now()
    lote.save(
        update_fields=[
            'status', 'total_autorizado', 'total_erro', 'total_ignorado', 'finalizado_em',
        ],
    )
    return lote


def listar_gatilhos_focus(cfg: FiscalConfig):
    if not cfg.focus_token:
        return []
    client = client_from_config(cfg)
    data = client.listar_webhooks()
    if isinstance(data, list):
        return data
    return data.get('hooks', []) if isinstance(data, dict) else []
