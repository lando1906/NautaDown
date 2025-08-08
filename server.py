from flask import Flask
import imaplib
import email
import smtplib
import os
import subprocess
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.mime.text import MIMEText
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
CHECK_INTERVAL = 1  # Segundos entre escaneos

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("NautaTransfer")

def buscar_correos_para_responder():
    """Busca correos no leídos de smorlando19@nauta.cu o miguelorlandos@nauta.cu"""
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        mail.login(GMAIL_EMAIL, GMAIL_PASSWORD)
        mail.select("inbox")

        # Buscar correos no leídos de cualquiera de los dos remitentes
        status, messages = mail.search(None, '(UNSEEN (OR FROM "smorlando19@nauta.cu" FROM "miguelorlandos@nauta.cu"))')
        if not messages[0]:
            logger.info("No se encontraron correos no leídos")
            mail.close()
            mail.logout()
            return []

        correos = []
        for msg_id in messages[0].split():
            status, msg_data = mail.fetch(msg_id, "(RFC822)")
            raw_email = msg_data[0][1]
            email_msg = email.message_from_bytes(raw_email)
            from_email = email.utils.parseaddr(email_msg['From'])[1]

            # Determinar el tipo de respuesta necesario
            if from_email == "smorlando19@nauta.cu":
                correos.append((email_msg, "hola"))
            elif from_email == "miguelorlandos@nauta.cu":
                # Buscar enlaces solo en correos de miguelorlandos
                enlace = None
                if email_msg.is_multipart():
                    for part in email_msg.walk():
                        if part.get_content_type() == "text/plain":
                            try:
                                cuerpo = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                                urls = re.findall(r'https?://[^\s<>"]+|www\.[^\s<>"]+', cuerpo)
                                if urls:
                                    enlace = urls[0]
                                    break
                            except Exception as e:
                                logger.error(f"Error al procesar el cuerpo del correo {msg_id}: {str(e)}")
                if enlace:
                    correos.append((email_msg, "enlace", enlace))

        mail.close()
        mail.logout()
        return correos

    except Exception as e:
        logger.error(f"Error al escanear Gmail: {str(e)}")
        return []

def responder_con_hola(email_original):
    """Responde al correo con un simple 'Hola'"""
    try:
        msg = MIMEMultipart()
        msg['From'] = GMAIL_EMAIL
        msg['To'] = email_original['From']
        msg['Subject'] = f"Re: {email_original['Subject']}" if 'Subject' in email_original else "Hola"
        
        # Mantener el hilo de conversación
        if 'Message-ID' in email_original:
            msg['In-Reply-To'] = email_original['Message-ID']
            msg['References'] = email_original['Message-ID']
        
        msg.attach(MIMEText("Hola", 'plain'))

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=10) as server:
            server.starttls()
            server.login(GMAIL_EMAIL, GMAIL_PASSWORD)
            server.send_message(msg)

        logger.info(f"Respondido con 'Hola' a {email_original['From']}")

    except Exception as e:
        logger.error(f"Error al responder con 'Hola': {str(e)}")

def descargar_y_enviar_archivo(email_original, enlace):
    """Descarga el archivo usando curl y lo envía como respuesta al correo original"""
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

        # Crear mensaje de respuesta
        msg = MIMEMultipart()
        msg['From'] = GMAIL_EMAIL
        msg['To'] = email_original['From']
        msg['Subject'] = f"Re: {email_original['Subject']}" if 'Subject' in email_original else "Archivo solicitado"
        
        # Añadir referencia al mensaje original
        if 'Message-ID' in email_original:
            msg['In-Reply-To'] = email_original['Message-ID']
            msg['References'] = email_original['Message-ID']
        
        # Añadir texto al correo
        texto = f"Adjunto el archivo solicitado: {nombre_archivo}"
        if len(partes) > 1:
            texto = f"Adjunto las partes del archivo solicitado: {nombre_archivo} (partes {len(partes)})"
        
        msg.attach(MIMEText(texto, 'plain'))

        # Adjuntar archivo(s)
        for parte in partes:
            with open(parte, 'rb') as f:
                adjunto = MIMEApplication(f.read(), _subtype="octet-stream")
                adjunto.add_header('Content-Disposition', 'attachment', filename=os.path.basename(parte))
                msg.attach(adjunto)

        # Enviar correo
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=10) as server:
            server.starttls()
            server.login(GMAIL_EMAIL, GMAIL_PASSWORD)
            server.send_message(msg)

        logger.info(f"Archivo enviado como respuesta al correo original")
        
        # Eliminar archivos temporales
        for parte in partes:
            if os.path.exists(parte):
                os.remove(parte)

        logger.info("¡Proceso completado con éxito!")

    except Exception as e:
        logger.error(f"Error al procesar el archivo: {str(e)}")
        if os.path.exists(ruta_archivo):
            os.remove(ruta_archivo)

def escaneo_constante():
    """Bucle infinito para escanear cada CHECK_INTERVAL segundos"""
    while True:
        try:
            correos = buscar_correos_para_responder()
            for correo in correos:
                if correo[1] == "hola":
                    responder_con_hola(correo[0])
                elif correo[1] == "enlace":
                    descargar_y_enviar_archivo(correo[0], correo[2])
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