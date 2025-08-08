from flask import Flask
import imaplib
import email
import smtplib
import os
import requests
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from threading import Thread
import time
import logging
from werkzeug.utils import secure_filename

app = Flask(__name__)

# Configuración Gmail (lectura IMAP + envío SMTP)
GMAIL_EMAIL = "seendmessenger@gmail.com"  # Cambiar en variables de entorno en Render
GMAIL_PASSWORD = "fzhtsyaoukqzhmtr"      # App Password con 2FA (variable de entorno)
IMAP_SERVER = "imap.gmail.com"           # Para escanear correos
IMAP_PORT = 993                          # SSL obligatorio
SMTP_SERVER = "smtp.gmail.com"           # Para enviar partes
SMTP_PORT = 587                          # TLS

PART_SIZE = 15 * 1024 * 1024  # 15 MB por parte
CHECK_INTERVAL = 1  # Segundos entre escaneos (ajustable)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("NautaTransfer")

def buscar_enlaces_en_gmail():
    """Busca correos no leídos de miguelorlandos@nauta.cu y extrae enlaces"""
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        mail.login(GMAIL_EMAIL, GMAIL_PASSWORD)
        mail.select("inbox")

        # Buscar correos NO LEÍDOS de miguelorlandos@nauta.cu
        status, messages = mail.search(None, '(UNSEEN FROM "miguelorlandos@nauta.cu")')
        if not messages[0]:
            return None

        enlaces = []
        for msg_id in messages[0].split():
            status, msg_data = mail.fetch(msg_id, "(RFC822)")
            raw_email = msg_data[0][1]
            email_msg = email.message_from_bytes(raw_email)

            # Extraer enlace del cuerpo (texto plano)
            if email_msg.is_multipart():
                for part in email_msg.walk():
                    if part.get_content_type() == "text/plain":
                        cuerpo = part.get_payload(decode=True).decode()
                        if "http" in cuerpo:
                            enlace = cuerpo.split()[-1].strip()  # Supone que el enlace está al final
                            enlaces.append(enlace)
                            break

        mail.close()
        mail.logout()
        return enlaces[0] if enlaces else None  # Retorna el primer enlace encontrado

    except Exception as e:
        logger.error(f"Error al escanear Gmail: {str(e)}")
        return None

def descargar_y_enviar_archivo(enlace):
    """Descarga el archivo y lo envía (o sus partes) a miguelorlandos@nauta.cu"""
    try:
        # Descargar archivo
        nombre_archivo = secure_filename(enlace.split('/')[-1].split('?')[0])
        ruta_archivo = f"/tmp/{nombre_archivo}"
        
        logger.info(f"Descargando archivo: {enlace}")
        response = requests.get(enlace, stream=True, timeout=60)
        with open(ruta_archivo, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        # Verificar tamaño y dividir si es necesario
        tamanio = os.path.getsize(ruta_archivo)
        partes = []

        if tamanio > PART_SIZE:
            parte_num = 1
            with open(ruta_archivo, 'rb') as f:
                while chunk := f.read(PART_SIZE):
                    nombre_parte = f"/tmp/{nombre_archivo}.part{parte_num}"
                    with open(nombre_parte, 'wb') as parte_f:
                        parte_f.write(chunk)
                    partes.append(nombre_parte)
                    parte_num += 1
            os.remove(ruta_archivo)
        else:
            partes.append(ruta_archivo)

        # Enviar cada parte como adjunto
        for parte in partes:
            msg = MIMEMultipart()
            msg['From'] = GMAIL_EMAIL
            msg['To'] = "miguelorlandos@nauta.cu"
            msg['Subject'] = f"Archivo: {nombre_archivo} - Parte {partes.index(parte) + 1}" if len(partes) > 1 else f"Archivo: {nombre_archivo}"

            with open(parte, 'rb') as f:
                adjunto = MIMEApplication(f.read(), _subtype="octet-stream")
                adjunto.add_header('Content-Disposition', 'attachment', 
                                filename=os.path.basename(parte))
                msg.attach(adjunto)

            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
                server.starttls()
                server.login(GMAIL_EMAIL, GMAIL_PASSWORD)
                server.send_message(msg)
            
            logger.info(f"Enviada parte: {os.path.basename(parte)}")
            os.remove(parte)

        logger.info("¡Proceso completado con éxito!")

    except Exception as e:
        logger.error(f"Error al procesar el archivo: {str(e)}")

def escaneo_constante():
    """Bucle infinito para escanear cada CHECK_INTERVAL segundos"""
    while True:
        enlace = buscar_enlaces_en_gmail()
        if enlace:
            logger.info(f"Enlace detectado: {enlace}")
            descargar_y_enviar_archivo(enlace)
        time.sleep(CHECK_INTERVAL)

@app.route('/')
def healthcheck():
    return "Servidor activo y escaneando correos", 200

if __name__ == '__main__':
    # Iniciar el escaneo en segundo plano
    Thread(target=escaneo_constante, daemon=True).start()
    
    # Iniciar servidor web (para Render)
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))