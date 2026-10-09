"""Catálogos para emissão NF-e (naturezas/CFOP comuns — revenda, GLP, varejo)."""

# (CFOP, descrição natureza da operação — enviada à SEFAZ)
NATUREZAS_NFE = [
    ('5101', 'Venda de produção do estabelecimento'),
    ('5102', 'Venda de mercadoria adquirida ou recebida de terceiros'),
    ('5103', 'Venda de produção do estabelecimento efetuada fora do estabelecimento'),
    ('5104', 'Venda de mercadoria adquirida ou recebida de terceiros, efetuada fora do estabelecimento'),
    ('5405', 'Venda de mercadoria adquirida ou recebida de terceiros, sujeita ao regime de ST'),
    ('5656', 'Venda de combustível ou lubrificante adquirido ou recebido de terceiros'),
    ('5667', 'Venda de combustível ou lubrificante a consumidor ou usuário final'),
    ('5929', 'Lançamento efetuado em decorrência de emissão de documento fiscal'),
    ('5949', 'Outra saída de mercadoria ou prestação de serviço não especificada'),
    ('6102', 'Venda de mercadoria adquirida ou recebida de terceiros (interestadual)'),
    ('6656', 'Venda de combustível ou lubrificante adquirido ou recebido de terceiros (interestadual)'),
]

# Dedupe CFOP keeping first description
_seen = set()
NATUREZAS_NFE_UNICAS: list[tuple[str, str]] = []
for cfop, desc in NATUREZAS_NFE:
    if cfop in _seen:
        continue
    _seen.add(cfop)
    NATUREZAS_NFE_UNICAS.append((cfop, desc))

FINALIDADE_NFE = [
    ('1', 'Normal'),
    ('2', 'Complementar'),
    ('3', 'Ajuste'),
    ('4', 'Devolução de mercadoria'),
    ('5', 'Nota de crédito'),
    ('6', 'Nota de débito'),
]

INDICADOR_IE_DESTINATARIO = [
    ('9', '9 — Não contribuinte ICMS'),
    ('2', '2 — Contribuinte isento de IE'),
    ('1', '1 — Contribuinte ICMS (informar IE)'),
]

PRESENCA_COMPRADOR_NFE = [
    ('0', '0 — Não se aplica'),
    ('1', '1 — Operação presencial'),
    ('2', '2 — Pela internet'),
    ('3', '3 — Teleatendimento'),
    ('4', '4 — Entrega a domicílio'),
    ('5', '5 — Fora do estabelecimento'),
    ('9', '9 — Outros'),
]

PERFIL_TRIBUTACAO_NFE = [
    ('produto', 'Usar tributação do produto / matriz'),
    ('cst_61_combustivel', 'Combustível — ICMS monofásico retido (CST 61)'),
    ('csosn_102', 'Simples Nacional — CSOSN 102'),
    ('csosn_500', 'ICMS cobrado anteriormente por ST — CSOSN 500'),
    ('csosn_400', 'Isento / não tributada — CSOSN 400'),
    ('csosn_300', 'Imune — CSOSN 300'),
    ('substituicao', 'Substituição tributária — CSOSN 500'),
]

# CSTs de ICMS monofásico sobre combustíveis (NT 2023.001)
CST_ICMS_MONOFASICO_COMBUSTIVEL = frozenset({'02', '15', '53', '61'})
CST_ICMS_ISENTO_NAO_TRIB_COMB = frozenset({'40', '41', '50'})

# CFOPs típicos de revenda GLP/combustível já tributado na origem (CST 61)
CFOPS_COMBUSTIVEL_REVENDA_CST61 = frozenset({
    '5656', '5667', '6656', '6667',
})

# Códigos ANP GLP (origComb / percentuais GN — LA18-20, LA21-20)
ANP_GLP_ORIGEM = frozenset({
    '210203001', '210203003', '210203004', '210203005',
})

# Sigla UF → código IBGE (tag cUFOrig em origComb — não usar sigla)
UF_SIGLA_PARA_IBGE: dict[str, str] = {
    'AC': '12', 'AL': '27', 'AM': '13', 'AP': '16', 'BA': '29', 'CE': '23', 'DF': '53',
    'ES': '32', 'GO': '52', 'MA': '21', 'MG': '31', 'MS': '50', 'MT': '51', 'PA': '15',
    'PB': '25', 'PE': '26', 'PI': '22', 'PR': '41', 'RJ': '33', 'RN': '24', 'RO': '11',
    'RR': '14', 'RS': '43', 'SC': '42', 'SE': '28', 'SP': '35', 'TO': '17',
}


def codigo_uf_ibge(sigla_uf: str, *, fallback: str = '33') -> str:
    s = (sigla_uf or '').strip().upper()[:2]
    if s.isdigit() and len(s) == 2:
        return s
    return UF_SIGLA_PARA_IBGE.get(s, fallback)

# CFOPs de saída de combustível (grupo comb obrigatório na NF-e)
CFOPS_COMBUSTIVEL = {
    '5651', '5652', '5653', '5654', '5655', '5656', '5657', '5658', '5659',
    '5660', '5661', '5662', '5663', '5664', '5665', '5666', '5667',
    '6651', '6652', '6653', '6654', '6655', '6656', '6657', '6658', '6659',
    '6660', '6661', '6662', '6663', '6664', '6665', '6666', '6667',
}


def cfop_exige_grupo_combustivel(cfop: str) -> bool:
    c = ''.join(ch for ch in (cfop or '') if ch.isdigit())[:4]
    if c in CFOPS_COMBUSTIVEL:
        return True
    return len(c) == 4 and c[1] == '6' and c[2] in '567'


def cfop_sugere_consumidor_final(cfop: str) -> str:
    """indFinal: 1 = consumidor final (CFOP 566x/666x venda ao usuário final)."""
    c = ''.join(ch for ch in (cfop or '') if ch.isdigit())[:4]
    if len(c) == 4 and c[2] == '6' and c[3] == '7':
        return '1'
    return '0'


def produto_sujeito_icms_monofasico(cfop: str, codigo_anp: str, *, ncm: str = '') -> bool:
    if not cfop_exige_grupo_combustivel(cfop):
        return False
    if (codigo_anp or '').strip():
        return True
    n = ''.join(c for c in (ncm or '') if c.isdigit())[:8]
    # GLP / gás (NCM 2711…) — exige grupo monofásico quando CFOP é de combustível
    return n.startswith('2711')


MODALIDADE_FRETE_NFE = [
    ('9', '9 — Sem ocorrência de transporte'),
    ('0', '0 — Por conta do emitente'),
    ('1', '1 — Por conta do destinatário'),
    ('2', '2 — Por conta de terceiros'),
    ('3', '3 — Transporte próprio (emitente)'),
    ('4', '4 — Transporte próprio (destinatário)'),
]


def natureza_por_cfop(cfop: str) -> str:
    for c, desc in NATUREZAS_NFE_UNICAS:
        if c == cfop:
            return desc
    return f'Operação CFOP {cfop}'
