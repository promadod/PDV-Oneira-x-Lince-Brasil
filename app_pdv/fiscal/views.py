import json
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_POST

from app_pdv.models import ItemVenda, Produto, Venda
from app_pdv.views import check_loja, loja_usa_taxa_servico

from .access import requer_acesso_fiscal
from .focus_client import FocusNFeError
from .forms import (
    CancelarDocumentoForm,
    CartaCorrecaoForm,
    ContabilidadePeriodoForm,
    ContingenciaForm,
    EmitirAvulsaForm,
    EmitirDocumentoForm,
    EmitirLoteForm,
    EmitirNFeForm,
    LoteAvulsoForm,
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
    reemitir_documento,
    get_or_create_config,
    processar_lote_avulso_emissao,
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
        {'titulo': 'Integração API fiscal', 'desc': 'Token, ambiente, teste de conexão e gatilhos', 'url': 'fiscal_focus', 'icone': 'fa-plug'},
        {'titulo': '1. Configurações', 'desc': 'Empresa, CRT, endereço e certificado digital', 'url': 'fiscal_config', 'icone': 'fa-building'},
        {'titulo': '2. Matriz tributária', 'desc': 'NCM, CFOP, CSOSN/CST e alíquotas', 'url': 'fiscal_matriz', 'icone': 'fa-table'},
        {'titulo': '3. Documentos', 'desc': 'NF-e / NFC-e / NFS-e emitidos', 'url': 'fiscal_documentos', 'icone': 'fa-file-invoice'},
        {'titulo': '4. Webhooks', 'desc': 'Callbacks assíncronos da SEFAZ/API', 'url': 'fiscal_webhooks', 'icone': 'fa-bolt'},
        {'titulo': '5. NFC-e', 'desc': 'Cupom fiscal eletrônico do consumidor', 'url': 'fiscal_emitir', 'icone': 'fa-receipt'},
        {'titulo': 'Emissão em lote', 'desc': 'Vendas PDV ou lote avulso por produto', 'url': 'fiscal_emitir_lote', 'icone': 'fa-layer-group'},
        {'titulo': 'Emissão avulsa', 'desc': 'NFC-e por produto (sem venda PDV)', 'url': 'fiscal_emitir_avulsa', 'icone': 'fa-box-open'},
        {'titulo': 'NF-e completa', 'desc': 'Modelo 55 com destinatário', 'url': 'fiscal_emitir_nfe', 'icone': 'fa-file-invoice'},
        {'titulo': 'Contabilidade', 'desc': 'ZIP XML/PDF, e-mail e WhatsApp', 'url': 'fiscal_contabilidade', 'icone': 'fa-balance-scale'},
        {'titulo': 'Relatórios fiscais', 'desc': 'Compras, documentos, vendas, SPED/Sintegra', 'url': 'fiscal_relatorios', 'icone': 'fa-chart-bar'},
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


def _log_focus_acao(acao: str, loja_id: int, **kwargs):
    extras = ' '.join(f'{k}={v}' for k, v in kwargs.items())
    logging.getLogger('app_pdv.fiscal').info(
        'fiscal_focus acao=%s loja=%s %s', acao, loja_id, extras.strip(),
    )


def _focus_integracao_page(request, loja, *, form=None):
    cfg = get_or_create_config(loja)
    webhook_sugerida = url_webhook_sistema(request)
    if form is None:
        form = FocusIntegracaoForm(
            instance=cfg,
            initial={'webhook_url_configurada': cfg.webhook_url_configurada or webhook_sugerida},
        )
    gatilhos = []
    if cfg.focus_token:
        try:
            gatilhos = listar_gatilhos_focus(cfg)
        except FocusNFeError:
            gatilhos = []
    checklist = [
        {'ok': bool(cfg.focus_token), 'texto': 'Token da API fiscal configurado (Basic Auth)'},
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
            checklist=checklist,
        ),
    )


@login_required
@requer_acesso_fiscal
@require_http_methods(['GET', 'POST'])
def fiscal_focus(request):
    loja = check_loja(request)
    if request.method == 'POST':
        acao = request.POST.get('acao', 'desconhecida')
        _log_focus_acao('legacy_post', loja.id, acao_post=acao, path=request.path)
        messages.warning(
            request,
            'Use os botões Salvar ou Testar conexão na tela (URLs dedicadas). Ação antiga ignorada.',
        )
        return redirect('fiscal_focus')
    return _focus_integracao_page(request, loja)


