import json
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from app_pdv.models import Produto, Venda
from app_pdv.views import check_loja

from .access import requer_acesso_fiscal
from .focus_client import FocusNFeError
from .forms import (
    CancelarDocumentoForm,
    CartaCorrecaoForm,
    ContingenciaForm,
    EmitirAvulsaForm,
    EmitirDocumentoForm,
    EmitirLoteForm,
    FocusIntegracaoForm,
    FiscalConfigForm,
    InutilizacaoForm,
    ManifestacaoForm,
    ProdutoDadosFiscaisForm,
    RegraTributariaForm,
)
from .models import (
    DocumentoFiscal,
    FiscalWebhookLog,
    InutilizacaoNumeracao,
    LoteEmissaoFiscal,
    NFeRecebida,
    ProdutoDadosFiscais,
    RegraTributaria,
)
from .services import (
    cancelar_documento,
    carta_correcao_documento,
    LOTE_EMISSAO_MAX_VENDAS,
    buscar_vendas_elegiveis_lote,
    emitir_documento,
    get_or_create_config,
    processar_lote_emissao,
    listar_gatilhos_focus,
    processar_webhook,
    registrar_gatilhos_focus,
    testar_conexao_focus,
    url_webhook_sistema,
)

logger = logging.getLogger(__name__)


def _ctx(request, loja, **extra):
    cfg = get_or_create_config(loja)
    base = {'loja': loja, 'fiscal_config': cfg}
    base.update(extra)
    return base


@login_required
@requer_acesso_fiscal
def fiscal_hub(request):
    loja = check_loja(request)
    cfg = get_or_create_config(loja)
    docs = DocumentoFiscal.objects.filter(loja=loja)
    pilares = [
        {'titulo': 'Integração Focus API', 'desc': 'Token, ambiente, teste de conexão e gatilhos', 'url': 'fiscal_focus', 'icone': 'fa-plug'},
        {'titulo': '1. Configurações', 'desc': 'Empresa, CRT, endereço e certificado Focus', 'url': 'fiscal_config', 'icone': 'fa-building'},
        {'titulo': '2. Matriz tributária', 'desc': 'NCM, CFOP, CSOSN/CST e alíquotas', 'url': 'fiscal_matriz', 'icone': 'fa-table'},
        {'titulo': '3. Documentos', 'desc': 'NF-e / NFC-e / NFS-e emitidos', 'url': 'fiscal_documentos', 'icone': 'fa-file-invoice'},
        {'titulo': '4. Webhooks', 'desc': 'Callbacks assíncronos da Focus', 'url': 'fiscal_webhooks', 'icone': 'fa-bolt'},
        {'titulo': '5. NFC-e', 'desc': 'Cupom fiscal eletrônico do consumidor', 'url': 'fiscal_emitir', 'icone': 'fa-receipt'},
        {'titulo': 'Emissão em lote', 'desc': 'Várias vendas de uma vez (SaaS)', 'url': 'fiscal_emitir_lote', 'icone': 'fa-layer-group'},
        {'titulo': 'Emissão avulsa', 'desc': 'NFC-e por produto (sem venda PDV)', 'url': 'fiscal_emitir_avulsa', 'icone': 'fa-box-open'},
        {'titulo': '6. Cancelamento / CC-e / Inutilização', 'desc': 'Ciclo de vida legal das notas', 'url': 'fiscal_inutilizacao', 'icone': 'fa-ban'},
        {'titulo': '7. Contingência', 'desc': 'Operação offline / SVC', 'url': 'fiscal_contingencia', 'icone': 'fa-wifi'},
        {'titulo': '8. Arquivos', 'desc': 'XML, DANFE/DANFCE e envio', 'url': 'fiscal_arquivos', 'icone': 'fa-folder-open'},
        {'titulo': '9. Reforma tributária', 'desc': 'Campos IBS/CBS / cClassTrib', 'url': 'fiscal_reforma', 'icone': 'fa-balance-scale'},
        {'titulo': '10. Manifestação / Entradas', 'desc': 'NF-e recebidas e ciência', 'url': 'fiscal_manifestacao', 'icone': 'fa-inbox'},
    ]
    return render(request, 'app_pdv/fiscal/hub.html', _ctx(
        request, loja,
        pilares=pilares,
        stats={
            'autorizados': docs.filter(status='autorizado').count(),
            'processando': docs.filter(status='processando').count(),
            'erros': docs.filter(status='erro').count(),
            'regras': RegraTributaria.objects.filter(loja=loja, ativa=True).count(),
            'webhooks': FiscalWebhookLog.objects.filter(loja=loja).count(),
            'contingencia': cfg.contingencia_ativa,
        },
    ))


