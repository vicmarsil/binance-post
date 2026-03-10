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
    precio = datos_mercado['lastPrice']

    # Lógica para mejorar el gancho (Hook) si la subida es fuerte
    instruccion_extra = ""
    if float(cambio) > 20:
        instruccion_extra = "- MENCIONA: Niveles de Sobrecompra (RSI) o Soportes clave para dar imagen de experto."

    prompt = f"""
    Actúa como un analista experto de criptomonedas para la marca 'vIcmAr'.
    DATOS: {moneda} cotiza a {precio} USDT (+{cambio}% en 24h).
    
    TAREA: Escribe un post para Binance Square optimizado para monetización.
    REGLAS:
    - Máximo 500 caracteres.
    - OBLIGATORIO: Incluye los cashtags ${moneda} y $BNB.
    - Tono: Profesional, objetivo, sin promesas de ganancias ("to the moon").
    - No incluyas URLs, solo texto y cashtags.
    - Estructura:
        1. Título atractivo (ej: "🚀 Análisis de {moneda}").
        2. Dato clave (precio y % de cambio).
        3. Análisis breve pero sustancioso: Menciona posibles catalizadores (noticias, volumen) o indicadores técnicos simples (como el RSI si hay sobrecompra).
        4. Pregunta de cierre para fomentar la interacción.
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

if __name__ == "__main__":
    print("🤖 Iniciando Bot vIcmAr...")
    print(f"⚙️ Versión 2.0 - Modelo Configurado: {GROQ_MODEL_NAME}")
    tendencia = obtener_moneda_tendencia()
    
    if tendencia:
        print(f"📈 Tendencia detectada: {tendencia['symbol']} ({tendencia['percent']}%)")
        post_final = generar_post_inteligente(tendencia)
        if post_final:
            if publicar_en_square(post_final):
                # Guardamos en el historial para no repetir SOLO si hubo éxito
                guardar_historial(tendencia['symbol'])
                print(f"💾 Guardado {tendencia['symbol']} en el historial.")
            else:
                print(f"⚠️ No se actualizó el historial para permitir reintento.")