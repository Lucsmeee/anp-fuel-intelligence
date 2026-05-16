"""
Dashboard analítico — ANP Fuel Intelligence
Execute com: streamlit run dashboard/app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from sqlalchemy import create_engine, text

# Garante que src/ está no path independente do diretório de execução
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.config import get_db_url  # noqa: E402

# =============================================================================
# Configuração da página
# =============================================================================
st.set_page_config(
    page_title="ANP Fuel Intelligence",
    page_icon="⛽",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# CSS mínimo para ajustar métricas e espaçamento
st.markdown(
    """
    <style>
    [data-testid="metric-container"] { background:#1e1e2e; border-radius:8px; padding:12px; }
    .block-container { padding-top: 1.5rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

# =============================================================================
# Conexão e cache de dados
# =============================================================================
@st.cache_resource(show_spinner=False)
def get_engine():
    return create_engine(get_db_url(), pool_pre_ping=True)


@st.cache_data(ttl=3600, show_spinner="Carregando dados...")
def load_kpis() -> dict:
    engine = get_engine()
    with engine.connect() as conn:
        total_postos = conn.execute(
            text("SELECT COUNT(*) FROM dim_postos")
        ).scalar()
        dist_ativas = conn.execute(
            text("SELECT COUNT(*) FROM dim_distribuidores WHERE is_ativa")
        ).scalar()
        capacidade_m3 = conn.execute(
            text("SELECT COALESCE(SUM(tancagem_total_m3), 0) FROM fct_tancagem_agregada WHERE is_distribuicao")
        ).scalar()
        postos_com_coord = conn.execute(
            text("SELECT COUNT(*) FROM dim_postos WHERE latitude IS NOT NULL")
        ).scalar()
    return {
        "total_postos": int(total_postos),
        "dist_ativas": int(dist_ativas),
        "capacidade_m3": float(capacidade_m3),
        "postos_com_coord": int(postos_com_coord),
    }


@st.cache_data(ttl=3600, show_spinner=False)
def load_postos_por_uf() -> pd.DataFrame:
    sql = """
        SELECT
            p.uf,
            pop.regiao,
            pop.nome_estado,
            COUNT(*)                                           AS total_postos,
            pop.populacao_estimada,
            ROUND(COUNT(*) * 100000.0 / pop.populacao_estimada, 1) AS postos_por_100k
        FROM dim_postos p
        JOIN dim_populacao_uf pop ON p.uf = pop.uf
        GROUP BY p.uf, pop.regiao, pop.nome_estado, pop.populacao_estimada
        ORDER BY total_postos DESC
    """
    return pd.read_sql(sql, get_engine())


@st.cache_data(ttl=3600, show_spinner=False)
def load_postos_por_bandeira() -> pd.DataFrame:
    sql = """
        SELECT
            COALESCE(bandeira, 'Não informado') AS bandeira,
            COUNT(*) AS total_postos
        FROM dim_postos
        GROUP BY bandeira
        ORDER BY total_postos DESC
        LIMIT 12
    """
    return pd.read_sql(sql, get_engine())


@st.cache_data(ttl=3600, show_spinner=False)
def load_mapa_postos(uf: str) -> pd.DataFrame:
    sql = text("""
        SELECT
            p.codigo_isimp,
            COALESCE(p.razao_social, 'Não informado')       AS razao_social,
            COALESCE(p.bandeira, 'Bandeira Branca')          AS bandeira,
            p.municipio,
            p.latitude,
            p.longitude,
            COALESCE(p.status_pmqc, 'Não informado')        AS status_pmqc,
            COALESCE(p.vinculacao_distribuidor, 'Não informado') AS distribuidor
        FROM dim_postos p
        WHERE p.latitude IS NOT NULL
          AND p.longitude IS NOT NULL
          AND p.uf = :uf
    """)
    return pd.read_sql(sql, get_engine(), params={"uf": uf})


@st.cache_data(ttl=3600, show_spinner=False)
def load_tancagem_por_empresa() -> pd.DataFrame:
    sql = """
        SELECT
            nome_empresarial                   AS empresa,
            SUM(tancagem_total_m3)             AS capacidade_m3,
            SUM(qtd_tanques)                   AS qtd_tanques,
            MAX(uf)                            AS uf
        FROM fct_tancagem_agregada
        WHERE is_distribuicao = true
        GROUP BY nome_empresarial
        ORDER BY capacidade_m3 DESC
        LIMIT 20
    """
    return pd.read_sql(sql, get_engine())


@st.cache_data(ttl=3600, show_spinner=False)
def load_tancagem_por_segmento() -> pd.DataFrame:
    sql = """
        SELECT
            segmento,
            SUM(tancagem_total_m3) AS capacidade_m3,
            SUM(qtd_tanques)       AS qtd_tanques
        FROM fct_tancagem_agregada
        GROUP BY segmento
        ORDER BY capacidade_m3 DESC
    """
    return pd.read_sql(sql, get_engine())


@st.cache_data(ttl=3600, show_spinner=False)
def load_tancagem_por_produto() -> pd.DataFrame:
    sql = """
        SELECT
            grupo_produtos             AS produto,
            SUM(tancagem_total_m3)     AS capacidade_m3
        FROM fct_tancagem_agregada
        WHERE grupo_produtos != 'NAO INFORMADO'
        GROUP BY grupo_produtos
        ORDER BY capacidade_m3 DESC
    """
    return pd.read_sql(sql, get_engine())


@st.cache_data(ttl=3600, show_spinner=False)
def load_infra_mercado() -> pd.DataFrame:
    sql = """
        SELECT
            d.nome_reduzido                          AS distribuidora,
            d.regiao,
            COUNT(DISTINCT p.codigo_isimp)           AS postos_vinculados,
            COALESCE(SUM(ta.tancagem_total_m3), 0)  AS capacidade_m3
        FROM dim_distribuidores d
        LEFT JOIN dim_postos p
               ON p.vinculacao_distribuidor_norm = d.nome_reduzido_norm
        LEFT JOIN fct_tancagem_agregada ta
               ON ta.cnpj = d.cnpj AND ta.is_distribuicao = true
        WHERE d.is_ativa = true
        GROUP BY d.nome_reduzido, d.regiao
        HAVING COUNT(DISTINCT p.codigo_isimp) > 10
        ORDER BY postos_vinculados DESC
    """
    return pd.read_sql(sql, get_engine())


@st.cache_data(ttl=3600, show_spinner=False)
def load_produtos_postos() -> pd.DataFrame:
    sql = """
        SELECT
            COALESCE(produto, 'Não informado') AS produto,
            COUNT(DISTINCT codigo_isimp)        AS postos,
            SUM(tancagem_m3)                    AS tancagem_total_m3,
            SUM(qtde_bico)                      AS total_bicos
        FROM fct_simp_postos
        WHERE produto IS NOT NULL
        GROUP BY produto
        ORDER BY postos DESC
        LIMIT 16
    """
    return pd.read_sql(sql, get_engine())


# =============================================================================
# Paleta de cores
# =============================================================================
COR_PRIMARIA = "#e63946"
COR_SECUNDARIA = "#457b9d"
COR_FUNDO = "#1d3557"
SEQUENCIA = px.colors.qualitative.Bold

# =============================================================================
# Layout principal
# =============================================================================
st.title("ANP Fuel Intelligence")
st.caption(
    "Análise da infraestrutura de distribuição de combustíveis no Brasil "
    "com base em dados públicos da ANP e IBGE — referência: abril/2026."
)

tabs = st.tabs([
    "Panorama Nacional",
    "Mapa de Postos",
    "Tancagem e Capacidade",
    "Infraestrutura x Mercado",
])

# =============================================================================
# TAB 1 — PANORAMA NACIONAL
# =============================================================================
with tabs[0]:
    kpis = load_kpis()
    df_uf = load_postos_por_uf()
    df_bandeira = load_postos_por_bandeira()

    # KPIs
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Postos cadastrados", f"{kpis['total_postos']:,}".replace(",", "."))
    c2.metric("Distribuidoras ativas", f"{kpis['dist_ativas']:,}".replace(",", "."))
    c3.metric(
        "Capacidade de distribuição",
        f"{kpis['capacidade_m3'] / 1_000_000:.1f} M m³",
    )
    c4.metric(
        "Postos com geolocalização",
        f"{kpis['postos_com_coord']:,}".replace(",", ".")
        + f" ({100 * kpis['postos_com_coord'] / kpis['total_postos']:.0f}%)",
    )

    st.markdown("---")

    col_esq, col_dir = st.columns([3, 2])

    with col_esq:
        st.subheader("Postos por UF")
        fig_uf = px.bar(
            df_uf,
            x="uf",
            y="total_postos",
            color="regiao",
            color_discrete_sequence=SEQUENCIA,
            labels={"uf": "UF", "total_postos": "Postos", "regiao": "Região"},
            text_auto=True,
        )
        fig_uf.update_layout(
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            legend_title_text="Região",
            xaxis_tickangle=-45,
            height=400,
        )
        fig_uf.update_traces(textposition="outside", textfont_size=10)
        st.plotly_chart(fig_uf, use_container_width=True)

    with col_dir:
        st.subheader("Top marcas")
        fig_band = px.bar(
            df_bandeira,
            x="total_postos",
            y="bandeira",
            orientation="h",
            color_discrete_sequence=[COR_SECUNDARIA],
            labels={"total_postos": "Postos", "bandeira": "Bandeira"},
            text_auto=True,
        )
        fig_band.update_layout(
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            yaxis={"categoryorder": "total ascending"},
            height=400,
        )
        fig_band.update_traces(textposition="outside")
        st.plotly_chart(fig_band, use_container_width=True)

    st.markdown("---")
    st.subheader("Postos por 100 mil habitantes")
    fig_100k = px.bar(
        df_uf.sort_values("postos_por_100k", ascending=False),
        x="uf",
        y="postos_por_100k",
        color="regiao",
        color_discrete_sequence=SEQUENCIA,
        labels={"uf": "UF", "postos_por_100k": "Postos / 100k hab.", "regiao": "Região"},
        text_auto=True,
    )
    fig_100k.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        xaxis_tickangle=-45,
        height=380,
    )
    fig_100k.update_traces(textposition="outside", textfont_size=9)
    st.plotly_chart(fig_100k, use_container_width=True)


# =============================================================================
# TAB 2 — MAPA DE POSTOS
# =============================================================================
with tabs[1]:
    df_uf_lista = load_postos_por_uf()
    ufs = df_uf_lista["uf"].tolist()

    col_filtro, col_info = st.columns([2, 5])
    with col_filtro:
        uf_sel = st.selectbox("Selecione a UF", ufs, index=ufs.index("SP"))
        cor_mapa = st.radio(
            "Colorir por",
            ["Bandeira", "Status PMQC", "Distribuidor"],
            horizontal=True,
        )
    cor_col = {
        "Bandeira": "bandeira",
        "Status PMQC": "status_pmqc",
        "Distribuidor": "distribuidor",
    }[cor_mapa]

    df_mapa = load_mapa_postos(uf_sel)
    n_postos_uf = df_uf_lista.loc[df_uf_lista["uf"] == uf_sel, "total_postos"].values[0]

    with col_info:
        st.markdown(
            f"**{uf_sel}** — {n_postos_uf:,} postos cadastrados | "
            f"{len(df_mapa):,} com coordenadas ({100*len(df_mapa)/n_postos_uf:.0f}%)"
        )

    if df_mapa.empty:
        st.warning(f"Nenhum posto com coordenadas encontrado para {uf_sel}.")
    else:
        fig_mapa = px.scatter_mapbox(
            df_mapa,
            lat="latitude",
            lon="longitude",
            color=cor_col,
            hover_name="razao_social",
            hover_data={
                "municipio": True,
                "bandeira": True,
                "distribuidor": True,
                "status_pmqc": True,
                "latitude": False,
                "longitude": False,
            },
            zoom=6,
            height=600,
            mapbox_style="open-street-map",
            color_discrete_sequence=SEQUENCIA,
            opacity=0.7,
        )
        fig_mapa.update_layout(
            margin={"r": 0, "t": 0, "l": 0, "b": 0},
            legend_title_text=cor_mapa,
        )
        st.plotly_chart(fig_mapa, use_container_width=True)


# =============================================================================
# TAB 3 — TANCAGEM E CAPACIDADE
# =============================================================================
with tabs[2]:
    df_tanc_emp = load_tancagem_por_empresa()
    df_tanc_seg = load_tancagem_por_segmento()
    df_tanc_prod = load_tancagem_por_produto()
    df_prod_postos = load_produtos_postos()

    st.subheader("Top 20 empresas por capacidade de armazenagem (ramo de distribuição)")
    df_tanc_emp["capacidade_m3_fmt"] = (
        df_tanc_emp["capacidade_m3"] / 1000
    ).round(1).astype(str) + " mil m³"
    fig_tanc = px.bar(
        df_tanc_emp,
        x="capacidade_m3",
        y="empresa",
        orientation="h",
        color_discrete_sequence=[COR_PRIMARIA],
        labels={"capacidade_m3": "Capacidade (m³)", "empresa": "Empresa"},
        hover_data={"qtd_tanques": True, "uf": True},
        text="capacidade_m3_fmt",
    )
    fig_tanc.update_layout(
        yaxis={"categoryorder": "total ascending"},
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        height=500,
    )
    fig_tanc.update_traces(textposition="outside")
    st.plotly_chart(fig_tanc, use_container_width=True)

    st.markdown("---")
    col_seg, col_prod = st.columns(2)

    with col_seg:
        st.subheader("Capacidade por tipo de instalação")
        fig_seg = px.pie(
            df_tanc_seg,
            names="segmento",
            values="capacidade_m3",
            color_discrete_sequence=SEQUENCIA,
            hole=0.4,
        )
        fig_seg.update_traces(textposition="inside", textinfo="percent+label")
        fig_seg.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            showlegend=False,
            height=380,
        )
        st.plotly_chart(fig_seg, use_container_width=True)

    with col_prod:
        st.subheader("Capacidade por grupo de produtos")
        fig_prod = px.pie(
            df_tanc_prod,
            names="produto",
            values="capacidade_m3",
            color_discrete_sequence=SEQUENCIA,
            hole=0.4,
        )
        fig_prod.update_traces(textposition="inside", textinfo="percent+label")
        fig_prod.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            showlegend=False,
            height=380,
        )
        st.plotly_chart(fig_prod, use_container_width=True)

    st.markdown("---")
    st.subheader("Combustíveis nos postos — cobertura e tancagem (SIMP)")
    fig_comb = px.bar(
        df_prod_postos,
        x="produto",
        y="postos",
        color_discrete_sequence=[COR_SECUNDARIA],
        labels={"produto": "Produto", "postos": "Postos"},
        text_auto=True,
    )
    fig_comb.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        xaxis_tickangle=-35,
        height=380,
    )
    fig_comb.update_traces(textposition="outside")
    st.plotly_chart(fig_comb, use_container_width=True)


