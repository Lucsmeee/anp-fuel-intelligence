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
    page_title="ANP Fuel Intelligence — Rede São Roque",
    page_icon="⛽",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# CSS — números maiores nos KPIs e paleta São Roque
st.markdown(
    """
    <style>
    /* KPI cards */
    [data-testid="metric-container"] {
        background: #1e1e2e;
        border-radius: 10px;
        padding: 18px 20px;
        border-left: 4px solid #D91F2A;
    }
    [data-testid="stMetricValue"] {
        font-size: 2.4rem !important;
        font-weight: 700 !important;
        color: #FFFFFF !important;
    }
    [data-testid="stMetricLabel"] {
        font-size: 0.95rem !important;
        color: #CCCCCC !important;
        font-weight: 500 !important;
    }
    /* Faixa de título */
    .bloco-titulo {
        background: linear-gradient(90deg, #D91F2A 0%, #1A2B4A 100%);
        border-radius: 10px;
        padding: 16px 24px;
        margin-bottom: 18px;
    }
    .bloco-titulo h2 { color: #FFFFFF !important; margin: 0; }
    .bloco-titulo p  { color: #F0F0F0 !important; margin: 0; font-size: 0.85rem; }
    /* Container geral */
    .block-container { padding-top: 1.2rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

# =============================================================================
# Paleta de cores — identidade São Roque
# =============================================================================
COR_PRIMARIA   = "#D91F2A"   # vermelho São Roque
COR_SECUNDARIA = "#F5A623"   # âmbar / dourado
COR_TERCIARIA  = "#1A2B4A"   # azul escuro
SEQUENCIA = [
    "#D91F2A", "#F5A623", "#1A2B4A", "#E8734A",
    "#2E7D32", "#6A1B9A", "#0277BD", "#558B2F",
    "#AD1457", "#00695C", "#4527A0", "#F57F17",
]

# =============================================================================
# Conexão e cache de dados
# =============================================================================
@st.cache_resource(show_spinner=False)
def get_engine():
    # No Streamlit Cloud, credenciais vêm de st.secrets
    # Localmente, vêm do .env via src.config
    from sqlalchemy import URL as SA_URL
    try:
        s = st.secrets
        url = SA_URL.create(
            "postgresql+psycopg2",
            username=s["DB_USER"],
            password=s["DB_PASSWORD"],   # URL.create escapa @ e outros caracteres
            host=s["DB_HOST"],
            port=int(s["DB_PORT"]),
            database=s["DB_NAME"],
            query={"sslmode": "require"},
        )
    except (KeyError, FileNotFoundError):
        url = get_db_url()
    return create_engine(url, pool_pre_ping=True)


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
            text(
                "SELECT COALESCE(SUM(tancagem_total_m3), 0) "
                "FROM fct_tancagem_agregada WHERE is_distribuicao"
            )
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
def load_mapa_postos(uf: str | None) -> pd.DataFrame:
    """Retorna postos com coordenadas. uf=None carrega Brasil inteiro."""
    if uf is None:
        sql = text("""
            SELECT
                p.codigo_isimp,
                p.uf,
                COALESCE(p.razao_social, 'Não informado')        AS razao_social,
                COALESCE(p.bandeira, 'Bandeira Branca')           AS bandeira,
                p.municipio,
                p.latitude,
                p.longitude,
                COALESCE(p.status_pmqc, 'Não informado')         AS status_pmqc,
                COALESCE(p.vinculacao_distribuidor, 'Não informado') AS distribuidor
            FROM dim_postos p
            WHERE p.latitude IS NOT NULL
              AND p.longitude IS NOT NULL
        """)
        return pd.read_sql(sql, get_engine())
    else:
        sql = text("""
            SELECT
                p.codigo_isimp,
                p.uf,
                COALESCE(p.razao_social, 'Não informado')        AS razao_social,
                COALESCE(p.bandeira, 'Bandeira Branca')           AS bandeira,
                p.municipio,
                p.latitude,
                p.longitude,
                COALESCE(p.status_pmqc, 'Não informado')         AS status_pmqc,
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
def load_distribuidores_lista() -> list[str]:
    """Lista de distribuidores presentes nos postos, em ordem alfabética."""
    sql = """
        SELECT DISTINCT vinculacao_distribuidor
        FROM dim_postos
        WHERE vinculacao_distribuidor IS NOT NULL
          AND vinculacao_distribuidor != 'Não informado'
        ORDER BY vinculacao_distribuidor
    """
    df = pd.read_sql(sql, get_engine())
    return df["vinculacao_distribuidor"].tolist()


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
# Helpers
# =============================================================================
def fmt_num(n: int | float) -> str:
    """Formata número com separador de milhar em pt-BR."""
    return f"{n:,.0f}".replace(",", ".")


def _donut_layout(height: int = 420) -> dict:
    """Layout padrão para gráficos de rosca com rótulos externos."""
    return dict(
        paper_bgcolor="rgba(0,0,0,0)",
        showlegend=True,
        legend=dict(
            x=1.02,
            y=0.5,
            xanchor="left",
            yanchor="middle",
            font=dict(size=12),
        ),
        margin=dict(l=0, r=160, t=30, b=0),
        height=height,
    )


# Estilo padrão para rótulos de barra — branco, legível no fundo escuro
_BAR_TEXTFONT = dict(size=14, color="#FFFFFF")


# =============================================================================
# Cabeçalho
# =============================================================================
st.markdown(
    """
    <div class="bloco-titulo">
      <h2>⛽ ANP Fuel Intelligence — Rede São Roque</h2>
      <p>Análise da infraestrutura de distribuição de combustíveis no Brasil
         · Dados públicos ANP e IBGE · Referência: abril/2026</p>
    </div>
    """,
    unsafe_allow_html=True,
)

tabs = st.tabs([
    "📊 Panorama Nacional",
    "🗺️ Mapa de Postos",
    "🛢️ Tancagem e Capacidade",
    "🏢 Infraestrutura x Mercado",
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
    c1.metric("Postos cadastrados", fmt_num(kpis["total_postos"]))
    c2.metric("Distribuidoras ativas", fmt_num(kpis["dist_ativas"]))
    c3.metric(
        "Capacidade de distribuição",
        f"{kpis['capacidade_m3'] / 1_000_000:.1f} M m³",
    )
    c4.metric(
        "Postos com geolocalização",
        f"{fmt_num(kpis['postos_com_coord'])}"
        f" ({100 * kpis['postos_com_coord'] / kpis['total_postos']:.0f}%)",
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
            text="total_postos",
        )
        fig_uf.update_layout(
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            legend_title_text="Região",
            xaxis_tickangle=-45,
            height=550,
            font=dict(size=13),
        )
        fig_uf.update_traces(
            textposition="inside",
            texttemplate="%{y:,}",
            textfont=dict(size=22, color="#FFFFFF", family="Arial Black"),
            insidetextanchor="end",
        )
        st.plotly_chart(fig_uf, use_container_width=True)

    with col_dir:
        st.subheader("Top marcas")
        fig_band = px.bar(
            df_bandeira,
            x="total_postos",
            y="bandeira",
            orientation="h",
            color_discrete_sequence=[COR_PRIMARIA],
            labels={"total_postos": "Postos", "bandeira": "Bandeira"},
            text="total_postos",
        )
        fig_band.update_layout(
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            yaxis={"categoryorder": "total ascending"},
            height=500,
            font=dict(size=13),
            margin=dict(r=100),
            xaxis=dict(range=[0, df_bandeira["total_postos"].max() * 1.25]),
        )
        fig_band.update_traces(
            textposition="outside",
            texttemplate="%{x:,}",
            textfont=dict(size=18, color="#FFFFFF", family="Arial Black"),
        )
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
        text="postos_por_100k",
    )
    fig_100k.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        xaxis_tickangle=-45,
        height=550,
        font=dict(size=13),
    )
    fig_100k.update_traces(
        textposition="inside",
        texttemplate="%{y:.1f}",
        textfont=dict(size=22, color="#FFFFFF", family="Arial Black"),
        insidetextanchor="end",
    )
    st.plotly_chart(fig_100k, use_container_width=True)


# =============================================================================
# TAB 2 — MAPA DE POSTOS
# =============================================================================
with tabs[1]:
    df_uf_lista = load_postos_por_uf()
    ufs_disponiveis = df_uf_lista["uf"].tolist()

    # ---- Filtros — linha 1 ----
    col_visao, col_uf, col_cor = st.columns([2, 2, 3])

    with col_visao:
        visao = st.radio(
            "Abrangência",
            ["Brasil completo", "Por UF"],
            horizontal=True,
        )

    with col_uf:
        if visao == "Por UF":
            uf_sel = st.selectbox(
                "Selecione a UF",
                ufs_disponiveis,
                index=ufs_disponiveis.index("SP"),
            )
        else:
            uf_sel = None
            st.markdown("&nbsp;")

    with col_cor:
        cor_mapa = st.radio(
            "Colorir por",
            ["Bandeira", "UF", "Status PMQC", "Distribuidor"],
            horizontal=True,
        )

    cor_col = {
        "Bandeira": "bandeira",
        "UF": "uf",
        "Status PMQC": "status_pmqc",
        "Distribuidor": "distribuidor",
    }[cor_mapa]

    # ---- Filtro — Distribuidores ----
    todos_dist = load_distribuidores_lista()
    dist_sel = st.multiselect(
        "Filtrar por distribuidor (deixe vazio para exibir todos)",
        options=todos_dist,
        default=[],
        placeholder="Selecione um ou mais distribuidores...",
    )

    # ---- Dados ----
    with st.spinner("Carregando mapa..."):
        df_mapa = load_mapa_postos(uf_sel)

    # Aplica filtro de distribuidores se houver seleção
    if dist_sel:
        df_mapa = df_mapa[df_mapa["distribuidor"].isin(dist_sel)]

    if visao == "Brasil completo":
        total_ref = kpis["total_postos"]
        zoom_inicial = 3.5
        centro_lat, centro_lon = -14.5, -51.0
        label_vis = "Brasil"
    else:
        total_ref = int(
            df_uf_lista.loc[df_uf_lista["uf"] == uf_sel, "total_postos"].values[0]
        )
        zoom_inicial = 6
        centro_lat = float(df_mapa["latitude"].mean()) if not df_mapa.empty else -15.0
        centro_lon = float(df_mapa["longitude"].mean()) if not df_mapa.empty else -51.0
        label_vis = uf_sel

    st.markdown(
        f"**{label_vis}** — {fmt_num(total_ref)} postos cadastrados | "
        f"{fmt_num(len(df_mapa))} com coordenadas "
        f"({100 * len(df_mapa) / total_ref:.0f}%)"
    )

    if df_mapa.empty:
        st.warning(f"Nenhum posto com coordenadas encontrado para {label_vis}.")
    else:
        fig_mapa = px.scatter_mapbox(
            df_mapa,
            lat="latitude",
            lon="longitude",
            color=cor_col,
            hover_name="razao_social",
            hover_data={
                "uf": True,
                "municipio": True,
                "bandeira": True,
                "distribuidor": True,
                "status_pmqc": True,
                "latitude": False,
                "longitude": False,
            },
            zoom=zoom_inicial,
            center={"lat": centro_lat, "lon": centro_lon},
            height=620,
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
    df_tanc_emp  = load_tancagem_por_empresa()
    df_tanc_seg  = load_tancagem_por_segmento()
    df_tanc_prod = load_tancagem_por_produto()
    df_prod_postos = load_produtos_postos()

    st.subheader("Top 20 empresas por capacidade de armazenagem (ramo de distribuição)")
    df_tanc_emp["cap_label"] = (
        (df_tanc_emp["capacidade_m3"] / 1_000).round(1).astype(str) + " mil m³"
    )
    fig_tanc = px.bar(
        df_tanc_emp,
        x="capacidade_m3",
        y="empresa",
        orientation="h",
        color_discrete_sequence=[COR_PRIMARIA],
        labels={"capacidade_m3": "Capacidade (m³)", "empresa": "Empresa"},
        hover_data={"qtd_tanques": True, "uf": True},
        text="cap_label",
    )
    fig_tanc.update_layout(
        yaxis={"categoryorder": "total ascending"},
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        height=520,
        font=dict(size=13),
    )
    fig_tanc.update_traces(
        textposition="outside",
        textfont=dict(size=18, color="#FFFFFF", family="Arial Black"),
    )
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
            hole=0.42,
        )
        fig_seg.update_traces(
            textposition="outside",
            textinfo="label+percent",
            textfont_size=12,
            pull=[0.03] * len(df_tanc_seg),
        )
        fig_seg.update_layout(**_donut_layout(460))
        st.plotly_chart(fig_seg, use_container_width=True)

    with col_prod:
        st.subheader("Capacidade por grupo de produtos")
        fig_prod = px.pie(
            df_tanc_prod,
            names="produto",
            values="capacidade_m3",
            color_discrete_sequence=SEQUENCIA,
            hole=0.42,
        )
        fig_prod.update_traces(
            textposition="outside",
            textinfo="label+percent",
            textfont_size=12,
            pull=[0.03] * len(df_tanc_prod),
        )
        fig_prod.update_layout(**_donut_layout(460))
        st.plotly_chart(fig_prod, use_container_width=True)

    st.markdown("---")
    st.subheader("Combustíveis nos postos — cobertura e tancagem (SIMP)")
    fig_comb = px.bar(
        df_prod_postos,
        x="produto",
        y="postos",
        color_discrete_sequence=[COR_SECUNDARIA],
        labels={"produto": "Produto", "postos": "Postos"},
        text="postos",
    )
    fig_comb.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        xaxis_tickangle=-35,
        height=400,
        font=dict(size=13),
        yaxis=dict(range=[0, df_prod_postos["postos"].max() * 1.25]),
    )
    fig_comb.update_traces(
        textposition="outside",
        texttemplate="%{y:,}",
        textfont=dict(size=18, color="#FFFFFF", family="Arial Black"),
    )
    st.plotly_chart(fig_comb, use_container_width=True)