@login_required
@requer_acesso_fiscal
@require_POST
def fiscal_focus_salvar(request):
    loja = check_loja(request)
    cfg = get_or_create_config(loja)
    _log_focus_acao('salvar', loja.id)
    form = FocusIntegracaoForm(request.POST, instance=cfg)
    if form.is_valid():
        form.save()
        _log_focus_acao('salvar_ok', loja.id, ambiente=form.instance.ambiente)
        messages.success(request, 'Integração fiscal salva.')
    else:
        _log_focus_acao('salvar_invalid', loja.id, erros=form.errors.as_json())
        messages.error(request, 'Corrija os campos antes de salvar.')
        return _focus_integracao_page(request, loja, form=form)
    return redirect('fiscal_focus')


@login_required
@requer_acesso_fiscal
@require_POST
def fiscal_focus_testar(request):
    loja = check_loja(request)
    cfg = get_or_create_config(loja)
    _log_focus_acao('testar', loja.id)
    form = FocusIntegracaoForm(request.POST, instance=cfg)
    if not form.is_valid():
        _log_focus_acao('testar_form_invalid', loja.id, erros=form.errors.as_json())
        messages.error(request, 'Corrija os campos do formulário antes de testar a conexão.')
        return _focus_integracao_page(request, loja, form=form)
    cfg = form.save()
    try:
        teste = testar_conexao_focus(cfg)
        _log_focus_acao(
            'testar_ok', loja.id,
            ambiente=cfg.ambiente, gatilhos=teste['gatilhos_cadastrados'],
        )
        messages.success(
            request,
            f'Conexão OK ({cfg.get_ambiente_display()}). '
            f'Gatilhos ativos: {teste["gatilhos_cadastrados"]}.',
        )
    except FocusNFeError as exc:
        _log_focus_acao('testar_falhou', loja.id, ambiente=cfg.ambiente, erro=str(exc))
        messages.error(request, str(exc))
    return redirect('fiscal_focus')


