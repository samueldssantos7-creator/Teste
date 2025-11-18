import streamlit as st
from pathlib import Path
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import os

# === CONFIGURAÇÃO SEGURA PARA STREAMLIT CLOUD ===
if 'STREAMLIT_CLOUD' in os.environ:
    BASE_DIR = Path('/mount/src/strava-dashboard')
else:
    BASE_DIR = Path(__file__).resolve().parent

# Usar BASE_DIR diretamente (mais seguro)
OUT_DIR = BASE_DIR

# importe as funções do seu etl.py (mesmo diretório)
from etl import (
    load_activities,
    create_distance_over_time, 
    create_activity_type_pie,
    create_pace_trend,
    create_monthly_stats,
    filter_by_date,    # <--- adicionada
)

# === CONFIGURAÇÃO DE CORES E DIRETÓRIOS ===
STRAVA_ORANGE = '#FC4C02'
LINE_COLOR = 'white'
# ==========================================

# === HELPER FUNCTIONS ===

def format_pace_minutes(pace_min):
    """Formata pace em minutos para MM:SS"""
    if pd.isna(pace_min) or pace_min == 0:
        return "N/A"
    pace_min = round(pace_min, 1)
    mins = int(pace_min)
    secs = int(round((pace_min - mins) * 60))
    return f"{mins}:{secs:02d}"

def format_minutes_hms(total_min):
    """Formata minutos para HH:MM:SS"""
    if pd.isna(total_min) or total_min == 0:
        return "0:00:00"
    total_min = round(total_min, 1)
    total_seconds = int(total_min * 60)
    hrs = total_seconds // 3600
    mins = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    return f"{hrs}:{mins:02d}:{secs:02d}"

def categorize_distance(distance_km):
    """Categoriza a corrida por distância"""
    if distance_km < 5:
        return "Treino leve (< 5km)"
    elif distance_km < 10:
        return "Curta (5-10km)"
    elif distance_km < 21:
        return "Médio (10-21km)"
    else:
        return "Meia maratona (> 21km)"

def total_runs_by_km(df_in):
    """Gráfico de dispersão: total corridas por km (cores por tipo de atividade)"""
    if df_in.empty:
        return None
    df_in = df_in.copy()
    df_in["distance_km"] = pd.to_numeric(df_in["distance_km"], errors="coerce").fillna(0)
    df_in["duration_min"] = pd.to_numeric(df_in["duration_min"], errors="coerce").fillna(0)

    # Cores por tipo (adapte se seus tipos forem diferentes)
    preferred = {
        "Run": "#FC4C02",        # laranja Strava
        "Ride": "#1f77b4",       # azul
        "Bike": "#17becf",       # ajustar bike para cor distinta
        "Walk": "#2ca02c",       # verde
        "Hike": "#8c564b",       # marrom
        "VirtualRun": "#9467bd",
        "EBikeRide": "#7f7f7f"
    }

    unique_types = [t for t in df_in["type"].dropna().unique()]
    # Palette fallback para tipos não mapeados
    fallback_palette = ["#e377c2", "#bcbd22", "#ff7f0e", "#17becf"]
    color_map = {}
    for i, t in enumerate(sorted(unique_types, key=lambda x: str(x))):
        color_map[t] = preferred.get(t, fallback_palette[i % len(fallback_palette)])

    fig = px.scatter(
        df_in,
        x="distance_km",
        y="distance_km",
        size="duration_min",
        color="type",
        hover_name="name",
        title="Distribuição de corridas por distância",
        labels={"distance_km": "Distância (km)"},
        trendline=None,
        color_discrete_map=color_map
    )

    # garantir sem título no eixo X (não forçar centralização)
    fig.update_layout(xaxis_title=None)
    return fig

