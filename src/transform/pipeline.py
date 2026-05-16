"""
Orquestrador da camada de transformação.

Executa todas as transformações em sequência e reporta um resumo.
Deve ser chamado após a extração estar completa (todos os parquets
de interim disponíveis).

Execute diretamente:

    python -m src.transform.pipeline
"""

from __future__ import annotations

import time

from src.utils.logging import get_logger
from src.transform.postos import transform_postos
from src.transform.distribuidores import transform_distribuidores
from src.transform.tancagem import transform_tancagem
from src.transform.simp import transform_simp

logger = get_logger(__name__)


def run_transform() -> dict[str, int]:
    """
    Executa todas as transformações e retorna contagem de linhas por artefato.
    """
    inicio = time.perf_counter()
    logger.info("=== Iniciando transformação completa ===")

    resultados: dict[str, int] = {}

    # Dimensões
    df_postos = transform_postos()
    resultados["dim_postos"] = len(df_postos)

    df_dist = transform_distribuidores()
    resultados["dim_distribuidores"] = len(df_dist)

    # Fatos
    df_tanques, df_tanc_agr = transform_tancagem()
    resultados["fct_tancagem_tanques"] = len(df_tanques)
    resultados["fct_tancagem_agregada"] = len(df_tanc_agr)

    df_simp = transform_simp()
    resultados["fct_simp_postos"] = len(df_simp)

    duracao = time.perf_counter() - inicio
    logger.info("=== Transformação concluída em %.1fs ===", duracao)
    logger.info("Resumo: %s", resultados)

    return resultados


if __name__ == "__main__":
    run_transform()