@login_required
@requer_acesso_fiscal
def fiscal_focus(request):
    loja = check_loja(request)
    cfg = get_or_create_config(loja)
    webhook_sugerida = url_webhook_sistema(request)
    gatilhos = []
    teste = None

    if request.method == 'POST':
        acao = request.POST.get('acao', 'salvar')
        if acao == 'registrar_webhooks':
            url_hook = (request.POST.get('webhook_url') or cfg.webhook_url_configurada or webhook_sugerida).strip()
            eventos = request.POST.getlist('eventos_webhook')
            try:
                resultados = registrar_gatilhos_focus(cfg, url_hook, eventos=eventos or None)
                ok = sum(1 for r in resultados if r.get('ok'))
                messages.success(request, f'{ok} gatilho(s) registrado(s) na Focus.')
            except FocusNFeError as exc:
                messages.error(request, str(exc))
            return redirect('fiscal_focus')

        form = FocusIntegracaoForm(request.POST, instance=cfg)
        if acao == 'salvar' and form.is_valid():
            form.save()
            messages.success(request, 'Integração Focus salva.')
            return redirect('fiscal_focus')
        if acao == 'testar':
            if not form.is_valid():
                messages.error(request, 'Corrija os campos do formulário antes de testar a conexão.')
                logger.info('fiscal_focus testar form_invalid loja=%s', loja.id)
            else:
                cfg = form.save()
                try:
                    teste = testar_conexao_focus(cfg)
                    messages.success(
                        request,
                        f'Conexão OK ({cfg.get_ambiente_display()}). '
                        f'Gatilhos na Focus: {teste["gatilhos_cadastrados"]}.',
                    )
                    logger.info(
                        'fiscal_focus testar ok loja=%s ambiente=%s gatilhos=%s',
                        loja.id, cfg.ambiente, teste['gatilhos_cadastrados'],
                    )
                except FocusNFeError as exc:
                    messages.error(request, str(exc))
                    logger.warning(
                        'fiscal_focus testar falhou loja=%s ambiente=%s erro=%s',
                        loja.id, cfg.ambiente, exc,
                    )
            return redirect('fiscal_focus')
    else:
        form = FocusIntegracaoForm(
            instance=cfg,
            initial={'webhook_url_configurada': cfg.webhook_url_configurada or webhook_sugerida},
        )

    if cfg.focus_token:
        try:
            gatilhos = listar_gatilhos_focus(cfg)
        except FocusNFeError:
            gatilhos = []

    checklist = [
        {'ok': bool(cfg.focus_token), 'texto': 'Token Focus configurado (Basic Auth)'},
        {'ok': bool(''.join(c for c in (cfg.cnpj or loja.cnpj or '') if c.isdigit())), 'texto': 'CNPJ do emitente preenchido'},
        {'ok': cfg.ambiente == 'homologacao' or cfg.ambiente == 'producao', 'texto': f'Ambiente: {cfg.get_ambiente_display()}'},
        {'ok': bool(cfg.emite_nfce or cfg.emite_nfe), 'texto': 'Tipo de documento habilitado (NF-e / NFC-e)'},
        {'ok': bool(cfg.csc_id and cfg.csc_token) if cfg.emite_nfce else True, 'texto': 'CSC NFC-e (obrigatório na SEFAZ para cupom)'},
    ]

    return render(
        request,
        'app_pdv/fiscal/focus_integracao.html',
        _ctx(
            request,
            loja,
            form=form,
            webhook_sugerida=webhook_sugerida,
            gatilhos=gatilhos,
            teste=teste,
            checklist=checklist,
        ),
    )


