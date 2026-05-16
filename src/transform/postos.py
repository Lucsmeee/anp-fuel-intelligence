"""
Transformação da dimensão de postos de combustíveis.

Combina os dados cadastrais da ANP (postos.parquet) com o SIMP
(simp_postos.parquet) para enriquecer cada posto com:
- Coordenadas geográficas (latitude/longitude decimal)
- Vinculação ao distribuidor fornecedor
- Status de conformidade PMQC

O join é feito por codigo_isimp, que existe em ambas as fontes.
Como o SIMP tem grain (posto, produto), é deduplicated para uma linha
por posto antes do join.

Saída: data/processed/dim_postos.parquet
"""

from __future__ import annotations

import pandas as pd

from src.config import INTERIM_DIR, PROCESSED_DIR
from src.utils.logging import get_logger

logger = get_logger(__name__)

_OUTPUT = "dim_postos.parquet"


def transform_postos() -> pd.DataFrame:
    """
    Produz a dimensão de postos com coordenadas e vínculo ao distribuidor.
    """
    logger.info("Transformando postos...")

    postos = pd.read_parquet(INTERIM_DIR / "postos.parquet")
    simp = pd.read_parquet(INTERIM_DIR / "simp_postos.parquet")

    logger.info("Postos base: %d | SIMP base: %d linhas", len(postos), len(simp))

    # Deduplica SIMP para uma linha por posto, mantendo lat/lon e vinculacao.
    # Como esses campos são os mesmos para todos os produtos de um posto,
    # basta manter a primeira ocorrência após ordenar por codigo_isimp.
    simp_dedup = (
        simp[["codigo_isimp", "latitude", "longitude",
              "vinculacao_distribuidor", "vinculacao_distribuidor_norm",
              "status_pmqc"]]
        .drop_duplicates(subset=["codigo_isimp"], keep="first")
    )
    logger.info("SIMP deduplicated: %d postos únicos", len(simp_dedup))

    # Left join: mantém todos os postos da ANP mesmo sem SIMP correspondente
    df = postos.merge(simp_dedup, on="codigo_isimp", how="left")

    # Postos sem coordenadas
    sem_coord = df["latitude"].isna().sum()
    if sem_coord:
        logger.warning(
            "%d postos sem coordenadas geográficas (%.1f%%)",
            sem_coord, 100 * sem_coord / len(df),
        )

    # Postos sem vínculo ao distribuidor (esperado para Bandeira Branca)
    sem_vinculo = df["vinculacao_distribuidor"].isna().sum()
    logger.info(
        "Postos com distribuidor vinculado: %d | sem vínculo: %d",
        len(df) - sem_vinculo, sem_vinculo,
    )

    colunas_finais = [
        "codigo_isimp",
        "cnpj",
        "razao_social",
        "bandeira",
        "vinculacao_distribuidor",
        "vinculacao_distribuidor_norm",
        "uf",
        "municipio",
        "municipio_norm",
        "cep",
        "endereco",
        "complemento",
        "bairro",
        "latitude",
        "longitude",
        "status_pmqc",
        "data_publicacao",
        "data_vinculacao",
    ]
    df = df[colunas_finais]

    output = PROCESSED_DIR / _OUTPUT
    df.to_parquet(output, index=False)
    logger.info("dim_postos gravado: %d linhas → %s", len(df), output)

    return df
