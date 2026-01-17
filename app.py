import streamlit as st
import pandas as pd
import numpy as np
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from scipy.stats import poisson
import random
import plotly.express as px

# ==============================================================================
# CONFIGURAÇÃO E CSS
# ==============================================================================
st.set_page_config(page_title="Bot Brasil - Robin Hood V2", page_icon="🏹", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #0f1419; color: #ffffff; }
    .stMetric { background-color: #1a1f2e; padding: 15px; border-radius: 10px; border-left: 4px solid #00d4ff; }
    </style>
""", unsafe_allow_html=True)

# ==============================================================================
# TÉCNICA ROBIN HOOD (SCRAPING LEVE COM BEAUTIFULSOUP)
# ==============================================================================

@st.cache_data(ttl=600) # Cache de 10 minutos para não sobrecarregar
def raspar_placar_futebol(url):
    try:
        # User-Agent para fingir ser um navegador comum e não ser bloqueado
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        # Faz a requisição rápida (sem abrir navegador)
        response = requests.get(url, headers=headers, timeout=10)
        
        # Transforma o HTML em objeto navegável
        soup = BeautifulSoup(response.text, 'html.parser')
        
        jogos = []
        
        # Tenta encontrar os jogos usando as classes comuns do site
        # 'match-list-item' é o container padrão de jogos no placardefutebol.com.br
        for partida in soup.find_all(['div', 'a'], class_=['match-list-item', 'match-card', 'container-main']):
            try:
                # Extrai todo o texto da partida e quebra em linhas limpas
                linhas = [line.strip() for line in partida.get_text(separator='\n').split('\n') if line.strip()]
                
                # Lógica para achar Hora e Times
                # Procura string com formato 00:00
                hora = next((l for l in linhas if ":" in l and len(l) == 5), "00:00")
                
                # Filtra o que não é hora, nem status "Ao Vivo" para achar os nomes dos times
                times = [l for l in linhas if len(l) > 2 and ":" not in l and "Ao Vivo" not in l and "Final" not in l and "Intervalo" not in l and "ENCERRADO" not in l]
                
                # Se achou pelo menos 2 nomes (Casa e Fora)
                if len(times) >= 2:
                    # Às vezes o nome do time é composto, pegamos o primeiro e o segundo elemento principal
                    jogos.append({
                        "hora": hora,
                        "casa": times[0],
                        "fora": times[1]
                    })
            except:
                continue
                
        return jogos
    except Exception as e:
        st.error(f"Erro na raspagem: {e}")
        return []

# ==============================================================================
# MOTOR ESTATÍSTICO
# ==============================================================================

def calcular_probabilidades(m_casa, m_fora):
    pv, pe, pd = 0, 0, 0
    # Distribuição de Poisson para prever placares de 0x0 até 9x9
    for h in range(10):
        for a in range(10):
            p = poisson.pmf(h, m_casa) * poisson.pmf(a, m_fora)
            if h > a: pv += p
            elif h == a: pe += p
            else: pd += p
    return pv, pe, pd

# ==============================================================================
# INTERFACE
# ==============================================================================

st.title("🏹 Bot Brasil - Robin Hood (Versão Leve)")
st.markdown("**Sistema Gratuito usando Raspagem HTTP (Sem Selenium)**")

with st.sidebar:
    st.header("⚙️ Ajustes")
    banca = st.number_input("Sua Banca (R$)", value=100.0)
    
    liga = st.selectbox("Escolha a Liga", [
        "Jogos de Hoje (Geral)", 
        "Brasileirão Série A", 
        "Premier League (ING)", 
        "La Liga (ESP)", 
        "Campeonato Baiano"
    ])
    
    # Mapeamento de URLs
    urls = {
        "Jogos de Hoje (Geral)": "https://www.placardefutebol.com.br/jogos-de-hoje",
        "Brasileirão Série A": "https://www.placardefutebol.com.br/brasileirao-serie-a",
        "Premier League (ING)": "https://www.placardefutebol.com.br/ingles",
        "La Liga (ESP)": "https://www.placardefutebol.com.br/espanhol",
        "Campeonato Baiano": "https://www.placardefutebol.com.br/baiano"
    }
    
    if st.button("🔄 Atualizar Dados", use_container_width=True):
        st.cache_data.clear()

# --- EXECUÇÃO PRINCIPAL ---

st.write(f"Buscando dados de: **{liga}**...")
dados_brutos = raspar_placar_futebol(urls[liga])

if not dados_brutos:
    st.warning(f"⚠️ Nenhum jogo encontrado em '{liga}' neste momento. Tente 'Jogos de Hoje (Geral)' ou verifique se há rodada hoje.")
else:
    resultados = []
    
    for j in dados_brutos:
        # --- SIMULAÇÃO DE ANÁLISE ---
        # Nota: Como scraping simples não traz estatísticas passadas (chutes, cantos),
        # usamos uma simulação de força baseada na aleatoriedade controlada para demonstração.
        # Em um app real de ADS, você conectaria isso a um banco de dados CSV com o histórico dos times.
        
        f_casa = random.uniform(0.9, 1.6) # Time da casa tende a ser mais forte
        f_fora = random.uniform(0.8, 1.4)
        
        # Médias de gols estimadas (Lambdas de Poisson)
        lambda_casa = 1.35 * f_casa
        lambda_fora = 1.10 * f_fora
        
        pv, pe, pd = calcular_probabilidades(lambda_casa, lambda_fora)
        
        odd_justa = 1/pv if pv > 0 else 100
        odd_real_simulada = odd_justa * 0.90 # Simula a margem da casa de aposta (juice)
        
        ev = (pv * odd_real_simulada) - 1
        
        # Formata para tabela
        resultados.append({
            "Hora": j['hora'],
            "Confronto": f"{j['casa']} x {j['fora']}",
            "Prob. Casa": f"{pv*100:.1f}%",
            "Odd Justa": round(odd_justa, 2),
            "Odd Mercado (Est.)": round(odd_real_simulada, 2),
            "EV (%)": round(ev * 100, 2),
            "Sugestão": "✅ APOSTAR" if ev > 0.05 else "❌ PASSAR"
        })

    df = pd.DataFrame(resultados)
    
    # Métricas de Topo
    c1, c2, c3 = st.columns(3)
    c1.metric("Jogos Encontrados", len(df))
    # Conta quantos jogos tem sugestão de aposta
    oportunidades = len(df[df['Sugestão'] == "✅ APOSTAR"])
    c2.metric("Oportunidades (+EV)", oportunidades)
    c3.metric("Banca", f"R$ {banca:.2f}")
    
    st.divider()
    
    # Tabela Principal
    st.subheader("📋 Painel de Análise")
    st.dataframe(
        df, 
        use_container_width=True,
        hide_index=True
    )

    # Gráfico de Valor Esperado
    if not df.empty:
        col_graf1, col_graf2 = st.columns(2)
        with col_graf1:
            st.markdown("### Ranking de Valor Esperado")
            # Ordena pelos melhores jogos
            df_sorted = df.sort_values("EV (%)", ascending=False).head(10)
            fig = px.bar(
                df_sorted, 
                x="EV (%)", 
                y="Confronto", 
                orientation='h',
                color="EV (%)",
                color_continuous_scale="RdYlGn",
                text="EV (%)"
            )
            fig.update_layout(yaxis={'categoryorder':'total ascending'})
            st.plotly_chart(fig, use_container_width=True)
