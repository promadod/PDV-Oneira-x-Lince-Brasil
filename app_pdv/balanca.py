"""Etiqueta de balança (Toledo Prix / EAN-13 interno) alinhada ao cadastro do PDV."""
from decimal import Decimal, ROUND_HALF_UP


PREFIXO_PADRAO = '2'
PLU_DIGITOS_PADRAO = 6
VARIAVEL_PADRAO = 'PESO'


def _apenas_digitos(valor):
    return ''.join(ch for ch in str(valor or '') if ch.isdigit())


def ean13_digito_verificador(doze_digitos):
    corpo = _apenas_digitos(doze_digitos)
    if len(corpo) != 12:
        raise ValueError('EAN-13 exige 12 dígitos antes do verificador.')
    soma = 0
    for i, ch in enumerate(corpo):
        n = int(ch)
        soma += n if i % 2 == 0 else n * 3
    return str((10 - (soma % 10)) % 10)


def ean13_valido(codigo):
    codigo = _apenas_digitos(codigo)
    if len(codigo) != 13:
        return False
    return ean13_digito_verificador(codigo[:12]) == codigo[12]


def normalizar_plu(codigo, plu_digitos=PLU_DIGITOS_PADRAO):
    """Retorna o PLU só com dígitos, com padding, se couber no tamanho da balança."""
    digitos = _apenas_digitos(codigo)
    if not digitos:
        return ''
    if len(digitos) > int(plu_digitos):
        return digitos
    return digitos.zfill(int(plu_digitos))


def chaves_busca_plu(codigo, plu_digitos=PLU_DIGITOS_PADRAO):
    """Variações do código cadastrado para achar o produto após a leitura da etiqueta."""
    bruto = str(codigo or '').strip()
    digitos = _apenas_digitos(bruto)
    chaves = set()
    if bruto:
        chaves.add(bruto)
    if digitos:
        chaves.add(digitos)
        chaves.add(digitos.lstrip('0') or '0')
        if len(digitos) <= int(plu_digitos):
            chaves.add(digitos.zfill(int(plu_digitos)))
    return [c for c in chaves if c]


def config_balanca_loja(loja=None):
    prefixo = PREFIXO_PADRAO
    plu_digitos = PLU_DIGITOS_PADRAO
    variavel = VARIAVEL_PADRAO
    ativa = False
    if loja is not None:
        prefixo = _apenas_digitos(getattr(loja, 'balanca_ean_prefixo', None) or PREFIXO_PADRAO) or PREFIXO_PADRAO
        plu_digitos = int(getattr(loja, 'balanca_plu_digitos', None) or PLU_DIGITOS_PADRAO)
        variavel = (getattr(loja, 'balanca_ean_variavel', None) or VARIAVEL_PADRAO).upper()
        ativa = bool(getattr(loja, 'trabalha_com_balanca_granel', False))
    if plu_digitos not in (4, 5, 6):
        plu_digitos = PLU_DIGITOS_PADRAO
    if variavel not in ('PESO', 'PRECO'):
        variavel = VARIAVEL_PADRAO
    return {
        'ativa': ativa,
        'prefixo': prefixo,
        'plu_digitos': plu_digitos,
        'variavel': variavel,
    }


