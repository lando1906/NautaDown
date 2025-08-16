import os
import time
import logging
import asyncio
from urllib.parse import urlparse
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from telegram.error import TelegramError

# 🔧 Configuración
TOKEN = "7011073342:AAFvvoKngrMkFWGXQLgmtKRTcZrc48suP20"
UPLOAD_FOLDER = "files"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

# 📝 Logger mejorado
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        doc = update.message.document
        if doc.file_size > MAX_FILE_SIZE:
            await update.message.reply_text(f"❌ Archivo demasiado grande (límite: {MAX_FILE_SIZE//(1024*1024)}MB)")
            return

        # Mensaje inicial
        msg = await update.message.reply_text("📤 Preparando para recibir archivo...")
        
        # Descargar archivo con progreso
        file = await doc.get_file()
        filename = f"{int(time.time())}_{doc.file_name}"
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        
        start_time = time.time()
        last_percent = 0
        
        async def download_progress(current, total):
            nonlocal last_percent
            percent = int((current * 100) / total)
            if percent > last_percent:
                elapsed = time.time() - start_time
                speed = current / elapsed if elapsed > 0 else 0
                eta = (total - current) / speed if speed > 0 else 0
                
                bar = "⬢" * (percent // 5) + "⬡" * (20 - percent // 5)
                progress_text = (
                    f"📤 Subiendo al servidor:\n"
                    f"{bar}\n"
                    f"📊 Progreso: {percent}%\n"
                    f"⚡ Velocidad: {speed/1024:.1f} KB/s\n"
                    f"⏳ Tiempo restante: {int(eta)}s"
                )
                await msg.edit_text(progress_text)
                last_percent = percent

        await file.download_to_drive(
            custom_path=file_path,
            read_timeout=30,
            write_timeout=30,
            progress=download_progress
        )

        await msg.edit_text(f"✅ Archivo guardado como: {filename}")

    except Exception as e:
        logger.error(f"Error en handle_document: {str(e)}")
        await update.message.reply_text("❌ Error al procesar el archivo")

async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        url = update.message.text.strip()
        if not url.startswith(('http://', 'https://')):
            await update.message.reply_text("❌ Enlace no válido")
            return

        msg = await update.message.reply_text("⏳ Procesando enlace...")
        
        # Simulación de descarga (reemplaza con tu lógica real)
        for progress in range(0, 101, 5):
            bar = "⬢" * (progress // 5) + "⬡" * (20 - progress // 5)
            await msg.edit_text(
                f"📥 Descargando:\n"
                f"{bar}\n"
                f"📊 Progreso: {progress}%\n"
                f"⚡ Velocidad: 1024 KB/s\n"
                f"⏳ Tiempo restante: {10 - progress//10}s"
            )
            await asyncio.sleep(0.5)

        await msg.edit_text("✅ Descarga completada (simulación)")

    except Exception as e:
        logger.error(f"Error en handle_link: {str(e)}")
        await update.message.reply_text("❌ Error al procesar el enlace")

if __name__ == "__main__":
    try:
        app = ApplicationBuilder().token(TOKEN).build()
        app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
        
        logger.info("Bot iniciado en modo polling")
        app.run_polling()
        
    except Exception as e:
        logger.critical(f"Error al iniciar bot: {str(e)}")