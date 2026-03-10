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
MODO_PRUEBA = os.getenv("MODO_PRUEBA", "True").lower() == "true" # 🟢 Configurable. Por defecto True si no se especifica.
ARCHIVO_HISTORIAL = "historial.json"

# Validación básica de seguridad
if not GROQ_API_KEY:
    raise ValueError("❌ Error: La variable GROQ_API_KEY no está configurada.")

client = Groq(api_key=GROQ_API_KEY)

def cargar_historial():
    if os.path.exists(ARCHIVO_HISTORIAL):
        try:
            with open(ARCHIVO_HISTORIAL, "r") as f:
                return json.load(f)
        except:
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
    try:
        # Usamos data-api.binance.vision para evitar error 451 (Geo-bloqueo en GitHub Actions/US)
        url = "https://data-api.binance.vision/api/v3/ticker/24hr"
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        
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

        # Buscamos en el TOP 10 de los CANDIDATOS (no repetidos) la primera moneda con logo
        for ticker in candidatos[:10]:
            symbol = ticker['symbol'].replace('USDT', '')
            
            # Probamos múltiples fuentes de iconos para asegurar imagen
            candidates = [
                f"https://raw.githubusercontent.com/spothq/cryptocurrency-icons/master/128/color/{symbol.lower()}.png",
                f"https://assets.coincap.io/assets/icons/{symbol.lower()}@2x.png"
            ]
            
            for url in candidates:
                try:
                    if requests.head(url, timeout=2).status_code == 200:
                        return {
                            "symbol": symbol,
                            "percent": ticker['priceChangePercent'],
                            "lastPrice": ticker['lastPrice'],
                            "logo_url": url
                        }
                except:
                    continue
            
            print(f"ℹ️ Saltando {symbol} (Top Gainer) porque no se encontró logo.")

        if not candidatos:
            print("⚠️ Todas las monedas trending han sido publicadas recientemente.")
            return None

        # Fallback: Si ninguna tiene logo, devolvemos la #1 de los candidatos sin imagen
        top_ticker = candidatos[0]
        symbol = top_ticker['symbol'].replace('USDT', '')
        return {
            "symbol": symbol,
            "percent": top_ticker['priceChangePercent'],
            "lastPrice": top_ticker['lastPrice'],
            "logo_url": None
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
    - Estructura:
        1. Título atractivo (ej: "🚀 Análisis de {moneda}").
        2. Dato clave (precio y % de cambio).
        3. Análisis breve pero sustancioso: Menciona posibles catalizadores (noticias, volumen) o indicadores técnicos simples (como el RSI si hay sobrecompra).
        4. Pregunta de cierre para fomentar la interacción.
    {instruccion_extra}
    """

    try:
        chat_completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            # He cambiado el modelo a uno estándar de Groq y ajustado la temperatura para un texto más rico
            model="llama-3.3-70b-versatile",
            temperature=0.7
        )
        return chat_completion.choices[0].message.content
    except Exception as e:
        print(f"⚠️ Error generando texto con Groq: {e}")
        return None

def publicar_en_square(contenido, imagen_url):
    """
    3. Publicación Automática:
    Envía el contenido y una imagen (si está disponible) a Binance Square.
    """
    if MODO_PRUEBA:
        print(f"\n🧪 [MODO PRUEBA] Simulación de envío a Binance Square:")
        print(f"--------------------------------------------------")
        if imagen_url:
            print(f"Imagen: {imagen_url}")
        else:
            print("Imagen: No se adjuntará imagen.")
        print(f"Texto:\n{contenido}")
        print(f"--------------------------------------------------")
        return

    url = "https://www.binance.com/bapi/composite/v1/public/pgc/openApi/content/add"
    headers = {
        "X-Square-OpenAPI-Key": SQUARE_API_KEY,
        "Content-Type": "application/json",
        "clienttype": "binanceSkill"
    }
    # El payload cambia si hay imagen o no
    if imagen_url:
        payload = {
            "body": contenido,
            "imageUrls": [imagen_url]
        }
        print(f"📡 Enviando post con imagen a Binance Square...")
    else:
        payload = {"bodyTextOnly": contenido}
        print(f"📡 Enviando post (solo texto) a Binance Square...")
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code == 200:
            print("🚀 ¡POST PUBLICADO REALMENTE EN BINANCE SQUARE!")
        else:
            # Imprimimos el error de forma más clara
            print(f"❌ Error al publicar ({response.status_code}): {response.text}")

    except Exception as e:
        print(f"⚠️ Error de red: {e}")

if __name__ == "__main__":
    print("🤖 Iniciando Bot vIcmAr...")
    tendencia = obtener_moneda_tendencia()
    
    if tendencia:
        print(f"📈 Tendencia detectada: {tendencia['symbol']} ({tendencia['percent']}%)")
        if tendencia['logo_url']:
            print(f"🖼️  Logo encontrado: {tendencia['logo_url']}")
        post_final = generar_post_inteligente(tendencia)
        if post_final:
            publicar_en_square(post_final, tendencia['logo_url'])
            
            # Guardamos en el historial para no repetir
            guardar_historial(tendencia['symbol'])
            print(f"💾 Guardado {tendencia['symbol']} en el historial.")