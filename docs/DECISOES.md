# Decisões Técnicas, Trade-offs e Limitações

Este documento não repete o que o código já mostra. Ele registra **por que** certas escolhas foram feitas, contra quais alternativas, o que faríamos no restante do projeto (Seção 4) se houvesse mais tempo, e como pensamos a evolução deste protótipo para um ambiente de produção real (Seção 7).

**Nota sobre escopo entregue:** dado o prazo, entregamos o Nível 1 completo (Partes A e B) e a Parte A do Nível 2 (regras em escala), ambos validados com números reais, não simulados. Preferimos essa entrega sólida e verificável a um Nível 2/3 implementados pela metade e não testados — na linha do que o próprio enunciado do desafio recomenda.

---

## 1. Trade-offs de arquitetura

### 1.1 Não usar `nivel_2/utils.py`

O enunciado especifica exatamente três arquivos em `nivel_2/`: `tools.py`, `agente.py`, `confronto.py`, e trata desvios de estrutura como fator que "atrasa a correção e perde pontos". Numa primeira versão do nosso planejamento técnico, propusemos um módulo `utils.py` compartilhado entre os dois níveis, para evitar duplicação de lógica.

**Decisão:** abandonamos essa ideia. Toda a lógica de sanitização e as duas regras determinísticas são escritas **inline no notebook** do Nível 1 (onde o raciocínio investigativo precisa aparecer célula a célula, com prints e decisões documentadas em markdown) e **reescritas como funções tipadas dentro de `nivel_2/tools.py`** para o Nível 2.

**Trade-off assumido:** como recusamos usar um módulo compartilhado, a lógica de dedup, tratamento de data nula, Regra 1 e Regra 2 precisa existir fisicamente em dois lugares — uma vez no notebook, outra vez em `nivel_2/tools.py` — com o mesmo comportamento, mas escrita duas vezes. Se um dia uma regra mudar, é preciso lembrar de atualizar nos dois lugares; nada garante automaticamente que eles não vão divergir por descuido. Decidimos aceitar esse risco em troca de manter a estrutura de pastas exatamente como o enunciado exige.

### 1.2 `cliente_id` como string opaca

Os dois arquivos de dados usam esquemas de ID diferentes (`CLI-A-1` no Nível 1, `CLI-001` no Nível 2). Nenhuma função do projeto faz parsing, split ou regex assumindo um formato específico — `cliente_id` é sempre comparado por igualdade de string. Validamos isso na prática: o código de `tools.py`, escrito olhando para o Nível 1, funcionou sem nenhuma adaptação ao ser aplicado ao Nível 2.

### 1.3 Nível 3 removido da estrutura de pastas

Removemos a pasta `nivel_3/` do repositório em vez de mantê-la vazia — preferimos não sinalizar uma trilha "em andamento" que não foi de fato iniciada. A trilha que teríamos escolhido, e por quê, está detalhada na Seção 5.

---

## 2. Trade-offs no tratamento de dados

### 2.1 Ordem de pipeline: deduplicar antes de aplicar regras

Confirmamos com dois casos reais (um em cada nível) que a ordem importa:
- **Nível 1:** a duplicata de `OP-0007` (cliente `CLI-A-3`) infla a soma diária desse cliente na Regra 1 se a deduplicação não acontecer antes do agrupamento.
- **Nível 2:** dos 7 valores nulos brutos em `data`, apenas 6 geraram a flag `ALERTA_DATA_AUSENTE` — o sétimo era a segunda ocorrência de uma linha duplicada (`OP-00040`, cliente `CLI-005`), removida na deduplicação antes mesmo da flag ser calculada. Isso não é um bug: é a prova, em um segundo dataset independente, de que a ordem (dedup → tratamento de nulos → regras) precisa ser essa e não outra.

### 2.2 Operações com `DATA_PENDENTE`: excluídas de um cálculo, mantidas em outro

