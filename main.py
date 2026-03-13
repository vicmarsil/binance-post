import os
from dotenv import load_dotenv

# Cargar variables de entorno ANTES de intentar leerlas
load_dotenv()

import requests
from groq import Groq
import json
import time
import random
from datetime import datetime, timedelta, timezone
import urllib.parse

# --- CONFIGURACIÓN Y VARIABLES DE ENTORNO ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
SQUARE_API_KEY = os.getenv("SQUARE_API_KEY")
if SQUARE_API_KEY:
    SQUARE_API_KEY = SQUARE_API_KEY.strip() # Limpieza de seguridad: elimina espacios al inicio/final
MODO_PRUEBA = os.getenv("MODO_PRUEBA", "False").lower() == "true" # 🟢 Configurable. Por defecto False (Producción).
GROQ_MODEL_NAME = os.getenv("GROQ_MODEL_NAME", "llama-3.3-70b-versatile").strip() # .strip() elimina espacios fantasma
TIPO_BOT = os.getenv("TIPO_BOT", "TENDENCIA") # 🟢 Nuevo: Selecciona el modo de operación

# Credenciales para Telegram
TOKEN_TELEGRAM = os.getenv("TOKEN_TELEGRAM")
ID_TELEGRAM = os.getenv("ID_TELEGRAM")

# Validación rápida de configuración de Telegram
if ID_TELEGRAM and not ID_TELEGRAM.lstrip('-').isdigit():
    print(f"⚠️ ALERTA CONFIG: Tu ID_TELEGRAM ('{ID_TELEGRAM}') parece incorrecto. Debe ser NUMÉRICO (sin letras ni @).")
    print("   👉 Usa @userinfobot en Telegram para obtener tu número real.")

# 🛡️ Parche de seguridad: Si el entorno (.env local) tiene el modelo viejo, forzamos el nuevo.
# Usamos 'in' para detectar variantes con espacios o comillas
if "llama3-8b-8192" in GROQ_MODEL_NAME:
    print("⚠️ Configuración detectada con modelo deprecado. Actualizando automáticamente a llama-3.3-70b-versatile.")
    GROQ_MODEL_NAME = "llama-3.3-70b-versatile"

ARCHIVO_HISTORIAL = "historial.json"

# --- LISTA DE MONEDAS A ANALIZAR (MAJORS & ALTA LIQUIDEZ) ---
MONEDAS_ANALISIS = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT', 
                    'ADAUSDT', 'AVAXUSDT', 'TRXUSDT', 'LINKUSDT', 'DOTUSDT', 'MATICUSDT']

# Mapeo para CoinGecko (Backup si Binance falla)
COINGECKO_IDS = {
    'BTCUSDT': 'bitcoin',
    'ETHUSDT': 'ethereum',
    'BNBUSDT': 'binancecoin',
    'SOLUSDT': 'solana',
    'XRPUSDT': 'ripple',
    'ADAUSDT': 'cardano',
    'AVAXUSDT': 'avalanche-2',
    'TRXUSDT': 'tron',
    'LINKUSDT': 'chainlink',
    'DOTUSDT': 'polkadot',
    'MATICUSDT': 'matic-network'
}

# Validación básica de seguridad
if not GROQ_API_KEY:
    raise ValueError("❌ Error: La variable GROQ_API_KEY no está configurada.")
if not MODO_PRUEBA and not SQUARE_API_KEY:
    raise ValueError("❌ Error: SQUARE_API_KEY es necesaria para publicar (MODO_PRUEBA=False). Revisa tus Secretos en GitHub.")
if not MODO_PRUEBA:
    print(f"🔑 SQUARE_API_KEY cargada correctamente (Longitud: {len(SQUARE_API_KEY)})")

