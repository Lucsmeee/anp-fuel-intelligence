-- =============================================================================
-- ANP Fuel Intelligence — Schema Relacional
-- =============================================================================
-- Modelo dimensional simplificado com três entidades principais (postos,
-- distribuidores, tancagem) e tabelas de suporte (SIMP, população).
--
-- Relacionamentos:
--   dim_postos.vinculacao_distribuidor_norm
--       → dim_distribuidores.nome_reduzido_norm   (FK lógica — ver nota abaixo)
--   fct_tancagem_tanques.cnpj
--       → dim_distribuidores.cnpj                 (FK hard)
--   fct_tancagem_agregada.cnpj
--       → dim_distribuidores.cnpj                 (FK hard)
--   fct_simp_postos.codigo_isimp
--       → dim_postos.codigo_isimp                 (FK hard)
--   dim_postos.uf / dim_distribuidores.uf
--       → dim_populacao_uf.uf                     (FK hard)
--
-- Nota sobre FK postos → distribuidores:
--   A vinculação entre postos e distribuidoras usa nome_reduzido_norm como
--   chave de junção (não CNPJ), pois o SIMP registra a marca do fornecedor
--   (ex: 'VIBRA', 'IPIRANGA') e não o CNPJ. Postos sem marca definida
--   trazem 'BANDEIRA BRANCA', que não existe na tabela de distribuidores.
--   Por isso, essa relação é mantida como FK lógica (enforced na aplicação)
--   e não como FOREIGN KEY no banco, para não violar a integridade referencial
--   nos ~47% dos postos sem bandeira definida.
-- =============================================================================

-- Garante schema limpo a cada execução (idempotente)
DROP TABLE IF EXISTS fct_simp_postos      CASCADE;
DROP TABLE IF EXISTS fct_tancagem_agregada CASCADE;
DROP TABLE IF EXISTS fct_tancagem_tanques  CASCADE;
DROP TABLE IF EXISTS dim_postos            CASCADE;
DROP TABLE IF EXISTS dim_distribuidores    CASCADE;
DROP TABLE IF EXISTS dim_populacao_uf      CASCADE;


-- -----------------------------------------------------------------------------
-- dim_populacao_uf
-- Estimativa populacional IBGE 2025 por unidade federativa.
-- Tabela de referência para calcular densidade de infraestrutura por habitante.
-- -----------------------------------------------------------------------------
CREATE TABLE dim_populacao_uf (
    uf                  CHAR(2)         NOT NULL,
    nome_estado         VARCHAR(60)     NOT NULL,
    regiao              VARCHAR(20)     NOT NULL,  -- Norte, Nordeste, Sudeste, Sul, Centro-Oeste
    populacao_estimada  BIGINT          NOT NULL,

    CONSTRAINT pk_populacao_uf PRIMARY KEY (uf)
);

COMMENT ON TABLE  dim_populacao_uf                IS 'Estimativa populacional IBGE 2025 por UF';
COMMENT ON COLUMN dim_populacao_uf.uf             IS 'Sigla da unidade federativa (2 letras)';
COMMENT ON COLUMN dim_populacao_uf.populacao_estimada IS 'Estimativa em 1º de julho de 2025';


-- -----------------------------------------------------------------------------
-- dim_distribuidores
-- Distribuidoras de combustíveis líquidos autorizadas pela ANP.
-- Chave primária: CNPJ (cada linha representa uma pessoa jurídica distinta).
-- Filiais do mesmo grupo econômico aparecem como linhas independentes.
-- -----------------------------------------------------------------------------
CREATE TABLE dim_distribuidores (
    cnpj                CHAR(14)        NOT NULL,   -- 14 dígitos sem formatação
    codigo_agente       VARCHAR(20),                -- código interno ANP do grupo
    codigo_isimp        VARCHAR(20),                -- código no sistema i-SIMP
    nome_reduzido       VARCHAR(200),               -- nome comercial/marca
    nome_reduzido_norm  VARCHAR(200),               -- nome normalizado (uppercase, sem acento)
    razao_social        VARCHAR(400),
    uf                  CHAR(2),
    regiao              VARCHAR(20),
    municipio           VARCHAR(200),
    municipio_norm      VARCHAR(200),
    cep                 CHAR(8),
    endereco            VARCHAR(400),
    bairro              VARCHAR(200),
    situacao            VARCHAR(60),                -- situação atual da autorização
    is_ativa            BOOLEAN         NOT NULL,   -- true = autorizada/habilitada
    inicio_situacao     DATE,
    data_publicacao     DATE,
    tipo_autorizacao    VARCHAR(100),
    numero_autorizacao  VARCHAR(60),

    CONSTRAINT pk_distribuidores PRIMARY KEY (cnpj),
    CONSTRAINT fk_dist_uf FOREIGN KEY (uf) REFERENCES dim_populacao_uf (uf)
);

