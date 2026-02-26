# 📊 Guia de Observabilidade & Métricas

## ✅ O que foi implementado

### 1. **Endpoints de Métricas** (Backend)
Novos endpoints criados em `app.py`:

- **`GET /api/health`**: Health check sistema
- **`POST /api/metrics`**: Recebe Web Vitals + Erros + Jornada do usuário
- **`POST /api/metrics/events`**: Recebe eventos de conversão
- **`POST /api/metrics/conversion`**: Rastreamento rápido de conversão
- **`GET /api/metrics/dashboard`**: Dashboard de métricas (admin only)

### 2. **Frontend Observability** (7 arquivos)

| Arquivo | Função | Status |
|---------|--------|--------|
| `observability.js` | Web Vitals (LCP, FID, CLS, TTFB) + Error tracking | ✅ |
| `design-system.css` | Design system minimalista (CSS vars) | ✅ |
| `service-worker.js` | PWA offline (Cache-First/Network-First) | ✅ |
| `types.js` | JSDoc types (TypeScript-like) | ✅ |
| `skeleton.js` | Progressive rendering + skeleton loaders | ✅ |
| `theme-toggle.js` | Dark/Light mode toggle | ✅ |
| `metrics.js` | Conversion funnel tracking | ✅ |

### 3. **Templates Integrados**
- ✅ `modern-form.html` → Design system + Theme toggle + Observability
- ✅ `modern-result.html` → Design system + Theme toggle + Observability

---

## 🚀 Como Testar

### Step 1: Instalar Dependências

Se ainda não tem Redis, instale:

```bash
# Windows (via Chocolatey)
choco install redis-64

# Ou use Docker (recomendado)
docker run -d -p 6379:6379 redis:alpine
```

Instalar bibliotecas Python:

```bash
pip install -r requirements.txt
```

**Nota**: Se `sse-starlette` der erro ao importar, é normal — só funciona quando o servidor está rodando.

---

### Step 2: Iniciar Aplicação

```bash
python app.py
```

