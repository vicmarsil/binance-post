--- /dev/null
+++ c:\Users\clauv\Victor\square_binance_publicador\config.py
@@ -0,0 +1,63 @@
+import os
+from dotenv import load_dotenv
+
+# Cargar variables de entorno
+load_dotenv()
+
+GROQ_API_KEY = os.getenv("GROQ_API_KEY")
+SQUARE_API_KEY = os.getenv("SQUARE_API_KEY")
+if SQUARE_API_KEY:
+    SQUARE_API_KEY = SQUARE_API_KEY.strip()
+
+MODO_PRUEBA = os.getenv("MODO_PRUEBA", "False").lower() == "true"
+GROQ_MODEL_NAME = os.getenv("GROQ_MODEL_NAME", "llama-3.3-70b-versatile").strip()
+
+# Parche de seguridad modelo antiguo
+if "llama3-8b-8192" in GROQ_MODEL_NAME:
+    GROQ_MODEL_NAME = "llama-3.3-70b-versatile"
+
+TIPO_BOT = os.getenv("TIPO_BOT", "TENDENCIA")
+REFERIDO_BITGET = os.getenv("REFERIDO_BITGET", "https://web3.bitget.com/share/1sEleg?inviteCode=vicmarsil18")
+LINK_TELEGRAM = os.getenv("LINK_TELEGRAM", "https://t.me/LaTerminaldevIcmAr")
+
+# Credenciales Redes
+TOKEN_TELEGRAM = os.getenv("TOKEN_TELEGRAM")
+ID_TELEGRAM = os.getenv("ID_TELEGRAM")
+ID_TELEGRAM_ADMIN = os.getenv("ID_TELEGRAM_ADMIN")
+BLOG_ID = os.getenv("BLOG_ID")
+FB_PAGE_ID = os.getenv("FB_PAGE_ID")
+FB_ACCESS_TOKEN = os.getenv("FB_ACCESS_TOKEN")
+
+TWITTER_API_KEY = os.getenv("TWITTER_API_KEY", "").strip() or None
+TWITTER_API_SECRET = os.getenv("TWITTER_API_SECRET", "").strip() or None
+TWITTER_ACCESS_TOKEN = os.getenv("TWITTER_ACCESS_TOKEN", "").strip() or None
+TWITTER_ACCESS_SECRET = os.getenv("TWITTER_ACCESS_SECRET", "").strip() or None
+
+ARCHIVO_HISTORIAL = "historial.json"
+
+# --- LISTA DE MONEDAS A ANALIZAR ---
+MONEDAS_ANALISIS = [
+    'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT', 
+    'ADAUSDT', 'AVAXUSDT', 'TRXUSDT', 'LINKUSDT', 'DOTUSDT', 'MATICUSDT',
+    'DOGEUSDT', 'SHIBUSDT', 'PEPEUSDT', 'WIFUSDT', 
+    'SUIUSDT', 'APTUSDT', 'ARBUSDT', 'OPUSDT', 'NEARUSDT', 'TIAUSDT', 
+    'INJUSDT', 'FETUSDT', 'RNDRUSDT' 
+]
+
+# Mapeo para CoinGecko
+COINGECKO_IDS = {
+    'BTCUSDT': 'bitcoin', 'ETHUSDT': 'ethereum', 'BNBUSDT': 'binancecoin',
+    'SOLUSDT': 'solana', 'XRPUSDT': 'ripple', 'ADAUSDT': 'cardano',
+    'AVAXUSDT': 'avalanche-2', 'TRXUSDT': 'tron', 'LINKUSDT': 'chainlink',
+    'DOTUSDT': 'polkadot', 'MATICUSDT': 'matic-network', 'DOGEUSDT': 'dogecoin',
+    'SHIBUSDT': 'shiba-inu', 'PEPEUSDT': 'pepe', 'WIFUSDT': 'dogwifcoin',
+    'SUIUSDT': 'sui', 'APTUSDT': 'aptos', 'ARBUSDT': 'arbitrum',
+    'OPUSDT': 'optimism', 'NEARUSDT': 'near', 'TIAUSDT': 'celestia',
+    'INJUSDT': 'injective-protocol', 'FETUSDT': 'fetch-ai', 'RNDRUSDT': 'render-token'
+}
