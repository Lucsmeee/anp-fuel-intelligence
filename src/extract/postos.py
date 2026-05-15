"""
Extração e limpeza estrutural do cadastro de revendedores varejistas
de combustíveis automotivos (postos) da ANP.

Lê o CSV oficial da ANP em modo local (a partir de DATA_LOCAL_PATH)
ou via download direto do endpoint público. Aplica padronizações
ortográficas e de tipo, mas NÃO faz modelagem dimensional — isso
é responsabilidade do módulo transform.

Saída: data/interim/postos.parquet
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import pandas as pd
import requests
from unidecode import unidecode

from src.config import (
    ANP_URLS,
    DATA_LOCAL_PATH,
    EXTRACT_MODE,
    INTERIM_DIR,
    RAW_DIR,
)
from src.utils.cnpj import normalize_cnpj
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Arquivo de origem dentro de DATA_LOCAL_PATH no modo from_local
_LOCAL_FILENAME = (
    "Dados Cadastrais dos Revendedores Varejistas de Combustíveis Automotivos/"
    "dados-cadastrais-revendedores-varejistas-combustiveis-automoveis.csv"
)

_RAW_FILENAME = "postos_anp.csv"
_INTERIM_FILENAME = "postos.parquet"

# UFs oficiais para validação
_UFS_VALIDAS = {
    "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA",
    "MG", "MS", "MT", "PA", "PB", "PE", "PI", "PR", "RJ", "RN",
    "RO", "RR", "RS", "SC", "SE", "SP", "TO",
}


def _resolve_source_path(mode: str) -> Path:
    """Decide de onde ler o CSV bruto conforme o modo configurado."""
    if mode == "from_local":
        path = DATA_LOCAL_PATH / _LOCAL_FILENAME
        if not path.exists():
            raise FileNotFoundError(
                f"Arquivo local não encontrado: {path}. "
                f"Confira DATA_LOCAL_PATH no .env."
            )
        return path

    if mode == "download":
        path = RAW_DIR / _RAW_FILENAME
        if path.exists():
            logger.info("Arquivo já existente em %s, pulando download", path)
            return path
        url = ANP_URLS["postos"]
        logger.info("Baixando postos de %s", url)
        response = requests.get(url, timeout=60)
        response.raise_for_status()
        path.write_bytes(response.content)
        logger.info("Download concluído em %s (%d bytes)", path, len(response.content))
        return path

    raise ValueError(f"EXTRACT_MODE inválido: {mode!r}")


def _normalize_text(value: str | None) -> str | None:
    """Uppercase, remove acentos e espaços extras. Mantém None."""
    if value is None or pd.isna(value):
        return None
    return unidecode(str(value)).upper().strip()


def extract_postos(mode: Literal["from_local", "download"] | None = None) -> pd.DataFrame:
    """
    Lê o CSV de postos da ANP, aplica padronizações estruturais e devolve
    um DataFrame limpo. Também persiste o resultado em parquet.
    """
    mode = mode or EXTRACT_MODE
    source = _resolve_source_path(mode)
    logger.info("Lendo postos de %s", source)

    # dtype=str para todas as colunas: CNPJ e CEP não podem ser inferidos
    # como inteiros (perderiam leading zeros ou precisão).
    df = pd.read_csv(
        source,
        sep=";",
        encoding="utf-8",
        dtype=str,
        keep_default_na=True,
    )
    n_inicial = len(df)
    logger.info("Lidas %d linhas brutas", n_inicial)

    # CNPJ normalizado (string de 14 dígitos ou None)
    df["cnpj"] = df["CNPJ"].apply(normalize_cnpj)
    invalidos = df["cnpj"].isna().sum()
    if invalidos:
        logger.warning("Descartando %d linhas com CNPJ inválido", invalidos)
        df = df.dropna(subset=["cnpj"])

    # CEP: 8 dígitos com zero à esquerda
    df["cep"] = df["CEP"].str.zfill(8).where(df["CEP"].notna())

    # UF: maiúsculas e validação
    df["uf"] = df["UF"].str.upper().str.strip()
    uf_invalida = ~df["uf"].isin(_UFS_VALIDAS) & df["uf"].notna()
    if uf_invalida.any():
        logger.warning("Descartando %d linhas com UF inválida", uf_invalida.sum())
        df = df[~uf_invalida]

    # Município: versão original (para dashboard) e normalizada (para joins)
    df["municipio"] = df["MUNICIPIO"].str.strip()
    df["municipio_norm"] = df["municipio"].apply(_normalize_text)

    # Datas em formato BR; valores inválidos viram NaT em vez de quebrar
    df["data_publicacao"] = pd.to_datetime(
        df["DATAPUBLICACAO"], format="%d/%m/%Y", errors="coerce"
    )
    df["data_vinculacao"] = pd.to_datetime(
        df["DATAVINCULACAO"], format="%d/%m/%Y", errors="coerce"
    )

    # Renomeia o restante para snake_case
    df = df.rename(
        columns={
            "CODIGOISIMP": "codigo_isimp",
            "AUTORIZACAO": "autorizacao",
            "RAZAOSOCIAL": "razao_social",
            "ENDERECO": "endereco",
            "COMPLEMENTO": "complemento",
            "BAIRRO": "bairro",
            "BANDEIRA": "bandeira",
        }
    )

    colunas_finais = [
        "codigo_isimp", "autorizacao", "data_publicacao",
        "razao_social", "cnpj",
        "endereco", "complemento", "bairro", "cep",
        "uf", "municipio", "municipio_norm",
        "bandeira", "data_vinculacao",
    ]
    df = df[colunas_finais]

    # Deduplicação por CNPJ (postos com múltiplos registros mantêm o mais recente)
    duplicados = df.duplicated(subset=["cnpj"]).sum()
    if duplicados:
        logger.warning("Removendo %d CNPJs duplicados (mantendo mais recente)", duplicados)
        df = (
            df.sort_values("data_publicacao", ascending=False, na_position="last")
              .drop_duplicates(subset=["cnpj"], keep="first")
        )

    n_final = len(df)
    logger.info("Postos prontos: %d linhas (descartadas %d)", n_final, n_inicial - n_final)

    # Persiste em parquet (preserva dtypes, compressão ~10x melhor que CSV)
    output = INTERIM_DIR / _INTERIM_FILENAME
    df.to_parquet(output, index=False)
    logger.info("Gravado em %s", output)

    return df


if __name__ == "__main__":
    extract_postos()