client = Groq(api_key=GROQ_API_KEY)

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
        headers = {"User-Agent": "Mozilla/5.0"} # CoinGecko requiere User-Agent
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        
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
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    for symbol in monedas_filtradas:
        ticker = None
        base_url = "https://api.binance.com"

        for url_ticker in endpoints:
            try:
                # 1. Obtener Datos de Precio 24h con rotación
                resp = requests.get(url_ticker, params={'symbol': symbol}, headers=headers, timeout=15)
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
                rsi, _ = calcular_rsi(symbol, base_url=base_url, headers=headers)
            else:
                rsi = 50 # RSI Neutro si usamos CoinGecko (solo estrategia de volatilidad)
            
            # Si falla el RSI (None) pero tenemos precio, usamos 50 para no descartar la moneda
            if rsi is None: rsi = 50

            candidatos.append({
                "symbol": symbol.replace("USDT", ""),
                "lastPrice": float(ticker['lastPrice']),
                "percent": float(ticker['priceChangePercent']),
                "rsi": rsi
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
    cambio = datos_mercado['percent']
    rsi = datos_mercado.get('rsi', 50)
    
    # Formateo visual "Limpieza Pro": Quita ceros extra (Ej: 0.5000 -> 0.5 | 0.00976000 -> 0.00976)
    precio = "{:.8f}".format(float(datos_mercado['lastPrice'])).rstrip("0").rstrip(".")

    # Contexto dinámico para que la IA tenga variedad en su análisis
    contexto_tecnico = "Tendencia normal de mercado."
    if float(cambio) > 20:
        contexto_tecnico = "Subida explosiva (posible FOMO). Menciona cautela por volatilidad."
    elif float(cambio) > 5:
        contexto_tecnico = "Tendencia alcista sólida. Menciona ruptura de niveles."
    
    estado_rsi = "Neutro"
    if rsi > 70: estado_rsi = "Sobrecompra (Riesgo de corrección)"
    elif rsi < 30: estado_rsi = "Sobreventa (Oportunidad de rebote)"

    # --- VARIACIÓN ALEATORIA DE ESTILO ---
    estilos = [
        "Enfócate en la psicología de masa (Miedo vs Codicia).",
        "Analiza niveles técnicos clave (Soportes y Resistencias).",
        "Sé extremadamente breve, directo y con sentido de urgencia.",
        "Usa un tono institucional, serio y analítico.",
        "Plantea un escenario de riesgo vs recompensa."
    ]
    estilo_seleccionado = random.choice(estilos)

    prompt = f"""
    Actúa como un trader experto y carismático en Binance Square.
    Tu objetivo es escribir un post que parezca 100% humano, natural y fluido.
    
    DATOS DEL MERCADO:
    - Activo: {moneda}
    - Precio: {precio} USDT (+{cambio}%)
    - RSI (1h): {rsi:.1f} ({estado_rsi})
    - Contexto: {contexto_tecnico}
    - ENFOQUE DE REDACCIÓN OBLIGATORIO: {estilo_seleccionado}
    
    INSTRUCCIONES PARA EVITAR SONAR COMO UN ROBOT:
    1. 🚫 PROHIBIDO USAR LISTAS (No uses formato "1. Gancho 2. Dato..."). Escribe párrafos conversacionales.
    2. 🚫 EVITA FRASES CLICHÉ: No digas simplemente "Sube por hype". Usa variaciones como "fuerte presión de compra", "despertar técnico", "rompiendo resistencias" o "volumen institucional".
    3. Integra los datos ({precio}, RSI) dentro de las oraciones de forma narrativa.
    4. Tono: Entusiasta pero analítico. Habla como si le contaras una novedad a un amigo trader.
    5. Cierra con una pregunta abierta para generar comentarios.
    
    REGLAS:
    - Máximo 450 caracteres.
    - Incluye al final: ${moneda} $BNB #{moneda}
    """

    try:
        print(f"🤖 Intentando conectar con Groq usando modelo: '{GROQ_MODEL_NAME}'")
        chat_completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            # Usamos la variable saneada
            model=GROQ_MODEL_NAME,
            temperature=0.7
        )
        return chat_completion.choices[0].message.content
    except Exception as e:
        print(f"⚠️ Error generando texto con Groq: {e}")
        return None

def obtener_fear_and_greed():
    """
    Obtiene el índice de Miedo y Codicia desde alternative.me
    """
    try:
        url = "https://api.alternative.me/fng/?limit=1"
        print(f"📡 Consultando Fear & Greed Index...")
        response = requests.get(url, timeout=10)
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
    
    ESTRUCTURA:
    1. 🌡️ TÍTULO: "SENTIMIENTO CRYPTO: {clasificacion}" (Elige emoji: 🥶 Miedo / 🤑 Codicia).
    2. 📊 EL DATO: Estamos en {valor}/100.
    3. 🧠 ANÁLISIS: Breve interpretación psicológica del mercado hoy.
    4. 👇 CIERRE: "¿Compras o vendes en este nivel? Te leo 👇 #Bitcoin #FearAndGreed"
    
    REGLAS:
    - Máximo 500 caracteres.
    """
    
    try:
        print(f"🤖 Generando análisis de sentimiento con modelo: '{GROQ_MODEL_NAME}'")
        chat_completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=GROQ_MODEL_NAME,
            temperature=0.7
        )
        return chat_completion.choices[0].message.content
    except Exception as e:
        print(f"⚠️ Error generando texto F&G con Groq: {e}")
        return None

def calcular_rsi(symbol, period=14, base_url="https://api.binance.com", headers=None):
    """
    Calcula el RSI (1h) para detectar sobreventa.
    """
    try:
        url = f"{base_url}/api/v3/klines"
        # Traemos 100 velas de 1h para calcular bien el promedio
        params = {'symbol': symbol, 'interval': '1h', 'limit': 100}
        response = requests.get(url, params=params, headers=headers, timeout=10)
        data = response.json()
        
        if not data or len(data) < period + 1:
            return None, None

        closes = [float(x[4]) for x in data]
        
        # Cálculo manual de RSI
        gains = []
        losses = []
        
        for i in range(1, len(closes)):
            delta = closes[i] - closes[i-1]
            gains.append(max(delta, 0))
            losses.append(max(-delta, 0))
            
        # Promedio inicial
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period
        
        # Suavizado (Wilder's Smoothing)
        for i in range(period, len(gains)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period
            
        if avg_loss == 0:
            rsi = 100
        else:
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
            
        return rsi, closes[-1]
    except Exception as e:
        # print(f"⚠️ Debug RSI {symbol}: {e}") # Descomentar para depuración profunda
        return None, None

def generar_post_rsi(datos):
    moneda = datos['symbol']
    rsi = int(datos['rsi']) if datos['rsi'] else 50
    precio = "{:.2f}".format(datos['price'])
    
    prompt = f"""
    Actúa como un trader veterano de Binance Square.
    DATOS: {moneda} está en zona de SOBREVENTA (RSI: {rsi}) en gráfico de 1h. Precio: {precio}.
    
    OBJETIVO: Alerta de "Buy the Dip" (Oportunidad de rebote).
    
    ESTRUCTURA:
    1. 🔔 TÍTULO: "¡ATENCIÓN {moneda} EN ZONA DE COMPRA!" o "💎 Oportunidad en {moneda}".
    2. 📉 EL DATO: RSI en {rsi}/100 (Extrema sobreventa).
    3. 🧠 ANÁLISIS: "Históricamente, tocar estos niveles suele anticipar un rebote técnico a corto plazo."
    4. 🎯 CONCLUSIÓN: Zona clave para vigilar o acumular.
    5. 👇 CIERRE: "Dale Like ❤️ si crees que rebota aquí 📈".
    
    REGLAS:
    - Máximo 500 caracteres.
    - OBLIGATORIO: Cashtags ${moneda} #BuyTheDip #{moneda}
    """
    # Reutilizamos la lógica de conexión a Groq copiando el bloque try/except simple
    try:
        print(f"🤖 Generando alerta RSI con modelo: '{GROQ_MODEL_NAME}'")
        chat_completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=GROQ_MODEL_NAME,
            temperature=0.7
        )
        return chat_completion.choices[0].message.content
    except Exception as e:
        print(f"⚠️ Error generando texto RSI: {e}")
        return None

def generar_articulo_blog(datos):
    """
    Genera un artículo educativo y técnico extenso (>500 palabras)
    con estilo 'Diario de un Programador Cripto'.
    """
    symbol = datos.get('symbol')
    precio = datos.get('price', datos.get('lastPrice'))
    rsi = datos.get('rsi', 'N/A')
    cambio = datos.get('percent', 'N/A')
    
    prompt = f"""
    Actúa como vIcmAr, un bot de trading programado en Python que opera desde servidores en la nube pero con "alma argentina".
    
    TAREA: Escribir un artículo de blog técnico y educativo en Markdown para Publish0x.
    TEMA: Análisis técnico profundo de {symbol}.
    DATOS: Precio: {precio} USDT. RSI: {rsi}. Cambio 24h: {cambio}%.
    
    IDIOMA: INGLÉS (ENGLISH). TODO el contenido debe estar en inglés.
    
    ESTILO DE REDACCIÓN (IMPORTANTE):
    - Tono: "Diario de un Programador". Usa primera persona.
    - Frases OBLIGATORIAS (En Inglés): "From my terminal in Argentina...", "Analyzing my script logs...", "The algorithm detected...".
    - Enfoque: Técnico pero explicativo. Enseña qué es el RSI o el volumen mientras analizas.
    - NO uses frases genéricas de IA como "In today's digital world". Sé crudo, directo y 'geek'.
    - FORMATO: Usa HTML simple compatible con Telegram. Usa <b> para negritas/títulos y <i> para énfasis. NO USES MARKDOWN (** o __).
    
    ESTRUCTURA (HTML):
    1. <b>Título Principal</b> (Llamativo y técnico)
    2. **INTRODUCCIÓN**: El primer párrafo debe presentar brevemente el proyecto de automatización vIcmAr.
    3. <b>📟 Console Discovery</b> (Contexto)
    4. <b>⚙️ Data Analysis</b> (Desglose de precio y RSI)
    5. <b>🔮 Code Projection</b> (Conclusión)
    6. **TAGS**: Al final, genera una lista de 5 tags recomendados (ej: #Bitcoin #Trading #AI #RSI #{symbol}).
    
    Longitud: Mínimo 500 palabras.
    """
    
    try:
        print(f"✍️ Redactando artículo de blog para {symbol}...")
        chat_completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=GROQ_MODEL_NAME,
            temperature=0.7
        )
        return chat_completion.choices[0].message.content
    except Exception as e:
        print(f"⚠️ Error generando artículo blog: {e}")
        return None

def publicar_en_square(contenido):
    """
    3. Publicación Automática:
    Envía el contenido a Binance Square (Solo texto para asegurar entrega).
    """
    if MODO_PRUEBA:
        print(f"\n🧪 [MODO PRUEBA] Simulación de envío a Binance Square:")
        print(f"--------------------------------------------------")
        print(f"Texto:\n{contenido}")
        print(f"--------------------------------------------------")
        return True

    # Endpoint oficial para AI Skills / Short Posts
    url = "https://www.binance.com/bapi/composite/v1/public/pgc/openApi/content/add"
    
    headers = {
        "X-Square-OpenAPI-Key": SQUARE_API_KEY,
        "Content-Type": "application/json",
        "clienttype": "binanceSkill" # Este campo es vital para que Binance sepa que es un Skill
    }

    # Intentamos primero solo con texto para asegurar que la cuenta está activa
    # Binance a veces rechaza URLs de imágenes externas por seguridad
    payload = {
        "bodyTextOnly": contenido 
    }
    
    print(f"📡 Enviando post (solo texto) a Binance Square...")
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        resultado = response.json()
        
        # El código "000000" es el éxito real en Binance
        if resultado.get("code") == "000000":
            # Intentamos obtener el ID de forma segura
            post_id = resultado.get('data', {}).get('id', 'Desconocido')
            print(f"🚀 PUBLICADO! ID del Post: {post_id}")
            return True
        else:
            print(f"❌ Binance rechazó el post: {resultado.get('message')} (Código: {resultado.get('code')})")
            return False

    except Exception as e:
        print(f"⚠️ Error técnico: {e}")
        return False

def generar_imagen_ia(symbol, prompt_context="crypto trading chart futuristic style"):
    """Genera una imagen IA on-the-fly usando Pollinations.ai (Gratis) si no hay logo."""
    try:
        # Prompt descriptivo para la IA
        full_prompt = f"{symbol} coin logo, {prompt_context}, 3d render, 8k resolution, neon lighting"
        encoded_prompt = urllib.parse.quote(full_prompt)
        
        # Generamos URL (Pollinations no requiere API Key)
        url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=1024&nologo=true&seed={int(time.time())}"
        print(f"🎨 Generando imagen IA para {symbol}...")
        return url
    except Exception as e:
        print(f"⚠️ Error generando imagen IA: {e}")
        return None

def obtener_imagen_binance(symbol):
    """Obtiene logo de Binance, GitHub o genera uno con IA."""
    try:
        # 1. Intentar API interna de Binance
        url = "https://www.binance.com/bapi/asset/v2/public/asset-service/product/get-product-by-symbol"
        params = {"symbol": symbol} # Ej: BTCUSDT
        resp = requests.get(url, params=params, timeout=5)
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
        check = requests.head(github_url, timeout=3)
        if check.status_code == 200:
            return github_url
    except: pass

    # 3. Último recurso: Generar imagen con IA sobre el tema
    return generar_imagen_ia(symbol.replace("USDT", ""), "bullish trend rising chart glowing")

def enviar_telegram_multimedia(mensaje, imagen_url):
    """Envía imagen + texto. Si cabe en caption usa un solo mensaje, si no, envía por separado."""
    url_photo = f"https://api.telegram.org/bot{TOKEN_TELEGRAM}/sendPhoto"
    
    # 1. Intentar Caption (Límite 1024 chars para captions en Telegram)
    if len(mensaje) < 1000:
        payload = {"chat_id": ID_TELEGRAM, "photo": imagen_url, "caption": mensaje, "parse_mode": "HTML"}
        try:
            r = requests.post(url_photo, json=payload, timeout=10)
            if r.status_code == 200: return
        except: pass
    
    # 2. Si falla o es largo: Foto sola + Texto separado
    try:
        requests.post(url_photo, json={"chat_id": ID_TELEGRAM, "photo": imagen_url}, timeout=10)
    except: pass
    enviar_telegram(mensaje)

def enviar_telegram(mensaje):
    """
    Envía el mensaje formateado a Telegram. Divide mensajes largos si es necesario.
    """
    # --- FILTRO HORARIO DESACTIVADO PARA ESTA ESTRATEGIA ---
    # Al usar cronjobs específicos (09:30 y 22:00 UTC), controlamos la hora desde GitHub.
    # El código de silencio anterior podría bloquear el reporte de las 06:30 AM exactas.
    pass
    # ------------------------------------------------

    if not TOKEN_TELEGRAM or not ID_TELEGRAM:
        print("⚠️ Telegram: Credenciales no configuradas. Se omite el envío.")
        return

    url = f"https://api.telegram.org/bot{TOKEN_TELEGRAM}/sendMessage"
    
    # Telegram limita a 4096 caracteres.
    # Fragmentación inteligente: 2000 chars y corte por saltos de línea para proteger el Markdown.
    max_length = 2000
    mensajes_split = []
    
    temp_msg = mensaje
    while len(temp_msg) > 0:
        if len(temp_msg) <= max_length:
            mensajes_split.append(temp_msg)
            break
        
        # Cortar en el último salto de línea (o espacio) dentro del límite para no romper etiquetas ** o __
        corte = temp_msg.rfind('\n', 0, max_length)
        if corte == -1: corte = temp_msg.rfind(' ', 0, max_length)
        if corte == -1: corte = max_length

        mensajes_split.append(temp_msg[:corte])
        temp_msg = temp_msg[corte:].lstrip() # Avanzamos y limpiamos espacios al inicio del siguiente bloque

    for i, msg_chunk in enumerate(mensajes_split):
        payload = {
            "chat_id": ID_TELEGRAM,
            "text": msg_chunk,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        try:
            print(f"📨 Enviando parte {i+1}/{len(mensajes_split)} a Telegram...")
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                print("✅ Telegram enviado correctamente.")
            else:
                print(f"⚠️ Error Telegram {response.status_code}: {response.text}")
                
                if "chat not found" in response.text:
                    print("💡 AYUDA: El bot no tiene permiso para escribirte. Envíale /start en Telegram o verifica tu ID_TELEGRAM.")
                # Si falla por formato Markdown (muy común con IA), reintentamos sin formato.
                # Usamos 'elif' para no reintentar si el chat no existe (sería inútil).
                elif response.status_code == 400:
                    print("🔄 Reintentando envío sin formato HTML (texto plano)...")
                    payload.pop("parse_mode", None)
                    requests.post(url, json=payload, timeout=10)
            time.sleep(1) # Pequeña pausa para evitar rate limits
        except Exception as e:
            print(f"⚠️ Error enviando a Telegram: {e}")

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
            
            # Generamos Post Corto para Square (usamos la lógica inteligente general o RSI si es extremo)
            if oportunidad['rsi'] <= 30 or oportunidad['rsi'] >= 70:
                post_square = generar_post_rsi(oportunidad)
            else:
                post_square = generar_post_inteligente(oportunidad)
            
            # Publicar en Square
            if post_square and publicar_en_square(post_square):
                print(f"✅ Publicado en Square. Procediendo a Blog/Telegram...")
                guardar_historial(oportunidad['symbol']) # Opcional: Para evitar repetir si fallara algo externo
                
                # Generar Artículo Blog Extenso
                articulo_blog = generar_articulo_blog(oportunidad)
                img_url = obtener_imagen_binance(oportunidad['symbol'])
                
                if articulo_blog:
                    articulo_blog = articulo_blog.strip()
                    lineas = articulo_blog.split('\n')
                    titulo_blog = lineas[0].replace('#', '').strip()
                    contenido_blog = "\n".join(lineas[1:]).strip()
                    
                    mensaje_final = (
                        f"📌 <b>{titulo_blog}</b>\n"
                        f"------------------------------\n"
                        f"📝 <b>ARTICLE:</b>\n{contenido_blog}\n"
                        f"------------------------------\n"
                        f"🔗 <a href='https://www.binance.com/es-LA/square/profile/victormarsilli'>Source: Binance Square</a>"
                    )
                    
                    enviar_telegram_multimedia(mensaje_final, img_url)
                else:
                    enviar_telegram("⚠️ No se pudo generar el artículo de blog, pero el post de Square está activo.")