Data nula é preenchida com o marcador `"DATA_PENDENTE"` e sinalizada com `ALERTA_DATA_AUSENTE`. A partir daí:
- **Regra 1 (Fracionamento):** operações com `DATA_PENDENTE` são **excluídas** do agrupamento diário — uma data desconhecida não pode ser comparada com outra para inferir "mesmo dia".
- **Regra 2 (Valor Atípico) e agregações gerais:** essas operações **permanecem ativas** — o valor financeiro é real e precisa continuar auditável.

### 2.3 Limitação conhecida: resolução de entidade em `contraparte`

Nomes de contraparte combinam razão social e sufixo societário (ex.: `Alfa Comercio LTDA` vs. `Alfa Assessoria LTDA`, `Farol Transportes ME` vs. `Farol Transportes SA`). Nenhuma função do projeto agrupa contrapartes por prefixo ou similaridade — cada string é uma identidade distinta. Plano de solução detalhado na Seção 4.5.

---

## 3. Trade-offs na integração com o LLM

### 3.1 Modelo Gemini: mudança forçada durante o desenvolvimento

`gemini-2.0-flash`, especificado no nosso planejamento inicial, foi descontinuado pela Google durante o desenvolvimento (erro 404 na API). A alternativa seguinte, `gemini-2.5-flash`, também retornou indisponível para a chave usada. Migramos para `gemini-3.6-flash` somente depois de confirmar disponibilidade real via `client.models.list()` — não aceitamos o nome sugerido pela mensagem de erro sem essa checagem direta.

Evitamos deliberadamente o alias `gemini-flash-latest` (que sempre aponta para o Flash mais recente): um alias variável enfraquece a garantia de reprodutibilidade do cache, cuja chave depende de `versao_modelo` ser um valor fixo e rastreável.

### 3.2 Cache de respostas: por que a chave inclui prompt e modelo

A chave de cache é um hash MD5 de `cliente_id` + hash do `prompt_template` + `versao_modelo` + dump JSON ordenado (`sort_keys=True`) dos dados da operação. Se a chave não incluísse o template do prompt, as duas versões testadas na Parte B (V1 zero-shot e V2 chain-of-thought) colidiriam na mesma chave — a chamada de V1 preencheria o cache, e a "chamada" de V2 seria na verdade um cache HIT reaproveitando a resposta de V1, invalidando o teste A/B sem gerar erro visível. Validamos isso com um `assert` explícito no notebook comparando as chaves de V1 e V2.

### 3.3 Achado real: violação da "regra de ouro" pelo próprio modelo

Mesmo com o payload já contendo valores pré-calculados, o prompt V1 (zero-shot) produziu, por conta própria, um percentual ("94% do volume total") que não estava em nenhum campo do payload — o modelo somou as operações e dividiu pelo volume total sem que isso fosse pedido. Não afetou nenhuma decisão do pipeline (o número aparece só na prosa do parecer), mas é uma violação real da regra de que o LLM deve apenas interpretar, nunca calcular. O V2, com a instrução explícita "NÃO REFAÇA CÁLCULOS MATEMÁTICOS", não repetiu esse comportamento.

### 3.4 Falha real de schema no V2 — não simulada

O prompt V2 devolveu, em uma chamada real, uma resposta aninhada sob `"parecer_auditoria"` com campos inventados, em vez do schema plano pedido. O `try/except` capturou isso corretamente. Hipótese: o V1 lista os quatro nomes de campo explicitamente no texto, enquanto o V2 pede apenas "devolva a estrutura JSON validada" sem repeti-los — e a persona de "Auditor Sênior" empurrou o modelo para um formato de relatório mais elaborado. Mantivemos o texto exato dos dois prompts como especificado no enunciado, mesmo sabendo dessa falha, para não invalidar a comparação pedida.

### 3.5 Autoteste do fallback sem gastar cota real

Isolamos a função de chamada à API com `unittest.mock.patch` para forçar respostas malformadas de forma determinística, e validamos com `assert` que o fallback esgota as tentativas e produz o parecer de contingência esperado — sem gastar cota. A prova de que o mecanismo funciona em condição real veio depois, quando o V2 falhou de fato (item 3.4).

---

## 4. O que faríamos com mais tempo — Nível 2, Partes B, C e D

