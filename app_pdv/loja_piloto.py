"""Importação de produtos e parâmetros fiscais a partir de lojas piloto."""
from __future__ import annotations

from dataclasses import dataclass, field

from django.db import transaction

# Lojas piloto padrão por segmento (produção).
PILOTO_PADRAO_POR_SEGMENTO = {
    'mercadinho': 15,  # Sacolão / Mercadinho da Cris
    'revenda_gas': 16,  # Massini — revenda/depósito/distribuidora de gás
}

CAMPOS_PRODUTO_COPIAR = (
    'nome_venda',
    'codigo_barras',
    'preco_compra',
    'preco_venda',
    'preco_venda_completo',
    'quantidade_baixa',
    'ativo',
    'vende_vasilhame_vazio',
    'rastrear_recompra',
    'usa_venda_completa',
    'dias_recompra',
    'mensagem_recompra',
    'eh_kit',
)


@dataclass
class ResultadoImportacaoPiloto:
    produtos_criados: int = 0
    itens_estoque_criados: int = 0
    grupos_criados: int = 0
    fiscais_copiados: int = 0
    kits_copiados: int = 0
    avisos: list[str] = field(default_factory=list)


def lojas_piloto_queryset():
    """Lojas elegíveis no select de importação (flag piloto + padrões do segmento)."""
    from .models import Loja

    ids_padrao = set(PILOTO_PADRAO_POR_SEGMENTO.values())
    return (
        Loja.objects.filter(ativo=True)
        .filter(models_Q_loja_piloto_ou_padrao(ids_padrao))
        .order_by('nome')
    )


def models_Q_loja_piloto_ou_padrao(ids_padrao):
    from django.db.models import Q

    return Q(loja_piloto=True) | Q(pk__in=ids_padrao)


def opcoes_loja_piloto():
    """Lista (id, rótulo) para o select do admin."""
    from .models import Loja

    opcoes = [('', '— Não importar (cadastro normal)')]
    por_id = {loja.id: loja for loja in lojas_piloto_queryset()}

    for segmento, loja_id in PILOTO_PADRAO_POR_SEGMENTO.items():
        loja = por_id.get(loja_id) or Loja.objects.filter(pk=loja_id).first()
        if not loja:
            continue
        rotulo_seg = dict(Loja.SEGMENTO_CHOICES).get(segmento, segmento)
        opcoes.append((str(loja.id), f'{rotulo_seg} — {loja.nome} (piloto padrão)'))

    for loja in por_id.values():
        if loja.id in PILOTO_PADRAO_POR_SEGMENTO.values():
            continue
        opcoes.append((str(loja.id), f'{loja.nome} (loja piloto)'))
    return opcoes


def resolver_loja_piloto_id(*, segmento: str = '', loja_piloto_id=None) -> int | None:
    """Prioridade: loja piloto explícita no select; senão, padrão do segmento."""
    if loja_piloto_id:
        try:
            return int(loja_piloto_id)
        except (TypeError, ValueError):
            return None
    segmento = (segmento or '').strip()
    return PILOTO_PADRAO_POR_SEGMENTO.get(segmento)


def produtos_da_piloto(loja_piloto):
    from .models import Produto

    return (
        Produto.objects.filter(loja=loja_piloto, ativo=True)
        .select_related('item_estoque', 'item', 'grupo', 'dados_fiscais')
        .prefetch_related('componentes_kit__item_estoque')
        .order_by('nome_venda')
    )


def _obter_ou_criar_item(destino, origem_item, mapa_itens, resultado: ResultadoImportacaoPiloto):
    if origem_item is None:
        return None
    if origem_item.pk in mapa_itens:
        return mapa_itens[origem_item.pk]

    from .models import ItemEstoque

    item, created = ItemEstoque.objects.get_or_create(
        loja=destino,
        nome=origem_item.nome,
        defaults={
            'unidade_medida': origem_item.unidade_medida or 'UN',
            'quantidade_estoque': 0,
            'quantidade_vazios': 0,
            'data_validade': None,
            'observacao': '',
        },
    )
    if created:
        resultado.itens_estoque_criados += 1
    mapa_itens[origem_item.pk] = item
    return item


