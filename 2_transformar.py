"""
2_transformar.py
----------------
Fase 2 - Transformacao e camada Silver.

Copia as tabelas Raw (texto) para as tabelas Silver (tipadas):

1. Converte texto para DECIMAL (virgula decimal) e para DATE (DD/MM/AAAA).
2. Limpa os textos (espacos, vazios, tamanho maximo da coluna).
3. Calcula valor_total e duracao_dias em silver_viagem.
4. Respeita a integridade referencial: silver_viagem e carregada antes
   das tabelas filhas, e registros orfaos (sem viagem) sao descartados.
5. Remove duplicidades das chaves (id_viagem e id_viagem + sequencia).

Regras de negocio definidas neste projeto:
    valor_total  = diarias + passagens + outros gastos - devolucao
    duracao_dias = data_fim - data_inicio + 1 (conta o dia inicial e o final)

Idempotente: as tabelas Silver sao esvaziadas antes da carga.

Uso (na raiz do projeto, com o .venv ativo):
    python 2_transformar.py
"""

import logging
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation

from mysql.connector import Error

from banco import conectar, executar, inserir_em_lote
from config import PASTA_RAIZ, TAMANHO_BLOCO

PASTA_LOGS = PASTA_RAIZ / "logs"
ARQUIVO_LOG = PASTA_LOGS / "erros_transformacao.log"

FORMATO_DATA = "%d/%m/%Y"
TEXTO_PADRAO = "Não informado"
MAXIMO_DECIMAL = Decimal("99999999.99")  # limite de DECIMAL(10,2)
LOTE_INSERCAO = 10_000

# Ordem para esvaziar: filhas primeiro, pai por ultimo.
TABELAS_SILVER = (
    "silver_trecho",
    "silver_pagamento",
    "silver_passagem",
    "silver_viagem",
)

ERROS_ESPERADOS = (Error, RuntimeError, ValueError, OSError)


def configurar_log():
    """Cria a pasta logs/ e configura o registro de erros em arquivo."""
    PASTA_LOGS.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=ARQUIVO_LOG,
        level=logging.ERROR,
        format="%(asctime)s | %(levelname)s | %(message)s",
        encoding="utf-8",
        force=True,
    )


def limpar_texto(valor, tamanho=None, padrao=None):
    """
    Remove espacos das pontas. Texto vazio vira 'padrao' (ou None).
    Se 'tamanho' for informado, corta o texto nesse limite.
    """
    if valor is None:
        return padrao
    texto = str(valor).strip()
    if not texto:
        return padrao
    if tamanho:
        texto = texto[:tamanho]
    return texto


def converter_decimal(texto, maximo=MAXIMO_DECIMAL):
    """
    Converte texto com virgula decimal em Decimal (ex.: '1272,97' ->
    Decimal('1272.97')). Retorna None se estiver vazio, for invalido,
    negativo ou maior que o limite da coluna.
    """
    if texto is None:
        return None
    texto = str(texto).strip()
    if not texto:
        return None
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        valor = Decimal(texto)
        if not valor.is_finite():
            return None
        valor = valor.quantize(Decimal("0.01"))
    except InvalidOperation:
        return None
    if valor < 0 or valor > maximo:
        return None
    return valor


def converter_data(texto):
    """Converte texto DD/MM/AAAA em date. Retorna None se for invalido."""
    if texto is None:
        return None
    partes = str(texto).split()
    if not partes:
        return None
    try:
        return datetime.strptime(partes[0], FORMATO_DATA).date()
    except ValueError:
        return None


def converter_inteiro(texto):
    """Converte texto em int. Retorna None se estiver vazio ou invalido."""
    try:
        return int(str(texto).strip())
    except ValueError:
        return None


def calcular_valor_total(diarias, passagens, outros_gastos, devolucao):
    """valor_total = diarias + passagens + outros gastos - devolucao."""
    zero = Decimal("0.00")
    return (
        (diarias or zero)
        + (passagens or zero)
        + (outros_gastos or zero)
        - (devolucao or zero)
    )


def calcular_duracao_dias(data_inicio, data_fim):
    """duracao_dias = data_fim - data_inicio + 1 (None se faltar data)."""
    if data_inicio is None or data_fim is None or data_fim < data_inicio:
        return None
    return (data_fim - data_inicio).days + 1


def limpar_silver(conexao):
    """Esvazia as 4 tabelas Silver para a carga ser repetivel."""
    executar(conexao, "SET FOREIGN_KEY_CHECKS = 0")
    try:
        for tabela in TABELAS_SILVER:
            executar(conexao, f"TRUNCATE TABLE {tabela}")
    finally:
        executar(conexao, "SET FOREIGN_KEY_CHECKS = 1")