def pace_by_category(df_in):
    """Gráfico de barras: pace médio por categoria"""
    if df_in.empty:
        return None
    df_in = df_in.copy()
    df_in["distance_km"] = pd.to_numeric(df_in["distance_km"], errors="coerce").fillna(0)
    df_in["duration_min"] = pd.to_numeric(df_in["duration_min"], errors="coerce").fillna(0)
    df_in["category"] = df_in["distance_km"].apply(categorize_distance)
    df_in["pace_min_km"] = df_in.apply(
        lambda row: row["duration_min"] / row["distance_km"] if row["distance_km"] > 0 else pd.NA,
        axis=1
    )
    df_in["pace_min_km"] = pd.to_numeric(df_in["pace_min_km"], errors="coerce")
    df_in["pace_min_km"] = df_in["pace_min_km"].round(1)
    cat_pace = df_in.groupby("category")["pace_min_km"].mean().reset_index()
    cat_pace = cat_pace.sort_values("pace_min_km")
    cat_pace = cat_pace.dropna(subset=["pace_min_km"])
    if cat_pace.empty:
        return None
    fig = px.bar(cat_pace, x="category", y="pace_min_km",
                 title="Pace médio por categoria de distância",
                 labels={"category":"Categoria","pace_min_km":"Pace (min/km)"},
                 text=cat_pace["pace_min_km"].apply(lambda x: format_pace_minutes(x)),
                 color_discrete_sequence=["#FC4C02"])
    fig.update_traces(textposition="outside")
    fig.update_layout(xaxis_tickangle=-45, xaxis_title=None)
    return fig

# === CONFIGURAÇÃO INICIAL ===
st.set_page_config(page_title="Dashboard Strava", layout="wide")
st.title("🏃 Dashboard Strava — Interativo")

