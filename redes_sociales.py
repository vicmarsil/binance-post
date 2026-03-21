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
