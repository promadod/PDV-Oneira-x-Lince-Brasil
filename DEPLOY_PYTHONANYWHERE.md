# Deploy PythonAnywhere — checklist

Caminho no servidor: `/home/preapdev/Aplicativo-Delivery-SaaS/`  
URL: https://preapdev.pythonanywhere.com/

---

## Deploy rápido (sempre fazer nesta ordem)

1. Subir os arquivos listados na seção **Deploy atual** abaixo (mesmos caminhos no servidor).
2. Console:

```bash
cd ~/Aplicativo-Delivery-SaaS
workon venv
python manage.py migrate
python manage.py check
```

3. Aba **Web** → **Reload** `preapdev.pythonanywhere.com`

---

## Deploy atual — leitor de código de barras (migration `0049`)

### Migration

| Arquivo |
|---------|
| `app_pdv/migrations/0049_codigo_barras.py` |

### Backend — alterados

- [ ] `app_pdv/models.py` — `Loja.trabalha_com_leitor_codigo_barras`, `Produto.codigo_barras`
- [ ] `app_pdv/views.py` — contexto PDV com mapa de códigos
- [ ] `app_pdv/forms.py` — campo código de barras (só se loja ativa)
- [ ] `app_pdv/admin.py` — checkbox na Loja

### Templates — alterados

- [ ] `templates/app_pdv/vendas.html` — leitura USB na venda
- [ ] `templates/app_pdv/form_produto.html` — campo + layout corrigido

### Como usar

1. **Admin Django** → **Loja** → marque **Trabalha com leitor de código de barras?**
2. **Produtos** → cadastre o **Código de barras** em cada produto
3. **PDV** (`/vendas/nova/`) → passe o produto no leitor USB → produto selecionado automaticamente

---

## Deploy anterior — produto kit / promoção (migration `0048`)

### Migrations (obrigatório)

| Ordem | Arquivo |
|-------|---------|
| 1 | `app_pdv/migrations/0047_grupos_avaria.py` (se ainda não aplicada) |
| 2 | `app_pdv/migrations/0048_produto_kit.py` |

### Backend — alterados

- [ ] `app_pdv/models.py` — `eh_kit`, `ComponenteKit`, baixa/validação/devolução kit
- [ ] `app_pdv/views.py` — cadastro componentes, custo na venda
- [ ] `app_pdv/forms.py` — campo kit
- [ ] `app_pdv/admin.py` — `ComponenteKitAdmin`
- [ ] `app_pdv/signals.py` — estorno/baixa kit em vendas

### Templates — alterados

- [ ] `templates/app_pdv/form_produto.html` — seção componentes do kit
- [ ] `templates/app_pdv/lista_produtos.html` — badge KIT

### Como usar

1. **Produtos** → **Novo Produto** → marque **Produto kit / promoção?**
2. Defina **preço de venda** promocional (ex.: R$ 25,00)
3. Adicione componentes: ex. 2× Estoque A + 1× Estoque B + 4× Estoque C
4. Ao vender 1 kit no PDV, o sistema baixa automaticamente de cada estoque

### Testes

| O quê | Como |
|-------|------|
| Cadastro kit | `/produtos/novo/` → marcar kit → salvar com componentes |
| Venda PDV | `/vendas/nova/` → vender kit → conferir baixa nos 3 estoques |
| Cancelamento | Cancelar venda → estoque dos componentes devolvido |

---

## Deploy anterior — taxa de serviço, nota legível, recibo caixa com produtos (migration `0046`)

### Migration

| Arquivo |
|---------|
| `app_pdv/migrations/0046_taxa_servico.py` |

### Arquivos alterados

- [ ] `app_pdv/models.py` — `cobra_taxa_servico`, `taxa_servico_pct`, `Venda.taxa_servico`
- [ ] `app_pdv/views.py` — cálculo taxa serviço, agregação produtos no fechamento
- [ ] `app_pdv/admin.py`
- [ ] `templates/app_pdv/vendas.html`
- [ ] `templates/app_pdv/detalhes_venda.html`
- [ ] `templates/app_pdv/recibo_fechamento.html`

