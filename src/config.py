"""
Configuração central do projeto.

Carrega variáveis do .env e expõe paths e constantes utilizadas pelos
módulos de extract, transform, load e dashboard. Nenhum outro módulo
deve ler variáveis de ambiente diretamente.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Raiz do projeto: dois níveis acima deste arquivo (src/config.py -> raiz)
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Carrega .env da raiz do projeto. Se não existir, usa valores default.
load_dotenv(PROJECT_ROOT / ".env")


# Paths internos do projeto
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
INTERIM_DIR = DATA_DIR / "interim"
PROCESSED_DIR = DATA_DIR / "processed"
REFERENCE_DIR = DATA_DIR / "reference"
SQL_DIR = PROJECT_ROOT / "sql"
LOGS_DIR = PROJECT_ROOT / "logs"

# Garante que as pastas existam ao importar o config
for _path in (RAW_DIR, INTERIM_DIR, PROCESSED_DIR, REFERENCE_DIR, LOGS_DIR):
    _path.mkdir(parents=True, exist_ok=True)


# Modo de operação do pipeline de extração
# - "from_local": lê os arquivos da pasta DATA_LOCAL_PATH
# - "download": baixa direto dos endpoints da ANP
EXTRACT_MODE = os.getenv("EXTRACT_MODE", "from_local").lower()
DATA_LOCAL_PATH = Path(os.getenv("DATA_LOCAL_PATH", ""))


# Endpoints públicos da ANP
ANP_URLS = {
    "postos": (
        "https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/"
        "arquivos/dadosabertos/scc/dados-cadastrais-revendedores-varejistas-"
        "combustiveis-automotivos.csv"
    ),
    "distribuidores": (
        "https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/"
        "arquivos/dadosabertos/sdl/planilha-aea-filiais.csv"
    ),
    # Tancagem é publicada em arquivos mensais; a URL base referencia a
    # página de listagem. Download automático requer scraping desta página.
    "tancagem_base": (
        "https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/"
        "tancagem-do-abastecimento-nacional-de-combustiveis"
    ),
    # SIMP: exportação disponível via portal de dados abertos da ANP
    "simp_base": (
        "https://www.gov.br/anp/pt-br/assuntos/producao-e-fornecimento-de-"
        "biocombustiveis/simp-sistema-de-informacoes-de-movimentacoes-de-produtos-1"
    ),
}


# Conexão PostgreSQL
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "database": os.getenv("DB_NAME", "anp_fuel"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", ""),
}


def get_db_url(sslmode: str | None = None) -> str:
    """Devolve a URL de conexão PostgreSQL no formato SQLAlchemy.

    sslmode: se fornecido, adiciona ?sslmode=<valor> à URL.
    Se a variável de ambiente DB_SSLMODE estiver definida, usa ela.
    """
    c = DB_CONFIG
    ssl = sslmode or os.getenv("DB_SSLMODE", "")
    suffix = f"?sslmode={ssl}" if ssl else ""
    return (
        f"postgresql+psycopg2://{c['user']}:{c['password']}"
        f"@{c['host']}:{c['port']}/{c['database']}{suffix}"
    )