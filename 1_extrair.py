"""
1_extrair.py
------------
Fase 1 - Extracao e camada Raw.

1. Baixa o .zip do Google Drive (gdown) para a pasta data/.
2. Descompacta e localiza os 4 CSVs.
3. Le cada CSV em blocos e carrega, sem alterar o conteudo, nas
   tabelas raw_* (todas VARCHAR).

Idempotente: cada tabela Raw e esvaziada (TRUNCATE) antes da carga,
entao rodar o script varias vezes nao duplica registros.

Uso (na raiz do projeto, com o .venv ativo):
    python 1_extrair.py
"""

import shutil
import sys
import zipfile
from pathlib import Path

import gdown
import pandas as pd
from mysql.connector import Error

from banco import conectar, executar, inserir_em_lote
from config import (
    ARQUIVOS,
    CSV_ENCODING,
    CSV_SEPARADOR,
    DRIVE_FILE_ID,
    PASTA_DADOS,
    TAMANHO_BLOCO,
)

CAMINHO_ZIP = PASTA_DADOS / "dados.zip"

# Cada bloco lido do CSV e gravado em lotes menores, para nao estourar
# o max_allowed_packet do MySQL em colunas de texto longo.
LOTE_INSERCAO = 10_000

ERROS_ESPERADOS = (
    Error,
    RuntimeError,
    ValueError,
    OSError,
    zipfile.BadZipFile,
)