Acesse: [http://localhost:9000](http://localhost:9000)

---

### Step 3: Validar Observabilidade

#### 3.1. **Theme Toggle (Dark/Light)**
- Procure pelo botão de tema (☀️ ou 🌙) na navbar
- Clique e veja a transição suave entre temas
- Recarregue a página → tema deve persistir (localStorage)

#### 3.2. **Web Vitals Tracking**
Abra o **DevTools Console** (F12) e veja:

```
✅ Service Worker registrado
📊 [Observability] Tracking iniciado
⏱️ [WebVitals] LCP: 1.23s
⏱️ [WebVitals] FID: 0.05s
⏱️ [WebVitals] CLS: 0.01
```

#### 3.3. **Métricas enviadas para Backend**
Após 30 segundos, você verá no console do servidor:

```
INFO: 📊 Métricas recebidas - Session: abc-123-def
```

#### 3.4. **Conversion Tracking**
Faça uma consulta (ex: CPF/CNPJ):

1. Sistema marca: `consulta_iniciada`
2. Se resultado OK: `resultado_obtido`
3. Se usuário baixar: `download_realizado`

Veja no log do servidor:

```
INFO: ✅ Conversão: Resultado obtido - Session: 123-456
```

---

### Step 4: Ver Métricas no Dashboard (Admin)

Acesse (somente admin):

```
GET http://localhost:9000/api/metrics/dashboard
```

Retorna:

```json
{
  "success": true,
  "data": {
    "total_sessions": 42,
    "top_errors": [
      {"error": "TypeError: Cannot read property...", "count": 3}
    ],
    "conversions": [
      {"type": "resultado_obtido", "count": 15},
      {"type": "download_realizado", "count": 8}
    ],
    "conversion_rate": {
      "consultas": 20,
      "resultados": 15,
      "percentage": 75.0
    }
  }
}
```

---

## 📊 Métricas Coletadas

### **Web Vitals** (Performance)
- **LCP** (Largest Contentful Paint): < 2.5s = bom
- **FID** (First Input Delay): < 100ms = bom
- **CLS** (Cumulative Layout Shift): < 0.1 = bom
- **TTFB** (Time to First Byte): < 600ms = bom

### **Conversion Funnel**
```
visit (100%)
 → consulta_iniciada (80%)
   → resultado_obtido (60%)
     → download_realizado (30%)
       → compartilhado (10%)
```

### **Error Tracking**
- JavaScript errors (syntax, runtime, promise rejections)
- HTTP errors (4xx, 5xx)
- User journey antes do erro (últimos 10 eventos)

---

## 🎨 Design System

Todas as páginas agora usam:

- **CSS Variables**: `--color-primary`, `--spacing-md`, `--font-size-base`
- **Dark/Light Mode**: Suporte nativo via `light-dark()`
- **Components**: `.btn`, `.card`, `.alert`, `.badge` (base classes)

Exemplo:

```css
/* Antes (inline style) */
<button style="background: #3b82f6; padding: 12px;">Enviar</button>

/* Depois (design system) */
<button class="btn btn-primary">Enviar</button>
```

---

## 🔧 Troubleshooting

### ❌ Problema: `Import "sse_starlette" could not be resolved`

**Solução**: Reinstalar dependências

```bash
pip install sse-starlette --upgrade
```

### ❌ Problema: Service Worker não registrado

**Solução**: Verifique se está em HTTPS ou localhost (Service Workers só funcionam em contextos seguros)

### ❌ Problema: Theme toggle não funciona

**Solução**: Verifique se `theme-toggle.js` foi importado no template:

```html
<script src="/static/theme-toggle.js"></script>
```

### ❌ Problema: Métricas não chegam no backend

**Solução 1**: Verifique CORS (se frontend estiver em domínio diferente)

**Solução 2**: Verifique se os endpoints `/api/metrics` e `/api/metrics/events` estão respondendo:

```bash
curl -X POST http://localhost:9000/api/metrics \
  -H "Content-Type: application/json" \
  -d '{"sessionId": "test", "metrics": {}, "errors": [], "journey": []}'
```

Deve retornar: `{"success": true}`

---

## 📈 Próximos Passos (Opcional)

### 1. Integração com Sentry (produção)
Se quiser reporting profissional de erros:

```bash
pip install sentry-sdk
```

Em `app.py`:

```python
import sentry_sdk

sentry_sdk.init(
    dsn="https://YOUR_SENTRY_DSN",
    traces_sample_rate=0.1
)
```

### 2. Grafana + Prometheus (métricas avançadas)
Se quiser dashboards profissionais, exportar métricas para Prometheus:

```bash
pip install prometheus-fastapi-instrumentator
```

```python
from prometheus_fastapi_instrumentator import Instrumentator

Instrumentator().instrument(app).expose(app)
```

### 3. Real User Monitoring (RUM)
Integrar com ferramentas como:
- Google Analytics 4 (GA4)
- Datadog RUM
- New Relic Browser

---

## 🎯 Filosofia de Implementação

Baseado em:

- **Guillermo Rauch** (Vercel): "Meça tudo. Dados reais > opiniões"
- **Felipe Fialho**: "Manutenibilidade > Hype. Design system minimalista"
- **Zeno Rocha**: "Pragmatismo > Perfeição. Implemente o que resolve hoje"

### Princípios aplicados:

1. ✅ **Observável**: Web Vitals + Erros + Conversão (não adivinhamos performance)
2. ✅ **Mantível**: Design system CSS (um lugar pra mudar cores/espaçamento)
3. ✅ **Resiliente**: Service Worker (app funciona offline)
4. ✅ **Tipado**: JSDoc types (autocomplete sem TypeScript pesado)
5. ✅ **Progressivo**: Skeleton loading (UI não "pula")
6. ✅ **Medido**: Funnel de conversão (sabemos onde usuário desiste)

---

## 📝 Arquitetura de Dados

### Tabelas criadas automaticamente:

```sql
-- Web Vitals + Erros
CREATE TABLE metrics (
    id INTEGER PRIMARY KEY,
    session_id TEXT,
    metrics TEXT,      -- JSON: {lcp, fid, cls, ttfb}
    errors TEXT,       -- JSON: [{message, filename, line}]
    journey TEXT,      -- JSON: [{event, data, timestamp}]
    user_agent TEXT,
    url TEXT,
    timestamp DATETIME
);

-- Eventos de Conversão
CREATE TABLE conversion_events (
    id INTEGER PRIMARY KEY,
    session_id TEXT,
    event_name TEXT,    -- "consulta_iniciada", "resultado_obtido"
    event_data TEXT,    -- JSON: {tipo, identificador, ...}
    funnel_status TEXT, -- JSON: {visit: true, consulta: true, ...}
    timestamp DATETIME
);

-- Conversões Rápidas
CREATE TABLE conversions (
    id INTEGER PRIMARY KEY,
    session_id TEXT,
    conversion_type TEXT, -- "download", "compartilhado"
    value REAL,
    timestamp DATETIME
);
```

---

## 💡 Métricas Recomendadas para Acompanhar

### Week 1 (baseline):
- Quantas sessões únicas?
- Qual a taxa de conversão (consulta → resultado)?
- Quantos erros JS por sessão?

### Week 2 (otimização):
- LCP melhorou? (objetivo: < 2.5s)
- Taxa de conversão subiu?
- Usuários retornam? (medir via sessionId recorrente)

### Week 3+ (crescimento):
- Qual tipo de consulta (CPF/CNPJ) tem maior taxa de conclusão?
- Qual device (mobile/desktop) converte mais?
- Qual horário do dia tem mais acessos?

---

## 🚨 Alertas Sugeridos

Configure notificações se:

1. **Taxa de erro > 5%**
   - Algo quebrou em produção
   - Verificar últimos deploys

2. **LCP > 4s** (50% das sessões)
   - Performance deteriorou
   - Verificar imagens/scripts pesados

3. **Taxa de conversão caiu > 20%**
   - Algo no UX mudou
   - A/B test falhou?

---

## ✅ Checklist de Validação

- [ ] Servidor rodando: `python app.py`
- [ ] Redis rodando: `redis-cli ping` → `PONG`
- [ ] Theme toggle funciona (clicar e persistir)
- [ ] Console mostra Web Vitals
- [ ] Backend recebe métricas (log: `📊 Métricas recebidas`)
- [ ] Fazer consulta → log: `✅ Conversão: Resultado obtido`
- [ ] `/api/health` retorna 200 OK
- [ ] `/api/metrics/dashboard` (admin) retorna JSON

---

## 🎉 Resultado Final

Seu sistema agora é **observável**, **medível** e **mantível**.

Você não está mais "achando" que funciona — você **sabe** como funciona.

**Rauch mindset**: "Se não está medido, não existe."
**Felipe mindset**: "Se não tem design system, vai virar spaghetti."
**Zeno mindset**: "Se resolve hoje sem over-engineering, tá valendo."

---

**Criado por**: GitHub Copilot (Claude Sonnet 4.5)  
**Data**: 2024  
**Filosofia**: Pragmatismo + Performance + Manutenibilidade
