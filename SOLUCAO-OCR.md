# 🔧 Solução para Problema de Travamento com OCR

## 📋 Problema Identificado

O site estava travando (ficando "girando") na segunda pesquisa de OAB porque:

1. **EasyOCR baixa modelos gigantes** (centenas de MB) na primeira execução
2. **Download bloqueava todo o servidor** (execução síncrona)
3. **Timeout não configurado** - podia demorar minutos
4. **Sem fallback adequado** se OCR falhasse

## ✅ Correções Implementadas

### 1. **Cache Global do Modelo EasyOCR** 
```python
# Evita recarregar modelo a cada consulta
_OCR_READER = None  # singleton cached
```

### 2. **Execução Assíncrona com Thread Pool**
```python
# Não bloqueia mais o servidor
resultado = await loop.run_in_executor(
    executor,  # thread pool
    buscar_dados_completos_oab_com_ocr,
    ...
)
```

### 3. **Timeout de 60 segundos**
```python
# Evita espera infinita
resultado = await asyncio.wait_for(..., timeout=60.0)
```

### 4. **Fallback Automático**
```python
# Se OCR falhar, usa API simples
except (asyncio.TimeoutError, Exception):
    return await buscar_oab_api_simples(...)
```

### 5. **Variável de Ambiente para Desabilitar OCR**
```python
ENABLE_OAB_OCR=false  # desabilita OCR completamente
```

## 🚀 Configuração no Railway

### **Opção 1: Desabilitar OCR (RECOMENDADO para início)**

No Railway → Variables, adicione:
```
ENABLE_OAB_OCR=false
```

**Vantagens:**
- ✅ Deploy rápido (sem download de modelos)
- ✅ Menor uso de memória/CPU
- ✅ Resposta mais rápida
- ⚠️ Menos campos retornados (nome, inscrição, seccional apenas)

### **Opção 2: Manter OCR Ativado**

Se quiser usar OCR (mais campos extraídos):

1. **Primeiro deploy COM OCR desabilitado:**
   ```
   ENABLE_OAB_OCR=false
   ```

2. **Depois que estiver funcionando, habilite:**
   ```
   ENABLE_OAB_OCR=true
   ```

3. **Aguarde primeira consulta OAB baixar modelos** (pode levar 5-10 min)
   - Acompanhe nos logs: "🔄 Inicializando EasyOCR"
   - Quando ver: "✅ EasyOCR inicializado com sucesso!"
   - Modelo fica em cache, consultas seguintes são rápidas

**Vantagens:**
- ✅ Mais dados extraídos (endereço, telefone, CEP, subseção)
- ⚠️ Primeira consulta demora (download)
- ⚠️ Usa mais memória RAM (~500MB extra)

## 📊 Comparação de Campos Retornados

| Campo | API Simples | OCR Completo |
|-------|-------------|--------------|
| Nome | ✅ | ✅ |
| Inscrição | ✅ | ✅ |
| Seccional (UF) | ✅ | ✅ |
| Tipo | ✅ | ✅ |
| Subseção | ❌ | ✅ |
| Endereço | ❌ | ✅ |
| Telefone | ❌ | ✅ |
| CEP | ❌ | ✅ |

## 🔍 Monitoramento

Verifique os logs no Railway:

```bash
# OCR Desabilitado
⚠️ OCR desabilitado via ENABLE_OAB_OCR - usando API simples
🔍 Buscando OAB (modo simples): 5553/RN

# OCR Ativado - Primeira Vez
🔍 Buscando OAB completa com OCR: 5553/RN
🔄 Inicializando EasyOCR (primeira vez)...
Downloading detection model...
Progress: |██████| 100% Complete
✅ EasyOCR inicializado com sucesso!

# OCR Ativado - Consultas Seguintes
🔍 Buscando OAB completa com OCR: 5553/RN
✅ Busca concluída com sucesso!

# Timeout/Erro - Fallback Automático
⏱️ Timeout na busca com OCR (60s) - usando fallback
🔍 Buscando OAB (modo simples): 5553/RN
```

## 🎯 Recomendação

**Para produção imediata:**
1. Adicione `ENABLE_OAB_OCR=false` nas variáveis do Railway
2. Faça redeploy
3. Sistema vai funcionar normalmente (sem OCR)

**Para testar OCR depois:**
1. Mude para `ENABLE_OAB_OCR=true`
2. Faça uma consulta OAB em horário de baixo uso
3. Aguarde download completar (5-10 minutos)
4. Consultas seguintes serão rápidas

## 📝 Arquivos Modificados

- ✅ `oab_ocr.py` - Cache do modelo EasyOCR
- ✅ `app.py` - Execução assíncrona + timeout + fallback
- ✅ Variável `ENABLE_OAB_OCR` adicionada

## 🆘 Troubleshooting

### "Site continua travando"
Verifique se `ENABLE_OAB_OCR=false` está configurado no Railway

### "Download não completa"
- Aumente timeout: Railway pode ter limit de memória/CPU
- Recomendação: use `ENABLE_OAB_OCR=false` 

### "Quero mais campos mas sem travar"
OCR funciona bem **após** primeiro download. Se travar:
1. Desabilite temporariamente
2. Upgrade do plano Railway (mais RAM)
3. Habilite OCR novamente
