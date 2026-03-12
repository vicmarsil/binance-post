import os
from dotenv import load_dotenv

# Cargar variables de entorno ANTES de intentar leerlas
load_dotenv()

import requests
from groq import Groq
import json
import time

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

def obtener_moneda_tendencia():
    """
    1. Monitorizar el mercado:
    Obtiene la moneda con mayor cambio porcentual positivo (Top Gainer) en las últimas 24h.
    """
    endpoints = [
        "https://data-api.binance.vision/api/v3/ticker/24hr",
        "https://api.binance.com/api/v3/ticker/24hr",
        "https://api1.binance.com/api/v3/ticker/24hr",
        "https://api2.binance.com/api/v3/ticker/24hr",
        "https://api3.binance.com/api/v3/ticker/24hr"
    ]

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    data = None
    for url in endpoints:
        try:
            print(f"📡 Probando conexión con: {url}")
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                break
            else:
                print(f"⚠️ Falló {url} con código {response.status_code}")
        except Exception as e:
            print(f"❌ Error conectando a {url}: {e}")
            continue

    if not data:
        return None

    try:
        
        # Filtramos solo pares con USDT para asegurar liquidez y relevancia
        tickers = [t for t in data if t['symbol'].endswith('USDT')]
        
        # Ordenamos por mayor subida (descendente)
        sorted_tickers = sorted(tickers, key=lambda x: float(x['priceChangePercent']), reverse=True)
        
        # Cargar historial y filtrar monedas ya publicadas en las últimas 24h
        historial = cargar_historial()
        ahora = time.time()
        candidatos = []
        
        for t in sorted_tickers:
            symbol = t['symbol'].replace('USDT', '')
            if symbol in historial and (ahora - historial[symbol] < 86400):
                continue
            candidatos.append(t)

        if not candidatos:
            print("⚠️ Todas las monedas trending han sido publicadas recientemente.")
            return None

        # Tomamos la primera moneda candidata que no ha sido publicada recientemente.
        top_ticker = candidatos[0]
        symbol = top_ticker['symbol'].replace('USDT', '')
        
        print(f"ℹ️ Moneda seleccionada: {symbol}. No se buscará logo para agilizar.")

        return {
            "symbol": symbol,
            "percent": top_ticker['priceChangePercent'],
            "lastPrice": top_ticker['lastPrice']
        }
    except Exception as e:
        print(f"⚠️ Error obteniendo datos de Binance: {e}")
        return None

