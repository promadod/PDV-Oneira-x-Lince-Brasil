---
updatedAt: 2026-07-08T16:20:49.000Z
---

Fetch the complete documentation index at: https://doc.focusnfe.com.br/llms.txt. Use this file to discover all available pages before exploring further. Append .md to any documentation page URL to get its markdown version.

# Introdução

A API Focus NFe permite emitir e consultar documentos fiscais eletrônicos a partir do seu sistema, em qualquer stack. Você envia os dados em formato estruturado (JSON); a API cuida da assinatura digital e da comunicação com a SEFAZ (estados), prefeituras (NFSe) ou demais órgãos competentes, conforme o documento.

Antes de integrar, confira as URLs por ambiente em [Ambiente](/reference/ambiente), o uso do token em [Autenticação](/reference/autenticacao) e o identificador de emissão em [Referência (ref)](/reference/referencia).

Documentos fiscais disponíveis:

* [CTe / CTe OS / CTe Simplificado](/reference/ctecteos)
* [MDFe](/reference/mdfe)
* [NFe](/reference/nfe)
* [NFCe](/reference/nfce)
* [NFCom](/reference/nfcom)
* [NFSe](/reference/nfse)
* [NFSe nacional](/reference/nfse-nacional)

Documentos recebidos (emitidos contra o seu CNPJ):

* [CTe recebidas](/reference/cte-recebidas)
* [NFe recebidas](/reference/nfe-recebidas)
* [NFSe nacional recebidas](/reference/nfsen-recebidas)

> Mais adiante nesta página há uma seção com mais informações.

Use esta documentação como guia principal da integração. Para explicações complementares, consulte os [Guides da Focus NFe](https://focusnfe.com.br/guides). Se ainda restar dúvida, entre em contato com o suporte em <suporte@focusnfe.com.br>.

## Como navegar nesta documentação

Comece por essa introdução (ambiente, autenticação e referência no início desta página) e, em seguida, abra a referência do que você vai emitir ou das notas recebidas que precisa acompanhar (veja as listas acima).

### Guarde e recupere os XMLs — backups sem depender só do seu servidor

Se o seu sistema cair, alguém apagar arquivo sem querer ou você precisar provar o histórico fiscal, ter **cópia dos XMLs** fora do dia a dia da aplicação evita dor de cabeça. A Focus NFe oferece **backups** dos documentos emitidos para você **listar, baixar e manter arquivo** com segurança. Hoje a API de backups cobre **NFe, NFCe, NFCom, CTe e MDFe**.

Para saber mais, leia a referência de [backups](/reference/backups).

### Seja notificado quando um documento for autorizado

Depois de enviar um documento, é comum precisar saber quando ele foi autorizado ou se houve erro. Resolver isso só com **consultas repetidas à API (vários GETs em sequência)** aumenta tráfego, pode bater em limites e atrasa a reação do seu sistema.

Para saber mais, leia a referência de [gatilhos e webhooks](/reference/webhooks).

### Terceiros emitindo contra seu CNPJ? Veja, arquive e responda à Receita quando couber

Quando **NFe, CTe ou NFSe nacional** são emitidos contra o seu CNPJ, acompanhar pela API evita surpresa na escrituração: você **sabe o que foi lançado em nome da empresa**, **baixa comprovantes** (XML, DANFE, DACTe, DANFSe em HTML ou PDF) e usa o que a Focus **guarda** dos documentos distribuídos.

Para saber mais, leia a referência de [NFe recebidas](/reference/nfe-recebidas), [CTe recebidas](/reference/cte-recebidas) e [NFSe nacional recebidas](/reference/nfsen-recebidas).

### Vários clientes emitindo por uma única integração?

Se você **centraliza vários CNPJs** (ERP, contabilidade ou SaaS), a **API de empresas** permite **cadastrar, listar, consultar, atualizar e excluir** cada empresa na Focus NFe. Tudo via integração, sem depender só do painel.

Para saber mais, leia a referência de [empresas](/reference/empresas).

### Precisa de consultas auxiliares (endereço, classificação fiscal, cadastro, municípios)?

Use as **APIs acessórias**:

* [CEPs](/reference/ceps)
* [CFOP](/reference/cfop)
* [CNAE](/reference/cnae)
* [CNPJ](/reference/cnpj)
* [Municípios](/reference/municipios)
* [NCM](/reference/ncm).