import os
import subprocess
import asyncio
import requests
from flask import Flask, request
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters

# 🔐 Token y URL del webhook
TOKEN = "8470331129:AAHBJWD_p9m7TMMYPD2iaBZBHLzCLUFpHQw"
WEBHOOK_URL = "https://videodown-77kj.onrender.com"

# 📁 Directorio de descargas
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# 🚀 Inicialización de Flask y Telegram
app = Flask(__name__)
bot = Bot(token=TOKEN)
application = Application.builder().token(TOKEN).build()

# 📌 Comando /start
async def start(update: Update, context):
    await update.message.reply_text(
        "👋 ¡Hola! Soy tu bot descargador de videos.\n\n📥 Envíame un enlace de YouTube o similar y lo descargaré en calidad 480p.\n\nEscribe /help para ver todo lo que puedo hacer."
    )

# 🛠 Comando /help
async def help_command(update: Update, context):
    await update.message.reply_text(
        "🛠 Comandos disponibles:\n"
        "/start – Mensaje de bienvenida\n"
        "/help – Muestra esta ayuda\n"
        "/info – Información sobre el bot\n"
        "/formato – Explica el formato de descarga\n"
        "/estado – Verifica si el bot está activo\n"
        "/cancelar – Cancela la operación actual\n\n"
        "📌 Solo envíame un enlace de video para comenzar la descarga."
    )

# ℹ️ Comando /info
async def info(update: Update, context):
    await update.message.reply_text(
        "ℹ️ Este bot fue creado para ayudarte a descargar videos en calidad 480p usando yt-dlp.\n"
        "🔧 Desarrollado por Landitho con ❤️ y código abierto.\n"
        "🌐 Compatible con YouTube, Vimeo, Twitter y más."
    )

# 🎞️ Comando /formato
async def formato(update: Update, context):
    await update.message.reply_text(
        "🎞️ El bot descarga el video en el mejor formato disponible hasta 480p.\n"
        "Esto garantiza buena calidad sin consumir demasiado espacio.\n"
        "¿Quieres soporte para otras resoluciones o audio MP3? ¡Dímelo!"
    )

# ✅ Comando /estado
async def estado(update: Update, context):
    await update.message.reply_text("✅ El bot está activo y listo para descargar videos.")

# 🚫 Comando /cancelar
async def cancelar(update: Update, context):
    await update.message.reply_text("🚫 No hay ninguna operación activa que cancelar.")

# 📥 Manejo de mensajes con enlaces
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

        # 📦 Encuentra el archivo más reciente
        files = sorted(os.listdir(DOWNLOAD_DIR), key=lambda x: os.path.getmtime(os.path.join(DOWNLOAD_DIR, x)), reverse=True)
        latest_file = os.path.join(DOWNLOAD_DIR, files[0])

        # 📤 Envío del video
        with open(latest_file, "rb") as f:
            await update.message.reply_video(video=f)

        os.remove(latest_file)

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

# 🧠 Registro de handlers
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("help", help_command))
application.add_handler(CommandHandler("info", info))
application.add_handler(CommandHandler("formato", formato))
application.add_handler(CommandHandler("estado", estado))
application.add_handler(CommandHandler("cancelar", cancelar))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# 🔄 Endpoint del webhook
@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    asyncio.run(application.update_queue.put(update))
    return "OK"

# 🟢 Endpoint raíz
@app.route("/")
def index():
    return "Bot activo."

# 🔧 Registro del webhook en Telegram
def set_webhook():
    url = f"https://api.telegram.org/bot{TOKEN}/setWebhook"
    response = requests.post(url, data={"url": f"{WEBHOOK_URL}/{TOKEN}"})
    print("✅ Webhook registrado:", response.json())

# 🏁 Inicio del servidor
if __name__ == "__main__":
    set_webhook()
    port = int(os.environ.get("PORT", 10000))
    application.run_webhook(
        listen="0.0.0.0",
        port=port,
        webhook_url=f"{WEBHOOK_URL}/{TOKEN}"
    )