def ler_blocos(conexao, tabela, colunas):
    """Le a tabela em blocos de TAMANHO_BLOCO linhas (gerador)."""
    cursor = conexao.cursor()
    cursor.execute(f"SELECT {', '.join(colunas)} FROM {tabela}")
    while True:
        bloco = cursor.fetchmany(TAMANHO_BLOCO)
        if not bloco:
            break
        yield bloco
    cursor.close()


def montar_linha_viagem(linha):
    """Converte uma linha de raw_viagem para silver_viagem."""
    (id_viagem, num_proposta, situacao, urgente, cod_orgao, nome_orgao,
     viajante, cargo, inicio, fim, destinos, motivo, diarias, passagens,
     devolucao, outros_gastos) = linha

    id_viagem = limpar_texto(id_viagem, 20)
    if id_viagem is None:
        return None
    data_inicio = converter_data(inicio)
    data_fim = converter_data(fim)
    valor_diarias = converter_decimal(diarias)
    valor_passagens = converter_decimal(passagens)
    valor_devolucao = converter_decimal(devolucao)
    valor_outros = converter_decimal(outros_gastos)
    return (
        id_viagem,
        limpar_texto(num_proposta, 20),
        limpar_texto(situacao, 50),
        limpar_texto(urgente, 5),
        limpar_texto(cod_orgao, 20),
        limpar_texto(nome_orgao, 255, TEXTO_PADRAO),
        limpar_texto(viajante, 255),
        limpar_texto(cargo, 255),
        data_inicio,
        data_fim,
        limpar_texto(destinos, 4000),
        limpar_texto(motivo, 4000),
        valor_diarias,
        valor_passagens,
        valor_devolucao,
        valor_outros,
        calcular_valor_total(
            valor_diarias, valor_passagens, valor_outros, valor_devolucao
        ),
        calcular_duracao_dias(data_inicio, data_fim),
    )


def montar_linha_pagamento(linha):
    """Converte uma linha de raw_pagamento para silver_pagamento."""
    (id_viagem, num_proposta, orgao_pagador, ug_pagadora, tipo,
     valor) = linha

    id_viagem = limpar_texto(id_viagem, 20)
    if id_viagem is None:
        return None
    return (
        id_viagem,
        limpar_texto(num_proposta, 20),
        limpar_texto(orgao_pagador, 255),
        limpar_texto(ug_pagadora, 255),
        limpar_texto(tipo, 50, TEXTO_PADRAO),
        converter_decimal(valor),
    )


def montar_linha_passagem(linha):
    """Converte uma linha de raw_passagem para silver_passagem."""
    (id_viagem, meio, pais_origem, uf_origem, cidade_origem, pais_destino,
     uf_destino, cidade_destino, valor, taxa, emissao) = linha

    id_viagem = limpar_texto(id_viagem, 20)
    if id_viagem is None:
        return None
    return (
        id_viagem,
        limpar_texto(meio, 50),
        limpar_texto(pais_origem, 60),
        limpar_texto(uf_origem, 40),
        limpar_texto(cidade_origem, 80),
        limpar_texto(pais_destino, 60),
        limpar_texto(uf_destino, 40),
        limpar_texto(cidade_destino, 80),
        converter_decimal(valor),
        converter_decimal(taxa),
        converter_data(emissao),
    )


def montar_linha_trecho(linha):
    """Converte uma linha de raw_trecho para silver_trecho."""
    (id_viagem, sequencia, origem_data, origem_uf, origem_cidade,
     destino_data, destino_uf, destino_cidade, meio, diarias) = linha

    id_viagem = limpar_texto(id_viagem, 20)
    if id_viagem is None:
        return None
    return (
        id_viagem,
        converter_inteiro(sequencia),
        converter_data(origem_data),
        limpar_texto(origem_uf, 40),
        limpar_texto(origem_cidade, 80),
        converter_data(destino_data),
        limpar_texto(destino_uf, 40),
        limpar_texto(destino_cidade, 80),
        limpar_texto(meio, 50),
        converter_decimal(diarias),
    )


def gravar_lote(escrita, sql_insert, linhas, resumo):
    """
    Grava um lote de linhas. Se o lote falhar, tenta linha a linha para
    isolar (e registrar no log) apenas as linhas problematicas.
    """
    try:
        inserir_em_lote(escrita, sql_insert, linhas)
        resumo["gravadas"] += len(linhas)
        return
    except Error:
        escrita.rollback()

    for linha in linhas:
        try:
            inserir_em_lote(escrita, sql_insert, [linha])
            resumo["gravadas"] += 1
        except Error as erro:
            escrita.rollback()
            resumo["invalidas"] += 1
            logging.error("Linha rejeitada | %s | %s", linha[:3], erro)


