"""
Configuração centralizada de logging do projeto.

Uso:
    from src.utils.logging import get_logger
    logger = get_logger(__name__)
    logger.info("mensagem")
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from src.config import LOGS_DIR

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_configured = False


def _configure_root_logger() -> None:
    """Configura o logger raiz uma única vez por execução."""
    global _configured
    if _configured:
        return

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    # Saída no console (stdout)
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    root.addHandler(stream_handler)

    # Saída em arquivo rotativo (mantém histórico, evita arquivo gigante)
    file_handler = RotatingFileHandler(
        LOGS_DIR / "pipeline.log",
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Devolve um logger nomeado, configurado de forma idempotente."""
    _configure_root_logger()
    return logging.getLogger(name)