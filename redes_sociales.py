import os
import time
import tempfile
import requests
import tweepy
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

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

def notificar_admin_telegram(mensaje_alerta, img_url=None):
    if not TOKEN_TELEGRAM or not ID_TELEGRAM_ADMIN: return
    url_bot = f"https://api.telegram.org/bot{TOKEN_TELEGRAM}/sendMessage"
    texto = f"🚨 <b>¡Fallo al publicar en X (Twitter)!</b>\n\nCopia este texto y súbelo manual a tu cuenta:\n\n<code>{mensaje_alerta}</code>"
    if img_url: texto += f"\n\n🖼️ Imagen: <a href='{img_url}'>Descargar aquí</a>"
    requests.post(url_bot, json={"chat_id": ID_TELEGRAM_ADMIN, "text": texto, "parse_mode": "HTML"}, timeout=10)

def publicar_en_blogger(titulo, contenido, etiquetas, img_url=None):
    if MODO_PRUEBA: return True
    if not BLOG_ID or not os.path.exists('token.json'): return False
    try:
        creds = Credentials.from_authorized_user_file('token.json', ['https://www.googleapis.com/auth/blogger'])
        service = build('blogger', 'v3', credentials=creds)
        etiquetas_limpias = [tag.replace('#', '') for tag in etiquetas]
        
        html_imagen = f'<div style="text-align: center; margin-bottom: 30px;"><img src="{img_url}" alt="{titulo}" style="max-width: 100%; border-radius: 12px;"></div>' if img_url else ""
        cuerpo = contenido.replace('\n', '<br>').replace('<b>', '<b style="color: #1a73e8; font-size: 1.15em; display: inline-block; margin-top: 10px;">').replace('<code>', '<code style="background-color: #282c34; color: #98c379; padding: 2px 6px; border-radius: 4px;">')
        cuerpo = cuerpo.replace('<a href=', '<a style="color: #d8a011; font-weight: bold; text-decoration: underline;" target="_blank" href=')
        contenido_html = f'<div style="font-family: \'Segoe UI\', sans-serif; line-height: 1.8;">{html_imagen}{cuerpo}</div>'
        
        request = service.posts().insert(blogId=BLOG_ID, body={'title': titulo, 'content': contenido_html, 'labels': etiquetas_limpias}, isDraft=False)
        print(f"✅ ¡PUBLICADO EN BLOGGER! URL: {request.execute().get('url')}")
        return True
    except Exception as e:
        print(f"⚠️ Error Blogger: {e}")
        return False

def publicar_en_twitter(mensaje, img_url=None):
    if MODO_PRUEBA: return True
    if not all([TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET]):
        notificar_admin_telegram(mensaje, img_url)
        return False
        
    client_tw = tweepy.Client(consumer_key=TWITTER_API_KEY, consumer_secret=TWITTER_API_SECRET, access_token=TWITTER_ACCESS_TOKEN, access_token_secret=TWITTER_ACCESS_SECRET)
    media_ids = None
    if img_url:
        try:
            api_v1 = tweepy.API(tweepy.OAuth1UserHandler(TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET))
            r = requests.get(img_url, timeout=15)
            if r.status_code == 200:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
                    tmp.write(r.content)
                    media_ids = [api_v1.media_upload(tmp.name).media_id]
                os.remove(tmp.name)
        except Exception as e:
            print(f"⚠️ Error imagen X: {e}")

    for intento in range(3):
        try:
            res = client_tw.create_tweet(text=mensaje, media_ids=media_ids) if media_ids else client_tw.create_tweet(text=mensaje)
            print(f"✅ ¡PUBLICADO EN X! ID: {res.data['id']}")
            return True
        except Exception as e:
            if any(err in str(e) for err in ["503", "500", "502"]): time.sleep(5)
            else: break
    notificar_admin_telegram(mensaje, img_url)
    return False

def publicar_en_facebook(mensaje, img_url=None):
    if MODO_PRUEBA or not FB_PAGE_ID or not FB_ACCESS_TOKEN: return MODO_PRUEBA
    try:
        url = f"https://graph.facebook.com/v19.0/{FB_PAGE_ID}/{'photos' if img_url else 'feed'}"
        payload = {'url': img_url, 'caption': mensaje, 'access_token': FB_ACCESS_TOKEN} if img_url else {'message': mensaje, 'access_token': FB_ACCESS_TOKEN}
        res = requests.post(url, data=payload, timeout=15).json()
        if 'id' in res:
            print(f"✅ ¡PUBLICADO EN FACEBOOK! ID: {res['id']}")
            return True
        print(f"❌ Error Facebook: {res.get('error', {}).get('message')}")
        return False
    except: return False

def enviar_telegram(mensaje):
    if not TOKEN_TELEGRAM or not ID_TELEGRAM: return
    url = f"https://api.telegram.org/bot{TOKEN_TELEGRAM}/sendMessage"
    temp_msg = mensaje
    while len(temp_msg) > 0:
        corte = temp_msg.rfind('\n', 0, 4000)
        if corte == -1: corte = 4000
        chunk = temp_msg[:corte]
        temp_msg = temp_msg[corte:].lstrip()
        try:
            res = requests.post(url, json={"chat_id": ID_TELEGRAM, "text": chunk, "parse_mode": "HTML", "disable_web_page_preview": True}, timeout=10)
            if res.status_code == 400: requests.post(url, json={"chat_id": ID_TELEGRAM, "text": chunk, "disable_web_page_preview": True}, timeout=10)
            time.sleep(1)
        except: pass

def enviar_telegram_multimedia(mensaje, imagen_url):
    if not imagen_url: return enviar_telegram(mensaje)
    url_photo = f"https://api.telegram.org/bot{TOKEN_TELEGRAM}/sendPhoto"
    if len(mensaje) < 1000:
        if requests.post(url_photo, json={"chat_id": ID_TELEGRAM, "photo": imagen_url, "caption": mensaje, "parse_mode": "HTML"}, timeout=10).status_code == 200: return
    requests.post(url_photo, json={"chat_id": ID_TELEGRAM, "photo": imagen_url}, timeout=10)
    enviar_telegram(mensaje)
