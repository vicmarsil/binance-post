import os
from dotenv import load_dotenv

# Cargar variables de entorno ANTES de intentar leerlas
load_dotenv()

import requests
from groq import Groq
import json

# --- CONFIGURACIÓN Y VARIABLES DE ENTORNO ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
SQUARE_API_KEY = os.getenv("SQUARE_API_KEY")

# Validación básica de seguridad
if not GROQ_API_KEY:
    raise ValueError("❌ Error: La variable GROQ_API_KEY no está configurada.")

client = Groq(api_key=GROQ_API_KEY)

def obtener_moneda_tendencia():
    """
    1. Monitorizar el mercado:
    Obtiene la moneda con mayor cambio porcentual positivo (Top Gainer) en las últimas 24h.
    """
    try:
        url = "https://api.binance.com/api/v3/ticker/24hr"
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        
        # Filtramos solo pares con USDT para asegurar liquidez y relevancia
        tickers = [t for t in data if t['symbol'].endswith('USDT')]
        
        # Encontramos la moneda con mayor subida
        top_ticker = max(tickers, key=lambda x: float(x['priceChangePercent']))
        
        return {
            "symbol": top_ticker['symbol'].replace('USDT', ''),
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
    - Máximo 300 caracteres.
    - OBLIGATORIO: Incluye los cashtags ${moneda} y $BNB.
    - Tono: Profesional, objetivo, sin promesas de ganancias ("to the moon").
    - Estructura: Dato clave -> Análisis breve -> Pregunta de cierre.
    {instruccion_extra}
    """

    try:
        chat_completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile",
            temperature=0.6
        )
        return chat_completion.choices[0].message.content
    except Exception as e:
        print(f"⚠️ Error generando texto con Groq: {e}")
        return None

def publicar_en_square(contenido):
    """
    3. Publicación Automática:
    Envía el contenido a Binance Square.
    """
    url = "https://www.binance.com/bapi/composite/v1/public/pgc/openApi/content/add"
    headers = {
        "X-Square-OpenAPI-Key": SQUARE_API_KEY,
        "Content-Type": "application/json",
        "clienttype": "binanceSkill"
    }
    payload = {"bodyTextOnly": contenido}
    
    try:
        print(f"📡 Enviando post a Binance Square...")
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code == 200:
            print("🚀 ¡POST PUBLICADO REALMENTE EN BINANCE SQUARE!")
        else:
            print(f"❌ Error al publicar: {response.text}")
    except Exception as e:
        print(f"⚠️ Error de red: {e}")

if __name__ == "__main__":
    print("🤖 Iniciando Bot vIcmAr...")
    tendencia = obtener_moneda_tendencia()
    
    if tendencia:
        print(f"📈 Tendencia detectada: {tendencia['symbol']} ({tendencia['percent']}%)")
        post_final = generar_post_inteligente(tendencia)
        if post_final:
            publicar_en_square(post_final)