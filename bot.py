import os
import time
import logging
import asyncio
import aria2p
from urllib.parse import urlparse
from telegram import Update, Bot
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from telegram.error import TelegramError

# 🔧 Configuración
TOKEN = "7011073342:AAFvvoKngrMkFWGXQLgmtKRTcZrc48suP20"  # Token público (cambiar en producción)
UPLOAD_FOLDER = "files"
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB (límite de Telegram para bots)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# 📝 Logger mejorado
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    filename="bot_activity.log"
)
logger = logging.getLogger(__name__)

# ⚙️ Inicialización de Aria2p
try:
    aria2 = aria2p.API(
        aria2p.Client(host="http://localhost", port=6800, secret="")
    )
except Exception as e:
    logger.critical(f"Error al conectar con Aria2: {str(e)}")
    raise

# 🔗 Validación de URLs
def is_valid_url(url):
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except:
        return False

# 📡 Descarga con progreso mejorado
async def download_url_with_progress(url, update):
    try:
        if not is_valid_url(url):
            await update.message.reply_text("❌ Enlace no válido.")
            return None

        filename = url.split("/")[-1].split("?")[0] or f"file_{int(time.time())}"
        path = os.path.join(UPLOAD_FOLDER, filename)

        # Opciones de descarga
        options = {
            "dir": UPLOAD_FOLDER,
            "out": filename,
            "max-file-not-found": 3,
            "timeout": 30
        }

        download = aria2.add_uris([url], options=options)
        msg = await update.message.reply_text("📡 Iniciando descarga...")
        last_update = time.time()

        while not download.is_complete:
            if time.time() - last_update > 5:  # Actualizar cada 5 segundos
                try:
                    download.update()
                    percent = int((download.completed_length or 0) * 100 / (download.total_length or 1))
                    speed = int(download.download_speed or 1)
                    eta = ((download.total_length or 0) - (download.completed_length or 0)) / (speed or 1)
                    bar = "⬢" * (percent // 10) + "⬡" * (10 - percent // 10)

                    text = (f"📡 Descargando:\n"
                           f"[{bar}] {percent}%\n"
                           f"⚡ {speed // 1024} KB/s\n"
                           f"⏳ ETA: {int(eta)}s")
                    await msg.edit_text(text)
                    last_update = time.time()
                except Exception as e:
                    logger.error(f"Error al actualizar progreso: {str(e)}")

            await asyncio.sleep(1)

        await msg.edit_text("✅ Descarga completada!")
        return filename

    except Exception as e:
        logger.error(f"Error en descarga: {str(e)}")
        await update.message.reply_text("❌ Error al descargar el archivo.")
        return None

# 📤 Subida con progreso mejorado
async def send_file_with_progress(bot: Bot, chat_id: int, path: str):
    try:
        if not os.path.exists(path):
            await bot.send_message(chat_id, "⚠️ Archivo no encontrado.")
            return

        file_size = os.path.getsize(path)
        if file_size > MAX_FILE_SIZE:
            await bot.send_message(chat_id, f"❌ Archivo demasiado grande (límite: {MAX_FILE_SIZE//(1024*1024)}MB)")
            return

        msg = await bot.send_message(chat_id, "📤 Preparando para subir...")
        start_time = time.time()
        last_percent = -1

        def progress(current, total):
            nonlocal last_percent
            percent = int((current * 100) / total)
            if percent != last_percent and percent % 5 == 0:  # Actualizar cada 5%
                last_percent = percent
                elapsed = time.time() - start_time
                speed = current / elapsed if elapsed > 0 else 0
                eta = (total - current) / speed if speed > 0 else 0
                bar = "⬢" * (percent // 10) + "⬡" * (10 - percent // 10)
                
                progress_text = (f"📤 Subiendo:\n"
                                f"[{bar}] {percent}%\n"
                                f"⚡ {speed//1024} KB/s\n"
                                f"⏳ ETA: {int(eta)}s")
                asyncio.create_task(msg.edit_text(progress_text))

        with open(path, "rb") as file:
            await bot.send_document(
                chat_id=chat_id,
                document=file,
                filename=os.path.basename(path),
                progress=progress
            )

        await msg.edit_text("✅ Archivo enviado con éxito!")
        try:
            os.remove(path)  # Limpieza después de enviar
        except:
            pass

    except Exception as e:
        logger.error(f"Error al subir archivo: {str(e)}")
        await bot.send_message(chat_id, "⚠️ Error al subir el archivo.")

# 📥 Manejador de documentos
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        doc = update.message.document
        if doc.file_size > MAX_FILE_SIZE:
            await update.message.reply_text(f"❌ Archivo demasiado grande (límite: {MAX_FILE_SIZE//(1024*1024)}MB)")
            return

        file = await doc.get_file()
        filename = f"{int(time.time())}_{doc.file_name}"
        path = os.path.join(UPLOAD_FOLDER, filename)

        msg = await update.message.reply_text("📥 Recibiendo archivo...")
        await file.download_to_drive(path)
        await msg.edit_text("✅ Archivo guardado en servidor.")

        await send_file_with_progress(context.bot, update.effective_chat.id, path)

    except TelegramError as e:
        logger.error(f"Error Telegram: {str(e)}")
        await update.message.reply_text("❌ Error al recibir el archivo.")
    except Exception as e:
        logger.error(f"Error inesperado: {str(e)}")
        await update.message.reply_text("⚠️ Error al procesar el archivo.")

# 🔗 Manejador de enlaces
async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    if not is_valid_url(url):
        await update.message.reply_text("❌ Por favor envía un enlace válido (http/https).")
        return

    logger.info(f"Iniciando descarga para {url}")
    filename = await download_url_with_progress(url, update)
    
    if filename:
        path = os.path.join(UPLOAD_FOLDER, filename)
        await send_file_with_progress(context.bot, update.effective_chat.id, path)

# 🚀 Inicio del bot
if __name__ == "__main__":
    try:
        app = ApplicationBuilder().token(TOKEN).build()
        app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
        
        logger.info("Bot iniciado correctamente")
        print("Bot en ejecución... Presiona Ctrl+C para detener")
        app.run_polling()
        
    except Exception as e:
        logger.critical(f"Error al iniciar bot: {str(e)}")
        raise