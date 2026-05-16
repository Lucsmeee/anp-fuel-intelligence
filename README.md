# ANP Fuel Intelligence

Pipeline de dados ponta a ponta com informações públicas da ANP (Agência Nacional do Petróleo) sobre revendedores varejistas, distribuidoras e tancagem do abastecimento nacional de combustíveis. O projeto contempla extração, transformação, modelagem relacional em PostgreSQL e dashboard analítico, com enriquecimento de dados populacionais do IBGE.

## Arquitetura da solução

A solução segue o padrão medalhão simplificado em três camadas, implementadas como módulos Python independentes:

```
Fontes ANP / IBGE
        │
        ▼
src/extract/          →  data/raw/        (CSVs e Excel originais, não versionados)
        │
        ▼
data/interim/         (parquets limpos por entidade)
        │
        ▼
src/transform/        →  data/processed/  (dimensões e fatos prontos para carga)
        │
        ▼
src/load/             →  PostgreSQL        (schema.sql + INSERT em lotes)
        │
        ▼
dashboard/            →  Streamlit         (visualização analítica)
```

Cada etapa pode ser executada de forma independente, desde que a etapa anterior tenha sido concluída. O formato Parquet foi escolhido para os intermediários por preservar tipos de dados (datetime, bool) e oferecer compressão superior ao CSV.

## Fontes de dados

| Fonte | Entidade | Modo de acesso |
|---|---|---|
| ANP — Revendedores varejistas | Postos de combustíveis | CSV local ou download |
| ANP — Distribuidores (AEA filiais) | Distribuidoras | CSV local ou download |
| ANP — Tancagem nacional | Capacidade de armazenagem | CSVs mensais locais |
| ANP — SIMP Postos | Coordenadas, tancagem e vínculo ao distribuidor | Excel local |
| IBGE — Estimativas populacionais 2025 | População por UF | XLS local |

## Modelo relacional

```
dim_populacao_uf (uf PK)
        │
        ├──── dim_distribuidores (cnpj PK, uf FK)
        │              │
        │              └──── fct_tancagem_tanques  (cnpj+cod_instalacao+tag PK)
        │              └──── fct_tancagem_agregada (cnpj+segmento+grupo_produtos PK)
        │
        └──── dim_postos (codigo_isimp PK, uf FK)
                       │
                       └──── fct_simp_postos (codigo_isimp+produto PK)
```

A relação entre `dim_postos` e `dim_distribuidores` é mantida como FK lógica (não enforçada no banco) via `vinculacao_distribuidor_norm` ↔ `nome_reduzido_norm`. Postos sem marca definida ("Bandeira Branca") não têm distribuidora associada, o que impede o uso de uma FK rígida sem violar a integridade referencial.

## Estrutura do repositório

```
anp-fuel-intelligence/
├── src/
│   ├── config.py               # configuração central (paths, .env, DB)
│   ├── extract/                # extratores por fonte
│   │   ├── postos.py
│   │   ├── distribuidoes.py
│   │   ├── tancagem.py
│   │   ├── simp.py
│   │   ├── populacao.py
│   │   └── pipeline.py         # orquestrador: python -m src.extract.pipeline
│   ├── transform/              # transformações por entidade
│   │   ├── postos.py
│   │   ├── distribuidores.py
│   │   ├── tancagem.py
│   │   ├── simp.py
│   │   └── pipeline.py         # orquestrador: python -m src.transform.pipeline
│   ├── load/
│   │   └── load.py             # carga no PostgreSQL: python -m src.load.load
│   └── utils/
│       ├── cnpj.py             # normalização e validação de CNPJ
│       └── logging.py          # logging centralizado (console + arquivo rotativo)
├── sql/
│   └── schema.sql              # DDL completo com PKs, FKs e índices
├── dashboard/
│   └── app.py                  # dashboard Streamlit
├── data/
│   ├── raw/                    # arquivos originais (não versionados)
│   ├── interim/                # parquets por entidade (não versionados)
│   ├── processed/              # dimensões e fatos (não versionados)
│   └── reference/              # dados estáticos de referência
├── .env.example
├── requirements.txt
└── README.md
```

## Reprodução local

**Pré-requisitos:** Python 3.10+, Git e PostgreSQL 14+.

```bash
git clone https://github.com/seu-usuario/anp-fuel-intelligence.git
cd anp-fuel-intelligence

python -m venv .venv
.venv\Scripts\Activate.ps1       # Windows PowerShell
# source .venv/bin/activate      # Linux / macOS

pip install -r requirements.txt

copy .env.example .env           # Windows
# cp .env.example .env           # Linux / macOS
```

Edite o arquivo `.env` com os valores do seu ambiente:

```
DATA_LOCAL_PATH=caminho/para/os/arquivos/anp
EXTRACT_MODE=from_local
DB_HOST=localhost
DB_PORT=5432
DB_NAME=anp_fuel
DB_USER=postgres
DB_PASSWORD=sua_senha
```

**Crie o banco de dados no PostgreSQL:**

```sql
CREATE DATABASE anp_fuel;
```

**Execute o pipeline completo em sequência:**

```bash
python -m src.extract.pipeline
python -m src.transform.pipeline
python -m src.load.load
```

**Inicie o dashboard:**

```bash
streamlit run dashboard/app.py
```

Tempo total esperado de execução do pipeline: aproximadamente 2 minutos (dominado pela leitura do Excel do SIMP com 193 mil linhas).

