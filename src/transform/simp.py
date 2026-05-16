"""
Transformação da tabela fato do SIMP de postos.

Agrega os dados por (codigo_isimp, produto) para produzir a capacidade
de tancagem e quantidade de bicos por combustível em cada posto.

Este é o detalhe que permite responder perguntas como:
"Qual a capacidade de etanol dos postos VIBRA em SP?"

Saída: data/processed/fct_simp_postos.parquet
"""

from __future__ import annotations

import pandas as pd

from src.config import INTERIM_DIR, PROCESSED_DIR
from src.utils.logging import get_logger

logger = get_logger(__name__)

_OUTPUT = "fct_simp_postos.parquet"


def transform_simp() -> pd.DataFrame:
    """
    Agrega o SIMP por (codigo_isimp, produto) e produz a tabela fato de
    capacidade dos postos.
    """
    logger.info("Transformando SIMP postos...")

    df = pd.read_parquet(INTERIM_DIR / "simp_postos.parquet")
    logger.info("SIMP base: %d linhas", len(df))

    # Agrega por posto e produto: soma tancagem e bicos
    fato = (
        df.groupby(["codigo_isimp", "produto", "produto_norm"], dropna=False)
        .agg(
            tancagem_m3=("tancagem_m3", "sum"),
            qtde_bico=("qtde_bico", "sum"),
        )
        .reset_index()
    )

    n_postos = fato["codigo_isimp"].nunique()
    n_produtos = fato["produto_norm"].nunique()
    logger.info(
        "fct_simp_postos: %d linhas | %d postos | %d produtos distintos",
        len(fato), n_postos, n_produtos,
    )

    output = PROCESSED_DIR / _OUTPUT
    fato.to_parquet(output, index=False)
    logger.info("fct_simp_postos gravado: %d linhas → %s", len(fato), output)

    return fato
