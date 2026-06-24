"""
Obtener el GMAIL_REFRESH_TOKEN (ejecutar UNA sola vez en tu PC).

Pasos:
  1. Descarga el archivo de credenciales OAuth desde Google Cloud
     (tipo "Aplicacion de escritorio") y guardalo en esta carpeta
     con el nombre:  client_secret.json
  2. Instala la libreria (solo para este paso):
        pip install google-auth-oauthlib
  3. Ejecuta:
        python get_gmail_token.py
  4. Se abrira tu navegador -> inicia sesion con tu Gmail -> "Permitir".
  5. Copia los 3 valores que se imprimen y ponlos en Render y/o en tu .env.
"""
from google_auth_oauthlib.flow import InstalledAppFlow

# Permiso minimo: solo enviar correos (no leer).
SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


def main():
    flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
    creds = flow.run_local_server(port=0)

    print("\n=========== COPIA ESTOS 3 VALORES ===========\n")
    print(f"GMAIL_CLIENT_ID={creds.client_id}")
    print(f"GMAIL_CLIENT_SECRET={creds.client_secret}")
    print(f"GMAIL_REFRESH_TOKEN={creds.refresh_token}")
    print("\n=============================================")
    print("Ponlos en Render (Environment) y en tu .env local.")


if __name__ == "__main__":
    main()
