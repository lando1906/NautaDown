from flask import Flask
import imaplib
import email
import smtplib
import os
import subprocess
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from threading import Thread
import time
import logging
from werkzeug.utils import secure_filename
import re

app = Flask(__name__)

# Configuración Gmail (lectura IMAP + envío SMTP)
GMAIL_EMAIL = os.getenv("GMAIL_EMAIL", "seendmessenger@gmail.com")
GMAIL_PASSWORD = os.getenv("GMAIL_PASSWORD", "fzhtsyaoukqzhmtr")
IMAP_SERVER = "imap.gmail.com"
IMAP_PORT = 993
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
PART_SIZE = 15 * 1024 * 1024  # 15 MB por parte
CHECK_INTERVAL = 10  # Segundos entre escaneos

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("NautaTransfer")

def buscar_enlaces_en_gmail():
    """Busca correos no leídos de miguelorlandos@nauta.cu y extrae enlaces"""
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        mail.login(GMAIL_EMAIL, GMAIL_PASSWORD)
        mail.select("inbox")

        status, messages = mail.search(None, '(UNSEEN FROM "miguelorlandos@nauta.cu")')
        if not messages[0]:
            logger.info("No se encontraron correos no leídos")
            mail.close()
            mail.logout()
            return None

        enlaces = []
        for msg_id in messages[0].split():
            status, msg_data = mail.fetch(msg_id, "(RFC822)")
            raw_email = msg_data[0][1]
            email_msg = email.message_from_bytes(raw_email)

            if email_msg.is_multipart():
                for part in email_msg.walk():
                    if part.get_content_type() == "text/plain":
                        try:
                            cuerpo = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                            urls = re.findall(r'https?://[^\s<>"]+|www\.[^\s<>"]+', cuerpo)
                            if urls:
                                enlaces.append(urls[0])
                                break
                        except Exception as e:
                            logger.error(f"Error al procesar el cuerpo del correo {msg_id}: {str(e)}")

        mail.close()
        mail.logout()
        return enlaces[0] if enlaces else None

    except Exception as e:
        logger.error(f"Error al escanear Gmail: {str(e)}")
        return None

def descargar_y_enviar_archivo(enlace):
    """Descarga el archivo usando curl y lo envía (o sus partes) a miguelorlandos@nauta.cu"""
    try:
        # Validar enlace
        if not re.match(r'https?://[^\s<>"]+|www\.[^\s<>"]+', enlace):
            logger.error(f"Enlace inválido: {enlace}")
            return

        # Generar nombre del archivo
        nombre_archivo = secure_filename(enlace.split('/')[-1].split('?')[0])
        ruta_archivo = f"/tmp/{nombre_archivo}"

        # Descargar archivo usando curl
        logger.info(f"Descargando archivo con curl: {enlace}")
        try:
            result = subprocess.run(
                ['curl', '-L', '-o', ruta_archivo, enlace],
                capture_output=True, text=True, timeout=60
            )
            if result.returncode != 0:
                logger.error(f"Error al descargar con curl: {result.stderr}")
                return
        except subprocess.TimeoutExpired:
            logger.error(f"Timeout al descargar el archivo: {enlace}")
            return
        except Exception as e:
            logger.error(f"Error al ejecutar curl: {str(e)}")
            return

        # Verificar que el archivo se descargó correctamente
        if not os.path.exists(ruta_archivo):
            logger.error(f"El archivo no se descargó: {ruta_archivo}")
            return

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
            try:
                msg = MIMEMultipart()
                msg['From'] = GMAIL_EMAIL
                msg['To'] = "miguelorlandos@nauta.cu"
                msg['Subject'] = f"Archivo: {nombre_archivo} - Parte {partes.index(parte) + 1}" if len(partes) > 1 else f"Archivo: {nombre_archivo}"

                with open(parte, 'rb') as f:
                    adjunto = MIMEApplication(f.read(), _subtype="octet-stream")
                    adjunto.add_header('Content-Disposition', 'attachment', filename=os.path.basename(parte))
                    msg.attach(adjunto)

                with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=10) as server:
                    server.starttls()
                    server.login(GMAIL_EMAIL, GMAIL_PASSWORD)
                    server.send_message(msg)

                logger.info(f"Enviada parte: {os.path.basename(parte)}")
                os.remove(parte)

            except Exception as e:
                logger.error(f"Error al enviar parte {os.path.basename(parte)}: {str(e)}")
                continue

        logger.info("¡Proceso completado con éxito!")

    except Exception as e:
        logger.error(f"Error al procesar el archivo: {str(e)}")
        if os.path.exists(ruta_archivo):
            os.remove(ruta_archivo)

def escaneo_constante():
    """Bucle infinito para escanear cada CHECK_INTERVAL segundos"""
    while True:
        try:
            enlace = buscar_enlaces_en_gmail()
            if enlace:
                logger.info(f"Enlace detectado: {enlace}")
                descargar_y_enviar_archivo(enlace)
            else:
                logger.debug("No se encontraron enlaces")
        except Exception as e:
            logger.error(f"Error en el bucle de escaneo: {str(e)}")
        time.sleep(CHECK_INTERVAL)

@app.route('/')
def healthcheck():
    return "Servidor activo y escaneando correos", 200

if __name__ == '__main__':
    # Verificar variables de entorno
    if not GMAIL_EMAIL or not GMAIL_PASSWORD:
        logger.error("Faltan variables de entorno GMAIL_EMAIL o GMAIL_PASSWORD")
        exit(1)

    # Verificar que curl esté instalado
    try:
        subprocess.run(['curl', '--version'], capture_output=True, check=True)
        logger.info("curl está instalado y disponible")
    except Exception as e:
        logger.error(f"curl no está instalado o no es accesible: {str(e)}")
        exit(1)

    # Iniciar el escaneo en segundo plano
    Thread(target=escaneo_constante, daemon=True).start()

    # Iniciar servidor web (para Render)
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))