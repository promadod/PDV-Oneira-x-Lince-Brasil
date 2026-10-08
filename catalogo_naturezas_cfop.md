# Catálogo de Naturezas de Operação x CFOP

## Base para sistema fiscal --- NF-e / NFC-e

> **Importante:** Natureza da operação não é uma tabela oficial fechada.
> O contribuinte pode criar/organizar a descrição da natureza conforme
> sua operação; no SPED, o Registro 0400 inclusive trata a natureza como
> uma codificação própria do contribuinte e deixa claro que ela não se
> confunde com CFOP. O **CFOP é que deve refletir a operação
> efetivamente realizada**.\
> Fonte: Guia Prático EFD-ICMS/IPI do SPED/CONFAZ.

------------------------------------------------------------------------

## 1. Regra fundamental para o seu sistema

Não modele a relação como:

`Natureza = CFOP`

Modele como:

`Natureza + tipo de operação + origem/destino + finalidade + produto/serviço + contexto fiscal -> CFOP`

Exemplo:

-   "Venda de mercadoria adquirida de terceiros"
    -   dentro da UF -\> **5.102**
    -   outra UF -\> **6.102**
    -   exterior -\> **7.102**
-   "Venda de produção própria"
    -   dentro da UF -\> **5.101**
    -   outra UF -\> **6.101**
    -   exterior -\> **7.101**

Isso evita que o usuário escolha um CFOP incompatível apenas porque a
descrição parece semelhante.

------------------------------------------------------------------------

# 2. Entradas --- compras e aquisições

## 1.100 --- Compras para industrialização, produção rural, comercialização ou prestação

  Natureza sugerida                                              CFOP
  ----------------------------------------------------------- -------
  Compra para industrialização                                  1.101
  Compra para comercialização                                   1.102
  Compra de produção rural para industrialização                1.101
  Compra de mercadoria para revenda                             1.102
  Compra de mercadoria para uso na prestação de serviço         1.102
  Entrada de mercadoria para industrialização por encomenda     1.124
  Entrada para industrialização efetuada por outra empresa      1.125
  Compra de energia elétrica para industrialização              1.251
  Compra de energia elétrica por estabelecimento comercial      1.252
  Compra de serviço de transporte                               1.352
  Compra de serviço de comunicação                              1.353
  Compra de combustível para consumo                            1.653
  Compra de mercadoria para uso ou consumo                      1.556

### Interestaduais

  -----------------------------------------------------------------------
  Natureza sugerida                                                  CFOP
  ------------------------------ ----------------------------------------
  Compra interestadual para                                         2.101
  industrialização               

  Compra interestadual para                                         2.102
  comercialização                

  Compra interestadual para                                         2.102
  revenda                        

  Entrada interestadual para                                        2.124
  industrialização por encomenda 

  Entrada interestadual para                                        2.125
  industrialização efetuada por  
  outra empresa                  

  Compra interestadual de                                           2.251
  energia elétrica               

  Compra interestadual de                                           2.352
  serviço de transporte          

  Compra interestadual de                                           2.353
  serviço de comunicação         

  Compra interestadual de                                           2.653
  combustível                    

  Compra interestadual para uso                                     2.556
  ou consumo                     
  -----------------------------------------------------------------------

### Importação

  Natureza sugerida                          CFOP
  --------------------------------------- -------
  Importação para industrialização          3.101
  Importação para comercialização           3.102
  Importação de mercadoria para revenda     3.102
  Importação de serviço de transporte       3.352
  Importação de serviço de comunicação      3.353
  Importação de energia elétrica            3.251
  Importação para uso ou consumo            3.556

------------------------------------------------------------------------

# 3. Devoluções de compras

