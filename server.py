import imaplib
import email
from email.utils import parsedate_to_datetime
from flask import Flask, jsonify, request, send_file
import threading
import time
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from dotenv import load_dotenv
import logging
import requests
from io import BytesIO
import urllib.parse

# Configuración inicial
load_dotenv()  # Carga variables de entorno desde .env

app = Flask(__name__)

# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuración para Nauta
EMAIL = os.getenv("NAUTA_EMAIL", "davidacosta05@nauta.com.cu")  # Usar formato usuario@nauta.com.cu
PASSWORD = os.getenv("NAUTA_PASSWORD", "David@05")
IMAP_SERVER = "imap.nauta.cu"
IMAP_PORT = 143  # Puerto IMAP estándar
SMTP_SERVER = "smtp.nauta.cu"
SMTP_PORT = 25   # Puerto SMTP estándar
USE_SSL = False  # Nauta normalmente no usa SSL en estos puertos
RESPONSE_TEXT = "¡Hola! Gracias por tu mensaje. Estoy online y te responderé pronto."

# Variable para almacenar el estado
status = {
    'running': True,
    'last_check': None,
    'total_messages': 0,
    'responded_messages': 0,
    'last_error': None
}

def download_file(url):
    try:
        response = requests.get(url, stream=True)
        if response.status_code == 200:
            # Obtener el nombre del archivo de la URL o de los headers
            filename = os.path.basename(urllib.parse.urlparse(url).path)
            if not filename:
                content_disposition = response.headers.get('content-disposition')
                if content_disposition:
                    filename = content_disposition.split('filename=')[1].strip('"\'')
                else:
                    filename = 'downloaded_file'
            
            file_data = BytesIO()
            for chunk in response.iter_content(1024):
                file_data.write(chunk)
            file_data.seek(0)
            
            return file_data, filename
        else:
            return None, None
    except Exception as e:
        logger.error(f"Error al descargar archivo: {str(e)}")
        return None, None

def send_auto_reply(to_email, attachment_data=None, attachment_filename=None):
    try:
        if attachment_data:
            msg = MIMEMultipart()
            msg['Subject'] = 'Archivo solicitado'
            msg['From'] = EMAIL
            msg['To'] = to_email
            
            msg.attach(MIMEText("Aquí está el archivo que solicitaste."))
            
            attachment = MIMEText(attachment_data.getvalue())
            attachment.add_header('Content-Disposition', 'attachment', filename=attachment_filename)
            msg.attach(attachment)
        else:
            msg = MIMEText(RESPONSE_TEXT)
            msg['Subject'] = 'Respuesta Automática'
            msg['From'] = EMAIL
            msg['To'] = to_email

        # Conexión SMTP adaptada para Nauta
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            if not USE_SSL:
                server.starttls()  # Usar STARTTLS para seguridad
            server.login(EMAIL, PASSWORD)
            server.send_message(msg)

        logger.info(f"Respuesta enviada a {to_email}")
        status['responded_messages'] += 1
        return True
    except Exception as e:
        error_msg = f"Error al enviar respuesta a {to_email}: {str(e)}"
        logger.error(error_msg)
        status['last_error'] = error_msg
        return False

