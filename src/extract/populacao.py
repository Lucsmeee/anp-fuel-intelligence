"""
Extração dos dados de população estimada por UF (IBGE, 2025).

Fonte: IBGE — Estimativas da população residente no Brasil e Unidades da
Federação com data de referência em 1º de julho de 2025.

O arquivo XLS traz Brasil + regiões + estados em sequência. Filtramos
apenas os 26 estados e o DF, mapeamos os nomes para siglas UF e
adicionamos a macrorregião.

Saída: data/reference/populacao_uf.parquet
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import pandas as pd
from unidecode import unidecode

from src.config import DATA_LOCAL_PATH, EXTRACT_MODE, REFERENCE_DIR
from src.utils.logging import get_logger

logger = get_logger(__name__)

_LOCAL_FILENAME = "população/POP2025_20260113.xls"
_REFERENCE_FILENAME = "populacao_uf.parquet"

# Mapeamento nome completo → sigla UF
# Chave em unicode normalizado (sem acentos, uppercase) para matching robusto
_NOME_NORM_TO_UF: dict[str, str] = {
    "RONDONIA": "RO", "ACRE": "AC", "AMAZONAS": "AM", "RORAIMA": "RR",
    "PARA": "PA", "AMAPA": "AP", "TOCANTINS": "TO",
    "MARANHAO": "MA", "PIAUI": "PI", "CEARA": "CE",
    "RIO GRANDE DO NORTE": "RN", "PARAIBA": "PB", "PERNAMBUCO": "PE",
    "ALAGOAS": "AL", "SERGIPE": "SE", "BAHIA": "BA",
    "MINAS GERAIS": "MG", "ESPIRITO SANTO": "ES", "RIO DE JANEIRO": "RJ",
    "SAO PAULO": "SP",
    "PARANA": "PR", "SANTA CATARINA": "SC", "RIO GRANDE DO SUL": "RS",
    "MATO GROSSO DO SUL": "MS", "MATO GROSSO": "MT", "GOIAS": "GO",
    "DISTRITO FEDERAL": "DF",
}

# Macrorregião por UF para enriquecimento analítico
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


def _resolve_source_path() -> Path:
    path = DATA_LOCAL_PATH / _LOCAL_FILENAME
    if not path.exists():
        raise FileNotFoundError(
            f"Arquivo de população não encontrado: {path}\n"
            "Confira DATA_LOCAL_PATH no .env."
        )
    return path


def extract_populacao(
    mode: Literal["from_local", "download"] | None = None,
) -> pd.DataFrame:
    """
    Lê o XLS do IBGE, extrai a população estimada por UF e persiste em
    parquet no diretório de referência.
    """
    mode = mode or EXTRACT_MODE

    if mode not in ("from_local", "download"):
        raise ValueError(f"EXTRACT_MODE inválido: {mode!r}")

    # Para dados de referência estáticos como população, sempre usamos o
    # arquivo local independente do modo configurado.
    source = _resolve_source_path()
    logger.info("Lendo população de %s", source)

    # Linha 0: título. Linha 1: cabeçalho real. skiprows=1 usa a linha 1.
    df = pd.read_excel(source, skiprows=1, header=0, engine="xlrd")

    # Nomear colunas de forma previsível
    df.columns = ["nome_estado", "populacao_estimada", "_nota"]

    # Manter apenas linhas com nome e população preenchidos
    df = df.dropna(subset=["nome_estado", "populacao_estimada"])
    df = df[df["populacao_estimada"].apply(lambda x: str(x).strip().isdigit() if isinstance(x, str) else isinstance(x, (int, float)))]

    # Normalizar nomes para matching robusto
    df["_nome_norm"] = df["nome_estado"].apply(
        lambda v: unidecode(str(v)).upper().strip()
    )

    # Filtrar apenas os 27 estados/DF (exclui Brasil, regiões, rodapé)
    df = df[df["_nome_norm"].isin(_NOME_NORM_TO_UF)].copy()

    if len(df) != 27:
        logger.warning(
            "Esperados 27 estados, encontrados %d — verifique o arquivo de população",
            len(df),
        )

    df["uf"] = df["_nome_norm"].map(_NOME_NORM_TO_UF)
    df["regiao"] = df["uf"].map(_UF_TO_REGIAO)
    df["populacao_estimada"] = pd.to_numeric(
        df["populacao_estimada"], errors="coerce"
    ).astype("Int64")

    colunas_finais = ["uf", "nome_estado", "regiao", "populacao_estimada"]
    df = df[colunas_finais].sort_values("uf").reset_index(drop=True)

    logger.info(
        "População pronta: %d UFs | população total BR: %s",
        len(df),
        f"{df['populacao_estimada'].sum():,.0f}",
    )

    output = REFERENCE_DIR / _REFERENCE_FILENAME
    df.to_parquet(output, index=False)
    logger.info("Gravado em %s", output)

    return df


if __name__ == "__main__":
    extract_populacao()
