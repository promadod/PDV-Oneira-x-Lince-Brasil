"""Serviços de emissão / tributação / webhooks."""
from __future__ import annotations

import copy
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


def _atualizar_data_emissao_payload(payload: dict) -> dict:
    p = copy.deepcopy(payload)
    tz = timezone.get_current_timezone()
    p['data_emissao'] = timezone.localtime(timezone.now(), tz).isoformat(timespec='seconds')
    p.pop('serie', None)
    p.pop('numero', None)
    return p


def _nfe_dados_from_payload(payload: dict, produto) -> dict:
    item = (payload.get('items') or [{}])[0]
    fp = (payload.get('formas_pagamento') or [{}])[0]
    qtd = float(item.get('quantidade_comercial') or item.get('quantidade') or 1)
    v_unit = float(item.get('valor_unitario_comercial') or item.get('valor_unitario') or 0)
    if v_unit <= 0 and qtd > 0:
        bruto = float(item.get('valor_bruto') or 0)
        if bruto > 0:
            v_unit = round(bruto / qtd, 2)
    return {
        'produto': produto,
        'quantidade': qtd,
        'preco_unitario': v_unit,
        'natureza_operacao': payload.get('natureza_operacao') or 'VENDA',
        'cfop': item.get('cfop'),
        'finalidade_emissao': payload.get('finalidade_emissao') or '1',
        'forma_pagamento': fp.get('forma_pagamento') or '99',
        'valor_desconto': float(payload.get('valor_desconto') or 0),
        'valor_acrescimo': float(payload.get('valor_outras_despesas') or 0),
        'cpf_destinatario': payload.get('cpf_destinatario') or '',
        'cnpj_destinatario': payload.get('cnpj_destinatario') or '',
        'nome_destinatario': payload.get('nome_destinatario') or '',
        'logradouro': payload.get('logradouro_destinatario') or '',
        'numero': payload.get('numero_destinatario') or '',
        'bairro': payload.get('bairro_destinatario') or '',
        'municipio': payload.get('municipio_destinatario') or '',
        'uf': payload.get('uf_destinatario') or '',
        'cep': payload.get('cep_destinatario') or '',
        'codigo_municipio': payload.get('codigo_municipio_destinatario') or '',
    }


def _montar_payload_para_reemissao(cfg: FiscalConfig, loja, doc: DocumentoFiscal) -> dict:
    from .focus_payload import montar_payload_emissao, montar_payload_nfe_form, montar_payload_nfce_avulso

    snap = doc.snapshot_tributario or {}
    payload_orig = doc.payload_envio if isinstance(doc.payload_envio, dict) else {}

    if snap.get('emissao_nfe_form') and doc.produto_avulso_id:
        try:
            return montar_payload_nfe_form(
                cfg, loja, _nfe_dados_from_payload(payload_orig, doc.produto_avulso),
            )
        except ValueError as exc:
            raise FocusNFeError(str(exc)) from exc

    if payload_orig.get('items'):
        return _atualizar_data_emissao_payload(payload_orig)

    if doc.venda_id:
        return montar_payload_emissao(cfg, loja, tipo=doc.tipo, venda=doc.venda)

    if snap.get('emissao_avulsa') and doc.produto_avulso_id:
        fp = (payload_orig.get('formas_pagamento') or [{}])[0]
        try:
            return montar_payload_nfce_avulso(
                cfg, loja, doc.produto_avulso,
                quantidade=float(snap.get('quantidade') or 1),
                preco_unitario=float(snap.get('preco_unitario') or 0),
                forma_pagamento=fp.get('forma_pagamento') or '99',
                interestadual=payload_orig.get('local_destino') == '2',
                valor_desconto=float(payload_orig.get('valor_desconto') or 0),
                valor_acrescimo=float(payload_orig.get('valor_outras_despesas') or 0),
                cpf_destinatario=payload_orig.get('cpf_destinatario') or '',
                cnpj_destinatario=payload_orig.get('cnpj_destinatario') or '',
                nome_destinatario=payload_orig.get('nome_destinatario') or '',
            )
        except ValueError as exc:
            raise FocusNFeError(str(exc)) from exc

    raise FocusNFeError('Não há dados suficientes para reemitir este documento.')


def _disparar_emissao_focus(
    doc: DocumentoFiscal,
    cfg: FiscalConfig,
    payload: dict,
    *,
    params_extra: dict | None = None,
) -> DocumentoFiscal:
    DocumentoFiscalEvento.objects.create(
        documento=doc,
        tipo='envio',
        descricao='Documento enviado para Focus NFe',
        payload=payload,
    )
    client = client_from_config(cfg)
    endpoint = _endpoint_tipo(doc.tipo)
    try:
        if endpoint == 'nfe':
            retorno = client.emitir_nfe(doc.ref, payload, query_params=params_extra or None)
        elif endpoint == 'nfse':
            retorno = client.emitir_nfse(doc.ref, payload, query_params=params_extra or None)
        else:
            retorno = client.emitir_nfce(doc.ref, payload, query_params=params_extra or None)
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


