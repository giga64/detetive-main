# 🚨 AÇÃO IMEDIATA - Railway Travando

## ⚡ Solução Rápida (5 minutos)

### **Passo 1: Desabilitar OCR**
1. Acesse seu projeto no Railway
2. Vá em **Variables**
3. Adicione nova variável:
   ```
   ENABLE_OAB_OCR=false
   ```
4. Clique em **Add**

### **Passo 2: Redeploy**
1. Vá na aba **Deployments**  
2. Clique nos 3 pontos (...) no deployment atual
3. Clique **Redeploy**
4. Aguarde o deploy completar

### **Passo 3: Testar**
1. Acesse o site
2. Faça login
3. Teste uma consulta OAB
4. **Deve funcionar normalmente agora!** ✅

---

## ⚙️ O Que Foi Feito

As correções já foram implementadas no código:

✅ **OCR executa em thread separada** (não trava mais)  
✅ **Timeout de 60 segundos** (evita espera infinita)  
✅ **Fallback automático** se OCR falhar  
✅ **Cache de modelos** (após download, fica rápido)  
✅ **Controle via variável** `ENABLE_OAB_OCR`  

---

## 📊 Diferença Com/Sem OCR

### **Sem OCR** (ENABLE_OAB_OCR=false)
- ⚡ Respostas rápidas (1-3 segundos)
- 💾 Menor uso de memória
- ✅ Campos retornados: Nome, Inscrição, Seccional, Tipo

### **Com OCR** (ENABLE_OAB_OCR=true)
- 🐢 Primeira consulta lenta (5-10 min para download)
- ⚡ Consultas seguintes rápidas
- 💾 Usa ~500MB RAM extra
- ✅ Campos extras: Endereço, Telefone, CEP, Subseção

---

## 🎯 Recomendação

**AGORA:**  
Use `ENABLE_OAB_OCR=false` para site voltar a funcionar

**DEPOIS (Opcional):**  
Se quiser endereço/telefone:
1. Em horário de baixo uso
2. Mude para `ENABLE_OAB_OCR=true`
3. Faça uma consulta OAB
4. Aguarde download (veja logs)
5. Pronto! Consultas seguintes serão rápidas

---

## 📝 Logs para Monitorar

Após configurar, monitore os logs no Railway:

✅ **Funcionando Corretamente:**
```
Configuração Telegram:
   OCR OAB: DESATIVADO
⚠️ OCR desabilitado via ENABLE_OAB_OCR - usando API simples
🔍 Buscando OAB (modo simples): 5553/RN
✅ Token obtido
```

❌ **Se ainda ver download:**
```
Downloading detection model...
Progress: |--| 2% Complete
```
→ Verifique se adicionou `ENABLE_OAB_OCR=false` corretamente

---

## 💡 Dica

O código agora tem **fallback automático**:
- Se OCR demorar > 60s → usa API simples
- Se OCR falhar → usa API simples
- Sistema nunca mais vai travar! 🎉
