"""
Orquestrador da camada de extração.

Executa os quatro extratores em sequência e reporta um resumo ao final.
Execute diretamente:

    python -m src.extract.pipeline

Ou importe run_extract() para chamar de outros módulos.
"""

from __future__ import annotations

import time

from src.utils.logging import get_logger
from src.extract.postos import extract_postos
from src.extract.distribuidoes import extract_distribuidores
from src.extract.tancagem import extract_tancagem
from src.extract.simp import extract_simp
from src.extract.populacao import extract_populacao

logger = get_logger(__name__)


def run_extract() -> dict[str, int]:
    """
    Executa todos os extratores e retorna um dicionário com o número de
    linhas produzido por cada fonte.
    """
    inicio = time.perf_counter()
    logger.info("=== Iniciando extração completa ===")

    resultados: dict[str, int] = {}

    etapas = [
        ("postos", extract_postos),
        ("distribuidores", extract_distribuidores),
        ("tancagem", extract_tancagem),
        ("simp_postos", extract_simp),
        ("populacao_uf", extract_populacao),
    ]

    for nome, fn in etapas:
        t0 = time.perf_counter()
        logger.info("--- Extraindo: %s ---", nome)
        df = fn()
        resultados[nome] = len(df)
        logger.info(
            "    %s concluído: %d linhas (%.1fs)",
            nome, len(df), time.perf_counter() - t0,
        )

    duracao = time.perf_counter() - inicio
    logger.info("=== Extração concluída em %.1fs ===", duracao)
    logger.info("Resumo: %s", resultados)

    return resultados


if __name__ == "__main__":
    run_extract()
