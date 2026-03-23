import os
import requests

from config import *

def publicar_en_square(contenido):
    if MODO_PRUEBA:
        print(f"\n🧪 [MODO PRUEBA] Simulación de envío a Binance Square:\n{contenido}\n")
        return True

    url = "https://www.binance.com/bapi/composite/v1/public/pgc/openApi/content/add"
    headers = {"X-Square-OpenAPI-Key": SQUARE_API_KEY, "Content-Type": "application/json", "clienttype": "binanceSkill"}
    try:
        response = requests.post(url, headers=headers, json={"bodyTextOnly": contenido})
        resultado = response.json()
        if resultado.get("code") == "000000":
            print(f"🚀 PUBLICADO! ID del Post: {resultado.get('data', {}).get('id', 'Desconocido')}")
            return True
        else:
            print(f"❌ Binance rechazó el post: {resultado.get('message')}")
            return False
    except Exception as e:
        print(f"⚠️ Error técnico en Square: {e}")
        return False

def enviar_telegram(mensaje):
    if not TOKEN_TELEGRAM or not ID_TELEGRAM:
        print("⚠️ Credenciales de Telegram faltantes. No se enviará el mensaje.")
        return False
        
    url = f"https://api.telegram.org/bot{TOKEN_TELEGRAM}/sendMessage"
    payload = {
        "chat_id": ID_TELEGRAM,
        "text": mensaje
    }
    try:
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            print("✅ Mensaje enviado a Telegram correctamente.")
            return True
        else:
            print(f"❌ Error al enviar a Telegram: {response.text}")
            return False
    except Exception as e:
        print(f"⚠️ Error técnico con Telegram: {e}")
        return False

def enviar_foto_telegram(url_imagen, caption=""):
    if not TOKEN_TELEGRAM or not ID_TELEGRAM:
        return False
        
    url = f"https://api.telegram.org/bot{TOKEN_TELEGRAM}/sendPhoto"
    payload = {
        "chat_id": ID_TELEGRAM,
        "photo": url_imagen,
        "caption": caption
    }
    try:
        response = requests.post(url, json=payload)
        return response.status_code == 200
    except Exception as e:
        print(f"⚠️ Error enviando foto a Telegram: {e}")
        return False