@login_required
@requer_acesso_fiscal
def fiscal_config(request):
    loja = check_loja(request)
    cfg = get_or_create_config(loja)
    if request.method == 'POST':
        form = FiscalConfigForm(request.POST, instance=cfg)
        if form.is_valid():
            form.save()
            if not loja.cnpj and form.cleaned_data.get('cnpj'):
                loja.cnpj = form.cleaned_data['cnpj']
                loja.save(update_fields=['cnpj'])
            messages.success(request, 'Configurações fiscais salvas.')
            return redirect('fiscal_config')
    else:
        form = FiscalConfigForm(instance=cfg)
    return render(request, 'app_pdv/fiscal/config.html', _ctx(request, loja, form=form))


@login_required
@requer_acesso_fiscal
def fiscal_matriz(request):
    loja = check_loja(request)
    regras = RegraTributaria.objects.filter(loja=loja)
    form = RegraTributariaForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        regra = form.save(commit=False)
        regra.loja = loja
        regra.save()
        messages.success(request, f'Regra "{regra.nome}" cadastrada.')
        return redirect('fiscal_matriz')
    return render(request, 'app_pdv/fiscal/matriz.html', _ctx(request, loja, regras=regras, form=form))


@login_required
@requer_acesso_fiscal
def fiscal_matriz_excluir(request, pk):
    loja = check_loja(request)
    regra = get_object_or_404(RegraTributaria, pk=pk, loja=loja)
    regra.delete()
    messages.success(request, 'Regra removida.')
    return redirect('fiscal_matriz')


@login_required
@requer_acesso_fiscal
def fiscal_produtos(request):
    loja = check_loja(request)
    produtos = Produto.objects.filter(loja=loja).select_related('dados_fiscais').order_by('nome_venda')
    return render(request, 'app_pdv/fiscal/produtos.html', _ctx(request, loja, produtos=produtos))


@login_required
@requer_acesso_fiscal
def fiscal_produto_editar(request, produto_id):
    loja = check_loja(request)
    produto = get_object_or_404(Produto, pk=produto_id, loja=loja)
    dados, _ = ProdutoDadosFiscais.objects.get_or_create(produto=produto)
    if request.method == 'POST':
        form = ProdutoDadosFiscaisForm(request.POST, instance=dados)
        if form.is_valid():
            form.save()
            messages.success(request, f'Dados fiscais de "{produto.nome_venda}" salvos.')
            return redirect('fiscal_produtos')
    else:
        form = ProdutoDadosFiscaisForm(instance=dados)
    return render(
        request, 'app_pdv/fiscal/produto_form.html',
        _ctx(request, loja, form=form, produto=produto),
    )


@login_required
@requer_acesso_fiscal
def fiscal_emitir_avulsa(request):
    loja = check_loja(request)
    initial = {}
    pid = request.GET.get('produto')
    if pid and str(pid).isdigit():
        initial['produto_id'] = str(pid)
    form = EmitirAvulsaForm(request.POST or None, loja=loja, initial=initial)
    if request.method == 'POST' and form.is_valid():
        produto = get_object_or_404(Produto, pk=int(form.cleaned_data['produto_id']), loja=loja)
        preco = form.cleaned_data.get('preco_unitario') or produto.preco_venda
        try:
            doc = emitir_documento(
                loja, request.user,
                tipo='nfce',
                avulso={
                    'produto': produto,
                    'quantidade': float(form.cleaned_data['quantidade']),
                    'preco_unitario': float(preco),
                    'forma_pagamento': form.cleaned_data['forma_pagamento'],
                    'interestadual': form.cleaned_data.get('operacao_interestadual', False),
                },
            )
            messages.success(request, f'NFC-e avulsa enviada — ref {doc.ref} ({doc.status}).')
            return redirect('fiscal_documento_detalhe', pk=doc.id)
        except FocusNFeError as exc:
            messages.error(request, str(exc))
    return render(
        request, 'app_pdv/fiscal/emitir_avulsa.html',
        _ctx(request, loja, form=form),
    )


