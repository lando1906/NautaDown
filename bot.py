import os
import time
import logging
import asyncio
import aria2p
from telegram import Update, Bot
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from telegram.error import TelegramError

# 📁 Configuración
TOKEN = "7011073342:AAFvvoKngrMkFWGXQLgmtKRTcZrc48suP20"
UPLOAD_FOLDER = "files"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# 🧠 Logger
logging.basicConfig(filename="bot_errors.log", level=logging.ERROR)

def log_error(e):
    logging.error(f"{type(e).__name__}: {str(e)}")

# ⚙️ Aria2p
aria2 = aria2p.API(
    aria2p.Client(host="http://localhost", port=6800, secret="")
)

# 📡 Descarga desde enlace con barra de progreso
async def download_url_with_progress(url, update):
    filename = url.split("/")[-1].split("?")[0] or f"file_{int(time.time())}"
    path = os.path.join(UPLOAD_FOLDER, filename)

    try:
        download = aria2.add_uris([url], options={"dir": UPLOAD_FOLDER, "out": filename})
        msg = await update.message.reply_text("📡 Iniciando descarga...")
        start = time.time()

        while not download.is_complete:
            percent = int(download.completed_length) * 100 // int(download.total_length or 1)
            speed = int(download.download_speed or 1)
            eta = (int(download.total_length) - int(download.completed_length)) / speed if speed > 0 else 0
            bar = "█" * (percent // 10) + "░" * (10 - percent // 10)

            text = f"📡 Descargando:\n[{bar}] {percent}%\n⏳ ETA: {int(eta)}s"
            await msg.edit_text(text)
            await asyncio.sleep(1)

        await msg.edit_text("✅ Descarga completada.")
        return filename

    except Exception as e:
        log_error(e)
        await update.message.reply_text("❌ Error al descargar el archivo.")
        return None

# 📤 Enviar archivo al chat con barra de subida
async def send_file_with_progress(bot: Bot, chat_id: int, path: str):
    try:
        file_size = os.path.getsize(path)
        start = time.time()
        msg = await bot.send_message(chat_id, "📤 Subiendo al chat...")

        last_percent = -1

        def progress(current, total):
            nonlocal last_percent
            percent = current * 100 // total
            if percent != last_percent:
                last_percent = percent
                bar = "█" * (percent // 10) + "░" * (10 - percent // 10)
                eta = (total - current) / (current / (time.time() - start)) if current > 0 else 0
                text = f"📤 Subiendo:\n[{bar}] {percent}%\n⏳ ETA: {int(eta)}s"
                asyncio.create_task(msg.edit_text(text))

        with open(path, "rb") as f:
            await bot.send_document(chat_id=chat_id, document=f, filename=os.path.basename(path), progress=progress)

        await msg.edit_text("✅ Archivo enviado al chat.")

    except Exception as e:
        log_error(e)
        await bot.send_message(chat_id, "⚠️ Error al subir el archivo al chat.")

# 📥 Manejar archivo subido por usuario
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        doc = update.message.document
        file = await doc.get_file()
        filename = f"{int(time.time())}_{doc.file_name}"
        path = os.path.join(UPLOAD_FOLDER, filename)

        msg = await update.message.reply_text("📥 Recibiendo archivo...")
        await file.download_to_drive(path)
        await msg.edit_text("✅ Archivo guardado en el servidor.")

        await send_file_with_progress(context.bot, update.effective_chat.id, path)

    except TelegramError as e:
        log_error(e)
        await update.message.reply_text("❌ Error al recibir el archivo. ¿Es demasiado grande?")
    except Exception as e:
        log_error(e)
        await update.message.reply_text("⚠️ No se pudo guardar el archivo.")

# 🔗 Manejar enlace de descarga directa
async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    if not url.startswith("http"):
        await update.message.reply_text("❌ Enlace no válido.")
        return

    await update.message.reply_text("⏳ Iniciando descarga con aria2p...")
    filename = await download_url_with_progress(url, update)
    if filename:
        path = os.path.join(UPLOAD_FOLDER, filename)
        await update.message.reply_text("📤 Enviando archivo al chat...")
        await send_file_with_progress(context.bot, update.effective_chat.id, path)

# 🚀 Iniciar bot
if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    app.run_polling()