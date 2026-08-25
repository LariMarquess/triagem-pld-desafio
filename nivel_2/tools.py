"""Ferramentas de triagem PLD para o Nível 2 — sanitização e regras em escala.

Reimplementa, como funções de módulo (não um import do notebook), a lógica de
tratamento de dados e as duas regras determinísticas já validadas em
nivel_1/nivel_1.ipynb, para aplicá-las sobre um volume maior de operações.

`cliente_id` é tratado em todo este módulo como uma string opaca: nunca é
feito parsing, split ou regex assumindo um formato específico (o Nível 1 usa
CLI-A-1, o Nível 2 usa CLI-001 — o código não pode depender de nenhum dos
dois formatos).
"""

import json

import pandas as pd

DATA_PENDENTE = "DATA_PENDENTE"


def carregar_dados(caminho_json: str) -> tuple[pd.DataFrame, float]:
    """Carrega um arquivo JSON de operações no formato do desafio.

    Args:
        caminho_json: caminho para o arquivo JSON, contendo um objeto com as
            chaves 'taxa_cambio_usd_brl' (float) e 'operacoes' (lista de
            dicionários, um por operação).

    Returns:
        Tupla (df, taxa_cambio_usd_brl):
          - df: DataFrame bruto (sem nenhum tratamento), construído
            diretamente da lista de operações.
          - taxa_cambio_usd_brl: taxa de conversão USD -> BRL embutida no
            arquivo.
    """
    with open(caminho_json, "r", encoding="utf-8") as f:
        dados_brutos = json.load(f)

    taxa_cambio_usd_brl = float(dados_brutos["taxa_cambio_usd_brl"])
    df = pd.DataFrame(dados_brutos["operacoes"])

    return df, taxa_cambio_usd_brl


def sanitizar_operacoes(df: pd.DataFrame, taxa_cambio_usd_brl: float = 5.4) -> pd.DataFrame:
    """Aplica a mesma sanitização de dados validada no Nível 1.

    Passos, nesta ordem:
      1. Deduplicação por 'id', preservando a primeira ocorrência
         (`keep="first"`) — mesmo critério do Nível 1: nada no enunciado
         sugere que duplicatas mais recentes sejam mais confiáveis, e a
         primeira ocorrência é a mais simples de justificar em auditoria.
      2. Criação da flag booleana 'ALERTA_DATA_AUSENTE', ANTES do
         preenchimento de data nula — para não perder a informação de que a
         data era originalmente ausente.
      3. Preenchimento de 'data' nula com o marcador textual 'DATA_PENDENTE'.
      4. Criação de 'valor_brl': `valor * taxa_cambio_usd_brl` quando
         `moeda == "USD"`, ou o valor original quando já está em BRL.

    Args:
        df: DataFrame bruto de operações (como devolvido por `carregar_dados`).
        taxa_cambio_usd_brl: taxa de conversão USD -> BRL a usar na
            normalização. Default 5.4 (valor observado nos dados dos
            Níveis 1 e 2); ao carregar um novo arquivo, passe a taxa
            devolvida por `carregar_dados` para não depender do default.

    Returns:
        Novo DataFrame tratado e normalizado, com as colunas adicionais
        'ALERTA_DATA_AUSENTE' (bool) e 'valor_brl' (float). O DataFrame de
        entrada não é modificado in-place.
    """
    linhas_antes = len(df)
    df_tratado = df.drop_duplicates(subset="id", keep="first").reset_index(drop=True)
    duplicatas_removidas = linhas_antes - len(df_tratado)

    df_tratado["ALERTA_DATA_AUSENTE"] = df_tratado["data"].isna()
    datas_ausentes_tratadas = int(df_tratado["ALERTA_DATA_AUSENTE"].sum())
    df_tratado["data"] = df_tratado["data"].fillna(DATA_PENDENTE)

    df_tratado["valor_brl"] = df_tratado["valor"].where(
        df_tratado["moeda"] != "USD", df_tratado["valor"] * taxa_cambio_usd_brl
    )

    print(f"Linhas antes da deduplicação: {linhas_antes} | depois: {len(df_tratado)}")
    print(f"Duplicatas removidas (por id, keep=first): {duplicatas_removidas}")
    print(f"Datas nulas tratadas (ALERTA_DATA_AUSENTE=True): {datas_ausentes_tratadas}")

    return df_tratado