@login_required
@requer_acesso_fiscal
@require_POST
def fiscal_focus_registrar_webhooks(request):
    loja = check_loja(request)
    cfg = get_or_create_config(loja)
    webhook_sugerida = url_webhook_sistema(request)
    _log_focus_acao('registrar_webhooks', loja.id)
    url_hook = (request.POST.get('webhook_url') or cfg.webhook_url_configurada or webhook_sugerida).strip()
    eventos = request.POST.getlist('eventos_webhook')
    try:
        resultados = registrar_gatilhos_focus(cfg, url_hook, eventos=eventos or None)
        ok = sum(1 for r in resultados if r.get('ok'))
        _log_focus_acao('registrar_webhooks_ok', loja.id, registrados=ok)
        messages.success(request, f'{ok} gatilho(s) registrado(s) na API.')
    except FocusNFeError as exc:
        _log_focus_acao('registrar_webhooks_falhou', loja.id, erro=str(exc))
        messages.error(request, str(exc))
    return redirect('fiscal_focus')


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
    if request.method == 'POST':
        if form.is_valid():
            produto = get_object_or_404(Produto, pk=int(form.cleaned_data['produto_id']), loja=loja)
            preco = form.cleaned_data.get('preco_unitario') or produto.preco_venda
            logging.getLogger('app_pdv.fiscal').info(
                'fiscal_emitir_avulsa enviando loja=%s produto=%s', loja.id, produto.id,
            )
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
                        'valor_desconto': float(form.cleaned_data.get('valor_desconto') or 0),
                        'valor_acrescimo': float(form.cleaned_data.get('valor_acrescimo') or 0),
                        'cpf_destinatario': form.cleaned_data.get('cpf_destinatario') or '',
                        'cnpj_destinatario': form.cleaned_data.get('cnpj_destinatario') or '',
                        'nome_destinatario': form.cleaned_data.get('nome_destinatario') or '',
                    },
                )
                logging.getLogger('app_pdv.fiscal').info(
                    'fiscal_emitir_avulsa ok loja=%s ref=%s status=%s',
                    loja.id, doc.ref, doc.status,
                )
                messages.success(request, f'NFC-e avulsa enviada — ref {doc.ref} ({doc.status}).')
                return redirect('fiscal_documento_detalhe', pk=doc.id)
            except FocusNFeError as exc:
                logging.getLogger('app_pdv.fiscal').warning(
                    'fiscal_emitir_avulsa falhou loja=%s produto=%s erro=%s',
                    loja.id, produto.id, exc,
                )
                messages.error(request, str(exc))
        else:
            logging.getLogger('app_pdv.fiscal').info(
                'fiscal_emitir_avulsa form_invalid loja=%s erros=%s',
                loja.id, form.errors.as_json(),
            )
            messages.error(request, 'Corrija os campos do formulário antes de emitir.')
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
@require_POST
def fiscal_documento_reemitir(request, pk):
    loja = check_loja(request)
    doc = get_object_or_404(DocumentoFiscal, pk=pk, loja=loja)
    novo = reemitir_documento(loja, request.user, doc)
    if novo.status == 'erro':
        messages.error(request, novo.mensagem_sefaz or 'Reemissão rejeitada pela API/SEFAZ.')
    elif novo.status == 'autorizado':
        messages.success(request, f'Reemissão autorizada — ref {novo.ref}.')
    else:
        messages.info(request, f'Reemissão enviada — ref {novo.ref} ({novo.get_status_display()}).')
    return redirect('fiscal_documento_detalhe', pk=novo.id)


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
        messages.success(request, 'Cancelamento enviado à SEFAZ.')
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
    form_avulso = LoteAvulsoForm(request.POST or None, loja=loja)
    preview_vendas = []
    limite = LOTE_EMISSAO_MAX_VENDAS

    if request.method == 'POST':
        acao = request.POST.get('acao', 'preview')
        if acao == 'lote_avulso' and form_avulso.is_valid():
            produto = get_object_or_404(
                Produto, pk=int(form_avulso.cleaned_data['produto_id']), loja=loja,
            )
            preco = form_avulso.cleaned_data.get('preco_unitario') or produto.preco_venda
            try:
                lote = processar_lote_avulso_emissao(
                    loja, request.user,
                    produto=produto,
                    quantidade_total=float(form_avulso.cleaned_data['quantidade_total']),
                    quantidade_por_cupom=float(form_avulso.cleaned_data['quantidade_por_cupom']),
                    preco_unitario=float(preco),
                    desconto_unitario=float(form_avulso.cleaned_data.get('desconto_unitario') or 0),
                    forma_pagamento=form_avulso.cleaned_data['forma_pagamento'],
                )
                messages.success(
                    request,
                    f'Lote avulso #{lote.id}: {lote.total_autorizado} autorizado(s), {lote.total_erro} erro(s).',
                )
                return redirect('fiscal_lote_detalhe', pk=lote.id)
            except FocusNFeError as exc:
                messages.error(request, str(exc))
        elif acao == 'emitir':
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
            form_avulso=form_avulso,
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
        LoteEmissaoFiscal.objects.prefetch_related('itens__venda', 'itens__documento', 'itens__produto'),
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
def fiscal_documento_arquivo(request, pk, formato):
    """Proxy autenticado para XML/DANFE na Focus (PDF ou HTML DANFCE)."""
    loja = check_loja(request)
    doc = get_object_or_404(DocumentoFiscal, pk=pk, loja=loja)
    cfg = get_or_create_config(loja)
    from .focus_arquivos import obter_conteudo_documento

    if formato not in ('xml', 'pdf'):
        return HttpResponse(status=404)
    if not cfg.focus_token:
        messages.error(request, 'Token da API fiscal não configurado.')
        return redirect('fiscal_documento_detalhe', pk=pk)
    conteudo, content_type, fname = obter_conteudo_documento(cfg, doc, formato=formato, refresh=True)
    if not conteudo:
        messages.error(request, 'Arquivo não disponível para este documento.')
        return redirect('fiscal_documento_detalhe', pk=pk)
    response = HttpResponse(conteudo, content_type=content_type)
    response['Content-Disposition'] = f'inline; filename="{fname}"'
    return response


