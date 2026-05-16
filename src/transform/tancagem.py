"""
Transformação da tabela fato de tancagem.

O interim já traz o snapshot mais recente por tanque (uma linha por
tag de tanque). Esta etapa produz dois artefatos:

1. fct_tancagem_tanques.parquet — granularidade por tanque individual
   (usado para contagem e análise por tipo de unidade/segmento).

2. fct_tancagem_agregada.parquet — capacidade total por
   (cnpj, segmento, grupo_produtos), otimizado para o dashboard de
   capacidade por distribuidora.

Saída:
  data/processed/fct_tancagem_tanques.parquet
  data/processed/fct_tancagem_agregada.parquet
"""

from __future__ import annotations

import pandas as pd

from src.config import INTERIM_DIR, PROCESSED_DIR
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Segmentos do ramo de distribuição (excluem produção/refino)
_SEGMENTOS_DISTRIBUICAO = {
    "BASES DO RAMO DE COMBUSTIVEIS",
    "BASES DO RAMO DE TRR",
    "BASES DO RAMO DE AVIACAO",
    "BASES DO RAMO DE LIQUEFEITOS",
    "TERMINAL",
}


def transform_tancagem() -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Produz a fato de tancagem em dois níveis de granularidade.
    Retorna (df_tanques, df_agregada).
    """
    logger.info("Transformando tancagem...")

    df = pd.read_parquet(INTERIM_DIR / "tancagem.parquet")
    logger.info("Tancagem base: %d tanques", len(df))

    # Flag: instalação pertence ao ramo de distribuição de combustíveis
    df["is_distribuicao"] = df["segmento"].isin(_SEGMENTOS_DISTRIBUICAO)

    dist_count = df["is_distribuicao"].sum()
    logger.info(
        "Tanques em instalações de distribuição: %d (%.1f%%) | "
        "outros segmentos: %d",
        dist_count, 100 * dist_count / len(df), len(df) - dist_count,
    )

    # --- Nível 1: granularidade por tanque individual ---
    tanques = df.copy()

    output_tanques = PROCESSED_DIR / "fct_tancagem_tanques.parquet"
    tanques.to_parquet(output_tanques, index=False)
    logger.info(
        "fct_tancagem_tanques gravado: %d linhas → %s",
        len(tanques), output_tanques,
    )

    # --- Nível 2: agregado por (cnpj, segmento, grupo_produtos) ---
    agregada = (
        df.groupby(
            ["cnpj", "nome_empresarial", "uf", "municipio",
             "segmento", "grupo_produtos", "is_distribuicao"],
            dropna=False,
        )
        .agg(
            qtd_tanques=("tag", "count"),
            tancagem_total_m3=("tancagem_m3", "sum"),
            tancagem_media_m3=("tancagem_m3", "mean"),
            data_referencia=("data", "max"),
        )
        .reset_index()
    )

    output_agregada = PROCESSED_DIR / "fct_tancagem_agregada.parquet"
    agregada.to_parquet(output_agregada, index=False)
    logger.info(
        "fct_tancagem_agregada gravado: %d linhas | "
        "capacidade total: %.0f m³ → %s",
        len(agregada),
        agregada["tancagem_total_m3"].sum(),
        output_agregada,
    )

    return tanques, agregada