-- Índice para join com dim_postos via nome da marca.
-- Não é UNIQUE: um mesmo nome_reduzido pode ter múltiplas filiais com CNPJs
-- distintos (ex: ARAPETRO CE, ARAPETRO BA). O join analítico filtra por
-- is_ativa = true para escolher o registro representativo do grupo.
CREATE INDEX idx_dist_nome_norm ON dim_distribuidores (nome_reduzido_norm);

-- Índice para filtros por situação e região
CREATE INDEX idx_dist_is_ativa ON dim_distribuidores (is_ativa);
CREATE INDEX idx_dist_uf       ON dim_distribuidores (uf);

COMMENT ON TABLE  dim_distribuidores              IS 'Distribuidoras de combustíveis autorizadas pela ANP';
COMMENT ON COLUMN dim_distribuidores.cnpj         IS 'CNPJ sem formatação, 14 dígitos com zeros à esquerda';
COMMENT ON COLUMN dim_distribuidores.is_ativa     IS 'True para situação AUTORIZADA, HABILITADA ou similar';
COMMENT ON COLUMN dim_distribuidores.nome_reduzido_norm IS 'Chave de junção lógica com dim_postos.vinculacao_distribuidor_norm';


-- -----------------------------------------------------------------------------
-- dim_postos
-- Revendedores varejistas de combustíveis automotivos registrados na ANP,
-- enriquecidos com coordenadas e vínculo ao distribuidor fornecedor (SIMP).
-- Chave primária: codigo_isimp (identificador único no sistema i-SIMP da ANP).
-- -----------------------------------------------------------------------------
CREATE TABLE dim_postos (
    codigo_isimp                VARCHAR(20)     NOT NULL,
    cnpj                        CHAR(14),
    razao_social                VARCHAR(400),
    bandeira                    VARCHAR(200),           -- marca exibida no posto
    vinculacao_distribuidor     VARCHAR(200),           -- nome do distribuidor fornecedor
    vinculacao_distribuidor_norm VARCHAR(200),          -- normalizado (para join com dim_distribuidores)
    uf                          CHAR(2),
    municipio                   VARCHAR(200),
    municipio_norm              VARCHAR(200),
    cep                         CHAR(8),
    endereco                    VARCHAR(400),
    complemento                 VARCHAR(200),
    bairro                      VARCHAR(200),
    latitude                    NUMERIC(10, 6),         -- WGS84, negativo para Sul
    longitude                   NUMERIC(10, 6),         -- WGS84, negativo para Oeste
    status_pmqc                 VARCHAR(50),            -- conformidade ao programa de qualidade
    data_publicacao             DATE,
    data_vinculacao             DATE,

    CONSTRAINT pk_postos PRIMARY KEY (codigo_isimp),
    CONSTRAINT fk_postos_uf FOREIGN KEY (uf) REFERENCES dim_populacao_uf (uf)
    -- FK lógica: vinculacao_distribuidor_norm → dim_distribuidores.nome_reduzido_norm
    -- Não enforçada no banco; ver nota no cabeçalho do schema.
);

CREATE INDEX idx_postos_cnpj          ON dim_postos (cnpj);
CREATE INDEX idx_postos_uf            ON dim_postos (uf);
CREATE INDEX idx_postos_bandeira      ON dim_postos (bandeira);
CREATE INDEX idx_postos_vinc_norm     ON dim_postos (vinculacao_distribuidor_norm);
CREATE INDEX idx_postos_municipio_norm ON dim_postos (municipio_norm);

COMMENT ON TABLE  dim_postos                         IS 'Postos de combustíveis cadastrados na ANP com coordenadas (SIMP)';
COMMENT ON COLUMN dim_postos.codigo_isimp            IS 'Chave primária: identificador único no sistema i-SIMP';
COMMENT ON COLUMN dim_postos.bandeira                IS 'Marca do posto conforme cadastro ANP';
COMMENT ON COLUMN dim_postos.vinculacao_distribuidor IS 'Nome do distribuidor fornecedor registrado no SIMP';
COMMENT ON COLUMN dim_postos.latitude                IS 'Latitude decimal WGS84 (fonte: SIMP ANP, cobertura 83%)';
COMMENT ON COLUMN dim_postos.status_pmqc             IS 'Status no Programa de Monitoramento da Qualidade de Combustíveis';


