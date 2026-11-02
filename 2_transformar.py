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
