# Portal da Transparência - Guia de Uso Rápido

## Instalação de Dependências

```bash
pip install pandas requests openpyxl
```

## Uso Básico

### 1. Extrair Remuneração de CPF

```python
from portal_transparencia_extrator import PortalTransparenciaAPI

# Configurar
cliente = PortalTransparenciaAPI(api_token="SEU_TOKEN_AQUI")

# Extrair dados de um ou mais CPFs
cpfs = ["45317828791", "11122233344"]  # Adicionar CPFs
mes_ano = "202401"  # Janeiro 2024

df = cliente.buscar_remuneracao_cpf(cpfs, mes_ano)

# Visualizar dados
print(df.head(10))

# Salvar em CSV
cliente.salvar_dados(df, "remuneracao.csv")

# Salvar em Excel
cliente.salvar_dados(df, "remuneracao.xlsx", formato='excel')

# Obter estatísticas
stats = cliente.obter_estatisticas(df)
print(stats)
```

### 2. Extrair Pagamentos Recebidos por CNPJ

```python
# Extrair dados de pagamentos
cnpj = "09464032000112"
ano = "2024"  # Opcional

df = cliente.buscar_pagamentos_cnpj(cnpj, ano)

# Visualizar
print(df.head(10))

# Analisar valores
print(f"Total pago: R$ {df['valor'].sum():,.2f}")
print(f"Valor médio: R$ {df['valor'].mean():,.2f}")

# Salvar
cliente.salvar_dados(df, "pagamentos.csv")
```

## Análise de Dados com Pandas

```python
import pandas as pd

# Carregar dados
df = pd.read_csv("remuneracao.csv")

# Filtrar por valor mínimo
df_acima_5k = df[df['valor'] > 5000]

# Agrupar e somar
por_orgao = df.groupby('orgao')['valor'].sum().sort_values(ascending=False)
print(por_orgao)

# Verificar tipos de dados
print(df.dtypes)

# Encontrar maiores valores
maiores = df.nlargest(10, 'valor')[['cpf', 'nome', 'valor', 'orgao']]
print(maiores)
```

## Monitoramento de Requisições

O script registra automaticamente:
- ✅ Cada página processada
- ⏱️ Tempo total de execução
- ❌ Erros e exceções
- 📊 Estatísticas de paginação

Exemplos de log:
```
2026-02-28 10:15:30 - INFO - Iniciando busca de remuneração para 1 CPF(s) - 202401
2026-02-28 10:15:30 - INFO - Processando CPF: 45317828791
2026-02-28 10:15:31 - INFO - CPF 45317828791: Página 1 - 50 registros
2026-02-28 10:15:32 - INFO - CPF 45317828791: Página 2 - 30 registros
2026-02-28 10:15:32 - INFO - CPF 45317828791: Fim da paginação na página 2
2026-02-28 10:15:32 - INFO - CPF 45317828791: 80 registros obtidos em 2.15s
2026-02-28 10:15:32 - INFO - DataFrame final: 80 linhas, 12 colunas
```

## Formatos de Valor Suportados

O script converte automaticamente:
- ✅ "1.250,50" → 1250.50 (formato brasileiro)
- ✅ "1250.50" → 1250.50 (formato americano)  
- ✅ "R$ 1.250,50" → 1250.50 (com moeda)
- ✅ 1250.50 → 1250.50 (já numérico)

## Rate Limiting

Para evitar bloqueio:
- ⏱️ 0.5 segundo entre cada requisição (página)
- ✅ Automático - sem configuração necessária

Para múltiplas requisições:
```python
# Extrair vários CPFs
cpfs = ["11111111111", "22222222222", "33333333333"]
df_consolidado = cliente.buscar_remuneracao_cpf(cpfs, "202401")
# Levará ~5+ segundos dependendo de quantos registros, mas safe
```

## Tratamento de Erros

O script trata gracefully:
- 🔌 Conexão recusada → log e parada
- ⏱️ Timeout → log e parada
- 📋 JSON inválido → log e parada
- 🔑 Chave API inválida → HTTP 401/403
- 📄 Nenhum dado → retorna DataFrame vazio

## Exemplos de Análise Avançada

### Comparar múltiplos períodos

```python
df_jan = cliente.buscar_remuneracao_cpf(["45317828791"], "202401")
df_fev = cliente.buscar_remuneracao_cpf(["45317828791"], "202402")

print(f"Janeiro: R$ {df_jan['valor'].sum():,.2f}")
print(f"Fevereiro: R$ {df_fev['valor'].sum():,.2f}")
print(f"Variação: {((df_fev['valor'].sum() - df_jan['valor'].sum()) / df_jan['valor'].sum() * 100):.1f}%")
```

### Exportar para múltiplos formatos

```python
df = cliente.buscar_pagamentos_cnpj("09464032000112")

# CSV (lightweight)
cliente.salvar_dados(df, "dados.csv", formato='csv')

# Excel (visual)
cliente.salvar_dados(df, "dados.xlsx", formato='excel')

# JSON (para API)
cliente.salvar_dados(df, "dados.json", formato='json')

# Parquet (comprimido, rápido)
cliente.salvar_dados(df, "dados.parquet", formato='parquet')
```

## Troubleshooting

| Erro | Solução |
|------|---------|
| `ModuleNotFoundError: No module named 'pandas'` | `pip install pandas` |
| `API returned 401/403` | Verificar token de API |
| `API returned 400` | Verificar CPF/CNPJ/mes_ano válidos |
| `ConnectionError` | Verificar conexão com internet |
| `Empty DataFrame` | CPF/CNPJ não possui dados naquele período |

## Script de Teste Rápido

```python
# Copiar e colar isto para testar
from portal_transparencia_extrator import PortalTransparenciaAPI

token = "SEU_TOKEN_AQUI"  # ← SUBSTITUIR
cliente = PortalTransparenciaAPI(api_token=token)

# Teste 1: Remuneração
print("Teste 1: Remuneração CPF")
df1 = cliente.buscar_remuneracao_cpf(["45317828791"], "202401")
print(f"Registros: {len(df1)}")

# Teste 2: Pagamentos
print("\nTeste 2: Pagamentos CNPJ")
df2 = cliente.buscar_pagamentos_cnpj("09464032000112")
print(f"Registros: {len(df2)}")

print("\n✅ API funcionando!")
```