@login_required
@requer_acesso_fiscal
def fiscal_documentos(request):
    loja = check_loja(request)
    tipo = (request.GET.get('tipo') or '').strip()
    status = (request.GET.get('status') or '').strip()
    qs = DocumentoFiscal.objects.filter(loja=loja).select_related('venda', 'produto_avulso')
    if tipo:
        qs = qs.filter(tipo=tipo)
    if status:
        qs = qs.filter(status=status)
    return render(
        request, 'app_pdv/fiscal/documentos.html',
        _ctx(request, loja, documentos=qs[:200], filtro_tipo=tipo, filtro_status=status),
    )


@login_required
@requer_acesso_fiscal
def fiscal_documento_detalhe(request, pk):
    loja = check_loja(request)
    doc = get_object_or_404(
        DocumentoFiscal.objects.select_related('produto_avulso', 'venda').prefetch_related('eventos'),
        pk=pk, loja=loja,
    )
    cancel_form = CancelarDocumentoForm()
    cce_form = CartaCorrecaoForm()
    return render(
        request, 'app_pdv/fiscal/documento_detalhe.html',
        _ctx(request, loja, doc=doc, cancel_form=cancel_form, cce_form=cce_form),
    )


@login_required
@requer_acesso_fiscal
@require_POST
def fiscal_documento_cancelar(request, pk):
    loja = check_loja(request)
    doc = get_object_or_404(DocumentoFiscal, pk=pk, loja=loja)
    form = CancelarDocumentoForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Justificativa inválida (mín. 15 caracteres).')
        return redirect('fiscal_documento_detalhe', pk=pk)
    try:
        cancelar_documento(doc, form.cleaned_data['justificativa'])
        messages.success(request, 'Cancelamento enviado à Focus NFe.')
    except FocusNFeError as exc:
        messages.error(request, str(exc))
    return redirect('fiscal_documento_detalhe', pk=pk)


@login_required
@requer_acesso_fiscal
@require_POST
def fiscal_documento_cce(request, pk):
    loja = check_loja(request)
    doc = get_object_or_404(DocumentoFiscal, pk=pk, loja=loja)
    form = CartaCorrecaoForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Texto da CC-e inválido.')
        return redirect('fiscal_documento_detalhe', pk=pk)
    try:
        carta_correcao_documento(doc, form.cleaned_data['correcao'])
        messages.success(request, 'Carta de correção enviada.')
    except FocusNFeError as exc:
        messages.error(request, str(exc))
    return redirect('fiscal_documento_detalhe', pk=pk)


@login_required
@requer_acesso_fiscal
def fiscal_emitir(request):
    loja = check_loja(request)
    form = EmitirDocumentoForm(request.POST or None, initial={'tipo': 'nfce'})
    if request.method == 'POST' and form.is_valid():
        venda = None
        venda_id = form.cleaned_data.get('venda_id')
        if venda_id:
            venda = get_object_or_404(Venda, pk=venda_id, loja=loja)
        try:
            doc = emitir_documento(
                loja, request.user,
                tipo=form.cleaned_data['tipo'],
                venda=venda,
            )
            messages.success(request, f'Documento {doc.ref} enviado (status: {doc.status}).')
            return redirect('fiscal_documento_detalhe', pk=doc.id)
        except FocusNFeError as exc:
            messages.error(request, str(exc))
    vendas_recentes = Venda.objects.filter(loja=loja).order_by('-id')[:30]
    return render(
        request, 'app_pdv/fiscal/emitir.html',
        _ctx(request, loja, form=form, vendas_recentes=vendas_recentes),
    )


