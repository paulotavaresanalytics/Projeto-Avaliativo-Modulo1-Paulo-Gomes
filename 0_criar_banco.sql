-- ============================================================
-- 0_criar_banco.sql
-- Fase 0 - Cria o database e as tabelas das camadas Raw e Silver
-- Projeto: Pipeline Medallion - Viagens a Servico (Portal da Transparencia)
--
-- Execucao (na raiz do projeto, no PowerShell):
--   & "$base\bin\mysql" -u root -p --default-character-set=utf8mb4 -e "source 0_criar_banco.sql"
--
-- O script e idempotente: pode ser rodado varias vezes (recria tudo).
-- ============================================================

CREATE DATABASE IF NOT EXISTS transparencia
    DEFAULT CHARACTER SET utf8mb4;

USE transparencia;


-- ------------------------------------------------------------
-- Limpeza (ordem: filhas primeiro, para respeitar as FKs)
-- ------------------------------------------------------------
DROP TABLE IF EXISTS silver_trecho;
DROP TABLE IF EXISTS silver_pagamento;
DROP TABLE IF EXISTS silver_passagem;
DROP TABLE IF EXISTS silver_viagem;

DROP TABLE IF EXISTS raw_trecho;
DROP TABLE IF EXISTS raw_passagem;
DROP TABLE IF EXISTS raw_pagamento;
DROP TABLE IF EXISTS raw_viagem;


-- ============================================================
-- CAMADA RAW
-- Copia fiel dos CSVs: todas as colunas VARCHAR, sem constraints.
-- As colunas seguem a MESMA ORDEM do cabecalho de cada CSV
-- (a carga em 1_extrair.py pode ser feita por posicao).
-- Valores (virgula decimal) e datas (DD/MM/AAAA) ficam como texto.
-- ============================================================