### 4.1 Ferramentas do agente (`historico_cliente`, `operacoes_do_dia`, `perfil_canal`) — Parte B

**Assinatura e contrato:**
```python
def historico_cliente(cliente_id: str) -> dict:
    """Resumo agregado: volume_total_brl, qtd_operacoes, flags ativas
    (ALERTA_FRACIONAMENTO, ALERTA_VALOR_ATIPICO, ALERTA_DATA_AUSENTE),
    contrapartes distintas, canais utilizados."""

def operacoes_do_dia(cliente_id: str, data: str) -> dict:
    """Recorte das operações do cliente numa data específica, com o mesmo
    nível de detalhe do 'historico_operacoes' já usado no payload do Nível 1."""

def perfil_canal(cliente_id: str) -> dict:
    """Distribuição percentual de uso por canal (value_counts(normalize=True)),
    com destaque para canais de maior risco relativo (ex.: 'especie')."""
```

**Decisão já tomada:** as três funções são **puras** (sem chamada ao LLM dentro delas) e reaproveitam diretamente o DataFrame sanitizado e as flags já calculadas em `nivel_2/tools.py` (Parte A, já implementada) — nenhuma reimplementação de lógica de negócio, só reformatação para o contrato de ferramenta.

**Como validaríamos:** teste manual comparando o retorno de cada função contra um cálculo feito à mão para 2-3 clientes conhecidos do próprio Top 10 já gerado (`outputs/top_10_clientes_nivel2.csv`) — o mesmo padrão de validação explícita já usado para a Regra 1 no Nível 1 (Seção 8 do notebook).

### 4.2 Agente com decisão de ferramentas (`nivel_2/agente.py`) — Parte B

**Decisão de framework:** SDK nativa do `google-genai` com *function calling* (tool declarations), não um framework como LangChain — para manter a superfície de dependências pequena e reaproveitar 100% do código de cache/Pydantic/fallback já escrito e validado no Nível 1.

**Fluxo pretendido:**
1. O agente recebe `cliente_id` + o motivo da sinalização (qual(is) regra(s) disparou).
2. O modelo decide, via function calling, quais das três ferramentas do item 4.1 invocar — nunca as três indiscriminadamente para todo cliente (o enunciado desencoraja isso explicitamente).
3. Com o resultado das ferramentas escolhidas, o modelo produz o parecer final no mesmo schema `ParecerPLD` já validado.

**Reaproveitamento direto do Nível 1:** cache com chave sensível a prompt/modelo/dados, schema Pydantic com normalização de acentuação, e estratégia de fallback com retry + backoff — importados de `nivel_2/tools.py`, não reescritos.

**Risco identificado antecipadamente:** *function calling* multi-turno consome mais tokens e RPM do que uma chamada única (cada ferramenta invocada é um round-trip adicional). Para 10 clientes com 2-3 ferramentas cada, estimamos 20-30 chamadas de API na Parte C — dentro da cota gratuita, mas exigindo o controle de intervalo mínimo entre chamadas que já está previsto em `.env.example` (`MIN_SECONDS_BETWEEN_CALLS`).

### 4.3 Execução em lote e persistência (`outputs/lote_pareceres.json`, `outputs/metricas_execucao.csv`) — Parte C

**Pipeline pretendido:** rodar o agente (item 4.2) sobre os 10 clientes já identificados em `outputs/top_10_clientes_nivel2.csv` (Parte A, já pronta), com:
- Intervalo mínimo configurável entre chamadas (controle de RPM)
- Backoff exponencial adicional em caso de erro 429 (rate limit)
- Registro em CSV **incremental** (uma linha por chamada, escrita a cada iteração — não só ao final) de: `cliente_id`, tokens prompt/completion, latência, número de retries, se veio do cache
- Persistência do parecer completo de cada cliente em `outputs/lote_pareceres.json`

**Diferença deliberada em relação ao Nível 1:** no notebook, tokens/latência foram só impressos (prints), por economia de tempo. Na Parte C, isso viraria um CSV real desde o início.