# CSS para KPIs
st.markdown(
    """
    <style>
    /* KPIs: centralizar título e valor */
    div[data-testid="metric-container"] {
        display: flex !important;
        justify-content: center !important;
    }
    div[data-testid="stMetric"] {
        align-items: center !important;
        display: flex !important;
        flex-direction: column !important;
        background-color: #FC4C02 !important;
        border-radius: 10px !important;
        padding: 10px !important;
        color: white !important;
    }
    div[data-testid="stMetricValue"] {
        color: white !important;
        text-align: center !important;
        font-size: 1.4em !important;
    }
    div[data-testid="stMetricLabel"] {
        color: white !important;
        text-align: center !important;
        font-weight: bold !important;
    }

    /* Evita overflow nos gráficos do Plotly dentro do Streamlit */
    .element-container .stPlotlyChart div[role="img"] {
        box-sizing: border-box;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

@st.cache_data(ttl=3600)
def load_cached_activities(per_page: int, max_pages: int) -> pd.DataFrame:
    """Função para buscar dados do Strava, usa cache do Streamlit."""
    return load_activities(per_page=per_page, max_pages=max_pages)

# -- Removido bloco sidebar duplicado aqui para evitar StreamlitDuplicateElementId --
# (A barra lateral com filtros é definida mais abaixo, após o carregamento dos dados.)

# === CARREGAMENTO DE DADOS ===
btn_fetch = False  # Inicializa como False para evitar erro de referência antes da definição
try:
    csv_path = OUT_DIR / "activities.csv"
    if csv_path.exists():
        df = pd.read_csv(csv_path) 
        st.info(f"Carregado CSV local: {csv_path.name}")
    else:
        df = pd.DataFrame()
        st.warning("Sem dados locais. Pressione 'Buscar/Atualizar dados'.")
except Exception as e:
    st.error(f"Erro ao carregar CSV: {e}")
    df = pd.DataFrame()

if df.empty:
    st.error("❌ Não foi possível carregar os dados. Verifique suas credenciais no Streamlit Secrets.")
    st.stop()

# === TRATAMENTO DE COLUNAS ===
# Verificar coluna de data
date_col = None
for col in ["date", "start_date", "start_date_local"]:
    if col in df.columns:
        date_col = col
        break

if not date_col:
    st.error("❌ Nenhuma coluna de data encontrada")
    st.stop()

df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
df = df.rename(columns={date_col: "date"})

# Verificar coluna de distância
if "distance_km" not in df.columns:
    for col in ["distance", "distance_km"]:
        if col in df.columns:
            df["distance_km"] = pd.to_numeric(df[col], errors="coerce")
            if col == "distance":  # Se for em metros, converter para km
                df["distance_km"] = df["distance_km"] / 1000
            break

# Verificar coluna de duração
if "duration_min" not in df.columns:
    for col in ["moving_time", "elapsed_time", "duration"]:
        if col in df.columns:
            # Converter segundos para minutos
            df["duration_min"] = pd.to_numeric(df[col], errors="coerce") / 60
            break

# Verificar coluna de tipo
if "type" not in df.columns:
    for col in ["sport_type", "type", "activity_type"]:
        if col in df.columns:
            df["type"] = df[col]
            break

# Remover linhas com dados essenciais faltando
df = df.dropna(subset=['date'])
if "distance_km" in df.columns:
    df = df[df["distance_km"] > 0]
if "duration_min" in df.columns:
    df = df[df["duration_min"] > 0]

if df.empty:
    st.error("❌ Nenhum dado válido após o processamento")
    st.stop()

# -------------------------------------------------------------------
# REMOVIDO: bloco que aplicava filtro de período antes do sidebar
# -------------------------------------------------------------------

# === SIDEBAR: CONFIGURAÇÃO E FILTROS (ANO / MÊS / DIA) ===
with st.sidebar:
    st.header("Configuração")
    per_page = st.number_input("Atividades por página", min_value=10, max_value=200, value=50, step=10, key="per_page")
    max_pages = st.number_input("Máx páginas", min_value=1, max_value=50, value=4, key="max_pages")
    btn_fetch = st.button("Buscar/Atualizar dados", key="btn_fetch")

    # >>> REMOVIDO: date_input (filtro de período)
    # from datetime import date
    # min_date = df["date"].min().date() if 'df' in locals() and not df.empty else date.today()
    # max_date = df["date"].max().date() if 'df' in locals() and not df.empty else date.today()
    # start_date, end_date = st.date_input("Período", value=(min_date, max_date), key="filter_range")

    # filtros por ano / mês / dia
    years = sorted(df["date"].dt.year.dropna().unique())
    year_options = ["Todos"] + [str(y) for y in years]
    selected_year = st.selectbox("Ano", options=year_options, index=0, key="sel_year")

    months_present = sorted(df["date"].dt.month.dropna().unique())
    month_map = {1:"Jan",2:"Fev",3:"Mar",4:"Abr",5:"Mai",6:"Jun",7:"Jul",8:"Ago",9:"Set",10:"Out",11:"Nov",12:"Dez"}
    month_options = ["Todos"] + [f"{m:02d} - {month_map.get(m,str(m))}" for m in months_present]
    selected_month_raw = st.selectbox("Mês", options=month_options, index=0, key="sel_month")

    days_present = sorted(df["date"].dt.day.dropna().unique())
    day_options = ["Todos"] + [str(int(d)) for d in days_present]
    selected_day = st.selectbox("Dia", options=day_options, index=0, key="sel_day")

# >>> NOVO: aplicar filtros (sem período) imediatamente após o sidebar
# cria df_filtered padrão para evitar NameError (pode ser modificado pelos filtros abaixo)
df_filtered = df.copy()

try:
    # aplicar filtro por ano
    if selected_year != "Todos":
        df_filtered = df_filtered[df_filtered["date"].dt.year == int(selected_year)]

    # aplicar filtro por mês (selected_month_raw no formato "MM - Nome" ou "Todos")
    if selected_month_raw != "Todos":
        month_num = int(selected_month_raw.split(" - ")[0])
        df_filtered = df_filtered[df_filtered["date"].dt.month == month_num]

    # aplicar filtro por dia
    if selected_day != "Todos":
        df_filtered = df_filtered[df_filtered["date"].dt.day == int(selected_day)]
except Exception:
    # em caso de qualquer problema, mantém df_filtered original
    df_filtered = df.copy()

# === KPIs NO CORPO PRINCIPAL (primeiros, centralizados) ===
st.markdown("")  # espaço mínimo abaixo do título
kpi_col_count = 4
cols = st.columns(kpi_col_count, gap="large")

# calculate metrics on df_filtered (will be updated below if filters applied)
def render_kpis(df_kpi):
    total_acts = len(df_kpi)
    total_dist = round(df_kpi["distance_km"].sum(), 1) if "distance_km" in df_kpi.columns else None
    # duração total em horas (solicitado)
    total_dur_hours = round(df_kpi["duration_min"].sum() / 60, 1) if "duration_min" in df_kpi.columns else None
    first_date = df_kpi["date"].min().strftime('%Y-%m-%d') if "date" in df_kpi.columns else ""
    last_date = df_kpi["date"].max().strftime('%Y-%m-%d') if "date" in df_kpi.columns else ""

    # calcular pace médio (min/km) como duração total / distância total
    avg_pace = None
    try:
        if ("duration_min" in df_kpi.columns) and ("distance_km" in df_kpi.columns) and df_kpi["distance_km"].sum() > 0:
            avg_pace = round(df_kpi["duration_min"].sum() / df_kpi["distance_km"].sum(), 1)
    except Exception:
        avg_pace = None

    with cols[0]:
        st.metric("Total Atividades", f"{total_acts}")
    with cols[1]:
        st.metric("Distância Total (km)", f"{total_dist}" if total_dist is not None else "N/A")
    with cols[2]:
        st.metric("Duração Total (h)", f"{total_dur_hours} h" if total_dur_hours is not None else "N/A")
    with cols[3]:
        # substitui "Período" por "Pace médio"
        pace_display = format_pace_minutes(avg_pace) if avg_pace is not None else "N/A"
        st.metric("Pace médio (min/km)", pace_display)

# Se usuário clicar em aplicar filtros, faz o filtro; caso contrário, mantém tudo
if 'apply_filters' in locals() and apply_filters:
    df_filtered = df.copy()
    try:
        if selected_year != "Todos":
            df_filtered = df_filtered[df_filtered["date"].dt.year == int(selected_year)]
        if selected_month != "Todos":
            df_filtered = df_filtered[df_filtered["date"].dt.month == int(selected_month)]
        if selected_day != "Todos":
            df_filtered = df_filtered[df_filtered["date"].dt.day == int(selected_day)]
    except Exception:
        # em caso de qualquer problema, mantém df_filtered original
        df_filtered = df.copy()

# Render KPIs sempre com o
render_kpis(df_filtered)

# === GRÁFICOS ===
st.subheader("🏃 Resumo Geral")

# helper para remover emoji no título da figura (caso venham de etl.py)
def remove_emoji_from_fig_title(fig):
    try:
        title_text = fig.layout.title.text
        if title_text:
            # remove o emoji de corrida se existir e retira espaços iniciais
            new_title = title_text.replace("🏃", "").lstrip()
            fig.update_layout(title_text=new_title)
    except Exception:
        pass
    return fig

with st.spinner("Gerando gráficos..."):
    col1, col2 = st.columns(2, gap="large")
    
    with col1:
        fig1 = create_distance_over_time(df_filtered)
        if fig1:
            fig1 = remove_emoji_from_fig_title(fig1)
            fig1.update_layout(title_text="🏃 Distância acumulada")    # título com ícone
            fig1.update_traces(marker_color="#FC4C02", line_color="#FC4C02")
            fig1.update_layout(xaxis_title=None)
            fig1.update_layout(margin=dict(t=40, b=60, l=40, r=20), height=420)
            st.plotly_chart(fig1, use_container_width=True)

        fig3 = create_pace_trend(df_filtered)
        if fig3:
            fig3 = remove_emoji_from_fig_title(fig3)
            fig3.update_layout(title_text="🏃 Tendência de pace")    # título com ícone
            fig3.update_traces(marker_color="#FC4C02", line_color="#FC4C02")
            fig3.update_layout(xaxis_title=None)
            fig3.update_layout(margin=dict(t=40, b=60, l=40, r=20), height=420)
            st.plotly_chart(fig3, use_container_width=True)

    with col2:
        fig2 = create_activity_type_pie(df_filtered)
        if fig2:
            fig2 = remove_emoji_from_fig_title(fig2)
            fig2.update_layout(title_text="🏃 Tipos de atividade")    # título com ícone

            color_map = {
                "Run": "#FC4C02",
                "Walk": "#2ca02c",
                "Ride": "#1f77b4",
            }
            try:
                labels = list(fig2.data[0].labels)
                colors = [color_map.get(lbl, "#A0522D") for lbl in labels]
                fig2.update_traces(marker=dict(colors=colors))
            except Exception:
                fig2.update_traces(marker=dict(colors=["#FC4C02", "#2ca02c", "#1f77b4", "#A0522D"]))

            fig2.update_layout(xaxis_title=None)
            fig2.update_layout(margin=dict(t=40, b=60, l=40, r=20), height=420)
            st.plotly_chart(fig2, use_container_width=True)

        fig_km = total_runs_by_km(df_filtered)
        if fig_km:
            fig_km = remove_emoji_from_fig_title(fig_km)
            fig_km.update_layout(title_text="🏃 Distribuição por distância")   # título com ícone
            fig_km.update_layout(xaxis_title=None)
            fig_km.update_layout(margin=dict(t=40, b=60, l=40, r=20), height=460)
            fig_km.update_yaxes(automargin=True)
            st.plotly_chart(fig_km, use_container_width=True)

    fig_monthly = create_monthly_stats(df_filtered)
    if fig_monthly:
        fig_monthly = remove_emoji_from_fig_title(fig_monthly)
        # manter título ou ajustar se quiser; aqui removemos apenas o eixo Y
        fig_monthly.update_layout(title_text="🏃 Total distância")
        # esconder todo o eixo Y (linhas, ticks e labels)
        fig_monthly.update_yaxes(visible=False)
        fig_monthly.update_traces(marker_color="#FC4C02")
        fig_monthly.update_layout(xaxis_title=None)
        fig_monthly.update_layout(margin=dict(t=70, b=100, l=40, r=20), height=540)
        fig_monthly.update_layout(uniformtext_minsize=8, uniformtext_mode='show')
        st.plotly_chart(fig_monthly, use_container_width=True)

    fig_cat = pace_by_category(df_filtered)
    if fig_cat:
        fig_cat = remove_emoji_from_fig_title(fig_cat)
        # manter título ou ajustar se quiser; aqui removemos apenas o eixo Y
        fig_cat.update_layout(title_text="🏃 Pace médio por categoria")
        # esconder todo o eixo Y (linhas, ticks e labels)
        fig_cat.update_yaxes(visible=False)
        fig_cat.update_traces(marker_color="#FC4C02")
        fig_cat.update_layout(xaxis_title=None)
        fig_cat.update_layout(margin=dict(t=70, b=100, l=40, r=20), height=540)
        fig_cat.update_layout(uniformtext_minsize=8, uniformtext_mode='show')
        st.plotly_chart(fig_cat, use_container_width=True)

# Download
if not df_filtered.empty:
    csv_bytes = df_filtered.to_csv(index=False).encode("utf-8")
    st.download_button("Baixar CSV", data=csv_bytes, file_name="activities.csv", mime="text/csv")

if not df.empty:
    st.write("Período total:", df["date"].min().strftime('%Y-%m-%d'), "→", df["date"].max().strftime('%Y-%m-%d'))

# === ARQUIVO .gitignore SUGERIDO ===
"""
.venv/
__pycache__/
*.pyc
activities.csv
"""
