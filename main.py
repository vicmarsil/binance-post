import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from groq import Groq
import json
import time
import random
from datetime import datetime, timezone
import urllib.parse
import re
import os

from config import *
from redes_sociales import (
    publicar_en_square, publicar_en_blogger,
    publicar_en_facebook, enviar_telegram, enviar_telegram_multimedia
)

if ID_TELEGRAM and not (ID_TELEGRAM.lstrip('-').isdigit() or ID_TELEGRAM.startswith('@')):
    print(f"⚠️ ALERTA CONFIG: Tu ID_TELEGRAM ('{ID_TELEGRAM}') parece incorrecto. Debe ser NUMÉRICO.")

# Validación básica de seguridad
if not GROQ_API_KEY:
    raise ValueError("❌ Error: La variable GROQ_API_KEY no está configurada.")
if not MODO_PRUEBA and not SQUARE_API_KEY and TIPO_BOT not in ["BITGET", "LAUNCHPOOL"]:
    raise ValueError("❌ Error: SQUARE_API_KEY es necesaria para publicar en Binance (MODO_PRUEBA=False). Revisa tus Secretos en GitHub.")
if not MODO_PRUEBA and SQUARE_API_KEY:
    print(f"🔑 SQUARE_API_KEY cargada correctamente (Longitud: {len(SQUARE_API_KEY)})")

client = Groq(api_key=GROQ_API_KEY)

# --- CONFIGURACIÓN DE RED AVANZADA ---
# Reutiliza conexiones TCP (más rápido) y añade reintentos automáticos si hay micro-cortes.
sesion_http = requests.Session()
reintentos = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
sesion_http.mount('https://', HTTPAdapter(max_retries=reintentos))
sesion_http.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
})

def generar_texto_ia(prompt, temperatura=0.7):
    """Función centralizada para interactuar con el modelo de IA de Groq."""
    try:
        print(f"🤖 Conectando con Groq (Modelo: {GROQ_MODEL_NAME})...")
        chat_completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=GROQ_MODEL_NAME,
            temperature=temperatura
        )
        return chat_completion.choices[0].message.content
    except Exception as e:
        print(f"⚠️ Error generando texto con IA: {e}")
        return None

