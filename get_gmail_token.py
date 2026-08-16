"""
Obtener el GMAIL_REFRESH_TOKEN (ejecutar UNA sola vez en tu PC).

Instala la libreria (solo para este paso):
    pip install google-auth-oauthlib

Luego ejecuta:
    python get_gmail_token.py

Te pedira el Client ID y el Client Secret (los copias de Google Cloud,
en "APIs y servicios" -> "Credenciales" -> tu cliente OAuth).
Se abrira el navegador -> inicia sesion con tu Gmail -> "Permitir".
Al final imprime los 3 valores para poner en Render y/o en tu .env.
"""
import os

from google_auth_oauthlib.flow import InstalledAppFlow

# Permiso minimo: solo enviar correos (no leer).
SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


def _flow_from_inputs():
    client_id = input("Pega tu Client ID y presiona Enter:\n").strip()
    client_secret = input("Pega tu Client Secret y presiona Enter:\n").strip()
    config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }
    return InstalledAppFlow.from_client_config(config, SCOPES)


def main():
    # Si existe client_secret.json lo usa; si no, pide los datos a mano.
    if os.path.exists("client_secret.json"):
        flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
    else:
        flow = _flow_from_inputs()

    creds = flow.run_local_server(port=0)

    print("\n=========== COPIA ESTOS 3 VALORES ===========\n")
    print(f"GMAIL_CLIENT_ID={creds.client_id}")
    print(f"GMAIL_CLIENT_SECRET={creds.client_secret}")
    print(f"GMAIL_REFRESH_TOKEN={creds.refresh_token}")
    print("\n=============================================")
    print("Ponlos en Render (Environment) y en tu .env local.")


if __name__ == "__main__":
    main()
