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

import logging
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
    PASTA_RAIZ,
    TAMANHO_BLOCO,
)

CAMINHO_ZIP = PASTA_DADOS / "dados.zip"
PASTA_LOGS = PASTA_RAIZ / "logs"
ARQUIVO_LOG = PASTA_LOGS / "erros_extracao.log"

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


def colunas_da_tabela(conexao, tabela):
    """Retorna a lista de colunas da tabela, na ordem em que foram criadas."""
    cursor = conexao.cursor()
    cursor.execute(f"SHOW COLUMNS FROM {tabela}")
    colunas = [linha[0] for linha in cursor.fetchall()]
    cursor.close()
    return colunas


def contar_linhas(conexao, tabela):
    """Retorna quantas linhas existem na tabela."""
    cursor = conexao.cursor()
    cursor.execute(f"SELECT COUNT(*) FROM {tabela}")
    total = cursor.fetchone()[0]
    cursor.close()
    return total


def carregar_csv_na_raw(conexao, caminho_csv, tabela):
    """
    Esvazia a tabela Raw e carrega o CSV em blocos, sem alterar o conteudo.
    Tudo e lido como texto: virgula decimal e datas DD/MM/AAAA ficam como
    estao no arquivo. A carga e feita por posicao de coluna.
    Retorna o total de linhas lidas do CSV.
    """
    colunas = colunas_da_tabela(conexao, tabela)
    lista_colunas = ", ".join(f"`{coluna}`" for coluna in colunas)
    marcadores = ", ".join(["%s"] * len(colunas))
    sql_insert = (
        f"INSERT INTO {tabela} ({lista_colunas}) VALUES ({marcadores})"
    )

    executar(conexao, f"TRUNCATE TABLE {tabela}")

    total_lidas = 0
    blocos = pd.read_csv(
        caminho_csv,
        sep=CSV_SEPARADOR,
        encoding=CSV_ENCODING,
        dtype=str,
        keep_default_na=False,
        chunksize=TAMANHO_BLOCO,
    )
    for bloco in blocos:
        if bloco.shape[1] != len(colunas):
            raise ValueError(
                f"{caminho_csv.name} tem {bloco.shape[1]} colunas, mas "
                f"{tabela} tem {len(colunas)}."
            )
        linhas = list(bloco.itertuples(index=False, name=None))
        for inicio in range(0, len(linhas), LOTE_INSERCAO):
            inserir_em_lote(
                conexao, sql_insert, linhas[inicio:inicio + LOTE_INSERCAO]
            )
        total_lidas += len(linhas)
        print(f"  {tabela}: {total_lidas} linhas carregadas ...")
    return total_lidas


def carregar_todas_as_tabelas(conexao):
    """Carrega os 4 CSVs e retorna a lista de erros (vazia se deu certo)."""
    erros = []
    for nome, info in ARQUIVOS.items():
        tabela = info["tabela_raw"]
        caminho_csv = PASTA_DADOS / info["csv"]
        print(f"\n[{nome}] {caminho_csv.name} -> {tabela}")
        try:
            lidas = carregar_csv_na_raw(conexao, caminho_csv, tabela)
            gravadas = contar_linhas(conexao, tabela)
        except ERROS_ESPERADOS as erro:
            erros.append(f"{tabela}: {erro}")
            logging.error("%s | %s | %s", tabela, caminho_csv.name, erro)
            print(f"  ERRO: {erro}")
            continue
        situacao = "OK" if lidas == gravadas else "DIVERGENTE"
        print(f"  CSV: {lidas} | tabela: {gravadas} -> {situacao}")
        if lidas != gravadas:
            erros.append(f"{tabela}: contagem diferente do CSV")
            logging.error(
                "%s | contagem diferente (CSV=%s, tabela=%s)",
                tabela, lidas, gravadas,)
    return erros


def main():
    """Executa a Fase 1. Retorna 0 se tudo deu certo e 1 se houve erro."""
    conexao = None
    try:
        configurar_log()
        baixar_zip()
        descompactar_zip()
        conexao = conectar()
        erros = carregar_todas_as_tabelas(conexao)
    except ERROS_ESPERADOS as erro:
        logging.error("Erro na extracao: %s", erro)
        print(f"\nErro na extracao: {erro}")
        return 1
    finally:
        if conexao is not None and conexao.is_connected():
            conexao.close()

    if erros:
        print("\nFinalizado com erros:")
        for erro in erros:
            print(f" - {erro}")
        return 1
    print("\nCamada Raw carregada com sucesso.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
    