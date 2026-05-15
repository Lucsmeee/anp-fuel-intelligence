# ANP Fuel Intelligence

Pipeline de dados ponta a ponta com informações públicas da ANP (Agência Nacional do Petróleo) sobre revendedores varejistas, distribuidores e tancagem do abastecimento nacional de combustíveis. O projeto contempla extração, transformação, modelagem dimensional em PostgreSQL e dashboard analítico, com enriquecimento de dados populacionais do IBGE.

## Arquitetura

A solução segue um pipeline tradicional de três etapas, organizado em módulos independentes sob `src/`:

- **Extração** (`src/extract/`): coleta os dados das fontes da ANP via download direto ou leitura local, com modo configurável.
- **Transformação** (`src/transform/`): padroniza, limpa e normaliza os dados — CNPJ, localização, datas e categorias — antes da carga.
- **Carga** (`src/load/`): persiste os dados em um modelo dimensional no PostgreSQL.
- **Dashboard** (`dashboard/`): camada de visualização analítica.

O fluxo de dados percorre `data/raw/` (bruto), `data/interim/` (intermediário) e `data/processed/` (pronto para carga). Arquivos pequenos e estáticos de referência ficam em `data/reference/` versionados; dados de movimentação não são versionados.

## Estrutura do repositório

## Reprodução local

Requisitos: Python 3.10+, Git e PostgreSQL 14+.

```bash
git clone https://github.com/Lucsmeee/anp-fuel-intelligence.git
cd anp-fuel-intelligence

python -m venv .venv
.venv\Scripts\Activate.ps1      # Windows (PowerShell)
# source .venv/bin/activate     # Linux/macOS

pip install -r requirements.txt

copy .env.example .env          # ajuste os valores conforme seu ambiente
```

As instruções de execução do pipeline, criação do banco e do dashboard serão adicionadas em commits posteriores conforme cada etapa for implementada.

## Decisões técnicas

Documentação detalhada das escolhas de modelagem, tratamento de qualidade e enriquecimento será consolidada ao final do desenvolvimento.

## Status

Em desenvolvimento.