"""
Extração e limpeza dos dados do SIMP (Sistema de Informações de
Movimentações de Produtos) referentes a postos de combustíveis.

O arquivo exportação.xlsx traz o cadastro detalhado dos postos com:
- Coordenadas geográficas (Latitude/Longitude decimal)
- Vinculação ao distribuidor fornecedor (ponte entre postos e distribuidoras)
- Capacidade de tancagem por produto e quantidade de bicos
- Status de conformidade PMQC

O campo 'Código Instalação i-Simp' corresponde a 'codigo_isimp' na tabela
de postos e é a chave primária desta entidade.

Saída: data/interim/simp_postos.parquet
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import pandas as pd
from unidecode import unidecode

from src.config import DATA_LOCAL_PATH, EXTRACT_MODE, INTERIM_DIR
from src.utils.cnpj import normalize_cnpj
from src.utils.logging import get_logger

logger = get_logger(__name__)

_LOCAL_FILENAME = (
    "SIMP - Sistema de Informações de Movimentações de Produtos/"
    "Postos/exportação.xlsx"
)
_INTERIM_FILENAME = "simp_postos.parquet"

_UFS_VALIDAS = {
    "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA",
    "MG", "MS", "MT", "PA", "PB", "PE", "PI", "PR", "RJ", "RN",
    "RO", "RR", "RS", "SC", "SE", "SP", "TO",
}


def _normalize_text(value: str | None) -> str | None:
    """Uppercase, remove acentos e espaços extras. Mantém None."""
    if value is None or pd.isna(value):
        return None
    return unidecode(str(value)).upper().strip()


def _clean_cep(value: str | None) -> str | None:
    """Remove pontuação do CEP e garante 8 dígitos com zero à esquerda."""
    if value is None or pd.isna(value):
        return None
    digits = "".join(c for c in str(value) if c.isdigit())
    return digits.zfill(8) if digits else None


def _parse_coordinate(value: str | None) -> float | None:
    """
    Converte coordenada para float. Trata vírgula como separador decimal
    e rejeita strings vazias ou inválidas.
    """
    if value is None or pd.isna(value):
        return None
    try:
        return float(str(value).replace(",", "."))
    except ValueError:
        return None


def _resolve_source_path() -> Path:
    path = DATA_LOCAL_PATH / _LOCAL_FILENAME
    if not path.exists():
        raise FileNotFoundError(
            f"Arquivo SIMP não encontrado: {path}\n"
            "Confira DATA_LOCAL_PATH no .env."
        )
    return path


def extract_simp(
    mode: Literal["from_local", "download"] | None = None,
) -> pd.DataFrame:
    """
    Lê o Excel do SIMP de postos, normaliza campos e persiste em parquet.

    Colunas são selecionadas por posição para garantir robustez contra
    variações de encoding nos nomes originais do arquivo.
    """
    mode = mode or EXTRACT_MODE

    if mode == "from_local":
        source = _resolve_source_path()
    elif mode == "download":
        raise NotImplementedError(
            "Modo 'download' para SIMP não implementado. "
            "Configure EXTRACT_MODE=from_local e DATA_LOCAL_PATH no .env."
        )
    else:
        raise ValueError(f"EXTRACT_MODE inválido: {mode!r}")

    logger.info("Lendo SIMP de %s", source)

    # dtype=str em todo o arquivo: CNPJ vem como texto de 14 dígitos no Excel
    # e não pode ser convertido para float sem perda de precisão.
    df = pd.read_excel(source, dtype=str, engine="openpyxl")
    n_inicial = len(df)
    logger.info("Lidas %d linhas brutas", n_inicial)

    # Renomeia por posição para não depender dos nomes originais com
    # caracteres especiais (que variam conforme encoding do ambiente).
    # Ordem das colunas no arquivo exportação.xlsx (27 colunas):
    #  0  Nº Autorizacao
    #  1  Data Publicação DOU - Autorização
    #  2  Código Instalação i-Simp
    #  3  Razão Social
    #  4  CNPJ
    #  5  Endereço
    #  6  COMPLEMENTO
    #  7  BAIRRO
    #  8  CEP
    #  9  UF
    # 10  MUNICÍPIO
    # 11  Vinculação a Distribuidor
    # 12  Data de Vinculação a Distribuidor
    # 13  Produto
    # 14  Tancagem (m³)
    # 15  Qtde de Bico
    # 16  Latitude (ANP4C)   — formato DMS, descartado
    # 17  Longitude (ANP4C)  — formato DMS, descartado
    # 18  Delivery
    # 19  Data Autorização Delivery  — descartado
    # 20  Número Despacho Delivery   — descartado
    # 21  Status PMQC
    # 22  Latitude            — decimal, utilizado
    # 23  Longitude           — decimal, utilizado
    # 24  SRC                 — descartado
    # 25  Data da Obtenção    — descartado
    # 26  Origem              — descartado
    cols = df.columns
    rename_map = {
        cols[0]: "num_autorizacao",
        cols[1]: "data_publicacao",
        cols[2]: "codigo_isimp",
        cols[3]: "razao_social",
        cols[4]: "cnpj_raw",
        cols[5]: "endereco",
        cols[6]: "complemento",
        cols[7]: "bairro",
        cols[8]: "cep",
        cols[9]: "uf",
        cols[10]: "municipio",
        cols[11]: "vinculacao_distribuidor",
        cols[12]: "data_vinculacao_distribuidor",
        cols[13]: "produto",
        cols[14]: "tancagem_m3",
        cols[15]: "qtde_bico",
        cols[18]: "delivery",
        cols[21]: "status_pmqc",
        cols[22]: "latitude",
        cols[23]: "longitude",
    }
    df = df.rename(columns=rename_map)

    # CNPJ: o Excel armazena como texto de 14 dígitos com zeros à esquerda
    df["cnpj"] = df["cnpj_raw"].apply(normalize_cnpj)
    invalidos = df["cnpj"].isna().sum()
    if invalidos:
        logger.warning(
            "%d linhas com CNPJ inválido no SIMP (não descartadas — "
            "join principal é via codigo_isimp)",
            invalidos,
        )

    # CEP
    df["cep"] = df["cep"].apply(_clean_cep)

    # UF
    df["uf"] = df["uf"].str.upper().str.strip()
    uf_invalida = ~df["uf"].isin(_UFS_VALIDAS) & df["uf"].notna()
    if uf_invalida.any():
        logger.warning("Descartando %d linhas com UF inválida", uf_invalida.sum())
        df = df[~uf_invalida]

    # Município
    df["municipio"] = df["municipio"].str.strip()
    df["municipio_norm"] = df["municipio"].apply(_normalize_text)

    # Vinculação ao distribuidor (normalizado para join)
    df["vinculacao_distribuidor_norm"] = df["vinculacao_distribuidor"].apply(
        _normalize_text
    )

    # Produto normalizado
    df["produto_norm"] = df["produto"].apply(_normalize_text)

    # Campos numéricos
    df["tancagem_m3"] = pd.to_numeric(df["tancagem_m3"], errors="coerce")
    df["qtde_bico"] = pd.to_numeric(df["qtde_bico"], errors="coerce")
    df["latitude"] = df["latitude"].apply(_parse_coordinate)
    df["longitude"] = df["longitude"].apply(_parse_coordinate)

    # Datas
    df["data_publicacao"] = pd.to_datetime(
        df["data_publicacao"], format="%d/%m/%Y", errors="coerce"
    )
    df["data_vinculacao_distribuidor"] = pd.to_datetime(
        df["data_vinculacao_distribuidor"], format="%d/%m/%Y", errors="coerce"
    )

    # codigo_isimp como string limpa (é numérico mas é identificador)
    df["codigo_isimp"] = df["codigo_isimp"].str.strip()

    colunas_finais = [
        "codigo_isimp", "num_autorizacao", "data_publicacao",
        "razao_social", "cnpj",
        "endereco", "complemento", "bairro", "cep",
        "uf", "municipio", "municipio_norm",
        "vinculacao_distribuidor", "vinculacao_distribuidor_norm",
        "data_vinculacao_distribuidor",
        "produto", "produto_norm", "tancagem_m3", "qtde_bico",
        "delivery", "status_pmqc",
        "latitude", "longitude",
    ]
    df = df[colunas_finais]

    n_final = len(df)
    postos_com_coord = df["latitude"].notna().sum()
    logger.info(
        "SIMP pronto: %d linhas | %d postos com coordenadas (%.1f%%)",
        n_final,
        postos_com_coord,
        100 * postos_com_coord / n_final if n_final else 0,
    )

    output = INTERIM_DIR / _INTERIM_FILENAME
    df.to_parquet(output, index=False)
    logger.info("Gravado em %s", output)

    return df


if __name__ == "__main__":
    extract_simp()