-- -----------------------------------------------------------------------------
-- fct_tancagem_tanques
-- Capacidade de armazenagem por tanque físico em instalações autorizadas pela ANP.
-- Granularidade: um tanque (cnpj + cod_instalacao + tag).
-- Snapshot mais recente disponível (abril/2026).
-- Cobre distribuidoras, terminais, refinarias, produtores de etanol/biodiesel.
-- -----------------------------------------------------------------------------
CREATE TABLE fct_tancagem_tanques (
    cnpj                CHAR(14)        NOT NULL,
    cod_instalacao      VARCHAR(20)     NOT NULL,
    tag                 VARCHAR(100)    NOT NULL,
    data                DATE            NOT NULL,   -- data de referência do snapshot
    nome_empresarial    VARCHAR(400),
    uf                  CHAR(2),
    municipio           VARCHAR(200),
    municipio_norm      VARCHAR(200),
    segmento            VARCHAR(100),               -- tipo de instalação
    detalhe_instalacao  VARCHAR(60),                -- ex: EXCLUSIVA, COMPARTILHADA
    tipo_unidade        VARCHAR(50),                -- TANQUE, VASO DE PRESSAO, ESFERA
    grupo_produtos      VARCHAR(100)    NOT NULL DEFAULT 'NAO INFORMADO',
    tancagem_m3         NUMERIC(14, 2),
    is_distribuicao     BOOLEAN         NOT NULL,   -- true = segmento de distribuição

    CONSTRAINT pk_tancagem_tanques PRIMARY KEY (cnpj, cod_instalacao, tag),
    -- Distribuidores presentes na tancagem cobrem ~10% dos CNPJs registrados na ANP.
    -- CNPJs de terminais, refinarias e produtores de etanol/biodiesel não têm
    -- correspondência em dim_distribuidores e por isso esta FK não é enforçada.
    -- CONSTRAINT fk_tanc_dist FOREIGN KEY (cnpj) REFERENCES dim_distribuidores (cnpj)
    CONSTRAINT fk_tanc_uf FOREIGN KEY (uf) REFERENCES dim_populacao_uf (uf)
);

CREATE INDEX idx_tanc_cnpj      ON fct_tancagem_tanques (cnpj);
CREATE INDEX idx_tanc_segmento  ON fct_tancagem_tanques (segmento);
CREATE INDEX idx_tanc_uf        ON fct_tancagem_tanques (uf);
CREATE INDEX idx_tanc_is_dist   ON fct_tancagem_tanques (is_distribuicao);

COMMENT ON TABLE  fct_tancagem_tanques             IS 'Capacidade por tanque físico (snapshot abril/2026)';
COMMENT ON COLUMN fct_tancagem_tanques.tancagem_m3 IS 'Capacidade nominal em metros cúbicos';
COMMENT ON COLUMN fct_tancagem_tanques.is_distribuicao IS 'True para segmentos do ramo de distribuição de combustíveis';


-- -----------------------------------------------------------------------------
-- fct_tancagem_agregada
-- Capacidade total de armazenagem agregada por empresa, segmento e grupo de
-- produtos. Otimizada para consultas analíticas de capacidade instalada.
-- -----------------------------------------------------------------------------
CREATE TABLE fct_tancagem_agregada (
    cnpj                VARCHAR(14)     NOT NULL,
    segmento            VARCHAR(100)    NOT NULL,
    grupo_produtos      VARCHAR(100)    NOT NULL,
    nome_empresarial    VARCHAR(400),
    uf                  CHAR(2),
    municipio           VARCHAR(200),
    is_distribuicao     BOOLEAN         NOT NULL,
    qtd_tanques         INTEGER         NOT NULL,
    tancagem_total_m3   NUMERIC(16, 2),
    tancagem_media_m3   NUMERIC(14, 2),
    data_referencia     DATE,

    CONSTRAINT pk_tancagem_agregada PRIMARY KEY (cnpj, segmento, grupo_produtos)
);

CREATE INDEX idx_tanc_agr_cnpj     ON fct_tancagem_agregada (cnpj);
CREATE INDEX idx_tanc_agr_uf       ON fct_tancagem_agregada (uf);
CREATE INDEX idx_tanc_agr_is_dist  ON fct_tancagem_agregada (is_distribuicao);

COMMENT ON TABLE  fct_tancagem_agregada IS 'Capacidade agregada por empresa + segmento + produto (para dashboards)';


-- -----------------------------------------------------------------------------
-- fct_simp_postos
-- Capacidade de tancagem e número de bicos por produto em cada posto.
-- Granularidade: (posto, produto) — permite análise por tipo de combustível.
-- -----------------------------------------------------------------------------
CREATE TABLE fct_simp_postos (
    codigo_isimp    VARCHAR(20)     NOT NULL,
    produto         VARCHAR(200),
    produto_norm    VARCHAR(200),
    tancagem_m3     NUMERIC(12, 2),
    qtde_bico       NUMERIC(8, 0),

    CONSTRAINT pk_simp_postos PRIMARY KEY (codigo_isimp, produto),
    CONSTRAINT fk_simp_postos FOREIGN KEY (codigo_isimp) REFERENCES dim_postos (codigo_isimp)
);

CREATE INDEX idx_simp_produto_norm ON fct_simp_postos (produto_norm);

COMMENT ON TABLE  fct_simp_postos             IS 'Capacidade e bicos por produto em cada posto (fonte: SIMP ANP)';
COMMENT ON COLUMN fct_simp_postos.produto     IS 'Nome do produto conforme SIMP (ex: GASOLINA C COMUM, ETANOL HIDRATADO)';
COMMENT ON COLUMN fct_simp_postos.tancagem_m3 IS 'Capacidade total do produto no posto em metros cúbicos';
COMMENT ON COLUMN fct_simp_postos.qtde_bico   IS 'Quantidade de bicos abastecedores para o produto';