@login_required
@requer_acesso_fiscal
def fiscal_emitir_lote(request):
    loja = check_loja(request)
    form = EmitirLoteForm(request.POST or None)
    preview_vendas = []
    limite = LOTE_EMISSAO_MAX_VENDAS

    if request.method == 'POST':
        acao = request.POST.get('acao', 'preview')
        if acao == 'emitir':
            venda_ids = []
            for raw in request.POST.getlist('venda_ids'):
                raw = str(raw).strip()
                if raw.isdigit():
                    venda_ids.append(int(raw))
            tipo = request.POST.get('tipo') or 'nfce'
            if not venda_ids:
                messages.error(request, 'Selecione ao menos uma venda para emitir em lote.')
            else:
                from app_pdv.models import Venda
                vendas = list(
                    Venda.objects.filter(loja=loja, pk__in=venda_ids).order_by('data_venda', 'id'),
                )
                if len(vendas) > limite:
                    messages.error(request, f'Máximo de {limite} vendas por lote.')
                else:
                    lote = processar_lote_emissao(
                        loja, request.user,
                        tipo=tipo,
                        vendas=vendas,
                        filtros_meta={'observacao': f'Lote manual — {len(vendas)} venda(s)'},
                    )
                    messages.success(
                        request,
                        f'Lote #{lote.id} finalizado: {lote.total_autorizado} autorizado(s), '
                        f'{lote.total_erro} erro(s), {lote.total_ignorado} ignorado(s).',
                    )
                    return redirect('fiscal_lote_detalhe', pk=lote.id)
        elif form.is_valid():
            preview_vendas = buscar_vendas_elegiveis_lote(
                loja,
                tipo=form.cleaned_data['tipo'],
                data_de=form.cleaned_data.get('data_de'),
                data_ate=form.cleaned_data.get('data_ate'),
                venda_ids=form.cleaned_data.get('venda_ids_parsed'),
                pular_ja_emitidas=form.cleaned_data.get('pular_ja_emitidas', True),
                limite=limite,
            )
            if not preview_vendas:
                messages.warning(request, 'Nenhuma venda elegível encontrada para os filtros informados.')
            else:
                messages.info(
                    request,
                    f'{len(preview_vendas)} venda(s) elegível(eis). Revise a lista e confirme a emissão.',
                )

    lotes_recentes = LoteEmissaoFiscal.objects.filter(loja=loja)[:15]
    return render(
        request,
        'app_pdv/fiscal/emitir_lote.html',
        _ctx(
            request,
            loja,
            form=form,
            preview_vendas=preview_vendas,
            limite_lote=limite,
            lotes_recentes=lotes_recentes,
        ),
    )


@login_required
@requer_acesso_fiscal
def fiscal_lote_detalhe(request, pk):
    loja = check_loja(request)
    lote = get_object_or_404(
        LoteEmissaoFiscal.objects.prefetch_related('itens__venda', 'itens__documento'),
        pk=pk,
        loja=loja,
    )
    return render(
        request,
        'app_pdv/fiscal/lote_detalhe.html',
        _ctx(request, loja, lote=lote),
    )


@login_required
@requer_acesso_fiscal
def fiscal_webhooks(request):
    loja = check_loja(request)
    logs = FiscalWebhookLog.objects.filter(loja=loja).select_related('documento')[:150]
    return render(request, 'app_pdv/fiscal/webhooks.html', _ctx(request, loja, logs=logs))


@login_required
@requer_acesso_fiscal
def fiscal_contingencia(request):
    loja = check_loja(request)
    cfg = get_or_create_config(loja)
    if request.method == 'POST':
        form = ContingenciaForm(request.POST, instance=cfg)
        if form.is_valid():
            obj = form.save(commit=False)
            if obj.contingencia_ativa and not cfg.contingencia_inicio:
                obj.contingencia_inicio = timezone.now()
            if not obj.contingencia_ativa:
                obj.contingencia_inicio = None
            obj.save()
            messages.success(request, 'Contingência atualizada.')
            return redirect('fiscal_contingencia')
    else:
        form = ContingenciaForm(instance=cfg)
    return render(request, 'app_pdv/fiscal/contingencia.html', _ctx(request, loja, form=form))