A devolução normalmente deve espelhar a operação de entrada original.

  Natureza sugerida                                                        CFOP
  ------------------------------------------------------------- ---------------
  Devolução de compra para industrialização                               5.201
  Devolução de compra para comercialização                                5.202
  Devolução de compra para industrialização --- interestadual             6.201
  Devolução de compra para comercialização --- interestadual              6.202
  Devolução de compra para industrialização --- exterior                  7.201
  Devolução de compra para comercialização --- exterior                   7.202
  Devolução de compra de ativo imobilizado                        5.553 / 6.553
  Devolução de material para uso ou consumo                       5.556 / 6.556

> **Atenção:** devolução não deve ser escolhida apenas pelo texto. O
> CFOP deve ser compatível com o documento/operação que está sendo
> devolvido.

------------------------------------------------------------------------

# 4. Saídas --- vendas

## Venda de produção própria

  -----------------------------------------------------------------------
  Natureza sugerida                                                  CFOP
  ------------------------------ ----------------------------------------
  Venda de produção do                                              5.101
  estabelecimento                

  Venda de produção própria para                                    6.101
  outro estado                   

  Venda de produção própria para                                    7.101
  o exterior                     

  Venda de produção própria que                     5.105 / 6.105 / 7.105
  não transita pelo              
  estabelecimento                
  -----------------------------------------------------------------------

## Venda de mercadoria adquirida de terceiros

  -----------------------------------------------------------------------
  Natureza sugerida                                                  CFOP
  ------------------------------ ----------------------------------------
  Venda de mercadoria adquirida                                     5.102
  de terceiros                   

  Venda de mercadoria adquirida                                     6.102
  de terceiros para outro estado 

  Venda de mercadoria adquirida                                     7.102
  de terceiros para o exterior   

  Venda de mercadoria de                            5.106 / 6.106 / 7.106
  terceiros que não transita     
  pelo estabelecimento           
  -----------------------------------------------------------------------

------------------------------------------------------------------------

# 5. Vendas específicas

  -----------------------------------------------------------------------
  Natureza sugerida                                             CFOP base
  ------------------------------ ----------------------------------------
  Venda para entrega futura                                 5.116 / 6.116

  Venda de produção do                                      5.116 / 6.116
  estabelecimento para entrega   
  futura                         

  Venda de mercadoria adquirida                             5.117 / 6.117
  de terceiros para entrega      
  futura                         

  Venda à ordem                                             5.118 / 6.118

  Venda à ordem de mercadoria                               5.119 / 6.119
  adquirida de terceiros         

  Venda de produção própria para                            5.101 / 6.101
  consumidor final               

  Venda de mercadoria de                                    5.102 / 6.102
  terceiros para consumidor      
  final                          

  Venda de ativo imobilizado                                5.551 / 6.551

  Venda de material de uso ou                               5.556 / 6.556
  consumo                        
  -----------------------------------------------------------------------

> O CFOP exato depende do cenário. "Consumidor final" sozinho não
> determina o CFOP.

------------------------------------------------------------------------

# 6. Transferências entre estabelecimentos

  Natureza sugerida                                               CFOP
  ---------------------------------------------------- ---------------
  Transferência de produção própria                      5.151 / 6.151
  Transferência de mercadoria adquirida de terceiros     5.152 / 6.152
  Transferência de mercadoria para industrialização      5.151 / 6.151
  Transferência de mercadoria para comercialização       5.152 / 6.152
  Transferência de energia elétrica                      5.153 / 6.153
  Transferência de combustível                           5.157 / 6.157
  Transferência de ativo imobilizado                     5.552 / 6.552
  Transferência de material de uso ou consumo            5.557 / 6.557

------------------------------------------------------------------------

# 7. Remessas

## Demonstração / mostruário

  Natureza sugerida                                  CFOP
  --------------------------------------- ---------------
  Remessa para demonstração                 5.912 / 6.912
  Remessa de mercadoria para mostruário     5.912 / 6.912
  Retorno de demonstração                   5.913 / 6.913

