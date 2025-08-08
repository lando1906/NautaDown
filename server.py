import imaplib
import email
from email.utils import parsedate_to_datetime
from flask import Flask, jsonify
import threading
import time
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
import os
from dotenv import load_dotenv
import logging

# Configuración inicial
load_dotenv()  # Carga variables de entorno desde .env

app = Flask(__name__)

# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuración del correo desde variables de entorno
EMAIL = "seendmessenger@gmail.com"
PASSWORD = "fzhtsyaoukqzhmtr"
IMAP_SERVER = "imap.gmail.com"
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = "587"
RESPONSE_TEXT = "¡Hola! Gracias por tu mensaje. Estoy online y te responderé pronto."

# Variable para almacenar el estado
status = {
    'running': True,
    'last_check': None,
    'total_messages': 0,
    'responded_messages': 0,
    'last_error': None
}

def send_auto_reply(to_email):
    try:
        msg = MIMEText(RESPONSE_TEXT)
        msg['Subject'] = 'Respuesta Automática'
        msg['From'] = EMAIL
        msg['To'] = to_email
        
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL, PASSWORD)
            server.send_message(msg)
        
        logger.info(f"Respuesta automática enviada a {to_email}")
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
            
            with imaplib.IMAP4_SSL(IMAP_SERVER) as mail:
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
                            
                            if email_msg.is_multipart():
                                for part in email_msg.walk():
                                    content_type = part.get_content_type()
                                    content_disposition = str(part.get("Content-Disposition"))
                                    if content_type == "text/plain" and "attachment" not in content_disposition:
                                        body = part.get_payload(decode=True).decode(errors='ignore')
                                        break
                            else:
                                body = email_msg.get_payload(decode=True).decode(errors='ignore')
                            
                            # Verificar si el mensaje contiene "Hola" (case insensitive)
                            if any(keyword in body.lower() or keyword in subject.lower() 
                                  for keyword in ['hola', 'hello', 'hi']):
                                logger.info(f"Mensaje con 'Hola' detectado de {from_email}")
                                if send_auto_reply(from_email):
                                    # Marcar como leído
                                    mail.uid('store', e_uid, '+FLAGS', '\\Seen')
                
                mail.close()
                mail.logout()
                
        except Exception as e:
            error_msg = f"Error al comprobar correos: {str(e)}"
            logger.error(error_msg)
            status['last_error'] = error_msg
        
        # Esperar 30 segundos antes de la próxima comprobación
        time.sleep(30)

@app.route('/')
def index():
    return jsonify({
        'status': 'running' if status['running'] else 'stopped',
        'last_check': status['last_check'],
        'total_messages_processed': status['total_messages'],
        'auto_replies_sent': status['responded_messages'],
        'last_error': status['last_error'],
        'service': 'Email Auto-Responder',
        'version': '1.0'
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

def run_server():
    # Iniciar el monitoreo en un hilo separado
    monitor_thread = threading.Thread(target=check_emails, daemon=True)
    monitor_thread.start()
    
    # Iniciar el servidor Flask
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)), debug=os.getenv('DEBUG', 'false').lower() == 'true')

if __name__ == '__main__':
    run_server()