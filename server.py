from flask import Flask, jsonify
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

# Configuración Gmail (variables de entorno en Render)
GMAIL_EMAIL = "seendmessenger@gmail.com"
GMAIL_PASSWORD = "fzhtsyaoukqzhmtr"
IMAP_SERVER = "imap.gmail.com"
IMAP_PORT = 993
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

PART_SIZE = 15 * 1024 * 1024  # 15 MB

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("NautaRealtime")

def conectar_imap():
    """Conexión IMAP persistente con reintentos"""
    while True:
        try:
            mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
            mail.login(GMAIL_EMAIL, GMAIL_PASSWORD)
            mail.select("inbox")
            logger.info("✅ Conexión IMAP establecida")
            return mail
        except Exception as e:
            logger.error(f"❌ Error IMAP: {str(e)}. Reconectando en 10s...")
            time.sleep(10)

def procesar_correo(mail, msg_id):
    """Extrae el enlace de descarga del correo"""
    try:
        status, msg_data = mail.fetch(msg_id, "(RFC822)")
        raw_email = msg_data[0][1]
        email_msg = email.message_from_bytes(raw_email)

        if email_msg.is_multipart():
            for part in email_msg.walk():
                if part.get_content_type() == "text/plain":
                    cuerpo = part.get_payload(decode=True).decode()
                    if "http" in cuerpo:
                        return cuerpo.split()[-1].strip()
        return None
    except Exception as e:
        logger.error(f"❌ Error procesando correo: {str(e)}")
        return None

def descargar_y_enviar(enlace):
    """Descarga el archivo y envía partes divididas"""
    try:
        # Descargar archivo
        nombre_archivo = secure_filename(enlace.split('/')[-1].split('?')[0])
        ruta_archivo = f"/tmp/{nombre_archivo}"
        
        logger.info(f"⬇️ Descargando: {enlace}")
        with requests.get(enlace, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(ruta_archivo, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)

        # Dividir y enviar partes
        parte_num = 1
        with open(ruta_archivo, 'rb') as f:
            while chunk := f.read(PART_SIZE):
                parte_path = f"/tmp/{nombre_archivo}.part{parte_num}"
                with open(parte_path, 'wb') as pf:
                    pf.write(chunk)

                # Configurar correo
                msg = MIMEMultipart()
                msg['From'] = GMAIL_EMAIL
                msg['To'] = "miguelorlandos@nauta.cu"
                msg['Subject'] = f"[PART] {nombre_archivo} - parte{parte_num}"

                with open(parte_path, 'rb') as pf:
                    adjunto = MIMEApplication(pf.read(), _subtype="octet-stream")
                    adjunto.add_header('Content-Disposition', 'attachment', 
                                    filename=f"{nombre_archivo}.part{parte_num}")
                    msg.attach(adjunto)

                # Enviar via SMTP
                with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
                    server.starttls()
                    server.login(GMAIL_EMAIL, GMAIL_PASSWORD)
                    server.send_message(msg)

                logger.info(f"📤 Enviada parte {parte_num}")
                os.remove(parte_path)
                parte_num += 1

        os.remove(ruta_archivo)
        logger.info("🎉 ¡Archivo enviado completamente!")

    except Exception as e:
        logger.error(f"🔥 Error crítico: {str(e)}")

def escaneo_idle():
    """Bucle principal de escaneo en tiempo real"""
    mail = conectar_imap()
    try:
        while True:
            try:
                mail.send(b'IDLE\r\n')
                respuesta = mail.readline().decode()

                if "EXISTS" in respuesta:  # Nuevo correo
                    mail.send(b'DONE\r\n')
                    status, messages = mail.search(None, '(UNSEEN FROM "miguelorlandos@nauta.cu")')
                    if messages[0]:
                        for msg_id in messages[0].split():
                            if enlace := procesar_correo(mail, msg_id):
                                Thread(target=descargar_y_enviar, args=(enlace,)).start()

                elif "BYE" in respuesta:  # Conexión cerrada
                    raise ConnectionError("Servidor IMAP cerró la conexión")

            except (ConnectionError, imaplib.IMAP4.abort) as e:
                logger.warning(f"⚡ Reconectando: {str(e)}")
                mail = conectar_imap()
            except Exception as e:
                logger.error(f"⚠️ Error en IDLE: {str(e)}")
                time.sleep(5)

    finally:
        try:
            mail.logout()
        except:
            pass

@app.route('/')
def healthcheck():
    return jsonify({
        "status": "active",
        "service": "Nauta Transfer",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    }), 200

if __name__ == '__main__':
    # Iniciar escaneo en segundo plano
    Thread(target=escaneo_idle, daemon=True).start()
    
    # Iniciar servidor Flask
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 10000)))