"""
Normalização e validação de CNPJ.

Os arquivos da ANP trazem CNPJ em formatos heterogêneos: inteiro,
notação científica (4.354429e+13) e string com pontuação. Esta
camada padroniza tudo em string de 14 dígitos numéricos, condição
necessária para qualquer join entre as entidades.
"""

from __future__ import annotations

import re
from typing import Optional, Union

CnpjInput = Union[str, int, float, None]

_NON_DIGIT = re.compile(r"\D")


def _to_digits(value: CnpjInput) -> Optional[str]:
    """Converte qualquer entrada em string contendo apenas dígitos."""
    if value is None:
        return None

 # CNPJ jamais deve chegar como float: floats de 14 dígitos perdem
    # precisão na mantissa (float64). Rejeitamos a entrada e o chamador
    # deve forçar leitura como string na origem (dtype=str em read_csv,
    # converters em read_excel).
    if isinstance(value, float):
        return None
    elif isinstance(value, int):
        value = str(value)

    if not isinstance(value, str):
        return None

    return _NON_DIGIT.sub("", value)


def _is_valid_check_digits(cnpj: str) -> bool:
    """Valida os dois dígitos verificadores do CNPJ (módulo 11)."""
    weights_1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    weights_2 = [6] + weights_1

    def calc(digits: str, weights: list[int]) -> int:
        total = sum(int(d) * w for d, w in zip(digits, weights))
        remainder = total % 11
        return 0 if remainder < 2 else 11 - remainder

    return (
        calc(cnpj[:12], weights_1) == int(cnpj[12])
        and calc(cnpj[:13], weights_2) == int(cnpj[13])
    )


def normalize_cnpj(value: CnpjInput, validate: bool = False) -> Optional[str]:
    """
    Devolve o CNPJ como string de 14 dígitos com zero à esquerda.

    Retorna None quando o valor é vazio, todo zero, com dígitos repetidos
    ou, se validate=True, quando o dígito verificador não confere.
    """
    digits = _to_digits(value)
    if not digits:
        return None

    digits = digits.zfill(14)

    if len(digits) != 14:
        return None

    if len(set(digits)) == 1:
        return None

    if validate and not _is_valid_check_digits(digits):
        return None

    return digits


def format_cnpj(cnpj: str) -> str:
    """Formata um CNPJ normalizado para exibição: XX.XXX.XXX/XXXX-XX."""
    if not cnpj or len(cnpj) != 14:
        return cnpj
    return f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"