## Conserto / reparo

  Natureza sugerida                                         CFOP
  ---------------------------------------------- ---------------
  Remessa para conserto                            5.915 / 6.915
  Remessa para reparo                              5.915 / 6.915
  Retorno de mercadoria recebida para conserto     5.916 / 6.916

## Industrialização

  Natureza sugerida                                                 CFOP
  ------------------------------------------------------ ---------------
  Remessa para industrialização por encomenda              5.901 / 6.901
  Retorno de industrialização por encomenda                5.902 / 6.902
  Remessa de insumos para industrialização                 5.901 / 6.901
  Retorno de mercadoria recebida para industrialização     5.902 / 6.902

## Armazém geral / depósito

  Natureza sugerida                                   CFOP
  ---------------------------------------- ---------------
  Remessa para armazém geral                 5.905 / 6.905
  Retorno de mercadoria de armazém geral     5.906 / 6.906
  Remessa para depósito fechado              5.905 / 6.905
  Retorno de depósito fechado                5.906 / 6.906

------------------------------------------------------------------------

# 8. Bonificação, doação e brindes

  Natureza sugerida                                CFOP
  ------------------------------------- ---------------
  Entrada de bonificação                  1.910 / 2.910
  Remessa de bonificação                  5.910 / 6.910
  Remessa de doação                       5.910 / 6.910
  Remessa de brinde                       5.910 / 6.910
  Distribuição gratuita de mercadoria     5.910 / 6.910

> A tributação e o enquadramento fiscal podem mudar conforme a situação.
> O texto "bonificação" não deve ser usado como substituto da análise
> tributária.

------------------------------------------------------------------------

# 9. Amostra grátis

  Natureza sugerida                      CFOP
  --------------------------- ---------------
  Remessa de amostra grátis     5.911 / 6.911
  Entrada de amostra grátis     1.911 / 2.911

------------------------------------------------------------------------

# 10. Ativo imobilizado

  Natureza sugerida                                         CFOP
  ---------------------------------------------- ---------------
  Compra de bem para o ativo imobilizado           1.551 / 2.551
  Venda de bem do ativo imobilizado                5.551 / 6.551
  Transferência de ativo imobilizado               5.552 / 6.552
  Devolução de compra de ativo imobilizado         5.553 / 6.553
  Entrada decorrente de transferência de ativo     1.552 / 2.552

------------------------------------------------------------------------

# 11. Uso e consumo

  Natureza sugerida                                        CFOP
  --------------------------------------------- ---------------
  Compra de material para uso ou consumo          1.556 / 2.556
  Transferência de material de uso ou consumo     5.557 / 6.557
  Devolução de material de uso ou consumo         5.556 / 6.556

------------------------------------------------------------------------

# 12. Energia elétrica

  Natureza sugerida                                             CFOP
  -------------------------------------------------- ---------------
  Compra de energia elétrica para industrialização             1.251
  Compra de energia elétrica para comercialização              1.252
  Compra interestadual de energia elétrica                     2.251
  Venda de energia elétrica                            5.251 / 6.251
  Entrada de energia elétrica por transferência        1.253 / 2.253

------------------------------------------------------------------------

# 13. Combustíveis e lubrificantes

  -----------------------------------------------------------------------
  Natureza sugerida                                                  CFOP
  ------------------------------ ----------------------------------------
  Compra de combustível para                                1.651 / 2.651
  industrialização               

  Compra de combustível para                                1.652 / 2.652
  comercialização                

  Compra de combustível para                                1.653 / 2.653
  consumo                        

  Venda de combustível                                      5.651 / 6.651

  Venda de combustível ou                                   5.656 / 6.656
  lubrificante adquirido de      
  terceiros                      
  -----------------------------------------------------------------------

------------------------------------------------------------------------