**Como validaríamos:** reexecutar o lote duas vezes seguidas e confirmar, pelo CSV, que a segunda execução tem `veio_do_cache=True` para todos os 10 clientes.

### 4.4 Confronto entre regra e agente (`nivel_2/confronto.py`) — Parte D

**Critério de mapeamento já definido:**
- 2 regras distintas violadas → risco teórico `"alto"`
- 1 regra distinta violada → risco teórico `"médio"`
- 0 regras violadas → risco teórico `"baixo"`

**Achado real que já temos, sem ainda ter o código do confronto:** nos dados reais do Nível 2, **nenhum cliente violou as duas regras simultaneamente** (17 clientes violaram exatamente 1 regra, 13 violaram 0, conforme `outputs/top_10_clientes_nivel2.csv`). O critério "2 regras = alto risco" não teria nenhum caso real para validar neste dataset específico — o que reforça que depender só de regras simples subestima o risco real, e que o valor do agente qualitativo está exatamente em capturar padrões que nenhuma das duas regras isoladas comprovadamente captura.

**O que o script faria:** calcular taxa de concordância entre risco teórico e `nivel_risco` do agente, e — mais importante — **analisar qualitativamente as divergências**, com atenção a casos em que o agente rebaixaria o risco de um cliente sinalizado (falso positivo da regra simples) e casos em que elevaria o risco de um cliente com só 1 flag técnica mas contexto qualitativo agravante.

**Como validaríamos:** revisão manual de pelo menos 3 casos de divergência, documentando se ela parece justificada pela leitura humana do `historico_operacoes` daquele cliente.

### 4.5 Resolução de entidade em `contraparte`

**Abordagem pretendida:** normalização de texto (remoção de sufixos societários conhecidos — LTDA, ME, SA — e case-folding) seguida de matching fuzzy (`rapidfuzz`), com um limiar de similaridade conservador e um passo **obrigatório** de validação manual antes de qualquer agregação usar "contraparte normalizada" como chave.

---

## 5. Nível 3 — não implementado

**Trilha escolhida, se houvesse tempo: Trilha B (Servidor MCP local).**

**Justificativa:** as três ferramentas do item 4.1 já teriam um contrato de entrada/saída bem definido. Expor essas mesmas funções via um servidor MCP local (stdio) seria uma camada relativamente fina sobre um contrato já pensado, reforçando a separação entre "ferramenta determinística" e "decisão do agente" que já orienta o resto do projeto.

**Por que não a Trilha A (multiagente):** exigiria um novo desenho de estado compartilhado e condição de parada entre Triador, Investigador e Redator — arquitetura nova, não extensão do que já existe.

**Por que não a Trilha C (interface conversacional):** exigiria uma camada de UI inteira além da lógica de agente que ainda nem está pronta (Parte B).

---

## 6. Observabilidade de custo (bônus, não implementado como item separado)

O notebook do Nível 1 já registra tokens (prompt/completion) e latência por chamada, e sinaliza cache HIT/MISS. O que falta é a consolidação em um artefato persistente e agregado — já detalhado no item 4.3, pois seria natural implementá-lo junto com a Parte C do Nível 2.

---

## 7. Visão de produção — além do escopo deste desafio

Tudo que construímos aqui é um protótipo de triagem, validado sobre dados fictícios e estáticos. Pensando em como esse sistema evoluiria de verdade dentro de um banco — tratando cada operação sinalizada como um "ticket" que precisa fluir por um processo, parecido com um sistema de tickets de área financeira — esboçamos a arquitetura abaixo. Nada disso foi implementado; é a direção que tomaríamos depois da validação inicial que os Níveis 1 e 2 representam.

### 7.1 Pipeline de entrada e integração

Hoje o pipeline lê dois arquivos JSON estáticos. Em produção, a entrada viria de uma integração direta com o(s) sistema(s) transacional(is) do banco — o que muda a natureza do projeto de "processar um lote fechado" para "processar um fluxo contínuo". Isso implica repensar as regras determinísticas como funções que operam sobre uma janela de tempo móvel (ex.: "últimos 30 dias daquele cliente"), não sobre uma base fechada carregada de uma vez.

