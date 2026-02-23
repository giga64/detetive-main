# 🎯 GUIA RÁPIDO - OneSeek

## 🚀 Início Rápido

### Login Padrão
- **Usuário**: `admin`
- **Senha**: `admin123`
- ⚠️ Altere após primeiro acesso!

### Funcionalidades Principais

#### 🔍 Tipos de Busca
- **CPF** - Dados pessoais e relacionados
- **CNPJ** - Informações empresariais
- **Placa** - Dados veiculares
- **Nome** - Busca por nome completo
- **OAB** - Ficha completa com imagem (3-5s)

#### 📊 Dashboard
- Total de consultas (geral, hoje, semana, mês)
- Horário de pico
- Total de favoritos
- Acesso rápido ao histórico

#### 📝 Histórico
- Filtros de busca por texto e período
- Favoritos (⭐) para consultas importantes
- Notas (📝) para comentários
- Tags (🏷️) para organização
- Exportação CSV/JSON

#### 👥 Admin (Apenas)
- Dashboard de administração
- Gerenciar usuários (criar/editar/deletar)
- Ver logs de auditoria
- Relatórios mensais
- Backup do banco de dados
- Health check do sistema

---

## ⚡ Comandos Úteis

### Desenvolvimento Local
```bash
# Instalar dependências
pip install -r requirements.txt

# Gerar sessão Telegram
python generate_session.py

# Iniciar servidor
uvicorn app:app --reload
```

### Deploy Railway
```bash
# Fazer commit e push
git add .
git commit -m "update: descrição"
git push
```

---

## 🔐 Variáveis de Ambiente

| Variável | Descrição |
|----------|-----------|
| `TELEGRAM_API_ID` | ID da API Telegram |
| `TELEGRAM_API_HASH` | Hash da API Telegram |
| `TELEGRAM_GROUP_ID` | ID do grupo Telegram |
| `STRING_SESSION` | Sessão Telegram (gerar com `generate_session.py`) |
| `ENABLE_OAB_OCR` | `true` para mostrar imagem OAB completa |

---

## 🎨 Atalhos de Teclado

- **ESC** - Fechar modals/dropdowns
- **Ctrl+K** - Focar campo de busca

---

## 🐛 Problemas Comuns

**Erro: "Sessão Telegram não autorizada"**
→ Regenere a STRING_SESSION com `generate_session.py`

**Busca OAB muito lenta**
→ Timeout padrão é 20s. Verifique conexão com internet.

**Imagem OAB não aparece**
→ Verifique se `ENABLE_OAB_OCR=true` está configurado

---

## 📚 Documentação Adicional

- [README.md](README.md) - Documentação completa
- [TELEGRAM-CONFIG.md](TELEGRAM-CONFIG.md) - Configuração Telegram
- [SEGURANCA.md](SEGURANCA.md) - Políticas de segurança

---

**Sistema OneSeek** - Investigações Digitais 🔍