def _endpoint_tipo(tipo: str) -> str:
    return {
        'nfe': 'nfe',
        'nfce': 'nfce',
        'nfse': 'nfse',
        'nfse_nacional': 'nfse',
    }.get(tipo, 'nfce')


@transaction.atomic
def emitir_documento(loja, usuario, *, tipo='nfce', venda=None, avulso=None, nfe_dados=None, payload_extra=None):
    cfg = get_or_create_config(loja)
    if not cfg.focus_token:
        raise FocusNFeError('Configure o token Focus NFe em Configurações Fiscais.')

    if tipo == 'nfe' and not cfg.emite_nfe:
        raise FocusNFeError('Emissão de NF-e desabilitada nesta loja.')
    if tipo == 'nfce' and not cfg.emite_nfce:
        raise FocusNFeError('Emissão de NFC-e desabilitada nesta loja.')
    if tipo.startswith('nfse') and not (cfg.emite_nfse or cfg.emite_nfse_nacional):
        raise FocusNFeError('Emissão de NFS-e desabilitada nesta loja.')

    produto_avulso = None
    if nfe_dados:
        produto_avulso = nfe_dados.get('produto')
        bruto = float(nfe_dados['quantidade']) * float(nfe_dados['preco_unitario'])
        desconto = float(nfe_dados.get('valor_desconto') or 0)
        acrescimo = float(nfe_dados.get('valor_acrescimo') or 0)
        valor = Decimal(str(round(max(bruto - desconto + acrescimo, 0.01), 2)))
        ref = _nova_ref(loja, 'nfe', f'nfe{produto_avulso.id if produto_avulso else "x"}')
        snapshot = {'emissao_nfe_form': True, 'produto_id': getattr(produto_avulso, 'id', None)}
        tipo = 'nfe'
    elif avulso:
        produto_avulso = avulso['produto']
        if produto_avulso.loja_id != loja.id:
            raise FocusNFeError('Produto não pertence à loja atual.')
        bruto = float(avulso['quantidade']) * float(avulso['preco_unitario'])
        desconto = float(avulso.get('valor_desconto') or 0)
        acrescimo = float(avulso.get('valor_acrescimo') or 0)
        valor = Decimal(str(round(max(bruto - desconto + acrescimo, 0.01), 2)))
        ref = _nova_ref(loja, tipo, f'av{produto_avulso.id}')
        snapshot = {
            'emissao_avulsa': True,
            'produto_id': produto_avulso.id,
            'quantidade': str(avulso['quantidade']),
            'preco_unitario': str(avulso['preco_unitario']),
        }
    elif venda:
        snapshot = montar_snapshot_itens(loja, venda)
        valor = Decimal(str(venda.total))
        ref = _nova_ref(loja, tipo, getattr(venda, 'id', None))
    else:
        raise FocusNFeError('Informe a venda, emissão avulsa ou dados NF-e.')

    try:
        if nfe_dados:
            from .focus_payload import montar_payload_nfe_form
            payload = montar_payload_nfe_form(cfg, loja, nfe_dados)
        else:
            payload = montar_payload_emissao(
                cfg, loja, tipo=tipo, venda=venda, avulso=avulso if avulso else None,
            )
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
        produto_avulso=produto_avulso,
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
    return _disparar_emissao_focus(doc, cfg, payload, params_extra=params_extra or None)