@login_required
@requer_acesso_fiscal
def fiscal_arquivos(request):
    loja = check_loja(request)
    docs = DocumentoFiscal.objects.filter(loja=loja, status='autorizado').order_by('-criado_em')[:100]
    return render(request, 'app_pdv/fiscal/arquivos.html', _ctx(request, loja, documentos=docs))


def _redirect_contabilidade(mes_ref: str = ''):
    from django.urls import reverse

    url = reverse('fiscal_contabilidade')
    if mes_ref:
        url = f'{url}?mes={mes_ref}'
    return redirect(url)


def _parse_mes_referencia(mes_ref: str) -> tuple[int, int] | None:
    try:
        ano, mes = [int(x) for x in (mes_ref or '').split('-', 1)]
        if 1 <= mes <= 12:
            return ano, mes
    except (ValueError, IndexError):
        pass
    return None


@login_required
@requer_acesso_fiscal
def fiscal_contabilidade_baixar(request):
    """Download do ZIP via GET (evita falha silenciosa de validação do form POST)."""
    loja = check_loja(request)
    cfg = get_or_create_config(loja)
    parsed = _parse_mes_referencia(request.GET.get('mes', ''))
    if not parsed:
        messages.error(request, 'Informe o mês no formato AAAA-MM.')
        return _redirect_contabilidade()
    ano, mes = parsed
    from .contabilidade_service import montar_zip_contabilidade

    zip_bytes, nome = montar_zip_contabilidade(loja, cfg, ano=ano, mes=mes)
    response = HttpResponse(zip_bytes, content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="{nome}"'
    return response


@login_required
@requer_acesso_fiscal
def fiscal_contabilidade(request):
    loja = check_loja(request)
    cfg = get_or_create_config(loja)
    hoje = timezone.localdate()
    initial = {
        'mes_referencia': hoje.strftime('%Y-%m'),
        'email_destino': cfg.email_contabilidade or cfg.email_envio_xml or '',
        'whatsapp_destino': cfg.whatsapp_contabilidade or '',
    }
    mes_ref_atual = (
        request.GET.get('mes', '').strip()
        or (request.POST.get('mes_referencia') if request.method == 'POST' else '')
        or initial['mes_referencia']
    )
    initial['mes_referencia'] = mes_ref_atual
    form = ContabilidadePeriodoForm(request.POST or None, initial=initial)
    stats = None
    parsed_atual = _parse_mes_referencia(mes_ref_atual)
    whatsapp_link = None
    if request.method != 'POST':
        whatsapp_link = request.session.pop('fiscal_contabilidade_wa', None)
    if parsed_atual:
        from .contabilidade_service import resumo_contabilidade
        stats = resumo_contabilidade(loja, ano=parsed_atual[0], mes=parsed_atual[1])

    if request.method == 'POST':
        acao = request.POST.get('acao', 'atualizar')
        mes_ref = request.POST.get('mes_referencia', '').strip() or initial['mes_referencia']
        parsed = _parse_mes_referencia(mes_ref)
        if not parsed:
            messages.error(request, 'Mês de referência inválido.')
            return _redirect_contabilidade()
        ano, mes = parsed
        from .contabilidade_service import (
            enviar_zip_por_email,
            montar_zip_contabilidade,
            resumo_contabilidade,
        )

        stats = resumo_contabilidade(loja, ano=ano, mes=mes)
        if acao == 'atualizar':
            messages.info(request, f'{stats["autorizados"]} documento(s) autorizado(s) no período.')
            return _redirect_contabilidade(mes_ref)
        if acao == 'email':
            dest = (request.POST.get('email_destino') or '').strip() or cfg.email_contabilidade
            if not dest:
                messages.error(request, 'Informe o e-mail da contabilidade.')
                return _redirect_contabilidade(mes_ref)
            zip_bytes, nome = montar_zip_contabilidade(loja, cfg, ano=ano, mes=mes)
            try:
                enviar_zip_por_email(
                    dest,
                    f'Pacote fiscal {mes:02d}/{ano} — {loja.nome}',
                    f'Segue ZIP com XMLs/PDFs autorizados em {mes:02d}/{ano}.',
                    zip_bytes,
                    nome,
                )
                cfg.email_contabilidade = dest
                cfg.save(update_fields=['email_contabilidade', 'atualizado_em'])
                messages.success(request, f'Pacote enviado para {dest}.')
            except Exception as exc:
                messages.error(request, f'Falha ao enviar e-mail: {exc}')
            return _redirect_contabilidade(mes_ref)
        if acao == 'whatsapp':
            from app_pdv.whatsapp_service import gerar_link_whatsapp

            tel = (request.POST.get('whatsapp_destino') or '').strip() or cfg.whatsapp_contabilidade
            if not tel:
                messages.error(request, 'Informe o WhatsApp da contabilidade.')
                return _redirect_contabilidade(mes_ref)
            msg = (
                f'Pacote fiscal {mes:02d}/{ano} — {stats["autorizados"]} NFC-e/NF-e autorizadas. '
                f'Baixe o ZIP em Oneira > Fiscal > Contabilidade e anexe aqui.'
            )
            cfg.whatsapp_contabilidade = tel
            cfg.save(update_fields=['whatsapp_contabilidade', 'atualizado_em'])
            link = gerar_link_whatsapp(tel, msg)
            if not link:
                messages.error(request, 'Número de WhatsApp inválido. Use DDD + número (ex.: 5511999999999).')
                return _redirect_contabilidade(mes_ref)
            request.session['fiscal_contabilidade_wa'] = link
            request.session.modified = True
            messages.info(request, 'Clique em «Abrir WhatsApp» no topo se a conversa não abrir sozinha.')
            return _redirect_contabilidade(mes_ref)
    return render(
        request,
        'app_pdv/fiscal/contabilidade.html',
        _ctx(
            request,
            loja,
            form=form,
            stats=stats,
            whatsapp_link=whatsapp_link,
            fiscal_config=cfg,
            mes_referencia=mes_ref_atual,
        ),
    )


@login_required
@requer_acesso_fiscal
def fiscal_venda_preview(request, venda_id):
    """Resumo da venda para modal no lote fiscal (mesmo layout da nota do histórico)."""
    from decimal import Decimal

    loja = check_loja(request)
    venda = get_object_or_404(Venda, pk=venda_id, loja=loja)
    itens = ItemVenda.objects.filter(venda=venda).select_related('produto', 'produto__item_estoque')
    liquidacoes = list(venda.liquidacoes.all())
    subtotal_consumo = sum(
        (item.quantidade * item.preco_unitario for item in itens),
        Decimal('0'),
    )
    ctx = {
        'venda': venda,
        'itens': itens,
        'liquidacoes': liquidacoes,
        'subtotal_consumo': subtotal_consumo,
        'modo_taxa_servico': loja_usa_taxa_servico(loja),
    }
    return render(request, 'app_pdv/fiscal/partials/venda_resumo_modal.html', ctx)


@login_required
@requer_acesso_fiscal
def fiscal_relatorios(request):
    loja = check_loja(request)
    from .relatorio_service import RELATORIOS_FISCAIS

    return render(
        request,
        'app_pdv/fiscal/relatorios.html',
        _ctx(request, loja, relatorios=RELATORIOS_FISCAIS),
    )


@login_required
@requer_acesso_fiscal
def fiscal_relatorio(request, slug):
    from datetime import datetime

    loja = check_loja(request)
    from .relatorio_service import RELATORIOS_FISCAIS, gerar_relatorio

    slugs = {s for s, _, _ in RELATORIOS_FISCAIS}
    if slug not in slugs:
        messages.error(request, 'Relatório não encontrado.')
        return redirect('fiscal_relatorios')

    data_de = data_ate = None
    de_raw = request.GET.get('de', '')
    ate_raw = request.GET.get('ate', '')
    if de_raw:
        try:
            data_de = datetime.strptime(de_raw, '%Y-%m-%d').date()
        except ValueError:
            messages.error(request, 'Data inicial inválida.')
    if ate_raw:
        try:
            data_ate = datetime.strptime(ate_raw, '%Y-%m-%d').date()
        except ValueError:
            messages.error(request, 'Data final inválida.')

    ctx = gerar_relatorio(loja, slug, data_de=data_de, data_ate=data_ate)
    if slug in ('sped-efd', 'sintegra') and request.GET.get('download') == '1':
        texto = ctx.get('arquivo_texto', '')
        nome = ctx.get('nome_arquivo', f'{slug}.txt')
        response = HttpResponse(texto, content_type='text/plain; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="{nome}"'
        return response

    return render(
        request,
        'app_pdv/fiscal/relatorio_detalhe.html',
        _ctx(request, loja, **ctx),
    )


@login_required
@requer_acesso_fiscal
@require_POST
def fiscal_natureza_criar(request):
    loja = check_loja(request)
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'erro': 'JSON inválido.'}, status=400)
    from .natureza_service import criar_natureza_loja

    try:
        obj = criar_natureza_loja(
            loja,
            cfop=data.get('cfop') or '',
            descricao=data.get('descricao') or '',
            tributacao=data.get('tributacao') or 'produto',
        )
    except ValueError as exc:
        return JsonResponse({'erro': str(exc)}, status=400)
    return JsonResponse({
        'ok': True,
        'cfop': obj.cfop,
        'descricao': obj.descricao,
        'label': f'{obj.cfop} — {obj.descricao}',
    })


