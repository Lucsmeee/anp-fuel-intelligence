"""
Extração e limpeza dos dados de tancagem do abastecimento nacional de combustíveis.

A ANP publica snapshots mensais da capacidade de armazenagem de instalações
autorizadas (distribuidoras, terminais, refinarias, etc.). Localmente os dados
estão organizados em subpastas por ano e período:

    DATA_LOCAL_PATH/
        Tancagem do Abastecimento Nacional de Combustíveis/
            2024/janeiro.csv
            2024/marco-julho.csv
            ...
            2026/abril.csv

Estratégia: concatena todos os arquivos e mantém apenas o snapshot mais recente
por tanque individual (cnpj + cod_instalacao + tag), representando a capacidade
atual da infraestrutura sem duplicação histórica.

Saída: data/interim/tancagem.parquet
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

_LOCAL_DIR = "Tancagem do Abastecimento Nacional de Combustíveis"
_INTERIM_FILENAME = "tancagem.parquet"

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


def _list_local_csvs(base_dir: Path) -> list[Path]:
    """Retorna todos os CSVs de tancagem encontrados na pasta local, ordenados."""
    files = sorted(base_dir.rglob("*.csv"))
    if not files:
        raise FileNotFoundError(
            f"Nenhum CSV de tancagem encontrado em: {base_dir}\n"
            "Confira DATA_LOCAL_PATH no .env."
        )
    logger.info("Encontrados %d arquivos de tancagem em %s", len(files), base_dir)
    return files


def _read_and_concat(files: list[Path]) -> pd.DataFrame:
    """Lê e concatena todos os CSVs, registrando a origem de cada linha."""
    frames: list[pd.DataFrame] = []
    for path in files:
        df = pd.read_csv(path, encoding="utf-8-sig", dtype=str)
        df["_arquivo_origem"] = path.name
        frames.append(df)
        logger.debug("Lido %s (%d linhas)", path.name, len(df))

    combined = pd.concat(frames, ignore_index=True)
    logger.info(
        "Total bruto: %d linhas de %d arquivos", len(combined), len(files)
    )
    return combined


def extract_tancagem(
    mode: Literal["from_local", "download"] | None = None,
) -> pd.DataFrame:
    """
    Concatena todos os CSVs de tancagem, mantém o snapshot mais recente por
    tanque (cnpj + cod_instalacao + tag) e persiste o resultado em parquet.
    """
    mode = mode or EXTRACT_MODE

    if mode == "from_local":
        base_dir = DATA_LOCAL_PATH / _LOCAL_DIR
        files = _list_local_csvs(base_dir)
        df = _read_and_concat(files)
    elif mode == "download":
        raise NotImplementedError(
            "Modo 'download' para tancagem ainda não implementado. "
            "Configure EXTRACT_MODE=from_local e DATA_LOCAL_PATH no .env."
        )
    else:
        raise ValueError(f"EXTRACT_MODE inválido: {mode!r}")

    n_inicial = len(df)

    # Data: necessária para selecionar o snapshot mais recente
    df["data"] = pd.to_datetime(df["Data"], errors="coerce")
    data_invalida = df["data"].isna().sum()
    if data_invalida:
        logger.warning("Descartando %d linhas com data inválida", data_invalida)
        df = df.dropna(subset=["data"])

    # CNPJ: string de 14 dígitos
    df["cnpj"] = df["Cnpj"].apply(normalize_cnpj)
    invalidos = df["cnpj"].isna().sum()
    if invalidos:
        logger.warning("Descartando %d linhas com CNPJ inválido", invalidos)
        df = df.dropna(subset=["cnpj"])

    # UF
    df["uf"] = df["Uf"].str.upper().str.strip()
    uf_invalida = ~df["uf"].isin(_UFS_VALIDAS) & df["uf"].notna()
    if uf_invalida.any():
        logger.warning("Descartando %d linhas com UF inválida", uf_invalida.sum())
        df = df[~uf_invalida]

    # Município original e normalizado
    df["municipio"] = df["Municipio"].str.strip()
    df["municipio_norm"] = df["municipio"].apply(_normalize_text)

    # Campos categóricos normalizados
    df["segmento"] = df["Segmento"].apply(_normalize_text)
    df["grupo_produtos"] = df["GrupoDeProdutos"].apply(_normalize_text)
    df["tipo_unidade"] = df["TipoDaUnidade"].apply(_normalize_text)
    df["detalhe_instalacao"] = df["DetalheInstalacao"].apply(_normalize_text)

    # Tancagem como numérico
    df["tancagem_m3"] = pd.to_numeric(df["TancagemM3"], errors="coerce")

    df = df.rename(
        columns={
            "NomeEmpresarial": "nome_empresarial",
            "CodInstalacao": "cod_instalacao",
            "Tag": "tag",
        }
    )

    # Snapshot mais recente por tanque: cnpj + cod_instalacao + tag identificam
    # um tanque físico único. Ordenamos por data desc e mantemos a primeira
    # ocorrência, que representa o estado atual da infraestrutura.
    chave_tanque = ["cnpj", "cod_instalacao", "tag"]
    n_antes_dedup = len(df)
    df = (
        df.sort_values("data", ascending=False)
          .drop_duplicates(subset=chave_tanque, keep="first")
    )
    snapshots_removidos = n_antes_dedup - len(df)
    logger.info(
        "Snapshots históricos removidos: %d (mantendo o mais recente por tanque)",
        snapshots_removidos,
    )

    colunas_finais = [
        "data", "cnpj", "nome_empresarial",
        "uf", "municipio", "municipio_norm",
        "cod_instalacao", "segmento", "detalhe_instalacao",
        "tag", "tipo_unidade", "grupo_produtos", "tancagem_m3",
    ]
    df = df[colunas_finais]

    n_final = len(df)
    logger.info(
        "Tancagem pronta: %d tanques | capacidade total: %.0f m³ | "
        "descartadas do bruto: %d",
        n_final,
        df["tancagem_m3"].sum(),
        n_inicial - n_final,
    )

    output = INTERIM_DIR / _INTERIM_FILENAME
    df.to_parquet(output, index=False)
    logger.info("Gravado em %s", output)

    return df


if __name__ == "__main__":
    extract_tancagem()
