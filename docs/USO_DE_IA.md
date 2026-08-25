# Uso de IA no Desenvolvimento

Ponto de partida: planejamento próprio, antes de qualquer IA

Antes de abrir qualquer ferramenta de IA, li o enunciado do desafio por completo e preparei, no Obsidian, um plano próprio do que pretendia fazer — estrutura de pastas, ordem de execução das partes, e as decisões técnicas que já fazia sentido tomar de antemão (ex.: como tratar os dois níveis com esquemas de dados diferentes, a ideia inicial de estrutura do projeto). Foi só a partir desse plano já formado que comecei a usar o Claude como apoio — a IA entrou para auditar, acelerar e ajudar a executar um plano que já existia, não para definir o que fazer desde o zero.

## Ferramentas utilizadas e papel de cada uma

- **Claude (chat)** — usado como copiloto de arquitetura e revisão, não de implementação. Antes de qualquer código ser escrito, usamos o Claude para auditar nosso próprio planejamento técnico contra o enunciado do desafio (ex.: identificamos ali, antes de qualquer linha de código, o bug de colisão de cache entre os prompts V1/V2 e a inconsistência de estrutura de pastas do `utils.py`). Ao longo do desenvolvimento, cada bloco de código gerado pelo Claude Code passou primeiro por essa camada de revisão — conferência de lógica, aderência à "regra de ouro" do desafio (LLM não calcula), e decisão explícita de aprovar, ajustar ou rejeitar — antes de qualquer commit.


## Como o processo foi conduzido — não é geração automática sem controle

O fluxo de trabalho foi deliberadamente **iterativo e supervisionado**, não "peça tudo de uma vez e aceite o resultado":

1. Cada parte do desafio (ex.: Regra 1, schema Pydantic, cache, fallback) foi pedida como um bloco isolado e pequeno — nunca "implemente a Parte B inteira" de uma vez.
2. Depois de cada bloco gerado, paramos a execução, lemos o código linha por linha, e conferimos manualmente que a lógica batia com o que o enunciado pedia — incluindo validar contas à mão (ex.: recalculamos a mediana da Regra 2 e a soma da Regra 1 fora do notebook, comparando o resultado esperado com o output real antes de aceitar o bloco como correto).
3. Só depois dessa conferência explícita é que o bloco era aprovado para commit. Vários blocos passaram por ajuste ou questionamento antes de serem aceitos (ver exemplos abaixo).
4. Nenhuma chamada real à API do Gemini foi autorizada sem antes revisar o código que a dispararia — inclusive interrompendo blocos já escritos para confirmar disponibilidade de modelo antes de deixar a execução prosseguir.

Essa disciplina foi mantida mesmo sob pressão de prazo: preferimos reduzir escopo (entregar o Nível 1 completo e só a Parte A do Nível 2) a acelerar aceitando código não revisado nos níveis seguintes.

## Pontos em que a IA levou por um caminho que precisou de correção — e como identificamos e corrigimos

Registramos aqui justamente os momentos em que **não** aceitamos o que foi gerado sem questionar, porque isso evidencia a revisão ativa, não a ausência dela:

1. **Sugestão de modelo sem confirmar disponibilidade primeiro.** Quando `gemini-2.0-flash` foi descontinuado pela API durante a execução, o Claude Code sugeriu de imediato `gemini-3.6-flash` como "recomendado", citando que era o modelo apontado pela própria mensagem de erro. **Não aceitamos essa sugestão de primeira.** Optamos por testar antes `gemini-2.5-flash` — a opção mais conservadora, com nome fixo e sem sufixo `-preview` — e só migramos para `gemini-3.6-flash` depois de exigir e conferir uma checagem real de disponibilidade via `client.models.list()`, confirmando que as duas opções anteriores estavam de fato indisponíveis para a chave em uso. A decisão de qual modelo usar foi nossa, tomada com evidência, não a recomendação automática aceita como veio.

2. **Loop de tentativas desnecessárias de verificar encoding via terminal.** Depois de executar o notebook, o Claude Code insistiu (três variações de comando) em confirmar que os acentos em português estavam salvos corretamente no arquivo `.ipynb`, mesmo já tendo identificado corretamente que o problema era só de exibição no console do Windows (cp1252 vs UTF-8), não um defeito real no arquivo salvo. **Interrompemos esse loop manualmente** em vez de deixar rodar, e resolvemos com uma inspeção visual direta do notebook no VS Code — mais rápido e mais confiável do que insistir em scripts de diagnóstico redundantes.

3. **Escrita de um `docs/DECISOES.md` próprio, sem solicitação.** Em um comando ambíguo ("finalize aqui a Parte A do Nível 2"), o Claude Code interpretou isso como incluindo a escrita de uma versão própria e resumida do `DECISOES.md`, sem que isso tivesse sido pedido, e sem saber que já havia uma versão mais completa sendo preparada em paralelo. **Identificamos isso antes do commit**, revisando explicitamente o `git status` e o conteúdo staged antes de aprovar qualquer coisa, e instruímos para excluir esse arquivo daquele commit específico — a versão que efetivamente foi entregue neste documento e no `DECISOES.md` foi escrita e revisada por nós, com a IA atuando na formatação e organização do conteúdo que definimos.

## Observação geral

A IA foi usada para **acelerar a implementação e servir de segunda camada de revisão técnica**, não para tomar decisões de arquitetura, regra de negócio ou escopo por conta própria. Cada sugestão de mudança de comportamento do código (modelo, schema, lógica de regra) passou por entendimento e validação manual nossa antes de ser aceita — inclusive quando isso significou interromper uma execução em andamento, cancelar um comando, ou rejeitar um arquivo já escrito para pedir uma versão diferente. O ritmo de revisão bloco a bloco (nunca "gere tudo de uma vez") foi mantido do início ao fim do projeto, mesmo sob pressão de prazo.