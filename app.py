import os
import subprocess
from flask import Flask, request
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters

# 🔐 Token embebido directamente
TOKEN = "8470331129:AAHBJWD_p9m7TMMYPD2iaBZBHLzCLUFpHQw"
WEBHOOK_URL = "https://videodown-77kj.onrender.com/"

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

app = Flask(__name__)
bot = Bot(token=TOKEN)

application = Application.builder().token(TOKEN).build()

async def start(update: Update, context):
    await update.message.reply_text("🎬 Envíame un enlace de video y lo descargaré en calidad 480p.")

async def handle_message(update: Update, context):
    url = update.message.text.strip()
    await update.message.reply_text("⏳ Descargando video en 480p...")

    try:
        output_template = os.path.join(DOWNLOAD_DIR, "%(title)s.%(ext)s")
        cmd = [
            "yt-dlp",
            "-f", "best[height<=480]",
            "-o", output_template,
            url
        ]
        subprocess.run(cmd, check=True)

        # Encuentra el archivo más reciente
        files = sorted(os.listdir(DOWNLOAD_DIR), key=lambda x: os.path.getmtime(os.path.join(DOWNLOAD_DIR, x)), reverse=True)
        latest_file = os.path.join(DOWNLOAD_DIR, files[0])

        # Envíalo como video
        with open(latest_file, "rb") as f:
            await update.message.reply_video(video=f)

        os.remove(latest_file)

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    application.update_queue.put(update)
    return "OK"

@app.route("/")
def index():
    return "Bot activo."

if __name__ == "__main__":
    application.run_webhook(
        listen="0.0.0.0",
        port=10000,
        webhook_url=f"{WEBHOOK_URL}/{TOKEN}"
    )