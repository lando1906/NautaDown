import os
import json
import subprocess
from deltachat import Account
import qrcode

# Cargar configuración
with open("config.json") as f:
    config = json.load(f)

db_path = config["db_path"]
max_quality = config["max_quality"]
download_dir = config["download_dir"]

os.makedirs(download_dir, exist_ok=True)
account = Account(db_path)

def is_video_url(text):
    return any(domain in text for domain in ["youtube.com", "youtu.be", "vimeo.com"])

def download_video(url):
    output_template = os.path.join(download_dir, "%(title)s.%(ext)s")
    cmd = [
        "yt-dlp",
        "-f", f"bestvideo[height<=?{max_quality}]+bestaudio/best[height<=?{max_quality}]",
        "-o", output_template,
        url
    ]
    subprocess.run(cmd, check=True)
    files = sorted(os.listdir(download_dir), key=lambda x: os.path.getmtime(os.path.join(download_dir, x)), reverse=True)
    return os.path.join(download_dir, files[0]) if files else None

def handle_events():
    events = account.get_events()
    for event in events:
        if event["type"] == "message":
            chat_id = event["chat_id"]
            text = event["text"]
            if is_video_url(text):
                try:
                    account.send_message(chat_id, "⏳ Descargando video en 720p...")
                    video_path = download_video(text)
                    if video_path:
                        account.send_file(chat_id, video_path)
                        account.send_message(chat_id, "✅ Video enviado.")
                    else:
                        account.send_message(chat_id, "⚠️ No se encontró el archivo.")
                except Exception as e:
                    account.send_message(chat_id, f"❌ Error: {str(e)}")
            else:
                account.send_message(chat_id, "📎 Envíame un enlace de video para descargarlo en 720p.")

def generate_qr():
    uri = account.get_qr()
    img = qrcode.make(uri)
    path = os.path.join("static", "qr.png")
    img.save(path)
    return path