### 7.2 Anonimização condicional

Nenhum dado deste desafio é real ou sensível, então não implementamos anonimização — mas se este pipeline processasse dados reais de clientes, uma etapa de anonimização (ou pseudonimização, mantendo um índice reversível só para quem tem autorização) precisaria vir **antes** de qualquer dado sair do perímetro do banco em direção a um provedor de LLM externo (como o Gemini). Isso é especialmente relevante porque hoje o payload enviado ao modelo inclui nome de contraparte e detalhes operacionais — em produção, esse tipo de dado precisaria de uma camada de anonimização ou de um modelo hospedado dentro do perímetro do banco (self-hosted), dependendo da política de dados da instituição.

### 7.3 RAG para manter o contexto normativo sempre atualizado

O agente hoje só recebe o contexto da própria operação. Em produção, valeria integrar um sistema de recuperação (RAG) sobre a base de políticas internas de compliance do banco e a legislação vigente (normas do Banco Central, regras do COAF) — permitindo que o parecer cite a norma específica que fundamenta a suspeita, em vez de uma avaliação genérica. Como políticas e legislação mudam com o tempo, essa base precisaria de um processo próprio de atualização — o RAG resolve exatamente o problema de o modelo "saber" sobre uma norma nova sem precisar re-treinar nada.

### 7.4 Versionamento de configuração — nunca apagar, sempre versionar

Os limiares das regras determinísticas (R$ 50.000, 5x mediana, etc.) e os templates de prompt do agente não deveriam nunca ser sobrescritos silenciosamente. A proposta é versionar essas configurações — por exemplo, um arquivo JSON por versão, com data de vigência e o que mudou em relação à versão anterior — de forma que seja sempre possível auditar exatamente qual regra e qual prompt geraram um determinado parecer em qualquer ponto do passado. Em um contexto de compliance, essa rastreabilidade não é opcional: se um regulador perguntar "por que esse cliente não foi sinalizado em março", a resposta precisa vir de um histórico de configuração, não de memória.

### 7.5 Observabilidade orientada a criticidade, não só um dashboard passivo

Hoje registramos tokens e latência (Seção 6), mas isso é observabilidade de custo, não de risco. Em produção, pensamos em uma camada adicional: conforme cada operação chega e é processada pelo pipeline, uma tabela de observabilidade seria atualizada continuamente, e — dependendo de quão crítico ou atípico for o caso — dispararia uma notificação para a equipe de compliance responsável, em vez de esperar uma rodada de revisão em lote. A ideia central é reduzir o tempo entre "algo estranho aconteceu" e "um humano está ciente disso", já que esse intervalo é diretamente proporcional ao tamanho do problema que a instituição pode acumular antes de agir.

Um caso concreto desse fluxo: hoje, quando uma operação chega com `data` ausente, o pipeline só marca a flag `ALERTA_DATA_AUSENTE` e segue. Em produção, esse alerta deveria gerar uma notificação para a área de origem do dado, pedindo confirmação sobre se a ausência foi uma falha técnica de captura do sistema, ou se reflete algo que precisa de atenção (por exemplo, uma tentativa deliberada de dificultar o rastreamento de uma operação). Hoje o notebook sinaliza a ausência; não investiga a causa — essa investigação é justamente o tipo de etapa que só faz sentido existir quando há um sistema de notificação e resposta humana por trás.

### 7.6 Evolução futura: aprendizado sobre padrões históricos

Depois de um período de operação estável — com histórico real acumulado de operações, flags, pareceres do agente e decisões humanas de confronto (Seção 4.4) guardado em banco, não em arquivos soltos — valeria treinar um modelo próprio sobre esse histórico, buscando padrões específicos de determinados clientes ou de esquemas recorrentes que as duas regras determinísticas fixas (limiares estáticos) não capturam isoladamente. Esse é um passo que só faz sentido depois que a base de confronto regra-vs-agente tiver dados suficientes para validar se esse tipo de modelo aprendido realmente generaliza melhor do que a combinação atual de regra + LLM, e não apenas memoriza os poucos casos vistos até então.