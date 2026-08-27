"""Importação de produtos via Excel: somar/substituir estoque e reversão."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

import pandas as pd
from django.db import transaction
from django.utils import timezone

from .models import (
    GrupoProduto,
    ImportacaoProdutosItemSnapshot,
    ImportacaoProdutosLog,
    ImportacaoProdutosProdutoSnapshot,
    ItemEstoque,
    ItemVenda,
    Produto,
)


MODO_SOMAR = 'SOMAR'
MODO_SUBSTITUIR = 'SUBSTITUIR'


def normalizar_codigo_barras_excel(valor):
    """Converte célula Excel em código limpo (sem .0 / notação científica)."""
    if valor is None:
        return ''
    try:
        if pd.isna(valor):
            return ''
    except (TypeError, ValueError):
        pass

    if isinstance(valor, bool):
        return ''

    if isinstance(valor, int):
        return str(valor) if valor >= 0 else ''

    if isinstance(valor, float):
        if abs(valor) >= 1e16:
            return ''
        if valor == int(valor):
            return str(int(valor))
        return f'{valor:.0f}'

    texto = str(valor).strip()
    if not texto or texto.lower() in ('nan', 'none', 'nat'):
        return ''

    texto_norm = texto.replace(' ', '').replace(',', '.')
    if 'e+' in texto_norm.lower() or 'e-' in texto_norm.lower():
        try:
            num = float(texto_norm)
            if abs(num) >= 1e16:
                return ''
            if num == int(num):
                return str(int(num))
            return f'{num:.0f}'
        except ValueError:
            return ''

    if texto.endswith('.0') and texto[:-2].lstrip('-').isdigit():
        texto = texto[:-2]

    so_digitos = ''.join(ch for ch in texto if ch.isdigit())
    return so_digitos if so_digitos else texto.strip()


def normalizar_colunas_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = (
        df.columns.str.lower().str.strip()
        .str.replace(' ', '_')
        .str.replace('ç', 'c').str.replace('ã', 'a')
        .str.replace('á', 'a').str.replace('à', 'a')
        .str.replace('é', 'e').str.replace('ê', 'e')
        .str.replace('í', 'i').str.replace('ó', 'o')
        .str.replace('ô', 'o').str.replace('ú', 'u')
    )
    return df


def _limpar_preco(valor) -> float:
    if pd.isna(valor):
        return 0.0
    if isinstance(valor, (int, float)):
        return float(valor)
    valor = str(valor).replace('R$', '').replace(' ', '').replace('.', '').replace(',', '.')
    try:
        return float(valor)
    except ValueError:
        return 0.0


class ResultadoImportacaoProdutos:
    def __init__(self):
        self.produtos_criados = 0
        self.produtos_atualizados = 0
        self.linhas_processadas = 0
        self.avisos: list[str] = []


@transaction.atomic
def executar_importacao_produtos(
    loja,
    usuario,
    df: pd.DataFrame,
    nome_arquivo: str,
    modo_estoque: str,
) -> tuple[ImportacaoProdutosLog, ResultadoImportacaoProdutos]:
    if modo_estoque not in (MODO_SOMAR, MODO_SUBSTITUIR):
        raise ValueError('Modo de estoque inválido.')

    resultado = ResultadoImportacaoProdutos()
    log = ImportacaoProdutosLog.objects.create(
        loja=loja,
        usuario=usuario,
        nome_arquivo=nome_arquivo or 'importacao.xlsx',
        modo_estoque=modo_estoque,
    )

    item_snaps: dict[int, dict[str, Any]] = {}
    produto_snaps: list[dict[str, Any]] = []

    for index, row in df.iterrows():
        item_pai_nome = row.get('item_pai')
        nome_venda = row.get('nome_venda')

        if pd.isna(item_pai_nome) or pd.isna(nome_venda):
            continue

        item_pai_nome = str(item_pai_nome).strip()
        nome_venda = str(nome_venda).strip()
        if not item_pai_nome or not nome_venda:
            continue

        resultado.linhas_processadas += 1
        linha_planilha = int(index) + 2

        unidade = str(row.get('unidade', 'UN')).strip().upper()
        if unidade not in ('UN', 'KG', 'L'):
            unidade = 'UN'

        estoque_total = Decimal(str(_limpar_preco(row.get('estoque_total', 0))))
        qtd_baixa = _limpar_preco(row.get('qtd_baixa', 1))
        if qtd_baixa <= 0:
            qtd_baixa = 1

        custo = Decimal(str(_limpar_preco(row.get('preco_custo', 0))))
        venda = Decimal(str(_limpar_preco(row.get('preco_venda', 0))))
        codigo_barras = normalizar_codigo_barras_excel(row.get('codigo_barras', ''))

        grupo_nome = row.get('grupo')
        grupo_obj = None
        if pd.notna(grupo_nome) and str(grupo_nome).strip() and str(grupo_nome).strip().lower() != 'nan':
            grupo_obj, _ = GrupoProduto.objects.get_or_create(
                loja=loja,
                nome=str(grupo_nome).strip(),
            )

        validade_raw = row.get('data_validade')
        observacao_raw = row.get('observacao')
        data_val = None
        if pd.notna(validade_raw) and str(validade_raw).strip():
            try:
                data_val = pd.to_datetime(validade_raw).date()
            except (ValueError, TypeError):
                pass

        obs_val = str(observacao_raw).strip() if pd.notna(observacao_raw) else ''
        if obs_val == 'nan':
            obs_val = ''

        item, created_item = ItemEstoque.objects.get_or_create(
            nome=item_pai_nome,
            loja=loja,
            defaults={
                'unidade_medida': unidade,
                'data_validade': data_val,
                'observacao': obs_val,
            },
        )

        if not created_item:
            mudou = False
            if data_val:
                item.data_validade = data_val
                mudou = True
            if obs_val:
                item.observacao = obs_val
                mudou = True
            if mudou:
                item.save()

        if item.id not in item_snaps:
            item_snaps[item.id] = {
                'item': item,
                'estoque_antes': Decimal(str(item.quantidade_estoque)),
                'item_criado': created_item,
                'nome_item': item.nome,
            }

        if estoque_total > 0:
            if modo_estoque == MODO_SOMAR:
                item.quantidade_estoque = Decimal(str(item.quantidade_estoque)) + estoque_total
            else:
                item.quantidade_estoque = estoque_total
            item.save(update_fields=['quantidade_estoque'])
            item_snaps[item.id]['estoque_depois'] = Decimal(str(item.quantidade_estoque))

        if codigo_barras:
            conflito = Produto.objects.filter(
                loja=loja, codigo_barras=codigo_barras,
            ).exclude(nome_venda=nome_venda, item_estoque=item).exists()
            if conflito:
                resultado.avisos.append(
                    f"Código de barras '{codigo_barras}' já usado em outro produto "
                    f"(linha {linha_planilha}). Produto '{nome_venda}' importado sem o código."
                )
                codigo_barras = ''

        produto_existente = Produto.objects.filter(
            loja=loja, nome_venda=nome_venda, item_estoque=item,
        ).first()

        snap_produto = {
            'produto_existente': produto_existente,
            'produto_criado': produto_existente is None,
            'nome_venda': nome_venda,
            'linha_planilha': linha_planilha,
        }
        if produto_existente:
            snap_produto.update({
                'preco_compra_antes': produto_existente.preco_compra,
                'preco_venda_antes': produto_existente.preco_venda,
                'quantidade_baixa_antes': produto_existente.quantidade_baixa,
                'codigo_barras_antes': produto_existente.codigo_barras or '',
                'grupo_id_antes': produto_existente.grupo_id,
                'ativo_antes': produto_existente.ativo,
            })

        defaults_produto = {
            'quantidade_baixa': Decimal(str(qtd_baixa)),
            'preco_compra': custo,
            'preco_venda': venda,
            'ativo': True,
        }
        if codigo_barras:
            defaults_produto['codigo_barras'] = codigo_barras
        if grupo_obj is not None:
            defaults_produto['grupo'] = grupo_obj

        produto, created_prod = Produto.objects.update_or_create(
            loja=loja,
            nome_venda=nome_venda,
            item_estoque=item,
            defaults=defaults_produto,
        )
        snap_produto['produto'] = produto
        produto_snaps.append(snap_produto)

        if created_prod:
            resultado.produtos_criados += 1
        else:
            resultado.produtos_atualizados += 1

    for data in item_snaps.values():
        estoque_depois = data.get('estoque_depois', data['estoque_antes'])
        ImportacaoProdutosItemSnapshot.objects.create(
            importacao=log,
            item_estoque=data['item'],
            estoque_antes=data['estoque_antes'],
            estoque_depois=estoque_depois,
            item_criado=data['item_criado'],
            nome_item=data['nome_item'],
        )

    for data in produto_snaps:
        ImportacaoProdutosProdutoSnapshot.objects.create(
            importacao=log,
            produto=data['produto'],
            produto_criado=data['produto_criado'],
            nome_venda=data['nome_venda'],
            linha_planilha=data['linha_planilha'],
            preco_compra_antes=data.get('preco_compra_antes'),
            preco_venda_antes=data.get('preco_venda_antes'),
            quantidade_baixa_antes=data.get('quantidade_baixa_antes'),
            codigo_barras_antes=data.get('codigo_barras_antes', ''),
            grupo_id_antes=data.get('grupo_id_antes'),
            ativo_antes=data.get('ativo_antes'),
        )

    log.produtos_criados = resultado.produtos_criados
    log.produtos_atualizados = resultado.produtos_atualizados
    log.linhas_processadas = resultado.linhas_processadas
    log.save(update_fields=['produtos_criados', 'produtos_atualizados', 'linhas_processadas'])

    return log, resultado


class ResultadoReversaoImportacao:
    def __init__(self):
        self.ok = True
        self.mensagens: list[str] = []
        self.produtos_removidos = 0
        self.produtos_restaurados = 0
        self.itens_restaurados = 0


@transaction.atomic
def reverter_importacao_produtos(log: ImportacaoProdutosLog, usuario) -> ResultadoReversaoImportacao:
    out = ResultadoReversaoImportacao()

    if log.revertida_em:
        out.ok = False
        out.mensagens.append('Esta importação já foi revertida.')
        return out

    importacao_mais_recente = (
        ImportacaoProdutosLog.objects.filter(loja=log.loja, revertida_em__isnull=True)
        .order_by('-criado_em', '-id')
        .first()
    )
    if importacao_mais_recente and importacao_mais_recente.id != log.id:
        out.ok = False
        out.mensagens.append(
            f'Só é possível reverter a importação mais recente (#{importacao_mais_recente.id}). '
            f'Reverta as importações na ordem inversa (da mais nova para a mais antiga).'
        )
        return out

    produtos_com_venda = []
    for snap in log.produtos_snapshot.filter(produto_criado=True).select_related('produto'):
        if snap.produto_id and ItemVenda.objects.filter(produto_id=snap.produto_id).exists():
            produtos_com_venda.append(snap.nome_venda)

    if produtos_com_venda:
        out.ok = False
        amostra = ', '.join(produtos_com_venda[:5])
        extra = f' (+{len(produtos_com_venda) - 5} outros)' if len(produtos_com_venda) > 5 else ''
        out.mensagens.append(
            f'Não é possível reverter: produto(s) desta importação já têm vendas registradas '
            f'({amostra}{extra}).'
        )
        return out

    for snap in log.produtos_snapshot.filter(produto_criado=True).select_related('produto'):
        if snap.produto_id:
            snap.produto.delete()
            out.produtos_removidos += 1

    for snap in log.produtos_snapshot.filter(produto_criado=False).select_related('produto'):
        if not snap.produto_id:
            continue
        p = snap.produto
        if snap.preco_compra_antes is not None:
            p.preco_compra = snap.preco_compra_antes
        if snap.preco_venda_antes is not None:
            p.preco_venda = snap.preco_venda_antes
        if snap.quantidade_baixa_antes is not None:
            p.quantidade_baixa = snap.quantidade_baixa_antes
        p.codigo_barras = snap.codigo_barras_antes or ''
        p.grupo_id = snap.grupo_id_antes
        if snap.ativo_antes is not None:
            p.ativo = snap.ativo_antes
        p.save()
        out.produtos_restaurados += 1

    for snap in log.itens_snapshot.select_related('item_estoque'):
        item = snap.item_estoque
        if not item:
            continue
        delta = Decimal(str(snap.estoque_depois)) - Decimal(str(snap.estoque_antes))
        novo_estoque = Decimal(str(item.quantidade_estoque)) - delta
        if novo_estoque < 0:
            novo_estoque = Decimal('0')
        item.quantidade_estoque = novo_estoque
        item.save(update_fields=['quantidade_estoque'])
        out.itens_restaurados += 1

        if snap.item_criado and not Produto.objects.filter(item_estoque=item).exists():
            if item.quantidade_estoque <= 0:
                item.delete()

    log.revertida_em = timezone.now()
    log.revertida_por = usuario
    log.save(update_fields=['revertida_em', 'revertida_por'])

    return out