## Decisões técnicas

**Modo de extração duplo.** Cada extrator suporta dois modos controlados pela variável `EXTRACT_MODE`: `from_local` lê arquivos de uma pasta configurada em `DATA_LOCAL_PATH`, e `download` busca os dados diretamente nos endpoints públicos da ANP. O modo local foi implementado porque a ANP não expõe uma API REST estruturada — os arquivos disponíveis no portal são CSVs e Excels com estruturas que variam por dataset. Para produção, o modo `download` está implementado para postos e distribuidoras; a tancagem e o SIMP exigiriam scraping da página de listagem da ANP, o que foi deixado como melhoria futura.

**Formato Parquet para intermediários.** Os arquivos em `data/interim/` e `data/processed/` são salvos em Parquet em vez de CSV por três motivos: preservação de tipos (datetime e bool sobrevivem à serialização sem ambiguidade), compressão superior (fator ~10x em relação ao CSV original da tancagem) e leitura colunar mais rápida para transformações analíticas.

**Normalização de CNPJ.** Os arquivos da ANP apresentam CNPJ em formatos heterogêneos: inteiro, notação científica (`4.35e+13`) e string com pontuação. O utilitário `src/utils/cnpj.py` trata todos os casos e produz strings de 14 dígitos com zeros à esquerda. Floats são rejeitados por padrão porque float64 não comporta 14 dígitos com precisão total.

**Join postos ↔ distribuidoras via nome normalizado.** O SIMP registra a marca do fornecedor do posto (ex: "VIBRA", "IPIRANGA") em vez do CNPJ. A junção com a tabela de distribuidoras é feita via `nome_reduzido_norm`, com remoção de acentos e conversão para maiúsculas em ambos os lados. Das 65 marcas presentes no SIMP, 64 têm correspondência exata nas distribuidoras — a única exceção é "BANDEIRA BRANCA", que representa postos sem fornecedor exclusivo.

**Tancagem: snapshot mais recente.** Os 18 CSVs de tancagem (2024–2026) representam snapshots mensais da capacidade de armazenagem. Em vez de modelar uma série temporal, o pipeline concatena todos os arquivos e mantém apenas o registro mais recente por tanque (`cnpj + cod_instalacao + tag`). Isso simplifica o modelo e representa o estado atual da infraestrutura, que é o dado relevante para os KPIs do dashboard.

**Carga idempotente via DROP + INSERT.** O script de carga executa o `schema.sql` (que faz `DROP TABLE IF EXISTS` antes de cada `CREATE TABLE`) e depois insere os dados via `INSERT` em lotes de 2.000 linhas. A abordagem é simples e suficiente para um pipeline de atualização periódica — em produção com volumes maiores, UPSERT ou particionamento seriam mais apropriados.

**SIMP como enriquecimento geográfico.** O arquivo SIMP de postos contém coordenadas geográficas (latitude/longitude decimal, cobertura de 83% dos postos) que não estão presentes no cadastro principal da ANP. Essas coordenadas são essenciais para o mapa de distribuição geográfica no dashboard. O SIMP também registra a tancagem por produto em cada posto, permitindo análises de capacidade a nível de combustível.

## Qualidade dos dados

Durante o desenvolvimento foram identificadas e tratadas as seguintes ocorrências:

- **CNPJs em notação científica** nos arquivos de postos: tratados em `src/utils/cnpj.py`.
- **Cabeçalho de relatório de 4 linhas** no CSV de distribuidoras: tratado com `skiprows=4`.
- **Encoding heterogêneo**: postos em UTF-8, distribuidoras em CP1252, tancagem em UTF-8-BOM, SIMP em XLSX com openpyxl.
- **Postos cancelados presentes no SIMP**: 33 registros do SIMP referenciavam `codigo_isimp` ausentes no cadastro atual da ANP. Foram removidos no transform para garantir integridade referencial.
- **Filiais com mesmo nome comercial**: múltiplas distribuidoras com o mesmo `nome_reduzido_norm` mas CNPJs distintos (ex: ARAPETRO CE, ARAPETRO BA). A constraint UNIQUE inicialmente planejada para essa coluna foi removida.

## Possíveis melhorias

**Extração automatizada da tancagem.** Implementar scraping da página de listagem da ANP para baixar os CSVs de tancagem de forma automática, eliminando a dependência de arquivos locais.

**Série temporal de tancagem.** Em vez de manter apenas o snapshot mais recente, persistir a série histórica completa (2024–2026) para análises de evolução da capacidade instalada por distribuidora.

**Geocodificação dos postos sem coordenadas.** Cerca de 17% dos postos não têm latitude/longitude no SIMP. Uma etapa de geocodificação via Nominatim (OpenStreetMap) ou a API do IBGE poderia aumentar a cobertura.

**UPSERT em vez de DROP + INSERT.** Para pipelines de atualização incremental, substituir a carga completa por UPSERT (`INSERT ... ON CONFLICT DO UPDATE`) reduziria o tempo de carga e preservaria o histórico de alterações.

**Testes automatizados.** Adicionar testes de contrato para os extratores (schema das colunas, tipos esperados, ausência de duplicatas nas PKs) e testes de qualidade (porcentagem mínima de CNPJs válidos, cobertura de coordenadas).

**Dados SIMP de movimentação.** O SIMP disponibiliza dados de movimentação de combustíveis (volumes vendidos por produto e posto) que permitiriam análises de market share por distribuidora e sazonalidade de demanda por região.
