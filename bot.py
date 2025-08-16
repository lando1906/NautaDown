import os
import time
import logging
import asyncio
from urllib.parse import urlparse
from telegram import Update, Bot
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from telegram.error import TelegramError

# 🔧 Configuración
TOKEN = "7011073342:AAFvvoKngrMkFWGXQLgmtKRTcZrc48suP20"
UPLOAD_FOLDER = "files"
SERVER_URL = "https://nautadown-1.onrender.com"  # Cambiar por tu URL real
PORT = 10000
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# 📝 Logger
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bot_activity.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def get_download_link(filename):
    """Genera enlace de descarga directa"""
    return f"{SERVER_URL}/{UPLOAD_FOLDER}/{filename}"

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        doc = update.message.document
        file_size = doc.file_size
        
        # Verificar tamaño
        if file_size > MAX_FILE_SIZE:
            await update.message.reply_text(f"❌ Archivo demasiado grande (límite: {MAX_FILE_SIZE//(1024*1024)}MB)")
            return

        # Crear nombre único
        filename = f"{int(time.time())}_{doc.file_name}"
        path = os.path.join(UPLOAD_FOLDER, filename)
        
        # Mensaje inicial
        msg = await update.message.reply_text("📤 Preparando para recibir archivo...")
        start_time = time.time()
        last_update = start_time
        
        # Función de progreso
        def progress(current, total):
            nonlocal last_update
            now = time.time()
            if now - last_update > 1:  # Actualizar cada 1 segundo
                percent = int((current * 100) / total)
                speed = current / (now - start_time)
                eta = (total - current) / speed if speed > 0 else 0
                
                bar = "⬢" * (percent // 5) + "⬡" * (20 - percent // 5)
                progress_text = (
                    f"📤 Subiendo al servidor:\n"
                    f"{bar}\n"
                    f"📊 Progreso: {percent}%\n"
                    f"⚡ Velocidad: {speed/1024:.1f} KB/s\n"
                    f"⏳ Tiempo restante: {int(eta)}s"
                )
                asyncio.create_task(msg.edit_text(progress_text))
                last_update = now

        # Descargar archivo con progreso
        file = await doc.get_file()
        await file.download_to_drive(custom_path=path, progress=progress)
        
        # Verificar que se subió correctamente
        if os.path.exists(path):
            download_link = get_download_link(filename)
            file_info = os.stat(path)
            await msg.edit_text(
                f"✅ Archivo subido correctamente!\n\n"
                f"📝 Nombre: {filename}\n"
                f"📦 Tamaño: {file_info.st_size//1024} KB\n"
                f"🔗 Enlace directo: {download_link}\n\n"
                f"⚠️ El archivo se eliminará después de 24 horas"
            )
        else:
            await msg.edit_text("❌ Error al guardar el archivo en el servidor")

    except TelegramError as e:
        logger.error(f"Error Telegram: {str(e)}")
        await update.message.reply_text("❌ Error al recibir el archivo")
    except Exception as e:
        logger.error(f"Error inesperado: {str(e)}")
        await update.message.reply_text("⚠️ Error al procesar el archivo")

async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    if not url.startswith(("http://", "https://")):
        await update.message.reply_text("❌ Enlace no válido. Debe comenzar con http:// o https://")
        return

    msg = await update.message.reply_text("⏳ Iniciando descarga desde el enlace...")
    try:
        filename = url.split("/")[-1].split("?")[0] or f"file_{int(time.time())}"
        path = os.path.join(UPLOAD_FOLDER, filename)
        
        # Configurar progreso
        start_time = time.time()
        last_percent = 0
        
        async with context.bot.get_file(update.message) as file:
            with open(path, "wb") as f:
                async for chunk in file.download_as_bytearray():
                    f.write(chunk)
                    
                    # Actualizar progreso
                    current_size = os.path.getsize(path)
                    percent = int((current_size * 100) / (file.file_size or 1))
                    
                    if percent != last_percent and percent % 5 == 0:
                        elapsed = time.time() - start_time
                        speed = current_size / elapsed if elapsed > 0 else 0
                        eta = (file.file_size - current_size) / speed if speed > 0 else 0
                        
                        bar = "⬢" * (percent // 5) + "⬡" * (20 - percent // 5)
                        progress_text = (
                            f"📥 Descargando desde URL:\n"
                            f"{bar}\n"
                            f"📊 Progreso: {percent}%\n"
                            f"⚡ Velocidad: {speed/1024:.1f} KB/s\n"
                            f"⏳ Tiempo restante: {int(eta)}s"
                        )
                        await msg.edit_text(progress_text)
                        last_percent = percent
        
        if os.path.exists(path):
            download_link = get_download_link(filename)
            await msg.edit_text(
                f"✅ Descarga completada!\n\n"
                f"📝 Nombre: {filename}\n"
                f"📦 Tamaño: {os.path.getsize(path)//1024} KB\n"
                f"🔗 Enlace directo: {download_link}\n\n"
                f"⚠️ El archivo se eliminará después de 24 horas"
            )
        else:
            await msg.edit_text("❌ Error al guardar el archivo descargado")

    except Exception as e:
        logger.error(f"Error al descargar desde URL: {str(e)}")
        await msg.edit_text("❌ Error al procesar el enlace")

if __name__ == "__main__":
    try:
        app = ApplicationBuilder().token(TOKEN).build()
        app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
        
        logger.info(f"🚀 Iniciando bot en puerto {PORT}")
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=TOKEN,
            webhook_url=f"{SERVER_URL}/{TOKEN}"
        )
    except Exception as e:
        logger.critical(f"Error al iniciar bot: {str(e)}")
        raise