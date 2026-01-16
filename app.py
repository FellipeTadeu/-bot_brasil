import streamlit as st
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from scipy.stats import poisson
import time
import plotly.graph_objects as go
import plotly.express as px

# ==============================================================================
# CONFIGURAÇÃO DA PÁGINA
# ==============================================================================
st.set_page_config(
    page_title="Bot Brasil - Dashboard de Apostas",
    page_icon="🏆",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS Customizado
st.markdown("""
    <style>
    .main {
        background-color: #0f1419;
        color: #ffffff;
    }
    .stMetric {
        background-color: #1a1f2e;
        padding: 15px;
        border-radius: 10px;
        border-left: 4px solid #00d4ff;
    }
    .alerta-positivo {
        background-color: #1a3a1a;
        border-left: 4px solid #00ff00;
        padding: 10px;
        border-radius: 5px;
    }
    .alerta-neutro {
        background-color: #1a2a3a;
        border-left: 4px solid #00d4ff;
        padding: 10px;
        border-radius: 5px;
    }
    .alerta-negativo {
        background-color: #3a1a1a;
        border-left: 4px solid #ff4444;
        padding: 10px;
        border-radius: 5px;
    }
    </style>
""", unsafe_allow_html=True)

# ==============================================================================
# CONFIGURAÇÕES E CONSTANTES
# ==============================================================================
API_KEY = "a8267cf3a1c929aaa5a6451b683f7352" 
HEADERS = {
    "x-rapidapi-key": API_KEY,
    "x-rapidapi-host": "api-football-v1.p.rapidapi.com"
}
BASE_URL = "https://api-football-v1.p.rapidapi.com/v3"

TEMPORADA = 2026

# ==============================================================================
# FUNÇÕES ESTATÍSTICAS (MOTOR V9)
# ==============================================================================

@st.cache_data(ttl=3600)
def calcular_poisson(media_casa, media_visitante):
    """Calcula probabilidades de 1X2 usando distribuição de Poisson."""
    prob_v, prob_e, prob_d = 0, 0, 0
    max_gols = 10 
    for h in range(max_gols):
        for a in range(max_gols):
            p = poisson.pmf(h, media_casa) * poisson.pmf(a, media_visitante)
            if h > a: prob_v += p
            elif h == a: prob_e += p
            else: prob_d += p
    total = prob_v + prob_e + prob_d
    return (prob_v/total), (prob_e/total), (prob_d/total)

def criterio_kelly(prob_minha, odd_casa, fracao=0.25):
    """Calcula a porcentagem da banca a ser apostada (Kelly Fracionário)."""
    if odd_casa <= 1: return 0
    q = 1 - prob_minha
    f_star = (prob_minha * (odd_casa - 1) - q) / (odd_casa - 1)
    return max(0, f_star * fracao)

@st.cache_data(ttl=1800)
def buscar_odds_reais(fixture_id):
    """Busca odds da Bet365 para o mercado Match Winner."""
    try:
        params = {"fixture": fixture_id, "bookmaker": 8}
        r = requests.get(f"{BASE_URL}/odds", headers=HEADERS, params=params)
        data = r.json().get('response', [])
        if not data: return None
        
        for b in data[0].get('bookmakers', []):
            if b['id'] == 8:
                for bet in b.get('bets', []):
                    if bet['id'] == 1:
                        return {val['value']: float(val['odd']) for val in bet['values']}
    except:
        return None
    return None

@st.cache_data(ttl=1800)
def carregar_dados_liga(id_liga):
    """Carrega histórico e próximos jogos de uma liga."""
    try:
        # Histórico
        r_hist = requests.get(f"{BASE_URL}/fixtures", headers=HEADERS, params={"league": id_liga, "season": TEMPORADA, "status": "FT"})
        jogos_hist = r_hist.json().get('response', [])
        
        if not jogos_hist: return None, None
        
        df_hist = pd.DataFrame([{'home': j['teams']['home']['name'], 'away': j['teams']['away']['name'], 'gh': j['goals']['home'], 'ga': j['goals']['away']} for j in jogos_hist])
        
        # Próximos Jogos
        hoje = datetime.now().date()
        r_fut = requests.get(f"{BASE_URL}/fixtures", headers=HEADERS, params={"league": id_liga, "season": TEMPORADA, "status": "NS", "from": hoje.strftime("%Y-%m-%d"), "to": (hoje + timedelta(days=7)).strftime("%Y-%m-%d")})
        jogos_fut = r_fut.json().get('response', [])
        
        return df_hist, jogos_fut
    except Exception as e:
        st.error(f"Erro ao carregar dados: {e}")
        return None, None

def processar_jogo(jogo, df_hist, m_casa_liga, m_fora_liga, banca):
    """Processa um jogo individual e retorna análise completa."""
    f_id = jogo['fixture']['id']
    casa, fora = jogo['teams']['home']['name'], jogo['teams']['away']['name']
    data_dt = datetime.fromisoformat(jogo['fixture']['date'].replace('Z', '+00:00'))
    
    # Filtragem de histórico
    h_casa = df_hist[df_hist['home'] == casa]
    h_fora = df_hist[df_hist['away'] == fora]
    
    if len(h_casa) < 2 or len(h_fora) < 2:
        return None
    
    # Cálculo de Poisson
    l_h = (h_casa['gh'].mean() / m_casa_liga) * (h_fora['ga'].mean() / m_fora_liga) * m_casa_liga
    l_a = (h_fora['ga'].mean() / m_fora_liga) * (h_casa['gh'].mean() / m_casa_liga) * m_fora_liga
    
    pv, pe, pd = calcular_poisson(l_h, l_a)
    fair_odd = 1/pv if pv > 0 else 99
    
    # Odds Reais
    odds_reais = buscar_odds_reais(f_id)
    odd_casa_real = odds_reais.get('Home', 0) if odds_reais else 0
    
    # EV e Kelly
    ev = (pv * odd_casa_real) - 1 if odd_casa_real > 0 else -1
    stake_pct = criterio_kelly(pv, odd_casa_real) if ev > 0 else 0
    stake_valor = banca * stake_pct
    
    # Classificação
    if ev > 0.15: alerta = "🔥 VALOR ALTO"
    elif ev > 0.05: alerta = "✅ VALOR"
    elif pv > 0.70: alerta = "💎 FAVORITO"
    else: alerta = "⚠️ SEM VALOR"
    
    return {
        'fixture_id': f_id,
        'data': data_dt,
        'casa': casa,
        'fora': fora,
        'lambda_h': l_h,
        'lambda_a': l_a,
        'prob_vitoria': pv * 100,
        'prob_empate': pe * 100,
        'prob_derrota': pd * 100,
        'fair_odd': fair_odd,
        'odd_real': odd_casa_real,
        'ev': ev * 100,
        'stake_pct': stake_pct * 100,
        'stake_valor': stake_valor,
        'alerta': alerta
    }

# ==============================================================================
# INTERFACE STREAMLIT
# ==============================================================================

# Header
st.title("🏆 Bot Brasil - Dashboard de Apostas Profissional")
st.markdown("**Sistema Avançado de Tomada de Decisão com Análise de Valor Esperado (+EV)**")

# Sidebar
with st.sidebar:
    st.header("⚙️ Configurações")
    
    banca_total = st.number_input(
        "Banca Total (R$)",
        min_value=100.0,
        value=1000.0,
        step=100.0,
        help="Valor total disponível para apostas"
    )
    
    ligas_selecionadas = st.multiselect(
        "Ligas a Analisar",
        options=list(LIGAS_IDS.keys()),
        default=list(LIGAS_IDS.keys()),
        help="Selecione as ligas que deseja analisar"
    )
    
    ev_minimo = st.slider(
        "EV Mínimo (%)",
        min_value=0.0,
        max_value=20.0,
        value=5.0,
        step=0.5,
        help="Filtrar apenas apostas com este EV mínimo"
    )
    
    atualizar = st.button("🔄 Atualizar Análise", use_container_width=True)

# Tabs principais
tab1, tab2, tab3 = st.tabs(["📊 Análise Completa", "💰 Gestão de Banca", "📈 Estatísticas"])

# ==============================================================================
# TAB 1: ANÁLISE COMPLETA
# ==============================================================================
with tab1:
    if atualizar or True:
        st.info("🔄 Carregando dados... Isso pode levar alguns segundos.")
        
        todos_jogos = []
        
        for nome_liga in ligas_selecionadas:
            id_liga = LIGAS_IDS[nome_liga]
            df_hist, jogos_fut = carregar_dados_liga(id_liga)
            
            if df_hist is None or not jogos_fut:
                st.warning(f"⚠️ Sem dados para {nome_liga}")
                continue
            
            m_casa_liga, m_fora_liga = df_hist['gh'].mean(), df_hist['ga'].mean()
            
            for jogo in jogos_fut:
                resultado = processar_jogo(jogo, df_hist, m_casa_liga, m_fora_liga, banca_total)
                if resultado:
                    resultado['liga'] = nome_liga
                    todos_jogos.append(resultado)
        
        if todos_jogos:
            df_analise = pd.DataFrame(todos_jogos)
            
            # Filtrar por EV mínimo
            df_filtrado = df_analise[df_analise['ev'] >= ev_minimo]
            
            # Ordenar por EV decrescente
            df_filtrado = df_filtrado.sort_values('ev', ascending=False)
            
            # Métricas Gerais
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("Total de Jogos", len(df_analise))
            with col2:
                st.metric("Jogos com Valor", len(df_filtrado))
            with col3:
                st.metric("Stake Total Sugerido", f"R$ {df_filtrado['stake_valor'].sum():.2f}")
            with col4:
                lucro_esperado = (df_filtrado['ev'] / 100 * df_filtrado['stake_valor']).sum()
                st.metric("Lucro Esperado", f"R$ {lucro_esperado:.2f}", delta="+" if lucro_esperado > 0 else "-")
            
            st.divider()
            
            # Tabela Interativa
            st.subheader("📋 Análise Detalhada de Jogos")
            
            # Preparar dados para exibição
            df_display = df_filtrado.copy()
            df_display['data'] = df_display['data'].dt.strftime('%d/%m %H:%M')
            df_display['confronto'] = df_display['casa'] + " x " + df_display['fora']
            df_display['prob_vitoria'] = df_display['prob_vitoria'].round(1).astype(str) + "%"
            df_display['fair_odd'] = df_display['fair_odd'].round(2)
            df_display['odd_real'] = df_display['odd_real'].round(2)
            df_display['ev'] = df_display['ev'].round(2).astype(str) + "%"
            df_display['stake_valor'] = "R$ " + df_display['stake_valor'].round(2).astype(str)
            
            colunas_exibir = ['data', 'liga', 'confronto', 'prob_vitoria', 'fair_odd', 'odd_real', 'ev', 'stake_valor', 'alerta']
            df_display_final = df_display[colunas_exibir].rename(columns={
                'data': 'Data',
                'liga': 'Liga',
                'confronto': 'Confronto',
                'prob_vitoria': 'Prob. Vitória',
                'fair_odd': 'Fair Odd',
                'odd_real': 'Odd Real',
                'ev': 'EV',
                'stake_valor': 'Stake',
                'alerta': 'Alerta'
            })
            
            st.dataframe(df_display_final, use_container_width=True, height=400)
            
            # Gráficos
            st.subheader("📈 Visualizações")
            
            col_grafico1, col_grafico2 = st.columns(2)
            
            with col_grafico1:
                # Gráfico de EV por Jogo
                fig_ev = px.bar(
                    df_filtrado.sort_values('ev', ascending=True),
                    y='confronto',
                    x='ev',
                    orientation='h',
                    title="Valor Esperado (+EV) por Jogo",
                    labels={'ev': 'EV (%)', 'confronto': 'Confronto'},
                    color='ev',
                    color_continuous_scale='RdYlGn'
                )
                fig_ev.update_layout(height=400, showlegend=False)
                st.plotly_chart(fig_ev, use_container_width=True)
            
            with col_grafico2:
                # Gráfico de Distribuição de Probabilidades
                fig_prob = go.Figure()
                for idx, row in df_filtrado.head(5).iterrows():
                    fig_prob.add_trace(go.Bar(
                        x=['Vitória', 'Empate', 'Derrota'],
                        y=[row['prob_vitoria'], row['prob_empate'], row['prob_derrota']],
                        name=row['confronto']
                    ))
                fig_prob.update_layout(
                    title="Probabilidades (Top 5 Jogos)",
                    barmode='group',
                    height=400,
                    yaxis_title="Probabilidade (%)"
                )
                st.plotly_chart(fig_prob, use_container_width=True)
        else:
            st.error("❌ Nenhum jogo encontrado com os critérios selecionados.")

# ==============================================================================
# TAB 2: GESTÃO DE BANCA
# ==============================================================================
with tab2:
    st.subheader("💰 Gestão de Banca e Critério de Kelly")
    
    col_banca1, col_banca2 = st.columns(2)
    
    with col_banca1:
        st.metric("Banca Inicial", f"R$ {banca_total:.2f}")
        
        # Simulação de Apostas
        st.markdown("### 📊 Simulador de Apostas")
        
        prob_simulada = st.slider("Probabilidade de Sucesso (%)", 0, 100, 60) / 100
        odd_simulada = st.number_input("Odd Oferecida", min_value=1.0, value=2.0, step=0.1)
        
        ev_simulado = (prob_simulada * odd_simulada) - 1
        kelly_simulado = criterio_kelly(prob_simulada, odd_simulada)
        stake_simulado = banca_total * kelly_simulado
        
        st.markdown(f"""
        **Resultados da Simulação:**
        - **EV:** {ev_simulado*100:.2f}%
        - **Kelly (25%):** {kelly_simulado*100:.2f}% da banca
        - **Stake Sugerido:** R$ {stake_simulado:.2f}
        """)
    
    with col_banca2:
        # Tabela de Kelly para diferentes cenários
        st.markdown("### 📈 Tabela de Kelly (Referência)")
        
        kelly_data = []
        for prob in [0.50, 0.55, 0.60, 0.65, 0.70]:
            for odd in [1.50, 2.00, 2.50, 3.00]:
                ev = (prob * odd) - 1
                kelly = criterio_kelly(prob, odd)
                kelly_data.append({
                    'Probabilidade': f"{prob*100:.0f}%",
                    'Odd': f"{odd:.2f}",
                    'EV': f"{ev*100:.1f}%",
                    'Kelly (25%)': f"{kelly*100:.2f}%"
                })
        
        df_kelly = pd.DataFrame(kelly_data)
        st.dataframe(df_kelly, use_container_width=True)

# ==============================================================================
# TAB 3: ESTATÍSTICAS
# ==============================================================================
with tab3:
    st.subheader("📊 Estatísticas e Análises")
    
    # Resumo por Liga
    if 'df_analise' in locals() and not df_analise.empty:
        st.markdown("### 🏆 Resumo por Liga")
        
        resumo_liga = df_analise.groupby('liga').agg({
            'ev': ['count', 'mean', 'max'],
            'stake_valor': 'sum'
        }).round(2)
        
        st.dataframe(resumo_liga, use_container_width=True)
        
        # Distribuição de EV
        fig_dist = px.histogram(
            df_analise,
            x='ev',
            nbins=20,
            title="Distribuição de Valor Esperado",
            labels={'ev': 'EV (%)', 'count': 'Quantidade de Jogos'},
            color_discrete_sequence=['#00d4ff']
        )
        st.plotly_chart(fig_dist, use_container_width=True)

# Footer
st.divider()
st.markdown("""
---
**Bot Brasil V9.0** | Sistema Profissional de Tomada de Decisão em Apostas
- Desenvolvido com Streamlit
- Análise Estatística: Distribuição de Poisson
- Gestão de Risco: Critério de Kelly Fracionário
- Integração de Mercado: Odds Reais (Bet365)

⚠️ **Aviso Legal:** Este sistema é apenas uma ferramenta de análise. Apostas envolvem risco. Aposte responsavelmente.
""")
