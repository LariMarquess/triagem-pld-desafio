# Triagem PLD — Desafio Técnico de Estágio em Engenharia de IA

Pipeline de triagem para Prevenção à Lavagem de Dinheiro (PLD) de um banco fictício, combinando **regras determinísticas em pandas** (cálculo) com um **LLM** (Gemini) para interpretação qualitativa e geração de pareceres.

Todos os dados usados são fictícios, gerados para fins de avaliação.

## Status da entrega

| Nível | Status |
|---|---|
| **Nível 1 — Dados e primeira análise com LLM** | ✅ Completo (Partes A e B) |
| **Nível 2 — Escala, ferramentas e confronto** | 🟡 Parcial (Parte A — regras em escala) |
| **Nível 3 — Diferenciador** | ⬜ Não implementado |

Detalhamento completo de status por item em [`ENTREGA.yaml`](ENTREGA.yaml). Justificativas, trade-offs e o plano detalhado do que faríamos no restante do projeto estão em [`docs/DECISOES.md`](docs/DECISOES.md).

> 💡 Vale destacar a **[Seção 7 de `docs/DECISOES.md`](docs/DECISOES.md#7-visão-de-produção--além-do-escopo-deste-desafio)**: além do escopo do desafio, descrevemos como pensamos a evolução deste protótipo para um sistema de produção real — pipeline de entrada contínuo, anonimização, RAG para manter o contexto normativo (políticas internas e legislação) sempre atualizado, versionamento de configurações e prompts, observabilidade orientada a criticidade com notificação humana em tempo real, e evolução futura para um modelo próprio treinado sobre o histórico de decisões.

## O que foi feito

### Nível 1 (`nivel_1/nivel_1.ipynb`)

- Carregamento e investigação de qualidade de `dados/dados_nivel_1.json` (duplicatas, nulos, tipos) **antes** de qualquer tratamento
- Tratamento documentado: deduplicação por `id`, marcação e preenchimento de datas ausentes (`DATA_PENDENTE` + `ALERTA_DATA_AUSENTE`)
- Normalização de valores para BRL (`valor_brl`)
- Agregações: volume por cliente, contagem por canal
- **Regra 1 — Fracionamento** e **Regra 2 — Valor Atípico**, implementadas como funções tipadas, com célula de validação explícita comparando um caso que dispara contra um caso parecido que não dispara
- **Parte B:** parecer qualitativo via LLM (Gemini) para o cliente sinalizado `CLI-A-1`, com:
  - Schema Pydantic (`ParecerPLD`) com normalização de acentuação
  - Cache de respostas em disco (chave sensível a cliente, prompt, modelo e dados — evita que duas versões de prompt colidam no mesmo cache)
  - Estratégia de fallback com retry, backoff exponencial e parecer de contingência
  - Comparação A/B entre dois prompts (zero-shot vs. chain-of-thought), com tokens, latência e análise qualitativa da diferença real observada

### Nível 2 (`nivel_2/tools.py`)

- Mesma sanitização e as duas regras determinísticas do Nível 1, reescritas como funções reutilizáveis, aplicadas sobre `dados/dados_nivel_2.json` (~320 operações, 30 clientes)
- Contagem de regras distintas violadas por cliente (teto de 2)
- Top 10 clientes mais sinalizados, salvo em [`outputs/top_10_clientes_nivel2.csv`](outputs/top_10_clientes_nivel2.csv)

`nivel_2/agente.py` e `nivel_2/confronto.py` não foram implementados — ver plano detalhado em `docs/DECISOES.md`, seção 4.

## Como rodar

### Pré-requisitos

- Python 3.12+
- Uma chave de API do Gemini (gratuita em [aistudio.google.com/apikey](https://aistudio.google.com/apikey)) — necessária apenas para a Parte B do Nível 1

### Setup

```bash
python -m venv venv

# Windows
venv\Scripts\Activate.ps1
# Linux/Mac
source venv/bin/activate

pip install -r requirements.txt
python -m ipykernel install --user --name triagem-pld --display-name "Python (triagem-pld)"
```

Copie `.env.example` para `.env` e preencha `GEMINI_API_KEY` com sua chave:

```bash
cp .env.example .env
```

### Rodar o Nível 1

Abra `nivel_1/nivel_1.ipynb` no Jupyter ou VS Code, selecione o kernel **"Python (triagem-pld)"**, e rode todas as células. A Parte B faz chamadas reais à API do Gemini na primeira execução; execuções seguintes reaproveitam o cache em `.cache/` (não gastam cota nem geram custo adicional).

### Rodar o Nível 2 (Parte A)

```bash
python nivel_2/tools.py
```

Imprime o resumo do tratamento e o Top 10 no terminal, e salva o resultado em `outputs/top_10_clientes_nivel2.csv`.

## Estrutura do repositório

```
├── dados/                  # Bases originais fornecidas
├── nivel_1/nivel_1.ipynb   # Notebook completo (Partes A e B), com saídas executadas
├── nivel_2/
│   ├── tools.py             # Sanitização, regras e Top 10 (Parte A) — implementado
│   ├── agente.py            # Não implementado — ver docs/DECISOES.md
│   └── confronto.py         # Não implementado — ver docs/DECISOES.md
├── outputs/                 # Resultados persistidos (Top 10 do Nível 2)
└── docs/
    ├── DECISOES.md          # Trade-offs, limitações, plano detalhado e visão de produção
    └── USO_DE_IA.md         # Transparência sobre uso de Claude e Claude Code no desenvolvimento
```

## Modelo e provedor usados

`gemini-3.6-flash` via Google AI Studio. O modelo originalmente planejado (`gemini-2.0-flash`) foi descontinuado durante o desenvolvimento — ver `docs/DECISOES.md`, seção 3.1, para o raciocínio completo da migração.