def check_emails():
    while status['running']:
        try:
            logger.info("Comprobando correos...")
            status['last_check'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            status['last_error'] = None

            # Conexión IMAP adaptada para Nauta
            if USE_SSL:
                mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
            else:
                mail = imaplib.IMAP4(IMAP_SERVER, IMAP_PORT)
                
            mail.login(EMAIL, PASSWORD)
            mail.select('inbox')

            # Buscar correos no leídos en las últimas 2 horas
            since_date = (datetime.now() - timedelta(hours=2)).strftime("%d-%b-%Y")
            result, data = mail.uid('search', None, f'(UNSEEN SINCE "{since_date}")')

            if result == 'OK' and data[0]:
                email_uids = data[0].split()
                status['total_messages'] += len(email_uids)

                for e_uid in email_uids:
                    result, msg_data = mail.uid('fetch', e_uid, '(RFC822)')
                    if result == 'OK':
                        email_msg = email.message_from_bytes(msg_data[0][1])
                        from_email = email.utils.parseaddr(email_msg['From'])[1]
                        subject = email_msg['Subject'] or ""
                        body = ""

                        # Extraer solo el texto plano ignorando adjuntos
                        if email_msg.is_multipart():
                            for part in email_msg.walk():
                                content_type = part.get_content_type()
                                content_disposition = str(part.get("Content-Disposition"))
                                if content_type == "text/plain" and "attachment" not in content_disposition:
                                    body = part.get_payload(decode=True).decode(errors='ignore')
                                    break
                        else:
                            if "attachment" not in str(email_msg.get("Content-Disposition", "")):
                                body = email_msg.get_payload(decode=True).decode(errors='ignore')

                        # Procesar comando /dw
                        if body and '/dw' in body.lower():
                            logger.info(f"Comando /dw detectado de {from_email}")
                            lines = body.split('\n')
                            url = None
                            for line in lines:
                                if '/dw' in line.lower():
                                    parts = line.split()
                                    for i, part in enumerate(parts):
                                        if part.lower() == '/dw' and i+1 < len(parts):
                                            next_part = parts[i+1]
                                            if next_part.lower().startswith(('http://', 'https://')):
                                                url = next_part
                                                break
                                    if url:
                                        break
                            
                            if url:
                                logger.info(f"Descargando archivo desde: {url}")
                                file_data, filename = download_file(url)
                                if file_data:
                                    if send_auto_reply(from_email, file_data, filename):
                                        mail.uid('store', e_uid, '+FLAGS', '\\Seen')
                                else:
                                    send_auto_reply(from_email, MIMEText(f"No se pudo descargar el archivo de {url}"))
                                    logger.error(f"Error al descargar {url}")
                            else:
                                send_auto_reply(from_email, MIMEText("Formato incorrecto. Usa: /dw [URL]"))
                                logger.error("URL no encontrada después de /dw")

                        # Respuesta automática para saludos
                        elif body and any(keyword in body.lower() or keyword in subject.lower() 
                                      for keyword in ['hola', 'hello', 'hi']):
                            logger.info(f"Saludo detectado de {from_email}")
                            if send_auto_reply(from_email):
                                mail.uid('store', e_uid, '+FLAGS', '\\Seen')

            mail.close()
            mail.logout()

        except Exception as e:
            error_msg = f"Error al comprobar correos: {str(e)}"
            logger.error(error_msg)
            status['last_error'] = error_msg

        time.sleep(30)  # Esperar 30 segundos entre verificaciones

@app.route('/')
def index():
    return jsonify({
        'status': 'running' if status['running'] else 'stopped',
        'last_check': status['last_check'],
        'total_messages_processed': status['total_messages'],
        'auto_replies_sent': status['responded_messages'],
        'last_error': status['last_error'],
        'service': 'Email Auto-Responder para Nauta',
        'version': '2.0'
    })

@app.route('/start')
def start_monitoring():
    if not status['running']:
        status['running'] = True
        threading.Thread(target=check_emails, daemon=True).start()
    return jsonify({'status': 'Monitoring started'})

@app.route('/stop')
def stop_monitoring():
    status['running'] = False
    return jsonify({'status': 'Monitoring stopped'})

@app.route('/dw', methods=['GET'])
def download_via_web():
    url = request.args.get('url')
    if not url:
        return jsonify({'error': 'Parámetro URL requerido'}), 400
    
    file_data, filename = download_file(url)
    if file_data:
        return send_file(
            file_data,
            as_attachment=True,
            download_name=filename,
            mimetype='application/octet-stream'
        )
    else:
        return jsonify({'error': 'Descarga fallida'}), 500

def run_server():
    monitor_thread = threading.Thread(target=check_emails, daemon=True)
    monitor_thread.start()
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))

if __name__ == '__main__':
    run_server()