def montar_ean13_etiqueta(plu, peso_kg=None, preco_total=None, loja=None, config=None):
    """Monta o EAN-13 que a balança imprime (útil para testes e conferência)."""
    cfg = config or config_balanca_loja(loja)
    prefixo = cfg['prefixo']
    plu_n = int(cfg['plu_digitos'])
    plu_fmt = normalizar_plu(plu, plu_n)
    if len(_apenas_digitos(plu_fmt)) != plu_n:
        raise ValueError('PLU não cabe no tamanho configurado da balança.')
    tamanho_payload = 12 - len(prefixo) - plu_n
    if tamanho_payload < 1:
        raise ValueError('Prefixo + PLU excedem 12 dígitos do EAN-13.')
    if cfg['variavel'] == 'PRECO':
        centavos = int((Decimal(str(preco_total or 0)).quantize(Decimal('0.01')) * 100).to_integral_value())
        payload = str(max(centavos, 0)).zfill(tamanho_payload)[-tamanho_payload:]
    else:
        gramas = int((Decimal(str(peso_kg or 0)) * 1000).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
        payload = str(max(gramas, 0)).zfill(tamanho_payload)[-tamanho_payload:]
    corpo = f'{prefixo}{plu_fmt}{payload}'
    if len(corpo) != 12:
        raise ValueError('Composição EAN-13 inválida.')
    return corpo + ean13_digito_verificador(corpo)


def decodificar_ean13_balanca(codigo, loja=None, config=None):
    """
    Interpreta etiqueta de peso variável.
    Retorna dict com plu, quantidade (kg) ou preco_total, ou None.
    """
    cfg = config or config_balanca_loja(loja)
    bruto = _apenas_digitos(codigo)
    if len(bruto) != 13:
        return None
    prefixo = cfg['prefixo']
    if not bruto.startswith(prefixo):
        return None
    plu_n = int(cfg['plu_digitos'])
    inicio_plu = len(prefixo)
    fim_plu = inicio_plu + plu_n
    if fim_plu >= 12:
        return None
    plu = bruto[inicio_plu:fim_plu]
    payload = bruto[fim_plu:12]
    if not plu.isdigit() or not payload.isdigit():
        return None
    resultado = {
        'plu': plu,
        'plu_sem_zeros': plu.lstrip('0') or '0',
        'prefixo': prefixo,
        'variavel': cfg['variavel'],
        'ean13': bruto,
        'dv_ok': ean13_valido(bruto),
        'quantidade': None,
        'preco_total': None,
    }
    valor = int(payload)
    if cfg['variavel'] == 'PRECO':
        resultado['preco_total'] = (Decimal(valor) / Decimal('100')).quantize(Decimal('0.01'))
    else:
        resultado['quantidade'] = (Decimal(valor) / Decimal('1000')).quantize(Decimal('0.001'))
        if resultado['quantidade'] <= 0:
            return None
    if cfg['variavel'] == 'PRECO' and resultado['preco_total'] <= 0:
        return None
    return resultado


def quantidade_da_etiqueta(decodificado, preco_unitario=None):
    """Quantidade em kg (ou unidades) a lançar no PDV a partir da etiqueta."""
    if not decodificado:
        return None
    if decodificado.get('quantidade') is not None:
        return decodificado['quantidade']
    preco_total = decodificado.get('preco_total')
    if preco_total is None:
        return None
    try:
        unitario = Decimal(str(preco_unitario))
    except Exception:
        return None
    if unitario <= 0:
        return None
    qtd = (preco_total / unitario).quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)
    return qtd if qtd > 0 else None


def gerar_csv_carga_balanca(produtos, loja=None):
    """
    CSV para importar no MGV (Prix 4 Uno e Prix 3 Fit).
    codigo = o mesmo digitado na balança (cadastro do PDV).
    tipo_venda P = peso (granel).
    """
    cfg = config_balanca_loja(loja)
    linhas = ['codigo;descricao;preco;tipo_venda;unidade']
    for produto in produtos:
        codigo = (getattr(produto, 'codigo_barras', None) or '').strip()
        if not codigo:
            continue
        item = getattr(produto, 'item_estoque', None)
        unidade = (getattr(item, 'unidade_medida', None) or 'UN') if item else 'UN'
        if unidade != 'KG':
            continue
        plu = normalizar_plu(codigo, cfg['plu_digitos'])
        if not _apenas_digitos(plu):
            continue
        nome = (getattr(produto, 'nome_venda', None) or '').replace(';', ' ').strip()
        preco = Decimal(str(getattr(produto, 'preco_venda', 0) or 0)).quantize(Decimal('0.01'))
        linhas.append(f'{plu};{nome};{preco};P;KG')
    return '\n'.join(linhas) + '\n'
