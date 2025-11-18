import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import json
import streamlit as st
import os
from pathlib import Path

# === CONFIGURAÇÃO STRAVA (COMPATÍVEL COM STREAMLIT CLOUD) ===
def get_strava_credentials():
    """Obtém credenciais do Strava de forma segura para Streamlit Cloud"""
    try:
        # Tenta pegar do Streamlit Secrets (Streamlit Cloud)
        CLIENT_ID = st.secrets["STRAVA_CLIENT_ID"]
        CLIENT_SECRET = st.secrets["STRAVA_CLIENT_SECRET"] 
        REFRESH_TOKEN = st.secrets["STRAVA_REFRESH_TOKEN"]
        return CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN
    except Exception as e:
        # Fallback para valores padrão (apenas para teste)
        st.error(f"❌ Erro ao carregar credenciais: {e}")
        return None, None, None

# URLs da API
TOKEN_URL = "https://www.strava.com/oauth/token"
ACTIVITIES_URL = "https://www.strava.com/api/v3/athlete/activities"

def format_pace(seconds_per_km):
    """Converte segundos por km em formato MM:SS"""
    if pd.isna(seconds_per_km) or seconds_per_km <= 0:
        return "N/A"
    mins = int(seconds_per_km // 60)
    secs = int(seconds_per_km % 60)
    return f"{mins}:{secs:02d}"

def renew_access_token():
    """Renova o access token usando refresh token"""
    CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN = get_strava_credentials()
    
    if not all([CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN]):
        st.error("❌ Credenciais do Strava não configuradas. Verifique o Streamlit Secrets.")
        return None
    
    payload = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "refresh_token",
        "refresh_token": REFRESH_TOKEN
    }
    
    try:
        resp = requests.post(TOKEN_URL, data=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        st.success("✅ Token renovado com sucesso")
        return data.get("access_token")
    except Exception as e:
        st.error(f"❌ Erro ao renovar token: {e}")
        return None

def fetch_all_activities(access_token, per_page=50, max_pages=20):
    """Busca todas as atividades paginadas"""
    if not access_token:
        return []
        
    headers = {"Authorization": f"Bearer {access_token}"}
    activities = []
    
    with st.spinner("Buscando atividades do Strava..."):
        for page in range(1, max_pages + 1):
            params = {"per_page": per_page, "page": page}
            try:
                r = requests.get(ACTIVITIES_URL, headers=headers, params=params, timeout=15)
                r.raise_for_status()
                page_items = r.json()
                if not page_items:
                    break
                activities.extend(page_items)
                st.write(f"📄 Página {page}: {len(page_items)} atividades")
            except Exception as e:
                st.error(f"❌ Erro página {page}: {e}")
                break
                
    if activities:
        st.success(f"✅ Total de atividades carregadas: {len(activities)}")
    else:
        st.warning("⚠️ Nenhuma atividade encontrada")
        
    return activities

def transform_activities(activities: list) -> pd.DataFrame:
    """Transforma atividades em DataFrame limpo"""
    if not activities:
        return pd.DataFrame()
        
    records = []
    for act in activities:
        records.append({
            "id": act.get("id"),
            "name": act.get("name"),
            "type": act.get("type"),
            "date": pd.to_datetime(act.get("start_date_local")),
            "distance_km": act.get("distance", 0) / 1000,
            "duration_min": act.get("moving_time", 0) / 60,
            "elevation_m": act.get("total_elevation_gain", 0),
            "avg_speed_kmh": act.get("average_speed", 0) * 3.6,
            "max_speed_kmh": act.get("max_speed", 0) * 3.6,
            "calories": act.get("calories", 0),
            "kudos": act.get("kudos_count", 0),
            "polyline": act.get("map", {}).get("summary_polyline"),
        })
    
    df = pd.DataFrame(records)
    
    # Evita divisão por zero
    df["pace_min_km"] = df["duration_min"] / df["distance_km"].replace({0: pd.NA})
    
    # Formata com 1 casa decimal
    df["distance_km"] = df["distance_km"].round(1)
    df["pace_min_km"] = df["pace_min_km"].round(1)
    df["date_only"] = df["date"].dt.date
    df["month_year"] = df["date"].dt.to_period("M")
    
    return df

def save_csv(df: pd.DataFrame, name: str = "activities.csv"):
    """Salva DataFrame como CSV (usa /tmp no Streamlit Cloud)."""
    try:
        if 'STREAMLIT_CLOUD' in os.environ:
            path = Path("/tmp") / name
        else:
            # salva localmente na pasta do projeto (evita path não existente)
            path = Path(__file__).resolve().parent.parent / name
            path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(path, index=False)
        # usar print também para logs fora do Streamlit
        try:
            st.success(f"✅ CSV salvo: {path}")
        except Exception:
            print(f"CSV salvo: {path}")
        return path
    except Exception as e:
        try:
            st.error(f"❌ Erro ao salvar CSV: {e}")
        except Exception:
            print(f"Erro ao salvar CSV: {e}")
        return None

def create_distance_over_time(df: pd.DataFrame):
    """Gráfico de distância acumulada ao longo do tempo"""
    if df.empty:
        return None
    df_sorted = df.sort_values("date")
    df_sorted["cumulative_distance"] = df_sorted["distance_km"].cumsum()
    fig = px.line(df_sorted, x="date", y="cumulative_distance", markers=True,
                  title=" Distância Acumulada", 
                  labels={"cumulative_distance":"Distância (km)","date":"Data"})
    # remover título do eixo X de forma confiável
    fig.update_xaxes(title_text="")
    return fig

def create_activity_type_pie(df: pd.DataFrame):
    """Pizza com tipos de atividade"""
    if df.empty:
        return None
    counts = df["type"].value_counts().reset_index()
    counts.columns = ["type", "count"]
    fig = px.pie(counts, names="type", values="count", 
                 title=" Distribuição por Tipo de Atividade")
    fig.update_xaxes(title_text="")
    return fig

def create_pace_trend(df: pd.DataFrame):
    """Gráfico de tendência de pace"""
    if df.empty:
        return None
    df_filtered = df[df["distance_km"] > 0].sort_values("date")
    if df_filtered.empty:
        return None
    fig = px.scatter(df_filtered, x="date", y="pace_min_km", trendline="lowess",
                     title=" Tendência de Pace (min/km)", 
                     labels={"pace_min_km":"Pace (min/km)","date":"Data"},
                     hover_data=["name","distance_km","duration_min"])
    fig.update_xaxes(title_text="")
    return fig

def create_speed_vs_distance(df: pd.DataFrame):
    """Scatter: velocidade média vs distância"""
    if df.empty:
        return None
    fig = px.scatter(df, x="distance_km", y="avg_speed_kmh", size="duration_min",
                     color="type", hover_name="name",
                     title="⚡ Velocidade Média vs Distância",
                     labels={"distance_km":"Distância (km)","avg_speed_kmh":"Velocidade (km/h)"})
    fig.update_xaxes(title_text="")
    return fig

def create_monthly_stats(df: pd.DataFrame):
    """Gráfico de barras: distância total (km) por mês"""
    if df.empty:
        return None
    monthly = df.groupby("month_year", as_index=False).agg({
        "distance_km": "sum",
        "duration_min": "sum",
        "type": "count"
    })
    monthly["month_year"] = monthly["month_year"].astype(str)
    monthly = monthly.sort_values("month_year")
    
    fig = px.bar(monthly, x="month_year", y="distance_km",
                 title=" Distância Total por Mês",
                 labels={"month_year":"Mês","distance_km":"Distância (km)"},
                 text=monthly["distance_km"].round(1))
    fig.update_traces(textposition="outside")
    fig.update_layout(xaxis_tickangle=-45)
    fig.update_xaxes(title_text="")
    return fig

def create_elevation_histogram(df: pd.DataFrame):
    """Histograma de elevação"""
    if df.empty:
        return None
    df_filtered = df[df["elevation_m"] > 0]
    if df_filtered.empty:
        return None
    fig = px.histogram(df_filtered, x="elevation_m", nbins=20,
                       title=" Distribuição de Elevação", 
                       labels={"elevation_m":"Elevação (m)"})
    fig.update_xaxes(title_text="")
    return fig

def create_calories_vs_distance(df: pd.DataFrame):
    """Gráfico de calorias vs distância"""
    if df.empty:
        return None
    fig = px.scatter(df, x="distance_km", y="calories", color="type",
                     hover_name="name", trendline="lowess",
                     title=" Calorias vs Distância",
                     labels={"distance_km":"Distância (km)", "calories":"Calorias"})
    fig.update_xaxes(title_text="")
    return fig

def filter_by_date(df: pd.DataFrame, start_date: str = None, end_date: str = None) -> pd.DataFrame:
    """Filtra DataFrame pelo intervalo [start_date, end_date]"""
    if df.empty:
        return df
        
    if start_date:
        try:
            sd = pd.to_datetime(start_date)
            df = df[df["date"] >= sd]
        except:
            st.warning("⚠️ Data inicial inválida")
    
    if end_date:
        try:
            ed = pd.to_datetime(end_date)
            # Inclui o dia inteiro
            df = df[df["date"] <= ed + timedelta(days=1) - timedelta(seconds=1)]
        except:
            st.warning("⚠️ Data final inválida")
    
    return df

def get_activity_stats(df: pd.DataFrame):
    """Retorna estatísticas resumidas das atividades"""
    if df.empty:
        return {
            "total_activities": 0,
            "total_distance_km": 0,
            "total_duration_hours": 0,
            "total_elevation_m": 0,
            "avg_pace": 0,
            "first_date": None,
            "last_date": None
        }
    
    stats = {
        "total_activities": len(df),
        "total_distance_km": df["distance_km"].sum(),
        "total_duration_hours": df["duration_min"].sum() / 60,
        "total_elevation_m": df["elevation_m"].sum(),
        "avg_pace": df[df["pace_min_km"] > 0]["pace_min_km"].mean(),
        "first_date": df["date"].min(),
        "last_date": df["date"].max()
    }
    return stats

def load_activities(per_page=50, max_pages=20):
    """
    Função principal para carregar atividades - COMPATÍVEL COM STREAMLIT CLOUD
    """
    # 1. Renovar token
    access_token = renew_access_token()
    if not access_token:
        st.error("❌ Falha na autenticação com Strava")
        return pd.DataFrame()
    
    # 2. Buscar atividades
    activities = fetch_all_activities(access_token, per_page, max_pages)
    if not activities:
        st.error("❌ Nenhuma atividade encontrada")
        return pd.DataFrame()
    
    # 3. Transformar dados
    df = transform_activities(activities)
    
    if not df.empty:
        st.success(f"✅ Dados carregados: {len(df)} atividades")
    else:
        st.error("❌ Erro ao transformar dados")
        
    return df

# Função para uso local (sem Streamlit)
def main_local():
    """Função principal para execução local"""
    print("=== ETL STRAVA (Local) ===\n")
    
    # 1. Renovar token
    print("1. Renovando token...")
    access_token = renew_access_token()
    if not access_token:
        print("Falha ao renovar token. Abortando.")
        return
    
    # 2. Buscar atividades
    print("\n2. Buscando atividades...")
    activities = fetch_all_activities(access_token, per_page=50, max_pages=20)
    if not activities:
        print("Nenhuma atividade encontrada.")
        return
    
    # 3. Transformar
    print("\n3. Transformando dados...")
    df = transform_activities(activities)
    print(f"   Dimensões: {df.shape}")
    print(f"   Período: {df['date'].min()} a {df['date'].max()}")
    
    # 4. Estatísticas
    stats = get_activity_stats(df)
    print(f"\n📊 Total distância:")
    print(f"   Total atividades: {stats['total_activities']}")
    print(f"   Distância total: {stats['total_distance_km']:.1f} km")
    print(f"   Duração total: {stats['total_duration_hours']:.1f} horas")
    print(f"   Elevação total: {stats['total_elevation_m']:.0f} m")

if __name__ == "__main__":
    # Se executado localmente (sem Streamlit)
    import sys
    if 'streamlit' not in sys.modules:
        main_local()
