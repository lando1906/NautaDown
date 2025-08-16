import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode
from tempfile import NamedTemporaryFile
import subprocess

# Configuración
BOT_TOKEN = "7011073342:AAFvvoKngrMkFWGXQLgmtKRTcZrc48suP20"
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB (límite de Telegram)

# Logs
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Mensajes elegantes (Markdown V2)
WELCOME_MSG = """
✨ *¡Bienvenido al Compresor de Videos de Alta Calidad\!* ✨

📤 Envíame un video y lo optimizaré con *mínima pérdida de calidad* usando `FFmpeg` y el códec *H\.265* \(HEVC\)\.
🔹 *Tamaño máximo:* 50MB
🔹 *Formato recomendado:* MP4, MOV, MKV

🛠️ *Comandos:*
/start \- Muestra este mensaje
/help \- Ayuda y ejemplos
"""

COMPRESSING_MSG = """
🔄 *Procesando tu video\.\.\.*  
🔧 *Configuración aplicada:*
▫️ Códec: `libx265` \(HEVC\)
▫️ Calidad: `CRF 20` \(óptima\)
▫️ Audio: `Copiado sin pérdida`  
⏳ _Esto puede tardar unos segundos\.\.\._
"""

SUCCESS_MSG = """
✅ *¡Video comprimido con éxito\!*  

📊 *Detalles del proceso:*
▫️ Tamaño reducido con *mínima pérdida de calidad*\.
▫️ Formato: `MP4` \(H\.265 \+ AAC\)
▫️ Preset: `medium` \(equilibrio velocidad/compresión\)

👇 *Descarga el resultado aquí abajo\.*
"""

ERROR_MSG = """
❌ *¡Error al procesar el video\!*  

🔍 *Posibles causas:*
▫️ El archivo no es un video válido\.
▫️ Supera el límite de 50MB\.
▫️ El códec no es compatible\.

💡 *Solución:* Intenta con otro formato \(ej\. MP4\)\.
"""

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        WELCOME_MSG,
        parse_mode=ParseMode.MARKDOWN_V2
    )

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Verificar si es un video
    if not update.message.video and not (update.message.document and update.message.document.mime_type.startswith("video/")):
        await update.message.reply_text(
            "⚠️ *Por favor, envía un video válido.*",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return

    # Obtener archivo
    file = await (update.message.video or update.message.document).get_file()
    
    # Validar tamaño
    if file.file_size > MAX_FILE_SIZE:
        await update.message.reply_text(
            f"⚠️ *El video pesa {file.file_size // (1024 * 1024)}MB.* \n"
            "*Límite:* 50MB\. Sube un archivo más pequeño\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return

    # Mensaje de "procesando"
    processing_msg = await update.message.reply_text(
        COMPRESSING_MSG,
        parse_mode=ParseMode.MARKDOWN_V2
    )

    # Descargar video
    with NamedTemporaryFile(suffix=".mp4", delete=False) as temp_input:
        await file.download_to_drive(temp_input.name)
        temp_input_path = temp_input.name

    # Comprimir con FFmpeg (H.265)
    output_path = temp_input_path.replace(".mp4", "_compressed.mp4")
    ffmpeg_cmd = [
        "ffmpeg",
        "-i", temp_input_path,
        "-c:v", "libx265",
        "-crf", "20",
        "-preset", "medium",
        "-c:a", "copy",
        output_path
    ]

    try:
        subprocess.run(ffmpeg_cmd, check=True)
        # Enviar video comprimido
        await update.message.reply_video(
            video=open(output_path, "rb"),
            caption=SUCCESS_MSG,
            parse_mode=ParseMode.MARKDOWN_V2
        )
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg error: {e}")
        await update.message.reply_text(
            ERROR_MSG,
            parse_mode=ParseMode.MARKDOWN_V2
        )
    except Exception as e:
        logger.error(f"Error general: {e}")
        await update.message.reply_text(
            "❌ *Error inesperado.* Contacta al soporte.",
            parse_mode=ParseMode.MARKDOWN_V2
        )
    finally:
        # Limpiar archivos temporales
        os.unlink(temp_input_path)
        if os.path.exists(output_path):
            os.unlink(output_path)
        # Eliminar mensaje "procesando"
        await context.bot.delete_message(
            chat_id=update.message.chat_id,
            message_id=processing_msg.message_id
        )

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.VIDEO | filters.Document.VIDEO, handle_video))
    app.run_polling()

if __name__ == "__main__":
    main()