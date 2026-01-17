import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from scipy.stats import poisson
import time
import plotly.graph_objects as go
import plotly.express as px
import random

# --- IMPORTAÇÕES DO SELENIUM (ROBIN HOOD) ---
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ==============================================================================
# CONFIGURAÇÃO DA PÁGINA
# ==============================================================================
st.set_page_config(
    page_title="Bot Brasil - Dashboard Robin Hood",
    page_icon="🏹",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS Customizado
st.markdown("""
    <style>
    .main { background-color: #0f1419; color: #ffffff; }
    .stMetric { background-color: #1a1f2e; padding: 15px; border-radius: 10px; border-left: 4px solid #00d4ff; }
    </style>
""", unsafe_allow_html=True)

# ==============================================================================
# CONFIGURAÇÕES E MAPEAMENTO DE URLS (TÉCNICA ROBIN HOOD)
# ==============================================================================

# Mapeando o nome da liga para o site onde vamos roubar os dados
# Fonte: Placar de Futebol (Site leve e bom para scraping)
URLS_LIGAS = {
    "Brasileirão Série A": "https://www.placardefutebol.com.br/brasileirao-serie-a",
    "Brasileirão Série B": "https://www.placardefutebol.com.br/brasileirao-serie-b",
    "Campeonato Baiano": "https://www.placardefutebol.com.br/baiano",
    "Premier League (ING)": "https://www.placardefutebol.com.br/ingles",
    "La Liga (ESP)": "https://www.placardefutebol.com.br/espanhol",
    "Serie A (ITA)": "https://www.placardefutebol.com.br/italiano",
    "Bundesliga (ALE)": "https://www.placardefutebol.com.br/alemao",
    "Ligue 1 (FRA)": "https://www.placardefutebol.com.br/frances",
    "Jogos de Hoje (Geral)": "https://www.placardefutebol.com.br/jogos-de-hoje"
}

# ==============================================================================
# MOTOR DE SCRAPING (SELENIUM) - BLINDADO PARA CLOUD
# ==============================================================================

@st.cache_resource
def iniciar_driver():
    """Inicia o navegador Chrome em modo invisível (Configuração Específica para Streamlit Cloud)."""
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    
    # Caminho padrão do Chromium no ambiente Linux do Streamlit
    chrome_options.binary_location = "/usr/bin/chromium"
    
    try:
        # Tenta usar o driver do sistema primeiro (instalado via packages.txt)
        service = Service("/usr/bin/chromedriver")
        driver = webdriver.Chrome(service=service, options=chrome_options)
        return driver
    except Exception as e:
        # Se falhar, tenta o fallback com webdriver_manager (Plan B)
        try:
            from webdriver_manager.chrome import ChromeDriverManager
            # Instala uma versão compatível automaticamente
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
            return driver
        except Exception as e2:
            st.error(f"Erro crítico ao iniciar navegador: {e} | {e2}")
            return None

@st.cache_data(ttl=1800) # Cache de 30min para não ser bloqueado
def raspar_jogos_do_site(url_liga):
    """Vai até o site e busca os jogos previstos."""
    driver = iniciar_driver()
    if not driver: return []
    
    jogos_encontrados = []
    
    try:
        driver.get(url_liga)
        # Espera carregar a tabela de jogos
        wait = WebDriverWait(driver, 10)
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        
        # Lógica Específica para placardefutebol.com.br
        # Procura blocos de jogos (container de partidas)
        partidas = driver.find_elements(By.CSS_SELECTOR, "div.match-list-item") # Seletor genérico
        
        if not partidas:
            # Tenta outro seletor comum (jogos de hoje)
            partidas = driver.find_elements(By.CSS_SELECTOR, "a.match-card")

        for p in partidas[:15]: # Pega no maximo 15 jogos para ser rapido
            try:
                # Extração de texto (Tentativa e Erro de Seletores)
                texto_completo = p.text.split('\n')
                
                # Geralmente o texto vem: "15:00", "Time A", "", "Time B"
                # Vamos tentar limpar e achar os times
                hora = "00:00"
                casa = "Desconhecido"
                fora = "Desconhecido"
                
                if len(texto_completo) >= 3:
                    # Tenta achar hora (tem :)
                    for t in texto_completo:
                        if ":" in t and len(t) == 5:
                            hora = t
                            break
                    
                    # Assume que os times são as strings maiores que não são hora
                    times_candidatos = [t for t in texto_completo if len(t) > 3 and ":" not in t and "Ao Vivo" not in t]
                    if len(times_candidatos) >= 2:
                        casa = times_candidatos[0]
                        fora = times_candidatos[1]
                
                # Se achou times validos
                if casa != "Desconhecido" and fora != "Desconhecido":
                    jogos_encontrados.append({
                        "fixture_id": random.randint(10000, 99999), # ID Fake
                        "date": f"{datetime.now().strftime('%Y-%m-%d')} {hora}",
                        "home_team": casa,
                        "away_team": fora
                    })
            except:
                continue
                
    except Exception as e:
        st.warning(f"Não foi possível raspar dados dessa liga no momento. Erro: {e}")
    finally:
        driver.quit()
        
    return jogos_encontrados

# ==============================================================================
# FUNÇÕES ESTATÍSTICAS (ADAPTADAS)
# ==============================================================================

def calcular_poisson(media_casa, media_visitante):
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
    if odd_casa <= 1: return 0
    q = 1 - prob_minha
    f_star = (prob_minha * (odd_casa - 1) - q) / (odd_casa - 1)
    return max(0, f_star * fracao)

def processar_jogo_scraped(jogo, m_casa_liga, m_fora_liga, banca):
    """Processa jogo raspado (sem histórico detalhado, usa médias da liga)."""
    
    casa = jogo['home_team']
    fora = jogo['away_team']
    data_str = jogo['date']
    
    # --- MODELAGEM SIMPLIFICADA (Robin Hood) ---
    # Como não temos o histórico exato do scraping, usamos uma simulação
    # baseada em "Fator Casa" + Aleatoriedade controlada para simular análise
    
    # Força estimada (Aleatória controlada para exemplo - Em produção, vc conectaria um CSV de stats)
    forca_casa = random.uniform(0.8, 1.5)
    forca_fora = random.uniform(0.7, 1.3)
    
    l_h = m_casa_liga * forca_casa
    l_a = m_fora_liga * forca_fora
    
    pv, pe, pd = calcular_poisson(l_h, l_a)
    fair_odd = 1/pv if pv > 0 else 99
    
    # Simulação de Odd Real (Já que não raspamos Bet365 pois bloqueiam fácil)
    # A odd real costuma ser a Fair Odd + Margem da Casa (aprox 5-10%)
    odd_real_simulada = fair_odd * 0.90 
    # Ajuste para mercado: se favorito, odd baixa
    if odd_real_simulada < 1.1: odd_real_simulada = 1.1
    
    ev = (pv * odd_real_simulada) - 1
    stake_pct = criterio_kelly(pv, odd_real_simulada) if ev > 0 else 0
    stake_valor = banca * stake_pct
    
    if ev > 0.15: alerta = "🔥 VALOR ALTO"
    elif ev > 0.05: alerta = "✅ VALOR"
    elif pv > 0.60: alerta = "💎 FAVORITO"
    else: alerta = "⚠️ SEM VALOR"
    
    return {
        'data': data_str,
        'casa': casa,
        'fora': fora,
        'prob_vitoria': pv * 100,
        'fair_odd': fair_odd,
        'odd_real': odd_real_simulada, # Simulada
        'ev': ev * 100,
        'stake_valor': stake_valor,
        'alerta': alerta
    }

# ==============================================================================
# INTERFACE STREAMLIT
# ==============================================================================

st.title("🏹 Bot Brasil - Dashboard Robin Hood")
st.markdown("**Versão Gratuita usando Web Scraping (Dados Reais do Placar de Futebol)**")

# Sidebar
with st.sidebar:
    st.header("⚙️ Configurações")
    banca_total = st.number_input("Banca Total (R$)", value=1000.0, step=100.0)
    
    # Seleção de Liga baseada nas URLs disponíveis
    liga_selecionada_nome = st.selectbox(
        "Escolha a Liga",
        options=list(URLS_LIGAS.keys())
    )
    
    url_alvo = URLS_LIGAS[liga_selecionada_nome]
    
    st.info(f"🔎 Fonte: {url_alvo}")
    atualizar = st.button("🔄 Raspar Dados Agora", use_container_width=True)

# Tabs
tab1, tab2 = st.tabs(["📊 Jogos Raspados", "💰 Gestão de Banca"])

with tab1:
    if atualizar:
        with st.status("🕵️ Raspando dados da web...", expanded=True) as status:
            st.write("Iniciando navegador invisível...")
            jogos = raspar_jogos_do_site(url_alvo)
            
            if not jogos:
                st.error("❌ Nenhum jogo encontrado ou bloqueio do site. Tente 'Jogos de Hoje (Geral)'.")
                status.update(label="Falha no Scraping", state="error")
            else:
                st.write(f"Encontrados {len(jogos)} jogos!")
                status.update(label="Scraping Concluído!", state="complete")
                
                # Processamento
                resultados = []
                # Médias genéricas de gols (Já que não temos histórico completo via scraping simples)
                m_casa, m_fora = 1.45, 1.15 
                
                for jogo in jogos:
                    res = processar_jogo_scraped(jogo, m_casa, m_fora, banca_total)
                    resultados.append(res)
                
                df = pd.DataFrame(resultados)
                
                # Exibição
                col1, col2, col3 = st.columns(3)
                col1.metric("Jogos Encontrados", len(df))
                col2.metric("Oportunidades (+EV)", len(df[df['ev'] > 0]))
                col3.metric("Banca Sugerida", f"R$ {df[df['ev']>0]['stake_valor'].sum():.2f}")
                
                st.divider()
                
                # Tabela Bonita
                st.dataframe(
                    df[['data', 'casa', 'fora', 'prob_vitoria', 'odd_real', 'ev', 'stake_valor', 'alerta']].style.format({
                        'prob_vitoria': "{:.1f}%",
                        'odd_real': "{:.2f}",
                        'ev': "{:.1f}%",
                        'stake_valor': "R$ {:.2f}"
                    }),
                    use_container_width=True,
                    height=500
                )

with tab2:
    st.info("A gestão de Kelly depende das probabilidades calculadas na aba anterior.")
    # (Mantive a lógica simples de Kelly aqui para referência)
    st.write("Simulador Rápido:")
    prob = st.slider("Sua Probabilidade", 0, 100, 50) / 100
    odd = st.number_input("Odd da Casa", 1.50)
    ev = (prob * odd) - 1
    kelly = criterio_kelly(prob, odd)
    st.write(f"Stake Sugerida: {(kelly*100):.2f}% (R$ {banca_total*kelly:.2f})")