def identificar_grupos_fracionados(
    df: pd.DataFrame,
    limite_soma: float = 50_000.0,
    limite_operacao_isolada: float = 20_000.0,
    min_operacoes: int = 3,
    valor_pendente: str = DATA_PENDENTE,
) -> set[tuple[str, str]]:
    """Identifica pares (cliente_id, data) que caracterizam fracionamento (Regra 1).

    Um par (cliente, data) dispara a regra quando, considerando apenas
    operações com data válida (data != valor_pendente):
      1. o cliente tem `min_operacoes` ou mais operações naquela data;
      2. a soma de `valor_brl` dessas operações ultrapassa `limite_soma`; e
      3. nenhuma operação isolada do grupo atinge `limite_operacao_isolada`
         (i.e., o valor máximo do grupo é estritamente menor que o limite).

    `cliente_id` é tratado como string opaca — apenas comparado por
    igualdade/agrupamento, nunca parseado.

    Args:
        df: DataFrame de operações já sanitizado, contendo as colunas
            'cliente_id', 'data' e 'valor_brl'.
        limite_soma: valor que a soma diária precisa ultrapassar (exclusivo).
        limite_operacao_isolada: valor que nenhuma operação isolada pode atingir.
        min_operacoes: quantidade mínima de operações no mesmo dia.
        valor_pendente: marcador de data ausente, excluído do agrupamento.

    Returns:
        Conjunto de tuplas (cliente_id, data) que disparam a Regra 1.
    """
    operacoes_com_data_valida = df[df["data"] != valor_pendente]

    grupos = operacoes_com_data_valida.groupby(["cliente_id", "data"])["valor_brl"]
    quantidade = grupos.count()
    soma = grupos.sum()
    valor_maximo = grupos.max()

    disparado = (
        (quantidade >= min_operacoes)
        & (soma > limite_soma)
        & (valor_maximo < limite_operacao_isolada)
    )

    return set(disparado[disparado].index)


def aplicar_flag_fracionamento(
    df: pd.DataFrame, grupos_flagrados: set[tuple[str, str]]
) -> pd.Series:
    """Marca com True toda operação cujo par (cliente_id, data) está em `grupos_flagrados`.

    Args:
        df: DataFrame de operações, contendo as colunas 'cliente_id' e 'data'.
        grupos_flagrados: conjunto de pares (cliente_id, data), tipicamente o
            retorno de `identificar_grupos_fracionados`.

    Returns:
        pd.Series booleana alinhada ao índice de df.
    """
    pares_operacao = pd.Series(list(zip(df["cliente_id"], df["data"])), index=df.index)
    return pares_operacao.isin(grupos_flagrados)


def identificar_valores_atipicos(
    df: pd.DataFrame,
    multiplicador_mediana: float = 5.0,
    min_operacoes_cliente: int = 4,
) -> pd.Series:
    """Identifica operações com valor atípico em relação ao próprio cliente (Regra 2).

    Uma operação é sinalizada quando:
      1. o cliente a que ela pertence tem `min_operacoes_cliente` ou mais
         operações no total (contando todas, inclusive com DATA_PENDENTE); e
      2. `valor_brl` da operação é estritamente maior que
         `multiplicador_mediana` vezes a mediana de `valor_brl` daquele cliente.

    `cliente_id` é tratado como string opaca — usado apenas para agrupar.

    Args:
        df: DataFrame de operações já sanitizado e normalizado, contendo as
            colunas 'cliente_id' e 'valor_brl'.
        multiplicador_mediana: quantas vezes a mediana o valor precisa superar.
        min_operacoes_cliente: quantidade mínima de operações do cliente para
            que ele entre na análise.

    Returns:
        pd.Series booleana alinhada ao índice de df, True nas operações atípicas.
    """
    operacoes_por_cliente = df.groupby("cliente_id")["id"].transform("count")
    mediana_por_cliente = df.groupby("cliente_id")["valor_brl"].transform("median")

    cliente_elegivel = operacoes_por_cliente >= min_operacoes_cliente
    limite_atipico = mediana_por_cliente * multiplicador_mediana

    return cliente_elegivel & (df["valor_brl"] > limite_atipico)