### Admin (Loja)

- **Trabalha com entregas** — desmarcado
- **Cobra taxa de serviço** — marcado
- **Taxa de serviço padrão (%)** — ex.: 10

### Testes

| O quê | Como |
|-------|------|
| Taxa serviço PDV | `/vendas/nova/` → campo **Taxa Serviço (%)** → total com 10% |
| Nota venda | `/vendas/detalhes/<id>/` → TOTAL CONSUMO + SERVIÇO + TOTAL CUPOM, fonte Arial |
| Recibo caixa | Fechar caixa → `/caixa/recibo/<id>/` → produtos agregados + texto escuro |

---

## Deploy anterior — histórico, retomar venda, loja balcão, impressão, estoque gestor (migration `0045`)

### Migrations (obrigatório)

| Ordem | Arquivo |
|-------|---------|
| 1 | `app_pdv/migrations/0044_produto_usa_venda_completa.py` (se ainda não aplicada) |
| 2 | `app_pdv/migrations/0045_loja_entregas_impressao.py` |

### Backend — alterados / novos

- [ ] `app_pdv/models.py` — `trabalha_com_entregas`, `impressao_automatica`
- [ ] `app_pdv/views.py` — histórico total, retomar venda, entrega balcão, auto-print
- [ ] `app_pdv/filtros_venda.py` — filtros meio/forma
- [ ] `app_pdv/admin.py`
- [ ] `app_pdv/gestor_api.py` — `montar_estoque_gestor`
- [ ] `app_pdv/gestor_views.py` — `api_gestor_estoque`
- [ ] `app_pdv/urls.py`

### Templates — alterados

- [ ] `templates/app_pdv/lista_vendas.html`
- [ ] `templates/app_pdv/vendas.html`
- [ ] `templates/app_pdv/detalhes_venda.html`

### Painel Gestor (Vercel)

Rebuild e deploy do `painel_gestor/`:

- [ ] `src/pages/Estoque.tsx` **(NOVO)**
- [ ] `src/App.tsx`, `src/api/client.ts`, `src/types.ts`
- [ ] `src/pages/Dashboard.tsx`, `src/pages/Clientes.tsx`

### Testes pós-deploy

| O quê | Como testar |
|-------|-------------|
| Histórico filtros | `/vendas/historico/` → meio de liquidação + tipo lançamento + total rodapé |
| Retomar venda | `/vendas/retomar/<id>/` → agregar mesmo produto (sem "undefined") |
| Balcão com cliente | Admin → Loja → **Trabalha com entregas** desmarcado → PDV com cliente → status venda na loja |
| Impressão auto | Admin → **Impressão automática** → finalizar venda → nota 80mm Elgin i8 |
| Estoque gestor | App gestor → `/estoque` → lista completa via `GET /api/gestor/estoque/` |

### Configurações no Admin

Em **Lojas** → editar loja:

- **Trabalha com entregas** — desmarque para vendas PDV com cliente ficarem como balcão (sem entrega)
- **Impressão automática ao finalizar venda** — imprime nota ao finalizar no PDV

---

## Deploy anterior — melhorias PDV + central de logs (migration `0043`)

> Inclui: estoque baixo (3 itens), login, torre com select de entregador, fidelidade no PDV, cortesia, excluir transação, venda completa, `/central_logs/`, etc.

### Migrations (obrigatório — ordem)

Subir **todas** antes de `migrate`. Se alguma faltar, o migrate quebra:

| Ordem | Arquivo |
|-------|---------|
| 1 | `app_pdv/migrations/0041_parcela_fiado_agendada.py` |
| 2 | `app_pdv/migrations/0042_seguranca_login.py` |
| 3 | `app_pdv/migrations/0043_melhorias_pdv_logs.py` |

### Backend — novos

- [ ] `app_pdv/audit_log.py`

### Backend — alterados