@transaction.atomic
def reemitir_documento(loja, usuario, documento_origem: DocumentoFiscal) -> DocumentoFiscal:
    """Nova referência + mesmo conteúdo (payload salvo ou reconstruído)."""
    doc_orig = documento_origem
    if doc_orig.loja_id != loja.id:
        raise FocusNFeError('Documento não pertence à loja atual.')
    if doc_orig.status not in ('erro', 'denegado'):
        raise FocusNFeError('Só documentos com erro ou denegados podem ser reemitidos.')

    cfg = get_or_create_config(loja)
    tipo = doc_orig.tipo
    if tipo == 'nfe' and not cfg.emite_nfe:
        raise FocusNFeError('Emissão de NF-e desabilitada nesta loja.')
    if tipo == 'nfce' and not cfg.emite_nfce:
        raise FocusNFeError('Emissão de NFC-e desabilitada nesta loja.')
    if tipo.startswith('nfse') and not (cfg.emite_nfse or cfg.emite_nfse_nacional):
        raise FocusNFeError('Emissão de NFS-e desabilitada nesta loja.')

    payload = _montar_payload_para_reemissao(cfg, loja, doc_orig)
    ref_id = doc_orig.venda_id or doc_orig.produto_avulso_id or doc_orig.id
    ref = _nova_ref(loja, tipo, ref_id)

    serie_map = {
        'nfe': cfg.serie_nfe,
        'nfce': cfg.serie_nfce,
        'nfse': cfg.serie_nfse,
        'nfse_nacional': cfg.serie_nfse,
    }
    doc = DocumentoFiscal.objects.create(
        loja=loja,
        venda=doc_orig.venda,
        produto_avulso=doc_orig.produto_avulso,
        tipo=tipo,
        ref=ref,
        status='processando',
        valor_total=doc_orig.valor_total,
        serie=str(serie_map.get(tipo, 1)),
        payload_envio=payload,
        snapshot_tributario=doc_orig.snapshot_tributario or {},
        em_contingencia=cfg.contingencia_ativa,
        criado_por=usuario if getattr(usuario, 'is_authenticated', False) else None,
    )
    DocumentoFiscalEvento.objects.create(
        documento=doc,
        tipo='reemissao',
        descricao=f'Reemissão do documento #{doc_orig.id} (ref {doc_orig.ref})',
        payload={'documento_origem_id': doc_orig.id, 'ref_origem': doc_orig.ref},
    )
    params_extra = {}
    if cfg.contingencia_ativa and tipo == 'nfce':
        params_extra['forma_emissao'] = 'offline'
    try:
        return _disparar_emissao_focus(doc, cfg, payload, params_extra=params_extra or None)
    except FocusNFeError:
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
    from .focus_arquivos import resolver_url_arquivo_focus

    cfg = get_or_create_config(doc.loja)
    caminho_xml = retorno.get('caminho_xml_nota_fiscal') or retorno.get('caminho_xml') or ''
    caminho_pdf = retorno.get('caminho_danfe') or retorno.get('caminho_pdf') or ''
    doc.caminho_xml = str(caminho_xml)
    doc.caminho_pdf = str(caminho_pdf)
    doc.url_xml = resolver_url_arquivo_focus(cfg, str(caminho_xml))
    doc.url_pdf = resolver_url_arquivo_focus(cfg, str(caminho_pdf))
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


def processar_lote_avulso_emissao(
    loja,
    usuario,
    *,
    produto,
    quantidade_total: float,
    quantidade_por_cupom: float,
    preco_unitario: float,
    desconto_unitario: float = 0,
    forma_pagamento: str = '99',
    **avulso_extra,
):
    """Divide quantidade total em vários cupons NFC-e (padrão NetFiscal)."""
    import math

    if quantidade_por_cupom <= 0:
        raise FocusNFeError('Quantidade por cupom deve ser maior que zero.')
    if produto.loja_id != loja.id:
        raise FocusNFeError('Produto não pertence à loja atual.')

    q_total = float(quantidade_total)
    q_cupom = float(quantidade_por_cupom)
    n_cupons = max(1, int(math.ceil(q_total / q_cupom)))
    lote = LoteEmissaoFiscal.objects.create(
        loja=loja,
        tipo='nfce',
        modo='avulso',
        status='processando',
        total_solicitado=n_cupons,
        observacao=f'Lote avulso — {produto.nome_venda} ({q_total} un / {q_cupom} por cupom)'[:255],
        criado_por=usuario if getattr(usuario, 'is_authenticated', False) else None,
    )
    restante = q_total
    for _ in range(n_cupons):
        qtd = min(q_cupom, restante)
        restante = max(0, restante - qtd)
        desconto_cupom = round(float(desconto_unitario or 0) * qtd, 2)
        item = LoteEmissaoFiscalItem.objects.create(
            lote=lote, venda=None, produto=produto,
            quantidade_emitida=qtd, status='pendente',
        )
        try:
            doc = emitir_documento(
                loja, usuario,
                tipo='nfce',
                avulso={
                    'produto': produto,
                    'quantidade': qtd,
                    'preco_unitario': float(preco_unitario),
                    'forma_pagamento': forma_pagamento,
                    'valor_desconto': desconto_cupom,
                    **avulso_extra,
                },
            )
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

    if lote.total_erro == 0 and lote.total_autorizado > 0:
        lote.status = 'concluido'
    elif lote.total_autorizado == 0:
        lote.status = 'parcial' if lote.total_erro else 'vazio'
    else:
        lote.status = 'parcial'
    lote.finalizado_em = timezone.now()
    lote.save(update_fields=['status', 'total_autorizado', 'total_erro', 'finalizado_em'])
    return lote


def listar_gatilhos_focus(cfg: FiscalConfig):
    if not cfg.focus_token:
        return []
    client = client_from_config(cfg)
    data = client.listar_webhooks()
    if isinstance(data, list):
        return data
    return data.get('hooks', []) if isinstance(data, dict) else []
