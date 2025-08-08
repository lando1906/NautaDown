from flask import Flask, request, jsonify
import smtplib
import os
import requests
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from werkzeug.utils import secure_filename
from threading import Thread
import logging
from datetime import datetime

app = Flask(__name__)

# Configuración (usa variables de entorno en Render)
GMAIL_EMAIL = "seendmessenger@gmail.com"  # Ej: miguelorlandos97@gmail.com
GMAIL_PASSWORD = "fzhtsyaoukqzhmtr"  # App Password con 2FA
NAUTA_EMAIL = "miguelorlandos@nauta.cu"  # Ej: tuusuario@nauta.cu
PART_SIZE = 15 * 1024 * 1024  # 15 MB
ALLOWED_EXTENSIONS = {'zip', 'apk', 'rar', '7z', 'pdf', 'mp4'}  # Formatos permitidos

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("NautaTransfer")

def dividir_archivo(ruta_archivo):
    """Divide el archivo en partes de 15MB."""
    partes = []
    with open(ruta_archivo, 'rb') as f:
        parte_num = 1
        while True:
            chunk = f.read(PART_SIZE)
            if not chunk:
                break
            nombre_parte = f"{ruta_archivo}.part{parte_num}"
            with open(nombre_parte, 'wb') as parte:
                parte.write(chunk)
            partes.append(nombre_parte)
            parte_num += 1
    return partes

def enviar_parte(ruta_parte, nombre_original):
    """Envía una parte por correo a Nauta."""
    msg = MIMEMultipart()
    msg['From'] = GMAIL_EMAIL
    msg['To'] = NAUTA_EMAIL
    msg['Subject'] = f"[PART] {nombre_original} - {os.path.basename(ruta_parte)}"

    with open(ruta_parte, 'rb') as f:
        adjunto = MIMEApplication(f.read(), _subtype="octet-stream")
        adjunto.add_header('Content-Disposition', 'attachment', 
                          filename=os.path.basename(ruta_parte))
        msg.attach(adjunto)

    with smtplib.SMTP('smtp.gmail.com', 587) as server:
        server.starttls()
        server.login(GMAIL_EMAIL, GMAIL_PASSWORD)
        server.send_message(msg)
    logger.info(f"Parte enviada: {ruta_parte}")

def procesar_enlace(enlace):
    """Descarga, divide y envía el archivo en segundo plano."""
    try:
        # Descargar archivo
        nombre_archivo = secure_filename(enlace.split('/')[-1].split('?')[0])
        ruta_archivo = os.path.join('/tmp', nombre_archivo)
        
        logger.info(f"Descargando: {enlace}")
        response = requests.get(enlace, stream=True)
        with open(ruta_archivo, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        # Dividir y enviar
        tamanio = os.path.getsize(ruta_archivo)
        if tamanio > PART_SIZE:
            partes = dividir_archivo(ruta_archivo)
            for parte in partes:
                enviar_parte(parte, nombre_archivo)
                os.remove(parte)
        else:
            enviar_parte(ruta_archivo, nombre_archivo)
        
        os.remove(ruta_archivo)
        logger.info("Proceso completado ✅")

    except Exception as e:
        logger.error(f"Error: {str(e)}")

@app.route('/procesar', methods=['POST'])
def manejar_peticion():
    """Endpoint para recibir enlaces desde Termux."""
    data = request.json
    if not data or 'enlace' not in data:
        return jsonify({"error": "Se requiere 'enlace'"}), 400

    # Iniciar proceso en segundo plano
    Thread(target=procesar_enlace, args=(data['enlace'],)).start()
    return jsonify({"status": "Procesando archivo..."})

@app.route('/healthcheck', methods=['GET'])
def healthcheck():
    """Endpoint para verificar que el servidor está activo."""
    return jsonify({"status": "OK", "timestamp": str(datetime.utcnow())})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)￼Enter