def _obter_ou_criar_grupo(destino, origem_grupo, mapa_grupos, resultado: ResultadoImportacaoPiloto):
    if origem_grupo is None:
        return None
    if origem_grupo.pk in mapa_grupos:
        return mapa_grupos[origem_grupo.pk]

    from .models import GrupoProduto

    grupo, created = GrupoProduto.objects.get_or_create(
        loja=destino,
        nome=origem_grupo.nome,
        defaults={'ordem': origem_grupo.ordem or 0},
    )
    if created:
        resultado.grupos_criados += 1
    mapa_grupos[origem_grupo.pk] = grupo
    return grupo


def _copiar_dados_fiscais(origem_produto, destino_produto, resultado: ResultadoImportacaoPiloto):
    from app_pdv.fiscal.models import ProdutoDadosFiscais
    from app_pdv.fiscal.produto_fiscal import CAMPOS_DADOS_FISCAIS_REPLICAR

    try:
        origem_df = origem_produto.dados_fiscais
    except ProdutoDadosFiscais.DoesNotExist:
        return

    destino_df, _ = ProdutoDadosFiscais.objects.get_or_create(produto=destino_produto)
    for campo in CAMPOS_DADOS_FISCAIS_REPLICAR:
        setattr(destino_df, campo, getattr(origem_df, campo))
    destino_df.save()
    resultado.fiscais_copiados += 1


@transaction.atomic
def importar_produtos_da_piloto(destino, origem, produto_ids) -> ResultadoImportacaoPiloto:
    """Clona produtos selecionados (estoque zerado + dados fiscais) da piloto para a loja nova."""
    from .models import ComponenteKit, Produto

    resultado = ResultadoImportacaoPiloto()
    if not destino or not origem or destino.pk == origem.pk:
        resultado.avisos.append('Loja destino/piloto inválida.')
        return resultado

    ids = []
    for raw in produto_ids or []:
        try:
            ids.append(int(raw))
        except (TypeError, ValueError):
            continue
    if not ids:
        resultado.avisos.append('Nenhum produto selecionado.')
        return resultado

    origem_produtos = list(
        Produto.objects.filter(loja=origem, pk__in=ids)
        .select_related('item_estoque', 'item', 'grupo')
        .prefetch_related('componentes_kit__item_estoque')
    )
    if not origem_produtos:
        resultado.avisos.append('Produtos da piloto não encontrados.')
        return resultado

    mapa_itens = {}
    mapa_grupos = {}
    mapa_produtos = {}

    for origem_p in origem_produtos:
        item_ref = origem_p.item_estoque or origem_p.item
        novo_item = _obter_ou_criar_item(destino, item_ref, mapa_itens, resultado)
        novo_grupo = _obter_ou_criar_grupo(destino, origem_p.grupo, mapa_grupos, resultado)

        kwargs = {campo: getattr(origem_p, campo) for campo in CAMPOS_PRODUTO_COPIAR}
        kwargs['loja'] = destino
        kwargs['grupo'] = novo_grupo
        kwargs['fornecedor'] = None
        kwargs['item_estoque'] = novo_item
        kwargs['item'] = novo_item if origem_p.item_id and item_ref and origem_p.item_id == item_ref.pk else None

        # Evita conflito de OneToOne item → produto_principal.
        if kwargs['item'] is not None:
            if Produto.objects.filter(item=kwargs['item']).exists():
                kwargs['item'] = None

        if kwargs.get('codigo_barras'):
            if Produto.objects.filter(loja=destino, codigo_barras=kwargs['codigo_barras']).exists():
                kwargs['codigo_barras'] = ''

        novo = Produto.objects.create(**kwargs)
        mapa_produtos[origem_p.pk] = novo
        resultado.produtos_criados += 1
        _copiar_dados_fiscais(origem_p, novo, resultado)

    # Componentes de kit (itens já mapeados ou criados sob demanda).
    for origem_p in origem_produtos:
        novo = mapa_produtos.get(origem_p.pk)
        if not novo or not origem_p.eh_kit:
            continue
        for comp in origem_p.componentes_kit.all():
            item_dest = _obter_ou_criar_item(destino, comp.item_estoque, mapa_itens, resultado)
            if not item_dest:
                continue
            ComponenteKit.objects.get_or_create(
                produto_kit=novo,
                item_estoque=item_dest,
                defaults={
                    'quantidade': comp.quantidade,
                    'ordem': comp.ordem,
                },
            )
            resultado.kits_copiados += 1

    return resultado