# 14. Serviços de transporte --- entradas

  -----------------------------------------------------------------------
  Natureza sugerida                                                  CFOP
  ------------------------------ ----------------------------------------
  Aquisição de serviço de                                           1.352
  transporte dentro do estado    

  Aquisição de serviço de                                           2.352
  transporte interestadual       

  Aquisição de serviço de                                           3.352
  transporte do exterior         

  Anulação de valor relativo à                                      1.206
  aquisição de serviço de        
  transporte                     

  Anulação de valor relativo à                                      2.206
  aquisição de serviço de        
  transporte --- interestadual   

  Anulação de valor relativo à                                      3.206
  aquisição de serviço de        
  transporte --- exterior        
  -----------------------------------------------------------------------

### Observação sobre a imagem

O item selecionado na sua tela:

**"Anulação de valor relativo à prest. de serviço de transporte" + CFOP
1206**

está conceitualmente alinhado com a descrição do CFOP **1.206** para
anulação de valor relativo à aquisição de serviço de transporte.

Mas o seu sistema deve permitir a variação **2.206** ou **3.206** quando
o contexto da operação for outro estado ou exterior.

------------------------------------------------------------------------

# 15. Serviços de comunicação

  -----------------------------------------------------------------------
  Natureza sugerida                                                  CFOP
  ------------------------------ ----------------------------------------
  Aquisição de serviço de                                           1.353
  comunicação                    

  Aquisição interestadual de                                        2.353
  serviço de comunicação         

  Aquisição de comunicação do                                       3.353
  exterior                       

  Anulação de valor relativo à                      1.205 / 2.205 / 3.205
  aquisição de serviço de        
  comunicação                    
  -----------------------------------------------------------------------

------------------------------------------------------------------------

# 16. Exportação

  -----------------------------------------------------------------------
  Natureza sugerida                                                  CFOP
  ------------------------------ ----------------------------------------
  Exportação de produção própria                                    7.101

  Exportação de mercadoria                                          7.102
  adquirida de terceiros         

  Exportação de produção própria                                    7.105
  sem trânsito pelo              
  estabelecimento                

  Exportação de mercadoria de                                       7.106
  terceiros sem trânsito pelo    
  estabelecimento                

  Exportação de produção própria                                    7.127
  sob drawback                   

  Exportação de produto                                             7.129
  industrializado sob RECOF-Sped 
  -----------------------------------------------------------------------

------------------------------------------------------------------------

# 17. Devoluções de vendas

Para uma devolução, o sistema deve considerar **qual foi o CFOP da saída
original**.

Exemplos:

  Operação original                                          Devolução
  ---------------------------------------------------- ---------------
  Venda de produção própria                              1.201 / 2.201
  Venda de mercadoria adquirida de terceiros             1.202 / 2.202
  Venda de produção própria para outro estado                    2.201
  Venda de mercadoria de terceiros para outro estado             2.202
  Venda para exterior                                    3.201 / 3.202

> Não trate a devolução como uma natureza isolada. O sistema deve pedir
> ou recuperar o documento de origem.

------------------------------------------------------------------------

# 18. Outras operações / remessas

  Natureza sugerida                                                  CFOP
  ------------------------------------------------------- ---------------
  Outras saídas de mercadoria ou prestação de serviço               5.949
  Outras saídas interestaduais                                      6.949
  Outras entradas de mercadoria ou prestação de serviço             1.949
  Outras entradas interestaduais                                    2.949
  Outras entradas do exterior                                       3.949
  Entrada de mercadoria recebida para demonstração          1.912 / 2.912
  Entrada de mercadoria recebida para conserto              1.915 / 2.915
  Retorno de mercadoria remetida para conserto              1.916 / 2.916

------------------------------------------------------------------------

# 19. Arquitetura recomendada para o seu sistema

Não recomendo armazenar apenas:

``` json
{
  "natureza": "Compra para comercialização",
  "cfop": "1102"
}
```

Prefira algo próximo de:

``` json
{
  "natureza": "Compra para comercialização",
  "operacao": "entrada",
  "finalidade": "comercializacao",
  "origem_destino": "interna",
  "cfop": "1102",
  "descricao_cfop": "Compra para comercialização",
  "ativo": true
}
```

E para venda:

``` json
{
  "natureza": "Venda de mercadoria adquirida de terceiros",
  "operacao": "saida",
  "finalidade": "comercializacao",
  "origem_destino": "interna",
  "cfop": "5102",
  "descricao_cfop": "Venda de mercadoria adquirida ou recebida de terceiros",
  "ativo": true
}
```

------------------------------------------------------------------------

# 20. Melhor ainda: matriz de decisão

Para um sistema fiscal profissional, crie uma matriz:

``` text
TIPO DE OPERAÇÃO
│
├── Entrada
│   ├── Compra
│   ├── Devolução
│   ├── Retorno
│   ├── Transferência
│   ├── Importação
│   └── Anulação
│
└── Saída
    ├── Venda
    ├── Devolução
    ├── Remessa
    ├── Transferência
    ├── Exportação
    ├── Bonificação
    ├── Demonstração
    ├── Conserto
    └── Industrialização
```

Depois:

``` text
Operação
   ↓
Mercadoria ou serviço?
   ↓
Produção própria ou terceiros?
   ↓
Interna / interestadual / exterior?
   ↓
Finalidade
   ↓
Situação especial
   ↓
CFOP candidato
   ↓
Regras fiscais
   ↓
CST/CSOSN + ICMS + IPI + PIS/COFINS
```

------------------------------------------------------------------------

# 21. Regra crítica para o desenvolvedor

**CFOP não deve ser usado sozinho para determinar toda a tributação.**

O CFOP é apenas uma parte da classificação fiscal. O seu motor fiscal
deverá considerar, entre outros:

-   CFOP
-   CST/CSOSN
-   NCM
-   CEST
-   origem da mercadoria
-   CRT
-   UF de origem
-   UF de destino
-   consumidor final
-   contribuinte ou não contribuinte de ICMS
-   finalidade da operação
-   regime tributário
-   benefícios fiscais
-   ICMS próprio
-   ICMS-ST
-   DIFAL, quando aplicável
-   FCP, quando aplicável
-   IPI
-   PIS
-   COFINS
-   regras específicas do produto/operação

------------------------------------------------------------------------

# 22. Recomendação para a tela mostrada na imagem

Em vez de deixar o usuário simplesmente escolher:

**Natureza → CFOP**

faça:

``` text
Natureza da operação
[ Venda de mercadoria adquirida de terceiros ]

Tipo
[ Saída ]

Finalidade
[ Comercialização ]

Destino
[ Dentro do estado ▼ ]

Produção
[ Mercadoria adquirida de terceiros ▼ ]

CFOP sugerido
[ 5.102 ]

✓ Usar este CFOP
```

E deixe o usuário alterar o CFOP apenas se ele tiver
permissão/configuração fiscal adequada.

Isso reduz muito a possibilidade de uma nota ser autorizada com uma
classificação incompatível.

------------------------------------------------------------------------

## Fontes de referência

-   CONFAZ / SPED --- Guia Prático EFD-ICMS/IPI, Registro 0400: a
    natureza da operação/prestação é uma codificação própria do
    contribuinte e não se confunde com CFOP.
-   Tabelas oficiais de CFOP e documentos fiscais publicados por
    administrações tributárias estaduais.
-   O CFOP é uma classificação fiscal da operação/prestação; a descrição
    da natureza exibida no ERP pode ser criada pelo próprio sistema.

> **Aviso de implementação:** este arquivo é uma base de catálogo para
> parametrização de software, não substitui a análise fiscal da operação
> concreta. A classificação correta permanece responsabilidade do
> contribuinte. Regras estaduais, benefícios, regimes especiais e
> alterações de Ajustes SINIEF podem alterar a aplicação de determinado
> código.