@login_required
@requer_acesso_fiscal
def fiscal_arquivos(request):
    loja = check_loja(request)
    docs = DocumentoFiscal.objects.filter(loja=loja).exclude(
        caminho_xml='', caminho_pdf='', url_xml='', url_pdf='',
    ).order_by('-criado_em')[:100]
    # also include authorized with any path
    docs = DocumentoFiscal.objects.filter(loja=loja, status='autorizado').order_by('-criado_em')[:100]
    return render(request, 'app_pdv/fiscal/arquivos.html', _ctx(request, loja, documentos=docs))


@login_required
@requer_acesso_fiscal
def fiscal_reforma(request):
    loja = check_loja(request)
    regras = RegraTributaria.objects.filter(loja=loja).order_by('nome')
    return render(request, 'app_pdv/fiscal/reforma.html', _ctx(request, loja, regras=regras))


@login_required
@requer_acesso_fiscal
def fiscal_inutilizacao(request):
    loja = check_loja(request)
    itens = InutilizacaoNumeracao.objects.filter(loja=loja)[:50]
    form = InutilizacaoForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        obj = form.save(commit=False)
        obj.loja = loja
        obj.criado_por = request.user
        obj.ref = f'inut-{loja.id}-{timezone.now().strftime("%Y%m%d%H%M%S")}'
        obj.status = 'registrado_local'
        obj.mensagem = 'Registro local. Envio à Focus pode ser feito quando o token estiver ativo.'
        obj.save()
        messages.success(request, 'Pedido de inutilização registrado.')
        return redirect('fiscal_inutilizacao')
    return render(
        request, 'app_pdv/fiscal/inutilizacao.html',
        _ctx(request, loja, form=form, itens=itens),
    )


@login_required
@requer_acesso_fiscal
def fiscal_manifestacao(request):
    loja = check_loja(request)
    recebidas = NFeRecebida.objects.filter(loja=loja)[:100]
    return render(request, 'app_pdv/fiscal/manifestacao.html', _ctx(request, loja, recebidas=recebidas))


@login_required
@requer_acesso_fiscal
@require_POST
def fiscal_manifestar(request, pk):
    loja = check_loja(request)
    nfe = get_object_or_404(NFeRecebida, pk=pk, loja=loja)
    form = ManifestacaoForm(request.POST)
    if form.is_valid():
        nfe.manifestacao = form.cleaned_data['manifestacao']
        nfe.manifestacao_em = timezone.now()
        nfe.situacao = 'manifestada'
        nfe.save(update_fields=['manifestacao', 'manifestacao_em', 'situacao'])
        messages.success(request, 'Manifestação registrada (envio Focus quando configurado).')
    return redirect('fiscal_manifestacao')


@csrf_exempt
@require_POST
def fiscal_webhook_focus(request):
    """Pilar 4 — endpoint público para gatilhos Focus NFe."""
    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'status': 'erro', 'mensagem': 'JSON inválido'}, status=400)

    headers = {k: v for k, v in request.headers.items() if k.lower().startswith(('x-', 'content-', 'authorization'))}
    cnpj = ''.join(c for c in str(payload.get('cnpj_emitente') or '') if c.isdigit())
    loja = None
    if cnpj:
        from app_pdv.models import Loja
        for candidate in Loja.objects.filter(fiscal_habilitado=True):
            digits = ''.join(c for c in (candidate.cnpj or '') if c.isdigit())
            if digits == cnpj:
                loja = candidate
                break
            cfg = getattr(candidate, 'fiscal_config', None)
            if cfg and ''.join(c for c in (cfg.cnpj or '') if c.isdigit()) == cnpj:
                loja = candidate
                break

    log = processar_webhook(payload, headers=headers, loja=loja)
    return JsonResponse({'status': 'ok', 'log_id': log.id, 'processado': log.processado})