def contar_regras_violadas(df: pd.DataFrame) -> pd.DataFrame:
    """Conta, por cliente, quantas regras DISTINTAS de triagem foram violadas.

    O que importa é quantas regras diferentes o cliente violou, não quantas
    operações/ocorrências de flag ele tem: um cliente com 3 operações
    atípicas (Regra 2) ainda conta 1, não 3. O teto é 2 — Regra 1
    (fracionamento) e/ou Regra 2 (valor atípico).

    Args:
        df: DataFrame de operações já sanitizado, com as colunas booleanas
            'ALERTA_FRACIONAMENTO' e 'ALERTA_VALOR_ATIPICO' já aplicadas
            (ver `aplicar_flag_fracionamento` e `identificar_valores_atipicos`).

    Returns:
        DataFrame com uma linha por cliente_id (todo cliente presente em df,
        inclusive os sem nenhuma violação) e as colunas:
          - 'cliente_id'
          - 'violou_regra_1' (bool): True se alguma operação do cliente
            está marcada com ALERTA_FRACIONAMENTO.
          - 'violou_regra_2' (bool): True se alguma operação do cliente
            está marcada com ALERTA_VALOR_ATIPICO.
          - 'qtd_regras_violadas' (int, 0 a 2): soma das duas colunas acima.
    """
    resumo = (
        df.groupby("cliente_id")[["ALERTA_FRACIONAMENTO", "ALERTA_VALOR_ATIPICO"]]
        .any()
        .rename(
            columns={
                "ALERTA_FRACIONAMENTO": "violou_regra_1",
                "ALERTA_VALOR_ATIPICO": "violou_regra_2",
            }
        )
    )
    resumo["qtd_regras_violadas"] = (
        resumo["violou_regra_1"].astype(int) + resumo["violou_regra_2"].astype(int)
    )

    return resumo.reset_index()


def top_clientes_sinalizados(df: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    """Retorna os N clientes mais sinalizados pelas regras de triagem.

    Critério de ordenação (decrescente em ambos os casos):
      1. quantidade de regras distintas violadas (`qtd_regras_violadas`,
         de `contar_regras_violadas`);
      2. volume total transacionado em BRL (`valor_brl` somado por cliente),
         usado como desempate entre clientes que violaram a mesma
         quantidade de regras.

    Args:
        df: DataFrame de operações já sanitizado e normalizado, com as
            flags 'ALERTA_FRACIONAMENTO'/'ALERTA_VALOR_ATIPICO' aplicadas.
        n: número de clientes a retornar (default 10).

    Returns:
        DataFrame com 'cliente_id', 'qtd_regras_violadas', 'violou_regra_1',
        'violou_regra_2' e 'volume_total_brl', ordenado pelo critério acima,
        limitado às `n` primeiras linhas.
    """
    regras_por_cliente = contar_regras_violadas(df)
    volume_por_cliente = (
        df.groupby("cliente_id")["valor_brl"].sum().rename("volume_total_brl").reset_index()
    )

    resumo = regras_por_cliente.merge(volume_por_cliente, on="cliente_id", how="left")
    resumo = resumo.sort_values(
        by=["qtd_regras_violadas", "volume_total_brl"], ascending=[False, False]
    ).reset_index(drop=True)

    return resumo.head(n)


if __name__ == "__main__":
    from pathlib import Path

    BASE_DIR = Path(__file__).resolve().parent.parent
    caminho_dados = BASE_DIR / "dados" / "dados_nivel_2.json"
    caminho_saida = BASE_DIR / "outputs" / "top_10_clientes_nivel2.csv"

    df, taxa = carregar_dados(str(caminho_dados))
    df = sanitizar_operacoes(df, taxa)

    grupos_fracionados = identificar_grupos_fracionados(df)
    df["ALERTA_FRACIONAMENTO"] = aplicar_flag_fracionamento(df, grupos_fracionados)
    df["ALERTA_VALOR_ATIPICO"] = identificar_valores_atipicos(df)

    top_10 = top_clientes_sinalizados(df, n=10)

    caminho_saida.parent.mkdir(parents=True, exist_ok=True)
    top_10.to_csv(caminho_saida, index=False)

    print(f"\nTop 10 clientes sinalizados salvo em: {caminho_saida}")
    print(top_10.to_string(index=False))
