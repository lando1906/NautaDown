import os
import re
import tempfile
import logging
import traceback
from flask import Flask, request
import requests
import yt_dlp

# Configuración
TELEGRAM_TOKEN = "8470331129:AAHBJWD_p9m7TMMYPD2iaBZBHLzCLUFpHQw"
BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
WEBHOOK_URL = "https://videodown-77kj.onrender.com"

MAX_UPLOAD_MB = 48
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024

app = Flask(__name__)

# Configuración de logging
logging.basicConfig(
    format='[%(asctime)s] %(levelname)s: %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def send_message(chat_id, text, reply_to=None):
    url = f"{BASE_URL}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }
    if reply_to:
        payload['reply_to_message_id'] = reply_to
    response = requests.post(url, json=payload)
    if not response.ok:
        logger.error(f"Error enviando mensaje: {response.text}")

def send_document(chat_id, file_path, filename, caption="", reply_to=None):
    url = f"{BASE_URL}/sendDocument"
    with open(file_path, "rb") as f:
        files = {"document": (filename, f)}
        data = {
            "chat_id": chat_id,
            "caption": caption
        }
        if reply_to:
            data['reply_to_message_id'] = reply_to
        response = requests.post(url, data=data, files=files)
    if not response.ok:
        logger.error(f"Error enviando documento: {response.text}")

def is_valid_url(text):
    url_regex = re.compile(r'^https?://.+$')
    return url_regex.match(text.strip())

def download_with_ytdlp(url, download_dir):
    ydl_opts = {
        'outtmpl': os.path.join(download_dir, '%(title).40s.%(ext)s'),
        'format': 'mp4/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best/best',
        'noplaylist': True,
        'max_filesize': MAX_UPLOAD_BYTES,
        'retries': 2,
        'nocheckcertificate': True,
        'quiet': True,
        'no_warnings': True
    }
    result = {}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
        
        if 'requested_downloads' in info and info['requested_downloads']:
            result['download_path'] = info['requested_downloads'][0]['filepath']
        elif '_filename' in info:
            result['download_path'] = info['_filename']
        else:
            raise Exception("No se pudo determinar el archivo descargado")

        result['title'] = info.get('title', "descarga")
        result['ext'] = os.path.splitext(result['download_path'])[1][1:]
        result['size'] = os.path.getsize(result['download_path'])
        return result
    except yt_dlp.utils.DownloadError as e:
        logger.warning(f'yt-dlp error: {str(e)}')
        raise Exception("No fue posible descargar el video con yt-dlp.")
    except Exception as e:
        logger.error(traceback.format_exc())
        raise

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        update = request.get_json(force=True)
        logger.info(f"Update recibido: {update}")
        
        if "message" in update:
            message = update["message"]
            chat_id = message["chat"]["id"]
            message_id = message["message_id"]
            text = message.get("text", "")

            if "entities" in message and message["entities"][0].get("type") == "bot_command":
                command = text.split()[0].lower()
                if command == "/start":
                    send_message(chat_id, (
                        "👋 ¡Hola! Soy un bot para descargar videos de casi cualquier plataforma.\n"
                        "Envíame cualquier URL de video soportada y te lo enviaré de vuelta como archivo (máx. 48MB).\n\n"
                        "⏳ Procesa un link por vez, espera confirmación antes de enviar otro.\n"
                        "Usa /help para obtener más información."
                    ), reply_to=message_id)
                elif command == "/help":
                    send_message(chat_id, (
                        "ℹ️ <b>Instrucciones</b>:\n"
                        "1. Envía una URL de video (YouTube, Vimeo, Twitter, TikTok, etc.).\n"
                        f"2. El video debe pesar menos de {MAX_UPLOAD_MB} MB.\n"
                        "3. Si falla, revisa la compatibilidad en https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md\n\n"
                        "⚠️ Ten en cuenta los límites de Telegram y Render (archivos grandes serán rechazados)."
                    ), reply_to=message_id)
                else:
                    send_message(chat_id, "Comando no reconocido. Usa /help.", reply_to=message_id)
                return "ok"

            if is_valid_url(text):
                send_message(chat_id, "⏳ Descargando video, por favor espera...", reply_to=message_id)
                with tempfile.TemporaryDirectory() as tmpdir:
                    try:
                        info = download_with_ytdlp(text, tmpdir)
                        if info['size'] >= MAX_UPLOAD_BYTES:
                            send_message(chat_id,
                                f"⚠️ Archivo demasiado grande para Telegram (> {MAX_UPLOAD_MB} MB).", reply_to=message_id)
                            return "ok"
                        caption = f"🎬 {info['title']}.{info['ext']} (descargado por bot)"
                        send_document(chat_id, info['download_path'], os.path.basename(info['download_path']),
                                      caption=caption, reply_to=message_id)
                    except Exception as e:
                        logger.error(f"Error descargando video: {e}")
                        send_message(chat_id,
                            f"❌ Error procesando la URL: {str(e)}.\n\n¿La URL requiere login o tiene DRM? Prueba con otro video.",
                            reply_to=message_id)
                return "ok"
                
            send_message(chat_id, 
                "🤖 Solo acepto URLs de video. Usa /help para instrucciones.", reply_to=message_id)
            return "ok"
        else:
            logger.warning("Update ignorado (no es tipo mensaje)")
            return "ok"
    except Exception as ex:
        logger.error(f"Error global en webhook: {traceback.format_exc()}")
        return "ok"

@app.route('/setwebhook', methods=['GET', 'POST'])
def set_webhook():
    if not WEBHOOK_URL:
        return "Define la URL del webhook", 400
    setwebhook_url = f"{BASE_URL}/setWebhook"
    target_url = f"{WEBHOOK_URL}/webhook"
    response = requests.post(setwebhook_url, json={'url': target_url})
    if response.ok:
        return "Webhook activado correctamente"
    else:
        logger.error(f"Respuesta Telegram setWebhook: {response.text}")
        return f"Error activando webhook: {response.text}", 500

@app.route("/", methods=["GET"])
def healthcheck():
    return "Bot online", 200

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=10000, debug=True)