- [ ] `app_pdv/models.py`
- [ ] `app_pdv/views.py`
- [ ] `app_pdv/urls.py`
- [ ] `app_pdv/admin.py`
- [ ] `app_pdv/forms.py`
- [ ] `app_pdv/fidelidade_service.py`

### Templates — alterados / novos

- [ ] `templates/base.html`
- [ ] `templates/registration/login.html`
- [ ] `templates/app_pdv/vendas.html`
- [ ] `templates/app_pdv/detalhes_venda.html`
- [ ] `templates/app_pdv/torre_controle.html`
- [ ] `templates/app_pdv/config_fidelidade.html`
- [ ] `templates/app_pdv/relatorios.html`
- [ ] `templates/app_pdv/central_logs.html` **(NOVO)**

### Console após upload

```bash
cd ~/Aplicativo-Delivery-SaaS
workon venv
python manage.py migrate
python manage.py check
```

Web → **Reload**

### Testes pós-deploy

| O quê | Como testar |
|-------|-------------|
| Login centralizado | `/accounts/login/` — mensagens só no card |
| PDV cortesia | `/vendas/nova/` → Tipo Lançamento **Cortesia** |
| Fidelidade | `/config/fidelidade/` — painel de clientes |
| Torre + motoboy | Loja com **Monitorar Entrega** desmarcado no Admin → `/torre-controle/` → select ao liberar rota |
| Central de logs | `/central_logs/` (rota oculta, não aparece no menu) |
| Excluir transação | `/relatorios/?tipo_relatorio=financeiro` → ícone lixeira |
| Venda completa | Admin → Loja → **Permitir venda completa** → PDV checkbox no produto cheio |

### Configurações no Admin (após deploy)

Em **Lojas** → editar loja:

- **Monitorar Entrega** — desmarque para usar select manual de entregador na Torre
- **Permitir venda completa** — habilita checkbox no PDV (gás + vasilhame)
- **Fidelidade** — `fidelidade_ativa`, meta, desconto %

Abra o PDV uma vez (`/vendas/nova/`) para criar a forma de pagamento **Cortesia** nas lojas existentes.

---

## Deploy anterior — segurança de login (migration `0042`)

> Se o servidor **já tem** a `0042` aplicada, pule os arquivos que já subiu. Caso contrário, suba junto com a seção acima.

### Arquivos novos

- [ ] `app_pdv/seguranca.py`
- [ ] `app_pdv/backends.py`
- [ ] `app_pdv/authentication.py`
- [ ] `app_pdv/signals.py`
- [ ] `app_pdv/views_seguranca.py`

### Arquivos alterados

- [ ] `app_pdv/apps.py`
- [ ] `app_pdv/middleware.py`
- [ ] `app_pdv/gestor_views.py`
- [ ] `setup/settings.py`
- [ ] `setup/urls.py`

### Comportamento

| Recurso | Detalhe |
|---------|---------|
| Rate limit IP | 5 logins errados → IP bloqueado 15 min |
| Conta congelada | 10 erros → desbloqueio via Admin |
| Sessão única | Web + API token (superusuário isento) |
| Desbloqueio IP | Admin → **Bloqueios de IP (login)** |

---

## Deploy anterior — Painel Gestor (API)

- [ ] `app_pdv/gestor_api.py`
- [ ] `app_pdv/gestor_views.py`
- [ ] `app_pdv/urls.py`
- [ ] `app_pdv/views.py`

Teste: `POST /api/login/` e `GET /api/gestor/resumo/` com Token.

---

## Migrations antigas (só se o servidor nunca recebeu)

Se `python manage.py showmigrations app_pdv` mostrar `[ ]` em alguma delas, suba o arquivo antes do `migrate`:

- `app_pdv/migrations/0037_pagamento_dividido_liquidacaovenda.py`
- `app_pdv/migrations/0038_venda_vasilhame_vazio.py`
- `app_pdv/migrations/0039_loja_estoque_diario_log_fechamento.py`
- `app_pdv/migrations/0040_rename_app_pdv_log_loja_dat_tipo_idx_app_pdv_log_loja_id_ce16db_idx_and_more.py`

