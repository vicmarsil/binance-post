from google_auth_oauthlib.flow import InstalledAppFlow
import os

# El permiso exacto que necesita el bot: Administrar tu Blogger
SCOPES = ['https://www.googleapis.com/auth/blogger']

def main():
    print("Iniciando proceso de autorización...")
    # Carga tus credenciales
    flow = InstalledAppFlow.from_client_secrets_file('client_secrets.json', SCOPES)
    
    # Esto abrirá una pestaña en tu navegador web
    creds = flow.run_local_server(port=0)
    
    # Guarda el token generado
    with open('token.json', 'w') as token_file:
        token_file.write(creds.to_json())
        
    print("✅ ¡ÉXITO! Archivo 'token.json' creado correctamente. Ya puedes cerrar esto.")

if __name__ == '__main__':
    main()
