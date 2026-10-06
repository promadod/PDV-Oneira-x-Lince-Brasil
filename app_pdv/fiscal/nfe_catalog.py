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


def natureza_por_cfop(cfop: str) -> str:
    for c, desc in NATUREZAS_NFE_UNICAS:
        if c == cfop:
            return desc
    return f'Operação CFOP {cfop}'