-- 2025_Viagem.csv (22 colunas)
CREATE TABLE raw_viagem (
    id_viagem               VARCHAR(20),    -- Identificador do processo de viagem
    num_proposta            VARCHAR(20),    -- Numero da Proposta (PCDP)
    situacao                VARCHAR(50),    -- Situacao
    viagem_urgente          VARCHAR(10),    -- Viagem Urgente
    justificativa_urgencia  VARCHAR(1000),  -- Justificativa Urgencia Viagem
    cod_orgao_superior      VARCHAR(20),    -- Codigo do orgao superior
    nome_orgao_superior     VARCHAR(255),   -- Nome do orgao superior
    cod_orgao_solicitante   VARCHAR(20),    -- Codigo orgao solicitante
    nome_orgao_solicitante  VARCHAR(255),   -- Nome orgao solicitante
    cpf_viajante            VARCHAR(20),    -- CPF viajante
    nome_viajante           VARCHAR(255),   -- Nome
    cargo                   VARCHAR(255),   -- Cargo
    funcao                  VARCHAR(255),   -- Funcao
    descricao_funcao        VARCHAR(255),   -- Descricao Funcao
    data_inicio             VARCHAR(20),    -- Periodo - Data de inicio
    data_fim                VARCHAR(20),    -- Periodo - Data de fim
    destinos                VARCHAR(4000),  -- Destinos
    motivo                  VARCHAR(4000),  -- Motivo
    valor_diarias           VARCHAR(30),    -- Valor diarias
    valor_passagens         VARCHAR(30),    -- Valor passagens
    valor_devolucao         VARCHAR(30),    -- Valor devolucao
    valor_outros_gastos     VARCHAR(30)     -- Valor outros gastos
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

-- 2025_Pagamento.csv (10 colunas)
CREATE TABLE raw_pagamento (
    id_viagem               VARCHAR(20),    -- Identificador do processo de viagem
    num_proposta            VARCHAR(20),    -- Numero da Proposta (PCDP)
    cod_orgao_superior      VARCHAR(20),    -- Codigo do orgao superior
    nome_orgao_superior     VARCHAR(255),   -- Nome do orgao superior
    cod_orgao_pagador       VARCHAR(20),    -- Codigo do orgao pagador
    nome_orgao_pagador      VARCHAR(255),   -- Nome do orgao pagador
    cod_ug_pagadora         VARCHAR(20),    -- Codigo da unidade gestora pagadora
    nome_ug_pagadora        VARCHAR(255),   -- Nome da unidade gestora pagadora
    tipo_pagamento          VARCHAR(100),   -- Tipo de pagamento
    valor                   VARCHAR(30)     -- Valor
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

-- 2025_Passagem.csv (19 colunas)
CREATE TABLE raw_passagem (
    id_viagem               VARCHAR(20),    -- Identificador do processo de viagem
    num_proposta            VARCHAR(20),    -- Numero da Proposta (PCDP)
    meio_transporte         VARCHAR(50),    -- Meio de transporte
    pais_origem_ida         VARCHAR(100),   -- Pais - Origem ida
    uf_origem_ida           VARCHAR(100),   -- UF - Origem ida
    cidade_origem_ida       VARCHAR(255),   -- Cidade - Origem ida
    pais_destino_ida        VARCHAR(100),   -- Pais - Destino ida
    uf_destino_ida          VARCHAR(100),   -- UF - Destino ida
    cidade_destino_ida      VARCHAR(255),   -- Cidade - Destino ida
    pais_origem_volta       VARCHAR(100),   -- Pais - Origem volta
    uf_origem_volta         VARCHAR(100),   -- UF - Origem volta
    cidade_origem_volta     VARCHAR(255),   -- Cidade - Origem volta
    pais_destino_volta      VARCHAR(100),   -- Pais - Destino volta
    uf_destino_volta        VARCHAR(100),   -- UF - Destino volta
    cidade_destino_volta    VARCHAR(255),   -- Cidade - Destino volta
    valor_passagem          VARCHAR(30),    -- Valor da passagem
    taxa_servico            VARCHAR(30),    -- Taxa de servico
    data_emissao            VARCHAR(20),    -- Data da emissao/compra
    hora_emissao            VARCHAR(20)     -- Hora da emissao/compra
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

-- 2025_Trecho.csv (14 colunas)
-- Obs.: o cabecalho do CSV traz um espaco no fim de "Identificador do processo de viagem ".
CREATE TABLE raw_trecho (
    id_viagem               VARCHAR(20),    -- Identificador do processo de viagem
    num_proposta            VARCHAR(20),    -- Numero da Proposta (PCDP)
    sequencia_trecho        VARCHAR(10),    -- Sequencia Trecho
    origem_data             VARCHAR(20),    -- Origem - Data
    origem_pais             VARCHAR(100),   -- Origem - Pais
    origem_uf               VARCHAR(100),   -- Origem - UF
    origem_cidade           VARCHAR(255),   -- Origem - Cidade
    destino_data            VARCHAR(20),    -- Destino - Data
    destino_pais            VARCHAR(100),   -- Destino - Pais
    destino_uf              VARCHAR(100),   -- Destino - UF
    destino_cidade          VARCHAR(255),   -- Destino - Cidade
    meio_transporte         VARCHAR(50),    -- Meio de transporte
    numero_diarias          VARCHAR(30),    -- Numero Diarias
    missao                  VARCHAR(10)     -- Missao?
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;


-- ============================================================
-- CAMADA SILVER
-- Dados tipados, com PK, FK e 2 constraints por tabela.
-- ============================================================

-- Tabela pai: uma linha por viagem.
-- Constraint 1: NOT NULL em nome_orgao_superior
-- Constraint 2: CHECK valor_diarias >= 0
CREATE TABLE silver_viagem (
    id_viagem            VARCHAR(20)    NOT NULL,
    num_proposta         VARCHAR(20),
    situacao             VARCHAR(50),
    viagem_urgente       VARCHAR(5),
    cod_orgao_superior   VARCHAR(20),
    nome_orgao_superior  VARCHAR(255)   NOT NULL,
    nome_viajante        VARCHAR(255),
    cargo                VARCHAR(255),
    data_inicio          DATE,
    data_fim             DATE,
    destinos             VARCHAR(4000),
    motivo               VARCHAR(4000),
    valor_diarias        DECIMAL(10, 2),
    valor_passagens      DECIMAL(10, 2),
    valor_devolucao      DECIMAL(10, 2),
    valor_outros_gastos  DECIMAL(10, 2),
    valor_total          DECIMAL(12, 2),
    duracao_dias         INT,
    PRIMARY KEY (id_viagem),
    CONSTRAINT chk_viagem_valor_diarias CHECK (valor_diarias >= 0)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

-- Constraint 1: CHECK valor_passagem >= 0
-- Constraint 2: CHECK taxa_servico >= 0
CREATE TABLE silver_passagem (
    id_passagem          INT            NOT NULL AUTO_INCREMENT,
    id_viagem            VARCHAR(20)    NOT NULL,
    meio_transporte      VARCHAR(50),
    pais_origem_ida      VARCHAR(60),
    uf_origem_ida        VARCHAR(40),
    cidade_origem_ida    VARCHAR(80),
    pais_destino_ida     VARCHAR(60),
    uf_destino_ida       VARCHAR(40),
    cidade_destino_ida   VARCHAR(80),
    valor_passagem       DECIMAL(10, 2),
    taxa_servico         DECIMAL(10, 2),
    data_emissao         DATE,
    PRIMARY KEY (id_passagem),
    CONSTRAINT fk_passagem_viagem FOREIGN KEY (id_viagem)
        REFERENCES silver_viagem (id_viagem),
    CONSTRAINT chk_passagem_valor CHECK (valor_passagem >= 0),
    CONSTRAINT chk_passagem_taxa CHECK (taxa_servico >= 0)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

-- Constraint 1: CHECK valor >= 0
-- Constraint 2: NOT NULL em tipo_pagamento
CREATE TABLE silver_pagamento (
    id_pagamento         INT            NOT NULL AUTO_INCREMENT,
    id_viagem            VARCHAR(20)    NOT NULL,
    num_proposta         VARCHAR(20),
    nome_orgao_pagador   VARCHAR(255),
    nome_ug_pagadora     VARCHAR(255),
    tipo_pagamento       VARCHAR(50)    NOT NULL,
    valor                DECIMAL(10, 2),
    PRIMARY KEY (id_pagamento),
    CONSTRAINT fk_pagamento_viagem FOREIGN KEY (id_viagem)
        REFERENCES silver_viagem (id_viagem),
    CONSTRAINT chk_pagamento_valor CHECK (valor >= 0)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

-- Constraint 1: CHECK numero_diarias >= 0
-- Constraint 2: UNIQUE (id_viagem, sequencia_trecho)
CREATE TABLE silver_trecho (
    id_trecho            INT            NOT NULL AUTO_INCREMENT,
    id_viagem            VARCHAR(20)    NOT NULL,
    sequencia_trecho     INT,
    origem_data          DATE,
    origem_uf            VARCHAR(40),
    origem_cidade        VARCHAR(80),
    destino_data         DATE,
    destino_uf           VARCHAR(40),
    destino_cidade       VARCHAR(80),
    meio_transporte      VARCHAR(50),
    numero_diarias       DECIMAL(10, 2),
    PRIMARY KEY (id_trecho),
    CONSTRAINT fk_trecho_viagem FOREIGN KEY (id_viagem)
        REFERENCES silver_viagem (id_viagem),
    CONSTRAINT chk_trecho_diarias CHECK (numero_diarias >= 0),
    CONSTRAINT uq_trecho_viagem_seq UNIQUE (id_viagem, sequencia_trecho)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;