def copiar_para_silver(leitura, escrita, tabela_raw, colunas_raw,
                       tabela_silver, colunas_silver, montar_linha,
                       ids_viagem=None, indices_chave=None):
    """
    Le a tabela Raw em blocos, converte cada linha e grava na Silver.

    - ids_viagem: conjunto de viagens validas; linhas de tabelas filhas
      cuja viagem nao existe (orfas) sao descartadas.
    - indices_chave: posicoes da linha que formam a chave unica; repeticoes
      dessa chave sao descartadas (duplicidades).
    Retorna um dicionario com a contagem de linhas.
    """
    marcadores = ", ".join(["%s"] * len(colunas_silver))
    sql_insert = (
        f"INSERT INTO {tabela_silver} ({', '.join(colunas_silver)}) "
        f"VALUES ({marcadores})"
    )
    resumo = {"lidas": 0, "gravadas": 0, "duplicadas": 0, "orfas": 0,
              "invalidas": 0}
    vistos = set()

    for bloco in ler_blocos(leitura, tabela_raw, colunas_raw):
        linhas = []
        for linha_raw in bloco:
            resumo["lidas"] += 1
            linha = montar_linha(linha_raw)
            if linha is None:
                resumo["invalidas"] += 1
                continue
            if ids_viagem is not None and linha[0] not in ids_viagem:
                resumo["orfas"] += 1
                continue
            if indices_chave:
                chave = tuple(linha[i] for i in indices_chave)
                if None not in chave:
                    if chave in vistos:
                        resumo["duplicadas"] += 1
                        continue
                    vistos.add(chave)
            linhas.append(linha)

        for inicio in range(0, len(linhas), LOTE_INSERCAO):
            gravar_lote(
                escrita, sql_insert, linhas[inicio:inicio + LOTE_INSERCAO],
                resumo,
            )
    return resumo


def carregar_ids_viagem(conexao):
    """Retorna o conjunto de id_viagem ja gravados em silver_viagem."""
    cursor = conexao.cursor()
    cursor.execute("SELECT id_viagem FROM silver_viagem")
    ids = {linha[0] for linha in cursor.fetchall()}
    cursor.close()
    return ids


def transformar_viagem(leitura, escrita):
    """Raw -> Silver de viagem (tabela pai, carregada primeiro)."""
    return copiar_para_silver(
        leitura, escrita,
        "raw_viagem",
        ["id_viagem", "num_proposta", "situacao", "viagem_urgente",
         "cod_orgao_superior", "nome_orgao_superior", "nome_viajante",
         "cargo", "data_inicio", "data_fim", "destinos", "motivo",
         "valor_diarias", "valor_passagens", "valor_devolucao",
         "valor_outros_gastos"],
        "silver_viagem",
        ["id_viagem", "num_proposta", "situacao", "viagem_urgente",
         "cod_orgao_superior", "nome_orgao_superior", "nome_viajante",
         "cargo", "data_inicio", "data_fim", "destinos", "motivo",
         "valor_diarias", "valor_passagens", "valor_devolucao",
         "valor_outros_gastos", "valor_total", "duracao_dias"],
        montar_linha_viagem,
        indices_chave=(0,),
    )


def transformar_pagamento(leitura, escrita, ids_viagem):
    """Raw -> Silver de pagamento (descarta pagamentos sem viagem)."""
    return copiar_para_silver(
        leitura, escrita,
        "raw_pagamento",
        ["id_viagem", "num_proposta", "nome_orgao_pagador",
         "nome_ug_pagadora", "tipo_pagamento", "valor"],
        "silver_pagamento",
        ["id_viagem", "num_proposta", "nome_orgao_pagador",
         "nome_ug_pagadora", "tipo_pagamento", "valor"],
        montar_linha_pagamento,
        ids_viagem=ids_viagem,
    )


def transformar_passagem(leitura, escrita, ids_viagem):
    """Raw -> Silver de passagem (descarta passagens sem viagem)."""
    colunas = ["id_viagem", "meio_transporte", "pais_origem_ida",
               "uf_origem_ida", "cidade_origem_ida", "pais_destino_ida",
               "uf_destino_ida", "cidade_destino_ida", "valor_passagem",
               "taxa_servico", "data_emissao"]
    return copiar_para_silver(
        leitura, escrita,
        "raw_passagem", colunas,
        "silver_passagem", colunas,
        montar_linha_passagem,
        ids_viagem=ids_viagem,
    )


def transformar_trecho(leitura, escrita, ids_viagem):
    """Raw -> Silver de trecho (sem orfaos e sem sequencia repetida)."""
    colunas = ["id_viagem", "sequencia_trecho", "origem_data", "origem_uf",
               "origem_cidade", "destino_data", "destino_uf",
               "destino_cidade", "meio_transporte", "numero_diarias"]
    return copiar_para_silver(
        leitura, escrita,
        "raw_trecho", colunas,
        "silver_trecho", colunas,
        montar_linha_trecho,
        ids_viagem=ids_viagem,
        indices_chave=(0, 1),
    )