# =============================================================================
# TAB 4 — INFRAESTRUTURA x MERCADO
# =============================================================================
with tabs[3]:
    df_im = load_infra_mercado()

    st.subheader("Presença de mercado vs. capacidade de armazenagem por distribuidora")
    st.caption(
        "Cada ponto representa uma distribuidora ativa com mais de 10 postos vinculados. "
        "Tamanho proporcional ao número de postos. "
        "Distribuidoras com capacidade zero não possuem instalações registradas na tancagem ANP."
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
        size_max=55,
        height=520,
    )
    fig_scatter.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(size=13),
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
            height=480,
            font=dict(size=13),
        )
        fig_rank.update_traces(
            textposition="outside",
            texttemplate="%{x:,}",
            textfont=dict(size=18, color="#FFFFFF", family="Arial Black"),
        )
        st.plotly_chart(fig_rank, use_container_width=True)

    with col_reg:
        st.subheader("Postos por região")
        df_reg = df_im.groupby("regiao")["postos_vinculados"].sum().reset_index()
        fig_reg = px.pie(
            df_reg,
            names="regiao",
            values="postos_vinculados",
            color_discrete_sequence=SEQUENCIA,
            hole=0.42,
        )
        fig_reg.update_traces(
            textposition="outside",
            textinfo="label+percent",
            textfont_size=13,
            pull=[0.03] * len(df_reg),
        )
        fig_reg.update_layout(**_donut_layout(420))
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
    "Desenvolvido com Python, PostgreSQL e Streamlit · Rede São Roque."
)
