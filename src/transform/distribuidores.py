"""
Transformação da dimensão de distribuidores de combustíveis.

Lê distribuidores.parquet e produz a dimensão final com:
- Flag de situação ativa (agrupa variantes de 'autorizada')
- Campo de macrorregião inferido da UF da sede
- Deduplicação por CNPJ (mantém o registro mais recente em caso de
  múltiplos registros para o mesmo CNPJ)

Saída: data/processed/dim_distribuidores.parquet
"""

from __future__ import annotations

import pandas as pd

from src.config import INTERIM_DIR, PROCESSED_DIR
from src.utils.logging import get_logger

logger = get_logger(__name__)

_OUTPUT = "dim_distribuidores.parquet"

# Situações consideradas ativas para fins analíticos
_SITUACOES_ATIVAS = {
    "AUTORIZADA",
    "AUTORIZADA POR DECISAO JUDICIAL",
    "HABILITADA",
}

_UF_TO_REGIAO: dict[str, str] = {
    "RO": "Norte", "AC": "Norte", "AM": "Norte", "RR": "Norte",
    "PA": "Norte", "AP": "Norte", "TO": "Norte",
    "MA": "Nordeste", "PI": "Nordeste", "CE": "Nordeste",
    "RN": "Nordeste", "PB": "Nordeste", "PE": "Nordeste",
    "AL": "Nordeste", "SE": "Nordeste", "BA": "Nordeste",
    "MG": "Sudeste", "ES": "Sudeste", "RJ": "Sudeste", "SP": "Sudeste",
    "PR": "Sul", "SC": "Sul", "RS": "Sul",
    "MS": "Centro-Oeste", "MT": "Centro-Oeste",
    "GO": "Centro-Oeste", "DF": "Centro-Oeste",
}


def transform_distribuidores() -> pd.DataFrame:
    """
    Produz a dimensão de distribuidores com flag de situação ativa e
    macrorregião. Mantém todos os registros (histórico incluso) para
    auditoria; filtros por is_ativa ficam nas queries analíticas.
    """
    logger.info("Transformando distribuidores...")

    df = pd.read_parquet(INTERIM_DIR / "distribuidores.parquet")
    logger.info("Distribuidores base: %d linhas", len(df))

    # Flag de situação ativa
    df["is_ativa"] = df["situacao"].isin(_SITUACOES_ATIVAS)

    # Macrorregião da sede
    df["regiao"] = df["uf"].map(_UF_TO_REGIAO)

    # Deduplicação por CNPJ: em caso de múltiplos registros para o mesmo
    # CNPJ (ex: mudança de situação), mantém o mais recente por data_publicacao
    n_antes = len(df)
    df = (
        df.sort_values("data_publicacao", ascending=False, na_position="last")
          .drop_duplicates(subset=["cnpj"], keep="first")
    )
    n_removidos = n_antes - len(df)
    if n_removidos:
        logger.info(
            "Deduplicação por CNPJ: %d registros removidos", n_removidos
        )

    ativas = df["is_ativa"].sum()
    logger.info(
        "dim_distribuidores: %d total | %d ativas | %d inativas/históricas",
        len(df), ativas, len(df) - ativas,
    )

    colunas_finais = [
        "cnpj",
        "codigo_agente",
        "codigo_isimp",
        "nome_reduzido",
        "nome_reduzido_norm",
        "razao_social",
        "uf",
        "regiao",
        "municipio",
        "municipio_norm",
        "cep",
        "endereco",
        "bairro",
        "situacao",
        "is_ativa",
        "inicio_situacao",
        "data_publicacao",
        "tipo_autorizacao",
        "numero_autorizacao",
    ]
    df = df[colunas_finais]

    output = PROCESSED_DIR / _OUTPUT
    df.to_parquet(output, index=False)
    logger.info("dim_distribuidores gravado: %d linhas → %s", len(df), output)

    return df