def generar_post_inteligente(datos_mercado):
    """
    2. Generación de Contenido con IA (Groq/Llama3):
    Redacta un análisis técnico breve y profesional.
    """
    moneda = datos_mercado['symbol']
    cambio = datos_mercado['percent']
    
    # Formateo visual "Limpieza Pro": Quita ceros extra (Ej: 0.5000 -> 0.5 | 0.00976000 -> 0.00976)
    precio = "{:.8f}".format(float(datos_mercado['lastPrice'])).rstrip("0").rstrip(".")

    # Lógica para mejorar el gancho (Hook) si la subida es fuerte
    instruccion_extra = ""
    if float(cambio) > 20:
        instruccion_extra = "- MENCIONA: Niveles de Sobrecompra (RSI) o Soportes clave para dar imagen de experto."

    prompt = f"""
    Actúa como un 'Top Creator' de Binance Square (estilo influencer inteligente y viral).
    DATOS: {moneda} cotiza a {precio} USDT (+{cambio}% en 24h).
    
    OBJETIVO: Escribir un post que genere likes y seguidores.
    
    ESTILO (Imita a los mejores):
    - Usa emojis visuales al inicio de las frases importantes.
    - Párrafos muy cortos y espaciosos.
    - Tono: Entusiasta, directo y con autoridad.
    
    ESTRUCTURA OBLIGATORIA:
    1. 🚨 GANCHO VISUAL: Título urgente (Ej: "¡{moneda} SE MUEVE!" o "🚀 ¿Oportunidad en {moneda}?").
    2. 📊 EL DATO: Precio actual y subida.
    3. 🧠 ANÁLISIS FLASH: ¿Por qué sube? (Volumen / Rompió resistencia / Hype). Sé breve.
    4. 🎯 CONCLUSIÓN RÁPIDA: ¿Sigue subiendo o esperamos?
    5. 👇 CIERRE VIRAL: "Dale Like ❤️ y Sígueme para más alertas 🦁".
    
    REGLAS:
    - Máximo 500 caracteres.
    - OBLIGATORIO: Cashtags ${moneda}, $BNB y #{moneda}.
    {instruccion_extra}
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

def calcular_rsi(symbol, period=14):
    """
    Calcula el RSI (1h) para detectar sobreventa.
    """
    try:
        url = "https://api.binance.com/api/v3/klines"
        # Traemos 100 velas de 1h para calcular bien el promedio
        params = {'symbol': symbol, 'interval': '1h', 'limit': 100}
        response = requests.get(url, params=params, timeout=5)
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
        return None, None

def verificar_rsi_majors():
    # Monedas 'Blue Chip' para buscar oportunidades de oro
    majors = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT']
    print("🔍 Escaneando oportunidades RSI en Majors (BTC, ETH, BNB, SOL)...")
    
    for symbol in majors:
        rsi, precio = calcular_rsi(symbol)
        if rsi is not None and rsi < 30: # Nivel de Sobreventa
            print(f"🚨 ¡ALERTA! {symbol} con RSI {rsi:.2f} (Sobreventa)")
            return {
                "symbol": symbol.replace('USDT', ''),
                "rsi": rsi,
                "price": precio
            }
    return None

def generar_post_rsi(datos):
    moneda = datos['symbol']
    rsi = int(datos['rsi'])
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
    
    ESTILO DE REDACCIÓN (IMPORTANTE):
    - Tono: "Diario de un Programador". Usa primera persona.
    - Frases OBLIGATORIAS: "Desde mi terminal en Argentina...", "Analizando los logs de mi script...", "El algoritmo detectó...".
    - Enfoque: Técnico pero explicativo. Enseña qué es el RSI o el volumen mientras analizas.
    - NO uses frases genéricas de IA como "En el mundo digital de hoy". Sé crudo, directo y 'geek'.
    - Generá el artículo de blog exclusivamente en inglés, usando un lenguaje técnico avanzado, pero mantené las alertas de Telegram en español.
    
    ESTRUCTURA MARKDOWN:
    1. # Título H1 (Llamativo y técnico)
    2. **INTRODUCCIÓN**: El primer párrafo debe presentar brevemente el proyecto de automatización vIcmAr.
    3. ## 📟 El hallazgo en la consola (Contexto)
    4. ## ⚙️ Análisis de los datos (Desglose de precio y RSI)
    5. ## 🔮 Proyección del código (Conclusión)
    6. **TAGS**: Al final, incluye obligatoriamente: #Crypto #Python #Trading #{symbol}
    
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

def enviar_telegram(mensaje):
    """
    Envía el mensaje formateado a Telegram. No detiene el bot si falla.
    """
    if not TOKEN_TELEGRAM or not ID_TELEGRAM:
        print("⚠️ Telegram: Credenciales no configuradas. Se omite el envío.")
        return

    url = f"https://api.telegram.org/bot{TOKEN_TELEGRAM}/sendMessage"
    payload = {
        "chat_id": ID_TELEGRAM,
        "text": mensaje,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    try:
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
                print("🔄 Reintentando envío sin formato Markdown (texto plano)...")
                payload.pop("parse_mode", None)
                requests.post(url, json=payload, timeout=10)
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
        # --- MODO TENDENCIA (Por defecto) ---
        
        # 1. Primero buscamos oportunidades VIP (RSI < 30 en Majors)
        # Esto tiene prioridad sobre las monedas random que suben.
        alerta_rsi = verificar_rsi_majors()
        
        if alerta_rsi:
            post_rsi = generar_post_rsi(alerta_rsi)
            if post_rsi and publicar_en_square(post_rsi):
                # Guardamos con sufijo _RSI para no repetir la alerta en 24h
                guardar_historial(f"{alerta_rsi['symbol']}_RSI")
                print(f"💾 Alerta RSI de {alerta_rsi['symbol']} guardada.")
                
                msg = f"🚨 *ALERTA RSI EXTREMO* 🚨\n" \
                      f"--------------------------\n" \
                      f"💎 *Moneda:* {alerta_rsi['symbol']}\n" \
                      f"💰 *Precio:* {alerta_rsi['price']} USDT\n" \
                      f"📉 *RSI (1h):* {alerta_rsi['rsi']:.2f}\n" \
                      f"--------------------------\n" \
                      f"🤖 *vIcmAr Insight:* Zona de sobreventa detectada.\n" \
                      f"--------------------------\n" \
                      f"🔗 [Ver Perfil Binance Square](https://www.binance.com/es-LA/square/profile/victormarsilli)"
                enviar_telegram(msg)
                
                # Generar y enviar artículo de blog
                articulo = generar_articulo_blog(alerta_rsi)
                if articulo:
                    # Separar título y contenido
                    lineas = articulo.split('\n')
                    titulo_blog = lineas[0].replace('#', '').strip()
                    contenido_blog = "\n".join(lineas[1:]).strip()
                    firma = "\n\nOriginally published on my Binance Square profile: https://www.binance.com/es-LA/square/profile/victormarsilli"
                    
                    # Mensajes telegram para copiado fácil
                    enviar_telegram(f"📝 *BLOG TITLE:*\n{titulo_blog}")
                    enviar_telegram(f"📄 *BLOG CONTENT (Ready to Paste):*\n\n{contenido_blog + firma}")
        
        else:
            # 2. Si no hay alertas VIP, buscamos tendencia normal (Top Gainers)
            tendencia = obtener_moneda_tendencia()
            if tendencia:
                print(f"📈 Tendencia detectada: {tendencia['symbol']} ({tendencia['percent']}%)")
                post_final = generar_post_inteligente(tendencia)
                if post_final:
                    if publicar_en_square(post_final):
                        guardar_historial(tendencia['symbol'])
                        print(f"💾 Guardado {tendencia['symbol']} en el historial.")
                        
                        # Calculamos RSI rápido para el reporte de Telegram
                        rsi_val, _ = calcular_rsi(tendencia['symbol'])
                        rsi_txt = f"{rsi_val:.2f}" if rsi_val else "N/A"
                        
                        msg = f"🚀 *TENDENCIA DETECTADA* 🚀\n" \
                              f"--------------------------\n" \
                              f"🔥 *Moneda:* {tendencia['symbol']}\n" \
                              f"📈 *Cambio 24h:* +{tendencia['percent']}%\n" \
                              f"💰 *Precio:* {tendencia['lastPrice']} USDT\n" \
                              f"📊 *RSI (1h):* {rsi_txt}\n" \
                              f"--------------------------\n" \
                              f"🤖 *vIcmAr Insight:* Tendencia detectada por volumen atípico.\n" \
                              f"--------------------------\n" \
                              f"🔗 [Ver Perfil Binance Square](https://www.binance.com/es-LA/square/profile/victormarsilli)"
                        enviar_telegram(msg)
                        
                        # Preparamos datos completos para el blog
                        datos_blog = tendencia.copy()
                        datos_blog['rsi'] = rsi_txt
                        
                        # Generar y enviar artículo de blog
                        articulo = generar_articulo_blog(datos_blog)
                        if articulo:
                            # Separar título y contenido
                            lineas = articulo.split('\n')
                            titulo_blog = lineas[0].replace('#', '').strip()
                            contenido_blog = "\n".join(lineas[1:]).strip()
                            firma = "\n\nOriginally published on my Binance Square profile: https://www.binance.com/es-LA/square/profile/victormarsilli"
                            
                            # Mensajes telegram para copiado fácil
                            enviar_telegram(f"📝 *BLOG TITLE:*\n{titulo_blog}")
                            enviar_telegram(f"📄 *BLOG CONTENT (Ready to Paste):*\n\n{contenido_blog + firma}")
                    else:
                        print(f"⚠️ No se actualizó el historial para permitir reintento.")