@login_required
@requer_acesso_fiscal
def fiscal_emitir_nfe(request):
    loja = check_loja(request)
    form = EmitirNFeForm(request.POST or None, loja=loja)
    if request.method == 'POST' and form.is_valid():
        produto = get_object_or_404(Produto, pk=int(form.cleaned_data['produto_id']), loja=loja)
        preco = form.cleaned_data.get('preco_unitario') or produto.preco_venda
        nfe_dados = {
            'produto': produto,
            'quantidade': float(form.cleaned_data['quantidade']),
            'preco_unitario': float(preco),
            'natureza_operacao': form.cleaned_data['natureza_operacao'],
            'cfop': form.cleaned_data['cfop'],
            'finalidade_emissao': form.cleaned_data['finalidade_emissao'],
            'presenca_comprador': form.cleaned_data['presenca_comprador'],
            'modalidade_frete': form.cleaned_data['modalidade_frete'],
            'forma_pagamento': form.cleaned_data['forma_pagamento'],
            'indicador_ie_destinatario': form.cleaned_data.get('indicador_ie_destinatario') or '9',
            'inscricao_estadual_destinatario': form.cleaned_data.get('inscricao_estadual_destinatario') or '',
            'valor_desconto': float(form.cleaned_data.get('valor_desconto') or 0),
            'valor_acrescimo': float(form.cleaned_data.get('valor_acrescimo') or 0),
            'cpf_destinatario': form.cleaned_data.get('cpf_destinatario') or '',
            'cnpj_destinatario': form.cleaned_data.get('cnpj_destinatario') or '',
            'nome_destinatario': form.cleaned_data.get('nome_destinatario') or '',
            'logradouro': form.cleaned_data['logradouro'],
            'numero': form.cleaned_data['numero'],
            'complemento': form.cleaned_data.get('complemento') or '',
            'bairro': form.cleaned_data['bairro'],
            'valor_frete': float(form.cleaned_data.get('valor_frete') or 0),
            'quantidade_volumes': int(form.cleaned_data.get('quantidade_volumes') or 0),
            'peso_bruto': float(form.cleaned_data.get('peso_bruto') or 0),
            'peso_liquido': float(form.cleaned_data.get('peso_liquido') or 0),
            'municipio': form.cleaned_data['municipio'],
            'uf': form.cleaned_data['uf'],
            'cep': form.cleaned_data['cep'],
            'codigo_municipio': form.cleaned_data.get('codigo_municipio') or '',
            'tributacao': form.cleaned_data.get('tributacao') or 'produto',
            'serie': form.cleaned_data.get('serie'),
        }
        try:
            doc = emitir_documento(loja, request.user, nfe_dados=nfe_dados)
            messages.success(request, f'NF-e enviada — ref {doc.ref} ({doc.status}).')
            return redirect('fiscal_documento_detalhe', pk=doc.id)
        except FocusNFeError as exc:
            messages.error(request, str(exc))
    from app_pdv.models import Cliente

    clientes = Cliente.objects.filter(loja=loja).order_by('nome')[:800]
    return render(
        request,
        'app_pdv/fiscal/emitir_nfe.html',
        _ctx(request, loja, form=form, clientes=clientes),
    )


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
