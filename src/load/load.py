"""
Carga dos dados processados no PostgreSQL.

Executa o schema.sql para (re)criar as tabelas e em seguida carrega
cada parquet processado via SQLAlchemy. A operação é idempotente:
rodar novamente sobrescreve os dados sem erros.

Ordem de carga respeita dependências de FK:
  1. dim_populacao_uf
  2. dim_distribuidores
  3. dim_postos
  4. fct_tancagem_tanques
  5. fct_tancagem_agregada
  6. fct_simp_postos
"""

from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

from src.config import PROCESSED_DIR, REFERENCE_DIR, SQL_DIR, get_db_url
from src.utils.logging import get_logger

logger = get_logger(__name__)

_SCHEMA_FILE = SQL_DIR / "schema.sql"

# Mapeamento: nome da tabela → arquivo parquet de origem
# Ordem importa: respeita FK (dim antes de fct)
_TABELAS: list[tuple[str, Path]] = [
    ("dim_populacao_uf",      REFERENCE_DIR / "populacao_uf.parquet"),
    ("dim_distribuidores",    PROCESSED_DIR / "dim_distribuidores.parquet"),
    ("dim_postos",            PROCESSED_DIR / "dim_postos.parquet"),
    ("fct_tancagem_tanques",  PROCESSED_DIR / "fct_tancagem_tanques.parquet"),
    ("fct_tancagem_agregada", PROCESSED_DIR / "fct_tancagem_agregada.parquet"),
    ("fct_simp_postos",       PROCESSED_DIR / "fct_simp_postos.parquet"),
]


def _execute_schema(engine) -> None:
    """Executa o schema.sql para (re)criar todas as tabelas."""
    sql = _SCHEMA_FILE.read_text(encoding="utf-8")
    logger.info("Executando schema.sql...")
    with engine.begin() as conn:
        conn.execute(text(sql))
    logger.info("Schema aplicado com sucesso.")


def _load_table(engine, tabela: str, parquet_path: Path) -> int:
    """
    Carrega um parquet em uma tabela PostgreSQL via INSERT em lotes.
    Retorna o número de linhas inseridas.
    """
    df = pd.read_parquet(parquet_path)

    # Converte colunas datetime64 para date quando o dtype é só data
    # (evita que SQLAlchemy tente inserir TIMESTAMP em colunas DATE)
    for col in df.select_dtypes(include=["datetime64[ns]"]).columns:
        df[col] = df[col].dt.date

    # Int64 nullable → int64 padrão para compatibilidade com psycopg2
    for col in df.select_dtypes(include=["Int64"]).columns:
        df[col] = df[col].astype("int64", errors="ignore")

    n = len(df)
    logger.info("Carregando %s: %d linhas...", tabela, n)

    t0 = time.perf_counter()
    df.to_sql(
        name=tabela,
        con=engine,
        if_exists="append",    # schema já criado pelo schema.sql
        index=False,
        method="multi",        # INSERT multi-row (mais rápido que um por um)
        chunksize=2_000,       # lotes de 2k linhas
    )
    elapsed = time.perf_counter() - t0

    logger.info(
        "    %s carregado: %d linhas em %.1fs (%.0f linhas/s)",
        tabela, n, elapsed, n / elapsed if elapsed > 0 else 0,
    )
    return n


def run_load() -> dict[str, int]:
    """
    Aplica o schema e carrega todos os parquets processados no PostgreSQL.
    Retorna um dicionário com a contagem de linhas por tabela.
    """
    inicio = time.perf_counter()
    logger.info("=== Iniciando carga no PostgreSQL ===")

    engine = create_engine(get_db_url(), future=True)

    # Testa conexão antes de prosseguir
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Conexão com PostgreSQL estabelecida.")
    except Exception as exc:
        logger.error(
            "Falha ao conectar ao PostgreSQL: %s\n"
            "Verifique as variáveis DB_* no arquivo .env.",
            exc,
        )
        raise

    _execute_schema(engine)

    resultados: dict[str, int] = {}
    for tabela, parquet_path in _TABELAS:
        resultados[tabela] = _load_table(engine, tabela, parquet_path)

    duracao = time.perf_counter() - inicio
    total = sum(resultados.values())
    logger.info(
        "=== Carga concluída: %d linhas em %.1fs ===", total, duracao
    )
    logger.info("Resumo: %s", resultados)

    return resultados


if __name__ == "__main__":
    run_load()
