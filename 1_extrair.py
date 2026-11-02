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



def baixar_zip():
    """Baixa o .zip do Google Drive para a pasta data/."""
    if "/" in DRIVE_FILE_ID:
        raise ValueError(
            "DRIVE_FILE_ID deve conter apenas o ID do arquivo, "
            "e nao a URL completa."
        )
    PASTA_DADOS.mkdir(parents=True, exist_ok=True)
    url = f"https://drive.google.com/uc?id={DRIVE_FILE_ID}"
    print(f"Baixando o .zip para {CAMINHO_ZIP} ...")
    resultado = gdown.download(url, str(CAMINHO_ZIP), quiet=False)
    if resultado is None:
        raise RuntimeError(
            "Falha no download do .zip. Verifique o DRIVE_FILE_ID e se "
            "o arquivo esta compartilhado para quem tem o link."
        )



def descompactar_zip():
    """Extrai os 4 CSVs esperados para a pasta data/ (sem subpastas)."""
    esperados = {info["csv"] for info in ARQUIVOS.values()}
    print("Descompactando os CSVs ...")
    with zipfile.ZipFile(CAMINHO_ZIP) as arquivo_zip:
        for nome in arquivo_zip.namelist():
            nome_base = Path(nome).name
            if nome_base not in esperados:
                continue
            destino = PASTA_DADOS / nome_base
            with arquivo_zip.open(nome) as origem:
                with open(destino, "wb") as saida:
                    shutil.copyfileobj(origem, saida)

    faltando = [c for c in sorted(esperados) if not (PASTA_DADOS / c).exists()]
    if faltando:
        raise FileNotFoundError(
            f"CSVs nao encontrados no .zip: {', '.join(faltando)}"
        )