---

## Verificar migrations no console

```bash
cd ~/Aplicativo-Delivery-SaaS
workon venv
python manage.py showmigrations app_pdv | tail -10
```

Esperado (últimas linhas com `[X]`):

```
[X] 0041_parcela_fiado_agendada
[X] 0042_seguranca_login
[X] 0043_melhorias_pdv_logs
[X] 0044_produto_usa_venda_completa
[X] 0045_loja_entregas_impressao
[X] 0046_taxa_servico
[X] 0047_grupos_avaria
[X] 0048_produto_kit
[X] 0049_codigo_barras
```

---

## Erros comuns

### `NodeNotFoundError: 0042 depende de 0041 (ausente)`

**Causa:** `0041` não foi enviada ao servidor.  
**Correção:** subir `0041_parcela_fiado_agendada.py` → `migrate` → Reload.

### `ImportError: cannot import name 'produto_baixa_apenas_vasilhame_vazio'`

**Causa:** `views.py` novo com `models.py` antigo.  
**Correção:** subir `app_pdv/models.py` → Reload.

### Site sobe, mas PDV dá erro ao salvar venda

**Causa:** migration `0043` não aplicada.  
**Correção:** subir `0043_melhorias_pdv_logs.py` → `migrate` → Reload.

### Importação rápida no console

```bash
python -c "from app_pdv.models import LogAuditoria, produto_baixa_apenas_vasilhame_vazio; print('OK')"
python -c "from app_pdv.audit_log import registrar_log; print('OK')"
```

---

## PythonAnywhere — IP real do cliente

O bloqueio por IP usa `HTTP_X_FORWARDED_FOR` ou `REMOTE_ADDR`.

### Settings (já no projeto — não remover)

Em `setup/settings.py`:

```python
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True
```

### Desbloquear IP bloqueado

1. Admin → **Bloqueios de IP (login)**
2. Marque o IP → ação **Liberar IP imediatamente**

### Descongelar usuário

1. Admin → **Usuários** → editar perfil
2. Desmarque **Conta congelada** → salvar

### Teste rate limit (opcional)

```bash
curl -X POST https://preapdev.pythonanywhere.com/api/login/ \
  -d "username=SEU_USER&password=SENHA_ERRADA"
# Repita 5x — a 6ª deve retornar HTTP 429
```

---

## Resumo — lista única para copiar (deploy completo atual)

```
app_pdv/audit_log.py                          (NOVO)
app_pdv/seguranca.py                          (NOVO — se ainda não subiu)
app_pdv/backends.py                           (NOVO — se ainda não subiu)
app_pdv/authentication.py                     (NOVO — se ainda não subiu)
app_pdv/signals.py                            (NOVO — se ainda não subiu)
app_pdv/views_seguranca.py                    (NOVO — se ainda não subiu)
app_pdv/models.py
app_pdv/views.py
app_pdv/urls.py
app_pdv/admin.py
app_pdv/forms.py
app_pdv/fidelidade_service.py
app_pdv/apps.py                               (se segurança ainda não subiu)
app_pdv/middleware.py                         (se segurança ainda não subiu)
app_pdv/gestor_views.py                       (se gestor ainda não subiu)
app_pdv/migrations/0041_parcela_fiado_agendada.py
app_pdv/migrations/0042_seguranca_login.py
app_pdv/migrations/0043_melhorias_pdv_logs.py
setup/settings.py                             (se segurança ainda não subiu)
setup/urls.py                                 (se segurança ainda não subiu)
templates/base.html
templates/registration/login.html
templates/app_pdv/vendas.html
templates/app_pdv/detalhes_venda.html
templates/app_pdv/torre_controle.html
templates/app_pdv/config_fidelidade.html
templates/app_pdv/relatorios.html
templates/app_pdv/central_logs.html           (NOVO)
```

Depois: `migrate` → `check` → **Reload**.