# =============================================================================
# TAB 4 — INFRAESTRUTURA x MERCADO
# =============================================================================
with tabs[3]:
    df_im = load_infra_mercado()

    st.subheader("Presença de mercado vs. capacidade de armazenagem por distribuidora")
    st.caption(
        "Cada ponto representa uma distribuidora ativa. "
        "Tamanho proporcional ao número de postos vinculados. "
        "Distribuidoras com tancagem zero não possuem instalações "
        "registradas na base de tancagem da ANP."
    )

    fig_scatter = px.scatter(
        df_im,
        x="postos_vinculados",
        y="capacidade_m3",
        size="postos_vinculados",
        color="regiao",
        hover_name="distribuidora",
        hover_data={"postos_vinculados": True, "capacidade_m3": True, "regiao": False},
        color_discrete_sequence=SEQUENCIA,
        labels={
            "postos_vinculados": "Postos vinculados",
            "capacidade_m3": "Capacidade de armazenagem (m³)",
            "regiao": "Região",
        },
        size_max=50,
        height=500,
    )
    fig_scatter.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig_scatter, use_container_width=True)

    st.markdown("---")
    col_rank, col_reg = st.columns([3, 2])

    with col_rank:
        st.subheader("Ranking por postos vinculados")
        fig_rank = px.bar(
            df_im.head(15),
            x="postos_vinculados",
            y="distribuidora",
            orientation="h",
            color="regiao",
            color_discrete_sequence=SEQUENCIA,
            labels={
                "postos_vinculados": "Postos",
                "distribuidora": "Distribuidora",
                "regiao": "Região",
            },
            text_auto=True,
        )
        fig_rank.update_layout(
            yaxis={"categoryorder": "total ascending"},
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            height=450,
        )
        fig_rank.update_traces(textposition="outside")
        st.plotly_chart(fig_rank, use_container_width=True)

    with col_reg:
        st.subheader("Postos por região")
        df_reg = df_im.groupby("regiao")["postos_vinculados"].sum().reset_index()
        fig_reg = px.pie(
            df_reg,
            names="regiao",
            values="postos_vinculados",
            color_discrete_sequence=SEQUENCIA,
            hole=0.4,
        )
        fig_reg.update_traces(textposition="inside", textinfo="percent+label")
        fig_reg.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            showlegend=False,
            height=380,
        )
        st.plotly_chart(fig_reg, use_container_width=True)

    st.markdown("---")
    st.subheader("Tabela de distribuidoras ativas")
    st.dataframe(
        df_im.rename(columns={
            "distribuidora": "Distribuidora",
            "regiao": "Região",
            "postos_vinculados": "Postos",
            "capacidade_m3": "Capacidade (m³)",
        }).style.format({"Capacidade (m³)": "{:,.0f}", "Postos": "{:,}"}),
        use_container_width=True,
        hide_index=True,
    )

# =============================================================================
# Rodapé
# =============================================================================
st.markdown("---")
st.caption(
    "Fontes: ANP — Cadastro de Revendedores Varejistas, Distribuidores, "
    "Tancagem do Abastecimento Nacional e SIMP (abril/2026). "
    "IBGE — Estimativas populacionais 2025. "
    "Projeto desenvolvido com Python, PostgreSQL e Streamlit."
)
