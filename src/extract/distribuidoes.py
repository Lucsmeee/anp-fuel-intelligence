"""
Extração e limpeza do cadastro de distribuidores do ramo de combustíveis
líquidos da ANP (autorização AEA - Autorização de Exercício de Atividade).

Lê o CSV oficial (planilha-aea-filiais.csv) em CP1252, descartando o
cabeçalho de relatório que precede o header real. Mantém todas as
situações (autorizadas, canceladas, revogadas) para fins de auditoria;
filtros por situação ativa ficam a cargo das views analíticas.

Saída: data/interim/distribuidores.parquet
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

_LOCAL_FILENAME = (
    "Dados abertos - Distribuidores de Combustíveis Líquidos/"
    "Distribuidores de combustíveis líquidos autorizados ao exercício da atividade/"
    "planilha-aea-filiais.csv"
)
_RAW_FILENAME = "distribuidores_anp.csv"
_INTERIM_FILENAME = "distribuidores.parquet"

# Linhas iniciais que devem ser puladas (cabeçalho de relatório ANP)
_SKIPROWS = 4

_UFS_VALIDAS = {
    "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA",
    "MG", "MS", "MT", "PA", "PB", "PE", "PI", "PR", "RJ", "RN",
    "RO", "RR", "RS", "SC", "SE", "SP", "TO",
}


def _resolve_source_path(mode: str) -> Path:
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
        url = ANP_URLS["distribuidores"]
        logger.info("Baixando distribuidores de %s", url)
        response = requests.get(url, timeout=60)
        response.raise_for_status()
        path.write_bytes(response.content)
        logger.info("Download concluído em %s (%d bytes)", path, len(response.content))
        return path

    raise ValueError(f"EXTRACT_MODE inválido: {mode!r}")


def _normalize_text(value: str | None) -> str | None:
    if value is None or pd.isna(value):
        return None
    return unidecode(str(value)).upper().strip()


def _clean_cep(value: str | None) -> str | None:
    """Remove hífen do CEP e garante 8 dígitos."""
    if value is None or pd.isna(value):
        return None
    digits = "".join(c for c in str(value) if c.isdigit())
    return digits.zfill(8) if digits else None


def extract_distribuidores(
    mode: Literal["from_local", "download"] | None = None,
) -> pd.DataFrame:
    """
    Lê o CSV de distribuidores da ANP, padroniza e grava em parquet.
    """
    mode = mode or EXTRACT_MODE
    source = _resolve_source_path(mode)
    logger.info("Lendo distribuidores de %s", source)

    df = pd.read_csv(
        source,
        sep=";",
        encoding="cp1252",
        skiprows=_SKIPROWS,
        dtype=str,
        keep_default_na=True,
    )
    n_inicial = len(df)
    logger.info("Lidas %d linhas brutas", n_inicial)

    # CNPJ já vem como string formatada (XX.XXX.XXX/XXXX-XX); normalize_cnpj
    # remove a pontuação e devolve 14 dígitos.
    df["cnpj"] = df["CNPJ"].apply(normalize_cnpj)
    invalidos = df["cnpj"].isna().sum()
    if invalidos:
        logger.warning("Descartando %d linhas com CNPJ inválido", invalidos)
        df = df.dropna(subset=["cnpj"])

    # CEP: remove hífen, zfill(8)
    df["cep"] = df["CEP"].apply(_clean_cep)

    # UF
    df["uf"] = df["UF"].str.upper().str.strip()
    uf_invalida = ~df["uf"].isin(_UFS_VALIDAS) & df["uf"].notna()
    if uf_invalida.any():
        logger.warning("Descartando %d linhas com UF inválida", uf_invalida.sum())
        df = df[~uf_invalida]

    # Município original e normalizado
    df["municipio"] = df["Municipio"].str.strip()
    df["municipio_norm"] = df["municipio"].apply(_normalize_text)

    # Nome reduzido normalizado para joins com BANDEIRA dos postos
    df["nome_reduzido_norm"] = df["Nome Reduzido"].apply(_normalize_text)

    # Datas em formato BR; inválidas viram NaT
    df["inicio_situacao"] = pd.to_datetime(
        df["Início da Situação"], format="%d/%m/%Y", errors="coerce"
    )
    df["data_publicacao"] = pd.to_datetime(
        df["Data Publicação"], format="%d/%m/%Y", errors="coerce"
    )

    # Situação normalizada (uppercase, sem acento)
    df["situacao"] = df["Situação"].apply(_normalize_text)

    df = df.rename(
        columns={
            "Código Agente": "codigo_agente",
            "Código Agente i-SIMP": "codigo_isimp",
            "Nome Reduzido": "nome_reduzido",
            "Razão Social": "razao_social",
            "Endereço da Matriz": "endereco",
            "Bairro": "bairro",
            "Tipo de Ato": "tipo_ato",
            "Tipo de Autorização": "tipo_autorizacao",
            "Número da Autorização": "numero_autorizacao",
        }
    )

    colunas_finais = [
        "codigo_agente", "codigo_isimp", "cnpj",
        "nome_reduzido", "nome_reduzido_norm", "razao_social",
        "endereco", "bairro", "cep", "uf", "municipio", "municipio_norm",
        "situacao", "inicio_situacao", "data_publicacao",
        "tipo_ato", "tipo_autorizacao", "numero_autorizacao",
    ]
    df = df[colunas_finais]

    # Deduplicação: distribuidor pode aparecer múltiplas vezes (filiais);
    # mantemos todas as linhas mas removemos duplicatas exatas
    duplicados = df.duplicated().sum()
    if duplicados:
        logger.warning("Removendo %d duplicatas exatas", duplicados)
        df = df.drop_duplicates()

    n_final = len(df)
    logger.info(
        "Distribuidores prontos: %d linhas (%d ativas, %d descartadas)",
        n_final,
        (df["situacao"] == "AUTORIZADA").sum(),
        n_inicial - n_final,
    )

    output = INTERIM_DIR / _INTERIM_FILENAME
    df.to_parquet(output, index=False)
    logger.info("Gravado em %s", output)

    return df


if __name__ == "__main__":
    extract_distribuidores()