def cargar_historial():
    if os.path.exists(ARCHIVO_HISTORIAL):
        try:
            with open(ARCHIVO_HISTORIAL, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            print(f"⚠️ Advertencia: El archivo {ARCHIVO_HISTORIAL} está corrupto o vacío. Se creará uno nuevo.")
            return {}
    return {}

def guardar_historial(symbol):
    historial = cargar_historial()
    historial[symbol] = time.time()
    # Limpieza: Eliminar entradas de más de 24 horas (86400 segundos)
    limite = time.time() - 86400
    historial = {k: v for k, v in historial.items() if v > limite}
    
    with open(ARCHIVO_HISTORIAL, "w") as f:
        json.dump(historial, f, indent=4)

def obtener_datos_coingecko(symbol):
    """Backup: Obtiene precio y cambio 24h desde CoinGecko."""
    try:
        cg_id = COINGECKO_IDS.get(symbol)
        if not cg_id: return None
        
        url = "https://api.coingecko.com/api/v3/simple/price"
        params = {'ids': cg_id, 'vs_currencies': 'usd', 'include_24hr_change': 'true'}
        resp = sesion_http.get(url, params=params, timeout=10)
        
        if resp.status_code == 200:
            data = resp.json()
            if cg_id in data:
                # Adaptamos formato para que sea idéntico al de Binance
                return {
                    'lastPrice': data[cg_id]['usd'],
                    'priceChangePercent': data[cg_id]['usd_24h_change']
                }
    except Exception as e:
        print(f"⚠️ Error CoinGecko ({symbol}): {e}")
    return None

def obtener_fomo_coingecko(symbol):
    """Obtiene el porcentaje de sentimiento alcista (FOMO) de la comunidad en CoinGecko."""
    cg_id = COINGECKO_IDS.get(symbol)
    if not cg_id: return None
    
    try:
        url = f"https://api.coingecko.com/api/v3/coins/{cg_id}"
        # Pedimos solo lo básico para no saturar la API
        params = {'localization': 'false', 'tickers': 'false', 'market_data': 'false', 'community_data': 'false', 'developer_data': 'false', 'sparkline': 'false'}
        resp = sesion_http.get(url, params=params, timeout=10)
        
        if resp.status_code == 200:
            data = resp.json()
            fomo = data.get('sentiment_votes_up_percentage')
            return float(fomo) if fomo is not None else None
    except Exception as e:
        print(f"⚠️ Error obteniendo FOMO social para {symbol}: {e}")
    return None

def analizar_oportunidades():
    """
    Analiza la lista MONEDAS_ANALISIS y selecciona la MEJOR oportunidad basada en:
    1. RSI Extremo (Prioridad): < 30 (Sobreventa) o > 70 (Sobrecompra).
    2. Alta Volatilidad: Mayor cambio % absoluto si no hay RSI extremo.
    """
    print(f"🔍 Iniciando escaneo de mercado: {len(MONEDAS_ANALISIS)} activos...")
    
    # --- FILTRO ANTI-REPETICIÓN ---
    historial = cargar_historial()
    ahora = time.time()
    # Filtramos monedas usadas en las últimas 16 horas para forzar variedad
    monedas_filtradas = [
        m for m in MONEDAS_ANALISIS 
        if (ahora - historial.get(m.replace("USDT", ""), 0)) > (16 * 3600)
    ]
    
    if not monedas_filtradas:
        print("⚠️ Todas las monedas son recientes. Usando lista completa para asegurar publicación.")
        monedas_filtradas = MONEDAS_ANALISIS
    else:
        print(f"ℹ️ Lista filtrada: {len(monedas_filtradas)} monedas candidatas (se ocultaron {len(MONEDAS_ANALISIS)-len(monedas_filtradas)} recientes).")

    candidatos = []

    # Endpoints de respaldo y Headers para evitar bloqueos
    endpoints = [
        "https://api.binance.us/api/v3/ticker/24hr",
        "https://api.binance.com/api/v3/ticker/24hr",
        "https://api1.binance.com/api/v3/ticker/24hr",
        "https://api2.binance.com/api/v3/ticker/24hr"
    ]

    # --- 0. OBTENER CONTEXTO GLOBAL (BITCOIN) ---
    contexto_btc = 0
    try:
        btc_resp = sesion_http.get("https://api.binance.com/api/v3/ticker/24hr", params={'symbol': 'BTCUSDT'}, timeout=10)
        if btc_resp.status_code == 200:
            contexto_btc = float(btc_resp.json()['priceChangePercent'])
        print(f"🌍 Contexto Global (Bitcoin): {contexto_btc}%")
    except Exception as e:
        print("⚠️ No se pudo obtener el contexto de Bitcoin.")

    for symbol in monedas_filtradas:
        ticker = None
        base_url = "https://api.binance.com"

        for url_ticker in endpoints:
            try:
                # 1. Obtener Datos de Precio 24h con rotación
                resp = sesion_http.get(url_ticker, params={'symbol': symbol}, timeout=15)
                if resp.status_code == 200:
                    ticker = resp.json()
                    base_url = url_ticker.split("/api")[0]
                    break # Éxito, salimos del bucle de endpoints
                elif resp.status_code == 451:
                    print(f"⚠️ Bloqueo regional detectado en {url_ticker}, saltando a API secundaria...")
                else:
                    print(f"⚠️ Error {resp.status_code} conectando a {url_ticker}")
            except Exception as e:
                print(f"⚠️ Error de conexión en {url_ticker}: {e}")
                continue

        if not ticker:
            # Si Binance falla completamente, intentamos CoinGecko
            print(f"⚠️ Binance bloqueado para {symbol}. Intentando CoinGecko...")
            ticker = obtener_datos_coingecko(symbol)
            if ticker:
                base_url = None # Indicamos que no hay API de Binance para RSI
            else:
                print(f"❌ No se pudo obtener datos para {symbol} en ninguna fuente.")
                continue

        try:
            # 2. Calcular RSI 1h
            if base_url:
                rsi, ema50, _ = calcular_indicadores(symbol, base_url=base_url, headers=headers)
            else:
                rsi = 50 # RSI Neutro si usamos CoinGecko (solo estrategia de volatilidad)
                ema50 = None
            
            # Si falla el RSI (None) pero tenemos precio, usamos 50 para no descartar la moneda
            if rsi is None: 
                rsi = 50
                ema50 = None

            candidatos.append({
                "symbol": symbol.replace("USDT", ""),
                "lastPrice": float(ticker['lastPrice']),
                "percent": float(ticker['priceChangePercent']),
                "rsi": rsi,
                "ema50": ema50,
                "btc_change": contexto_btc
            })
            time.sleep(0.1) # Pausa cortés a la API
        except Exception as e:
            print(f"⚠️ Error analizando {symbol}: {e}")
            continue

    if not candidatos:
        print("❌ No se obtuvieron datos de mercado.")
        return None

    # CRITERIO DE SELECCIÓN
    # Filtramos RSI extremos (<30 o >70)
    extremos_rsi = [c for c in candidatos if c['rsi'] <= 30 or c['rsi'] >= 70]

    if extremos_rsi:
        # Si hay extremos, ganan. Ordenamos por qué tan lejos están de 50 (cuanto más lejos, más extremo)
        ganador = sorted(extremos_rsi, key=lambda x: abs(x['rsi'] - 50), reverse=True)[0]
        print(f"🏆 Ganador por RSI Extremo: {ganador['symbol']} (RSI: {ganador['rsi']:.1f})")
    else:
        # Si no, gana la que tenga mayor movimiento porcentual absoluto (subida o bajada fuerte)
        ganador = sorted(candidatos, key=lambda x: abs(x['percent']), reverse=True)[0]
        print(f"🏆 Ganador por Volatilidad: {ganador['symbol']} ({ganador['percent']}%)")

    return ganador

def generar_post_inteligente(datos_mercado):
    """
    2. Generación de Contenido con IA (Groq/Llama3):
    Redacta un análisis técnico breve y profesional.
    """
    moneda = datos_mercado['symbol']
    # Formateo a 2 decimales para la variación porcentual (Ej: 0.336 -> 0.34)
    cambio = f"{float(datos_mercado['percent']):.2f}"
    rsi = datos_mercado.get('rsi', 50)
    
    # Formateo visual más seguro para evitar precios en '0' o vacíos
    precio_float = float(datos_mercado['lastPrice'])
    if precio_float < 1:
        # Para monedas menores a 1$ (ej. TRX, ADA)
        precio = f"{precio_float:.5f}".rstrip("0").rstrip(".")
        if not precio: precio = "0"
    else:
        # Para monedas como BTC, ETH, SOL
        precio = f"{precio_float:.2f}"

    # Contexto dinámico para que la IA tenga variedad en su análisis
    cambio_float = float(cambio)
    if cambio_float > 20:
        contexto_tecnico = "Subida explosiva (posible FOMO). Tendencia fuertemente alcista. Menciona cautela por volatilidad."
    elif cambio_float > 5:
        contexto_tecnico = "Tendencia alcista sólida. El activo está ganando valor. Menciona fortaleza."
    elif cambio_float < -20:
        contexto_tecnico = "Caída severa (posible capitulación o pánico). Tendencia fuertemente bajista. Analiza si es oportunidad de rebote o riesgo."
    elif cambio_float < -5:
        contexto_tecnico = "Tendencia bajista continua. El activo ha estado perdiendo valor de forma constante. Sugiere precaución."
    else:
        contexto_tecnico = "Mercado lateral o consolidando. Volatilidad moderada, tendencia neutra."
    
    estado_rsi = "Neutro"
    if rsi > 70: estado_rsi = "Sobrecompra (Riesgo de corrección)"
    elif rsi < 30: estado_rsi = "Sobreventa (Oportunidad de rebote)"
    
    # Condicionar si hablamos del RSI. Si es 50 (neutro o por defecto de API caída), omitimos mencionarlo.
    if rsi != 50:
        info_tecnica = f"- RSI (1h): {rsi:.1f} ({estado_rsi})"
        instruccion_datos = f"Integra los datos ({precio}, RSI) dentro de las oraciones de forma narrativa."
    else:
        info_tecnica = "- Enfoque: Acción del precio, volatilidad y tendencia reciente."
        instruccion_datos = f"Integra el precio ({precio}) y la variación dentro de las oraciones. NO menciones el RSI en absoluto."

    fomo = datos_mercado.get('fomo')
    if fomo:
        if fomo >= 75:
            info_tecnica += f"\n    - Sentimiento Social: 🔥 ALTO FOMO ({fomo}% de los usuarios están comprando/alcistas)."
        elif fomo <= 40:
            info_tecnica += f"\n    - Sentimiento Social: 😨 MIEDO / PÁNICO (Solo {fomo}% están alcistas, la mayoría vende)."
        else:
            info_tecnica += f"\n    - Sentimiento Social: ⚖️ Neutro/Indecisión ({fomo}% alcistas)."
        instruccion_datos += " Menciona también cómo se siente la comunidad (el FOMO o el Miedo) según el sentimiento social."

    ema50 = datos_mercado.get('ema50')
    if ema50:
        tendencia_ema = "Alcista (Precio > EMA50)" if precio_float > ema50 else "Bajista o Falso Rebote (Precio < EMA50)"
        info_tecnica += f"\n    - Media Móvil (EMA 50): {tendencia_ema}."

    btc_change = datos_mercado.get('btc_change', 0)
    if btc_change <= -2:
        info_tecnica += f"\n    - Efecto Bitcoin: ⚠️ BTC está cayendo ({btc_change}%), advierte que podría arrastrar a esta moneda."
    elif btc_change >= 2:
        info_tecnica += f"\n    - Efecto Bitcoin: 🔥 BTC subiendo ({btc_change}%), viento a favor para el mercado general."

    # --- VARIACIÓN ALEATORIA DE ESTRUCTURA Y TONO (ANTI-REPETICIÓN) ---
    enfoques = [
        "Empieza directamente con un dato histórico fascinante o curiosidad sobre la moneda, y luego conecta eso con la variación de precio actual.",
        "Ve directo al grano con el análisis del precio y volatilidad, y luego menciona una noticia o detalle técnico del proyecto que respalde el movimiento.",
        "Inicia con una pregunta provocativa sobre el futuro del activo. Analiza el precio actual y da una píldora de conocimiento experto.",
        "Usa un tono de urgencia (alerta de tendencia). Destaca el precio primero, luego lanza un 'dato que pocos saben' sobre su tecnología."
    ]
    enfoque_seleccionado = random.choice(enfoques)

    prompt = f"""
    Actúa como un creador premium de Binance Square. Eres experto, magnético y NUNCA suenas repetitivo.
    
    DATOS DEL MERCADO:
    - Activo: {moneda}
    - Precio: {precio} USDT (Variación: {cambio}%)
    {info_tecnica}
    - Contexto: {contexto_tecnico}
    
    INSTRUCCIONES DE REDACCIÓN OBLIGATORIAS:
    - 🎯 ENFOQUE DE ESTA PUBLICACIÓN: {enfoque_seleccionado}
    - 🚫 CERO PLANTILLAS: No uses siempre la misma estructura. Cambia la forma en la que presentas el post (a veces usa título, a veces entra directo al texto).
    - 🚫 PROHIBIDO hacer listas enumeradas (nada de 1. 2. 3.). Usa párrafos fluidos de 2-3 líneas máximo.
    - 🧠 VALOR AGREGADO: Es fundamental que incluyas una curiosidad o aspecto técnico real de la red/ecosistema de {moneda}.
    - 📊 INTEGRACIÓN: {instruccion_datos} Hazlo de forma conversacional.
    - 🎁 CTA (LLAMADO A LA ACCIÓN): Es VITAL que pidas sutilmente un "Me gusta" (👍) o que te sigan para recibir más análisis de valor (ej. "Sígueme y no te pierdas la próxima alerta").
    -  ENGAGEMENT: Termina con una pregunta fresca acorde al contexto, nunca repitas el típico "te leo en comentarios".
    - 🎯 ETIQUETAS: OBLIGATORIO mencionar a @BinanceES al final del tweet.
    
    REGLAS:
    - Máximo 260 caracteres ESTRICTO (para que quepa en un Tweet).
    - Incluye al final: ${moneda} $BNB #{moneda}
    """
    
    return generar_texto_ia(prompt)

def obtener_fear_and_greed():
    """
    Obtiene el índice de Miedo y Codicia desde alternative.me
    """
    try:
        url = "https://api.alternative.me/fng/?limit=1"
        print(f"📡 Consultando Fear & Greed Index...")
        response = sesion_http.get(url, timeout=10)
        data = response.json()
        if data['data']:
            return data['data'][0]
    except Exception as e:
        print(f"⚠️ Error obteniendo F&G Index: {e}")
    return None

def generar_post_fng(datos_fng):
    valor = datos_fng['value']
    clasificacion = datos_fng['value_classification']
    
    prompt = f"""
    Actúa como un 'Top Creator' de Binance Square.
    DATOS: Índice de Miedo y Codicia (Fear & Greed): {valor}/100 ({clasificacion}).
    
    OBJETIVO: Post diario de sentimiento de mercado (Viral).
    
    ESTILO:
    - Emojis al inicio.
    - Párrafos cortos.
    - Tono: Experto pero cercano.
    
    INSTRUCCIONES ANTI-REPETICIÓN Y ENGAGEMENT:
    - 🔄 TÍTULO DINÁMICO: No uses siempre el mismo título. Inventa titulares variados basados en el sentimiento actual ({clasificacion}).
    - 📊 EL DATO: Menciona que estamos en {valor}/100 de forma natural en el texto.
    - 🧠 ANÁLISIS: Haz una interpretación psicológica de lo que esto significa para los inversores HOY. Varía el enfoque (ballenas, pánico retail, etc.).
    - 🎁 CTA PARA SEGUIDORES: Pide directamente un "Like" o un "Follow" para recibir esta actualización de mercado cada día.
    - 👇 CIERRE: Haz una pregunta distinta cada día. No repitas siempre "¿Compras o vendes?".
    
    REGLAS:
    - 🚫 Prohibido usar formato de listas (1. 2.).
    - Máximo 260 caracteres ESTRICTO (para que quepa en un Tweet).
    - OBLIGATORIO: Hashtags #Bitcoin #FearAndGreed
    """
    
    return generar_texto_ia(prompt)

def calcular_indicadores(symbol, period_rsi=14, period_ema=50, base_url="https://api.binance.com", headers=None):
    """
    Calcula el RSI (1h) y la EMA 50 para confirmar tendencia.
    """
    try:
        url = f"{base_url}/api/v3/klines"
        # Traemos 100 velas de 1h para calcular bien el promedio
        params = {'symbol': symbol, 'interval': '1h', 'limit': 100}
        response = sesion_http.get(url, params=params, timeout=10)
        data = response.json()
        
        if not data or len(data) < max(period_rsi, period_ema) + 1:
            return None, None, None

        closes = [float(x[4]) for x in data]
        
        # Cálculo manual de RSI
        gains = []
        losses = []
        
        for i in range(1, len(closes)):
            delta = closes[i] - closes[i-1]
            gains.append(max(delta, 0))
            losses.append(max(-delta, 0))
            
        # Promedio inicial
        avg_gain = sum(gains[:period_rsi]) / period_rsi
        avg_loss = sum(losses[:period_rsi]) / period_rsi
        
        # Suavizado (Wilder's Smoothing)
        for i in range(period_rsi, len(gains)):
            avg_gain = (avg_gain * (period_rsi - 1) + gains[i]) / period_rsi
            avg_loss = (avg_loss * (period_rsi - 1) + losses[i]) / period_rsi
            
        if avg_loss == 0:
            rsi = 100
        else:
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
            
        # Cálculo de la EMA 50
        sma = sum(closes[:period_ema]) / period_ema
        ema = sma
        multiplier = 2 / (period_ema + 1)
        for close in closes[period_ema:]:
            ema = (close - ema) * multiplier + ema

        return rsi, ema, closes[-1]
    except Exception as e:
        # print(f"⚠️ Debug RSI {symbol}: {e}") # Descomentar para depuración profunda
        return None, None, None

def generar_post_rsi(datos):
    moneda = datos['symbol']
    rsi = int(datos['rsi']) if datos['rsi'] else 50
    
    precio_float = float(datos['price'])
    if precio_float < 1:
        precio = f"{precio_float:.8f}".rstrip("0").rstrip(".")
    else:
        precio = f"{precio_float:.2f}"
    
    fomo = datos.get('fomo')
    contexto_fomo = ""
    if fomo:
        if fomo >= 75:
            contexto_fomo = f"\n    - DATO EXTRA: La comunidad tiene 🔥 ALTO FOMO ({fomo}% alcistas)."
        elif fomo <= 40:
            contexto_fomo = f"\n    - DATO EXTRA: Hay 😨 MUCHO MIEDO en la comunidad ({fomo}% alcistas)."
        else:
            contexto_fomo = f"\n    - DATO EXTRA: Sentimiento social ⚖️ neutro ({fomo}% alcistas)."

    ema50 = datos.get('ema50')
    if ema50:
        tendencia_ema = "Soportada sobre la EMA 50 (Fuerte)" if precio_float > ema50 else "Debajo de la EMA 50 (Riesgo de falsa subida)"
        contexto_fomo += f"\n    - EMA 50: {tendencia_ema}."
        
    btc_change = datos.get('btc_change', 0)
    if btc_change <= -2:
        contexto_fomo += f"\n    - ALERTA MACRO: Bitcoin está sangrando ({btc_change}%)."
    elif btc_change >= 2:
        contexto_fomo += f"\n    - ALERTA MACRO: Bitcoin está liderando el mercado ({btc_change}%)."

    if rsi <= 30:
        estado = "SOBREVENTA (Oversold)"
        objetivo = 'alerta de oportunidad ("Buy the Dip" / posible rebote inminente)'
        explicacion_rsi = f"el RSI de {rsi}/100 indica agotamiento de vendedores o zona de acumulación"
        hashtag = "#BuyTheDip"
    else:
        estado = "SOBRECOMPRA (Overbought)"
        objetivo = 'alerta de precaución (posible corrección o toma de ganancias inminente)'
        explicacion_rsi = f"el RSI de {rsi}/100 indica euforia en el mercado, posible techo local o agotamiento de compradores"
        hashtag = "#TakeProfit"

    prompt = f"""
    Actúa como un trader veterano de Binance Square.
    DATOS: {moneda} está en zona de {estado} en gráfico de 1h. Precio: {precio}. {contexto_fomo}
    
    OBJETIVO: Crear una {objetivo} que suene ÚNICA y humana.
    
    INSTRUCCIONES ANTI-REPETICIÓN Y ENGAGEMENT:
    - 🔄 Varía el gancho inicial (a veces usa 'Atención', otras veces una pregunta directa, otras una observación técnica).
    - 🧠 Explica que {explicacion_rsi} con diferentes palabras cada vez.
    - 🚫 NO uses frases hechas como "Históricamente, tocar estos niveles...". Sé creativo.
    - 🎁 CTA PODEROSO: Las alertas en tiempo real valen oro. Pide a la gente que te siga o deje su "Like" en agradecimiento por este dato anticipado.
    - 🚫 NUNCA repitas el mismo cierre. Inventa un llamado a la acción distinto.
    - 🚫 NO uses listas enumeradas. Escribe en párrafos cortos y fluidos.
    
    REGLAS:
    - Máximo 260 caracteres ESTRICTO (para que quepa en un Tweet).
    - OBLIGATORIO: Cashtags ${moneda} {hashtag} #{moneda}
    """
    
    return generar_texto_ia(prompt)

def buscar_anuncios_binance():
    """Busca nuevos Launchpools o listados en Binance."""
    print("🔍 Buscando nuevos anuncios de Launchpool/Listados en Binance...")
    try:
        url = "https://www.binance.com/bapi/composite/v1/public/cms/article/catalog/list/query?catalogId=54&pageNo=1&pageSize=3"
        resp = sesion_http.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if data.get('success') and data.get('data') and data['data'].get('articles'):
                return data['data']['articles'][0] # El más reciente
    except Exception as e:
        print(f"⚠️ Error buscando noticias: {e}")
    return None

def generar_post_telegram(datos_mercado):
    """Genera un análisis exclusivo y profundo para el canal VIP de Telegram."""
    moneda = datos_mercado['symbol']
    cambio = f"{float(datos_mercado['percent']):.2f}"
    rsi = datos_mercado.get('rsi', 50)
    precio_float = float(datos_mercado['lastPrice'])
    precio = f"{precio_float:.5f}".rstrip("0").rstrip(".") if precio_float < 1 else f"{precio_float:.2f}"
    
    estado_rsi = "Neutro"
    if rsi > 70: estado_rsi = "🔴 Sobrecompra (Posible retroceso)"
    elif rsi < 30: estado_rsi = "🟢 Sobreventa (Oportunidad de compra)"
    
    info_rsi = f"- RSI (1h): {rsi:.1f} {estado_rsi}" if rsi != 50 else ""
    tendencia = "Alcista 📈" if float(cambio) > 0 else "Bajista 📉"

    fomo = datos_mercado.get('fomo')
    texto_fomo = ""
    if fomo:
        if fomo >= 75:
            texto_fomo = f" | Sentimiento Social: 🔥 ALTO FOMO ({fomo}% alcistas)"
        elif fomo <= 40:
            texto_fomo = f" | Sentimiento Social: 😨 MIEDO EXTREMO ({fomo}% alcistas)"
        else:
            texto_fomo = f" | Sentimiento Social: ⚖️ Neutro ({fomo}% alcistas)"

    ema50 = datos_mercado.get('ema50')
    if ema50:
        tend_ema = "🟢 Arriba de EMA50" if precio_float > ema50 else "🔴 Debajo de EMA50"
        texto_fomo += f" | Tendencia Macro: {tend_ema}"

    btc_change = datos_mercado.get('btc_change', 0)
    if btc_change <= -2:
        texto_fomo += f"\n⚠️ ADVERTENCIA: Bitcoin está cayendo ({btc_change}%). Precaución general."
    elif btc_change >= 2:
        texto_fomo += f"\n🚀 CONTEXTO: Bitcoin subiendo con fuerza ({btc_change}%)."

    prompt = f"""
    Actúa como vIcmAr, administrando tu canal VIP de Telegram 'La Terminal'.
    
    DATOS DE MERCADO: {moneda} | Precio: {precio} USDT | Cambio 24h: {cambio}% (Tendencia {tendencia}) {info_rsi} {texto_fomo}
    
    OBJETIVO: Escribir un análisis EXCLUSIVO de mercado para los suscriptores de tu canal.
    Debes aportar más "alfa" (valor técnico, posibles proyecciones o sentimiento) que en un simple Tweet.
    
    REGLAS:
    - Tono: Cercano, de comunidad VIP, "Hacker/Trader".
    - Formato: Usa HTML básico (<b> para negritas, <i> para énfasis, <code> para métricas clave).
    - Longitud: 3-4 párrafos fluidos y fáciles de leer. NO hagas testamentos inmensos.
    - NO pongas enlaces ni menciones redes sociales.
    """
    return generar_texto_ia(prompt)

def generar_articulo_blog(datos):
    """
    Genera un artículo educativo y técnico extenso (>500 palabras)
    con estilo 'Diario de un Programador Cripto'.
    """
    symbol = datos.get('symbol')
    precio_float = float(datos.get('price', datos.get('lastPrice')))
    if precio_float < 0.0001:
        precio = f"{precio_float:.8f}".rstrip("0").rstrip(".")
    elif precio_float < 1:
        precio = f"{precio_float:.5f}".rstrip("0").rstrip(".")
    else:
        precio = f"{precio_float:.2f}"
    if not precio: precio = "0"
    rsi = datos.get('rsi', 'N/A')
    cambio = datos.get('percent', 'N/A')
    cambio_float = float(cambio) if cambio != 'N/A' else 0
    tendencia = "Bullish (Uptrend)" if cambio_float > 0 else "Bearish (Downtrend/Drop)"
    
    fomo = datos.get('fomo')
    texto_fomo = ""
    if fomo:
        texto_fomo = f" Community Sentiment: {fomo}% Bullish (FOMO Indicator)."
    
    enfoques_blog = [
        "Start by discussing the broader macroeconomic sentiment or general crypto market volatility, then drill down into this specific coin.",
        "Begin with a reflection on trading psychology or technical analysis principles, connecting it to the current RSI and price action.",
        "Dive straight into the fundamentals, news, use cases, or technology behind this specific coin, then support your thesis with the technical data provided.",
        "Use an 'early warning' tone, discussing why these specific price levels and RSI could be pivotal for the upcoming weeks."
    ]
    enfoque = random.choice(enfoques_blog)

    prompt = f"""
    Act as vIcmAr, a passionate crypto programmer and market analyst from Argentina.
    
    TASK: Write a technical and educational blog article for Publish0x.
    TOPIC: Deep technical analysis of {symbol}.
    DATA: Price: {precio} USDT. RSI: {rsi}. 24h Change: {cambio}% ({tendencia}).{texto_fomo}
    
    LANGUAGE: ENGLISH. The entire content MUST be in English.
    
    WRITING STYLE (IMPORTANT):
    - Tone: Human, insightful, and professional but approachable. Use first person.
    - 🚫 AVOID REPETITION: DO NOT always introduce yourself. DO NOT use clichés like "From my terminal in Argentina..." or "In the ever-evolving world of crypto". Jump straight into delivering value.
    - FOCUS FOR THIS POST: {enfoque}
    - Explain concepts: If you mention RSI or momentum, briefly explain what it implies for {symbol} right now.
    - FORMAT: Use simple HTML compatible with Telegram: <b> for bold/titles, <i> for emphasis, and <code> for terminal variables. DO NOT USE MARKDOWN (** or __).
    - Use emojis to make the text visually engaging.
    
    STRUCTURE (HTML):
    1. FIRST LINE: Only the raw Main Title (Catchy, NO HTML tags on the first line).
    2. The rest of the article must be fluid paragraphs. Use creative <b>Subtitles</b> when transitioning topics, but DO NOT use the same generic subheadings every time. Make it read like a real human analyst's article.
    6. TAGS: At the very end, generate a list of 5 recommended tags (e.g., #Bitcoin #Trading #AI #RSI #{symbol}).
    
    Length: Minimum 400 words.
    """
    
    return generar_texto_ia(prompt)

def generar_articulo_bitget(referido):
    """Genera un artículo promocional diario de Bitget Wallet con enfoques aleatorios."""
    enfoques = [
        "Céntrate en la nueva Tarjeta Cripto (Bitget Card) y cómo facilita gastar saldo Web3 en compras diarias físicas o virtuales.",
        "Escribe sobre la seguridad, custodia descentralizada y las ventajas de usar Bitget Wallet frente a exchanges centralizados.",
        "Habla sobre la caza de Airdrops, los beneficios del token BWB y cómo la app ayuda a descubrir nuevas gemas en DeFi.",
        "Haz un tutorial conceptual sobre cómo dar los primeros pasos en DeFi de forma fácil usando Bitget Wallet."
    ]
    enfoque = random.choice(enfoques)
    
    prompt = f"""
    Actúa como vIcmAr, un educador apasionado por DeFi y Web3.
    
    TAREA: Escribir un post de blog natural y atractivo para promocionar 'Bitget Wallet' y su tarjeta cripto.
    ENFOQUE DE HOY: {enfoque}
    
    IDIOMA: Español.
    
    REGLAS ESTRICTAS:
    - Tono: Educativo, humano y entusiasta. NO suenes como un anuncio de teletienda ni hagas spam barato. Aporta valor real.
    - Enlace: OBLIGATORIO integrar el referido usando formato HTML: <a href="{referido}">Únete a Bitget aquí</a>. NUNCA pongas la URL en texto plano.
    - Llamada a la acción: Al final del artículo, antes de las etiquetas, añade un párrafo invitando a tu canal de Telegram con este enlace: <a href="{LINK_TELEGRAM}">Únete a mi canal VIP de Telegram aquí</a>.
    - Formato HTML: Usa <b> para subtítulos, <i> para énfasis y <a> para el enlace. Párrafos fluidos. NO uses listas 1. 2. 3.
    - Estructura: 
      1. PRIMERA LÍNEA: Solo el título principal atractivo (SIN etiquetas HTML).
      2. El resto del post.
      3. Al final, añade 5 etiquetas (ej: #BitgetWallet #Web3 #CryptoCard).
    - Extensión mínima: 350 palabras.
    """
    return generar_texto_ia(prompt)

def generar_imagen_ia(symbol, prompt_context="crypto trading chart futuristic style"):
    """Genera una imagen IA on-the-fly usando Pollinations.ai con sistema de reintentos."""
    full_prompt = f"{symbol} coin logo, {prompt_context}, 3d render, 8k resolution, neon lighting"
    encoded_prompt = urllib.parse.quote(full_prompt)
    
    for intento in range(3):
        try:
            initial_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=1024&nologo=true&seed={int(time.time())}"
            if intento == 0:
                print(f"🎨 Generando imagen IA para {symbol}...")
            else:
                print(f"🔄 Reintento {intento + 1}/3 para generar imagen IA...")
                
            response = sesion_http.get(initial_url, allow_redirects=True, timeout=60)
            
            if response.status_code == 200:
                final_url = response.url
                print(f"🖼️ URL final de la imagen obtenida: {final_url}")
                return final_url
            else:
                print(f"⚠️ Error {response.status_code} al resolver la URL de la imagen (Pollinations).")
                time.sleep(3) # Espera 3 segundos antes del próximo reintento
        except requests.exceptions.Timeout:
            print("⚠️ Timeout: La generación de la imagen tardó demasiado.")
            time.sleep(3)
        except Exception as e:
            print(f"⚠️ Error generando imagen IA: {e}")
            time.sleep(3)
            
    print("❌ Fallaron todos los intentos. Se omitirá la imagen IA.")
    return None

def obtener_imagen_binance(symbol):
    """Obtiene logo de Binance, GitHub o genera uno con IA."""
    try:
        # 1. Intentar API interna de Binance
        url = "https://www.binance.com/bapi/asset/v2/public/asset-service/product/get-product-by-symbol"
        params = {"symbol": symbol} # Ej: BTCUSDT
        resp = sesion_http.get(url, params=params, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            product_data = data.get("data")
            if product_data and isinstance(product_data, dict):
                return product_data.get("logoUrl")
    except Exception as e:
        print(f"⚠️ Warning buscando logo Binance: {e}")
    
    # 2. Fallback: Iconos genéricos de GitHub (Verificamos existencia)
    base = symbol.replace("USDT", "").lower()
    github_url = f"https://raw.githubusercontent.com/spothq/cryptocurrency-icons/master/128/color/{base}.png"
    try:
        check = sesion_http.head(github_url, timeout=3)
        if check.status_code == 200:
            return github_url
    except: pass

    # 3. Último recurso: Generar imagen con IA sobre el tema
    img_url = generar_imagen_ia(symbol.replace("USDT", ""), "bullish trend rising chart glowing")
    if img_url:
        return img_url
        
    # 4. Fallback estático en caso de que la IA falle por completo
    print("💡 Usando imagen genérica de respaldo para el reporte...")
    imagenes_respaldo = [
        "https://images.unsplash.com/photo-1621416894569-0f39ed31d247?q=80&w=1024&auto=format&fit=crop", # Crypto abstracta
        "https://images.unsplash.com/photo-1605792657660-596af9009e82?q=80&w=1024&auto=format&fit=crop", # Smartphone y finanzas
        "https://images.unsplash.com/photo-1642104704074-907c0698cbd9?q=80&w=1024&auto=format&fit=crop"  # Billetera digital / Bitcoin
    ]
    return random.choice(imagenes_respaldo)

if __name__ == "__main__":
    print("🤖 Iniciando Bot vIcmAr...")
    print(f"⚙️ Versión 2.1 - Modelo: {GROQ_MODEL_NAME} | Modo: {TIPO_BOT}")
    
    if TIPO_BOT == "FNG":
        # --- MODO FEAR & GREED ---
        datos = obtener_fear_and_greed()
        if datos:
            print(f"🌡️ Índice obtenido: {datos['value']} ({datos['value_classification']})")
            post = generar_post_fng(datos)
            if post:
                publicar_en_square(post)
                # Nota: No guardamos historial para F&G porque es un post diario único.
    
    elif TIPO_BOT == "BITGET":
        # --- MODO PROMOCIÓN BITGET WALLET ---
        print("🚀 Iniciando modo Promoción Bitget Wallet...")
        articulo = generar_articulo_bitget(REFERIDO_BITGET)
        
        if articulo:
            articulo = articulo.strip()
            lineas = articulo.split('\n')
            titulo = lineas[0].replace('#', '').strip()
            contenido = "\n".join(lineas[1:]).strip()
            
            hashtags = re.findall(r'#\w+', contenido)
            hashtags_unicos = list(dict.fromkeys(hashtags))
            texto_limpio = re.sub(r'#\w+', '', contenido).strip()
            tags_str = " ".join(hashtags_unicos)
            
            # Generamos una imagen IA relacionada con pagos cripto y Web3
            img_url = generar_imagen_ia("Bitget Wallet", "futuristic digital wallet floating credit card cyberpunk neon web3 payment")
            
            # Imagen de respaldo estática en caso de que la IA (Pollinations) falle definitivamente
            if not img_url:
                print("💡 Usando imagen promocional estática de respaldo...")
                imagenes_respaldo = [
                    "https://images.unsplash.com/photo-1621416894569-0f39ed31d247?q=80&w=1024&auto=format&fit=crop", # Crypto abstracta
                    "https://images.unsplash.com/photo-1621504450181-5d356f61d307?q=80&w=1024&auto=format&fit=crop", # Neón tecnológico
                    "https://images.unsplash.com/photo-1605792657660-596af9009e82?q=80&w=1024&auto=format&fit=crop", # Smartphone y finanzas
                    "https://images.unsplash.com/photo-1642104704074-907c0698cbd9?q=80&w=1024&auto=format&fit=crop"  # Billetera digital / Bitcoin
                ]
                img_url = random.choice(imagenes_respaldo)

            print("📝 Publicando promoción de Bitget en Blogger...")
            
            # Fallback de seguridad: Si la IA desobedeció y dejó la URL en texto plano, la convertimos a enlace HTML forzosamente
            texto_blogger = texto_limpio
            if f'href="{REFERIDO_BITGET}"' not in texto_blogger and f"href='{REFERIDO_BITGET}'" not in texto_blogger:
                texto_blogger = texto_blogger.replace(REFERIDO_BITGET, f'<a href="{REFERIDO_BITGET}">Haz clic aquí para unirte a Bitget</a>')
                
            publicar_en_blogger(titulo, texto_blogger, hashtags_unicos, img_url)
            
            print("📝 Publicando promoción de Bitget en Facebook...")
            texto_fb = re.sub(r'<[^>]+>', '', texto_limpio)
            # Añadimos el link explícito en Facebook y el CTA de Telegram
            publicar_en_facebook(f"📌 {titulo}\n\n{texto_fb}\n\n🔗 Únete a Bitget aquí: {REFERIDO_BITGET}\n\n💬 Únete a mi canal VIP de Telegram gratis: {LINK_TELEGRAM}\n\n{tags_str}", img_url)
            
            print("📝 Enviando promoción a Telegram...")
            mensaje_tg = f"📌 <b>{titulo}</b>\n\n{texto_limpio}\n\n🔗 <a href='{REFERIDO_BITGET}'>Solicita tu Bitget Card Aquí</a>\n\n <a href='{LINK_TELEGRAM}'>Únete al canal VIP para más análisis</a>\n\n{tags_str}"
            enviar_telegram(mensaje_tg)
            
        # IMPORTANTE: NO PUBLICAMOS EN BINANCE SQUARE para evitar baneos.

    elif TIPO_BOT == "LAUNCHPOOL":
        # --- MODO CAZADOR DE NOTICIAS ---
        print("🚀 Iniciando modo Cazador de Launchpools...")
        noticia = buscar_anuncios_binance()
        
        if noticia:
            codigo = noticia['code']
            titulo = noticia['title']
            historial = cargar_historial()
            
            # Verificamos si ya publicamos sobre este anuncio usando su código único
            if codigo in historial:
                print("😴 No hay anuncios nuevos en Binance Launchpool/Listing.")
            else:
                print(f"🚨 ¡NUEVO ANUNCIO DETECTADO!: {titulo}")
                link_noticia = f"https://www.binance.com/en/support/announcement/{codigo}"
                
                msg_tg = f"🚨 <b>¡ALERTA DE BINANCE!</b> 🚨\n\n{titulo}\n\n🔗 <a href='{link_noticia}'>Leer Anuncio Oficial</a>\n\n💬 <a href='{LINK_TELEGRAM}'>Únete al VIP aquí</a>"
                enviar_telegram(msg_tg)
                
                guardar_historial(codigo)

    else:
        # --- MODO REPORTE DIARIO (Matutino/Vespertino) ---
        
        # 1. Determinar Saludo según Horario UTC
        hora_actual = datetime.now(timezone.utc).hour
        saludo_telegram = "🤖 Reporte vIcmAr"
        
        # 09:30 UTC es mañana AR / 22:00 UTC es noche AR
        if 8 <= hora_actual <= 11:
            saludo_telegram = "🌅 Reporte Matutino vIcmAr"
        elif 20 <= hora_actual <= 23:
            saludo_telegram = "🌆 Reporte Vespertino vIcmAr"
            
        # 2. Obtener la Mejor Oportunidad de la Sesión
        oportunidad = analizar_oportunidades()
        
        if oportunidad:
            # Adaptamos datos para consistencia (lastPrice -> price en funciones viejas)
            oportunidad['price'] = oportunidad['lastPrice'] 
            
            # NUEVO: Obtener FOMO de la comunidad para la moneda ganadora
            print(f"👥 Obteniendo sentimiento social (FOMO) para {oportunidad['symbol']}...")
            oportunidad['fomo'] = obtener_fomo_coingecko(oportunidad['symbol'] + "USDT")
            
            # Generamos Post Corto para Square (usamos la lógica inteligente general o RSI si es extremo)
            if oportunidad['rsi'] <= 30 or oportunidad['rsi'] >= 70:
                post_square = generar_post_rsi(oportunidad)
            else:
                post_square = generar_post_inteligente(oportunidad)
            
            # Publicar en Square
            if post_square and publicar_en_square(post_square):
                print(f"✅ Publicado en Square. Procediendo a Blog/Telegram...")
                # Obtenemos la imagen antes de X para poder adjuntarla
                img_url = obtener_imagen_binance(oportunidad['symbol'])

                guardar_historial(oportunidad['symbol']) # Opcional: Para evitar repetir si fallara algo externo
                
                # --- POST EXCLUSIVO CANAL VIP TELEGRAM ---
                print("📝 Generando post exclusivo para el canal VIP de Telegram...")
                post_telegram = generar_post_telegram(oportunidad)
                if post_telegram:
                    enlace_trade = f"https://www.binance.com/es/trade/{oportunidad['symbol']}_USDT"
                    mensaje_tg = f"💎 <b>¡REPORTE VIP DE LA TERMINAL!</b> 💎\n\n{post_telegram}\n\n👉 <a href='{enlace_trade}'>Operar {oportunidad['symbol']} en Binance</a>\n\n💬 <a href='{LINK_TELEGRAM}'>Únete aquí para más reportes VIP</a>"
                    enviar_telegram_multimedia(mensaje_tg, img_url)
                
                # Generar Artículo Blog Extenso
                articulo_blog = generar_articulo_blog(oportunidad)
                
                if articulo_blog:
                    articulo_blog = articulo_blog.strip()
                    lineas = articulo_blog.split('\n')
                    titulo_blog = lineas[0].replace('#', '').strip()
                    contenido_blog = "\n".join(lineas[1:]).strip()
                    
                    # Extraer hashtags usando expresiones regulares
                    hashtags = re.findall(r'#\w+', contenido_blog)
                    hashtags_unicos = list(dict.fromkeys(hashtags)) # Eliminar duplicados
                    
                    # Limpiar el cuerpo del texto para que no tenga los hashtags al final
                    texto_limpio = re.sub(r'#\w+', '', contenido_blog).strip()
                    texto_limpio = re.sub(r'(?i)\bTAGS:\s*', '', texto_limpio).strip()

                    # Preparamos los hashtags en texto plano para usarlos en Telegram y Facebook
                    tags_str = " ".join(hashtags_unicos)

                    # 5. Publicar en Blogger
                    publicar_en_blogger(titulo_blog, texto_limpio, hashtags_unicos, img_url)
                    
                    # 6. Publicar en Facebook (Sin etiquetas HTML + Imagen)
                    # Facebook no soporta HTML, así que borramos las etiquetas (<b>, <i>, <code>)
                    texto_fb = re.sub(r'<[^>]+>', '', texto_limpio)
                    publicar_en_facebook(f"📌 {titulo_blog}\n\n{texto_fb}\n\n💬 Únete a mi canal VIP de Telegram para más alertas: {LINK_TELEGRAM}\n\n{tags_str}", img_url)
                else:
                    print("⚠️ No se pudo generar el artículo de blog, pero Telegram y Square están activos.")