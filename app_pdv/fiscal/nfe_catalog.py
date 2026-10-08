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
    ('csosn_102', 'Simples Nacional — CSOSN 102'),
    ('csosn_500', 'ICMS cobrado anteriormente por ST — CSOSN 500'),
    ('csosn_400', 'Isento / não tributada — CSOSN 400'),
    ('csosn_300', 'Imune — CSOSN 300'),
    ('substituicao', 'Substituição tributária — CSOSN 500'),
]

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
