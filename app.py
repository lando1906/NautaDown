import os
import logging
import time
import re
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode
from tempfile import NamedTemporaryFile
import subprocess
import psutil
import asyncio

# Configuración
BOT_TOKEN = os.getenv("BOT_TOKEN", "7011073342:AAFvvoKngrMkFWGXQLgmtKRTcZrc48suP20")  # Usa variables de entorno en producción
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB (límite de Telegram)
UPDATE_INTERVAL = 1  # Actualizar progreso cada 1 segundo

# Logs
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Mensajes
WELCOME_MSG = """
✨ *¡Bienvenido al Compresor de Videos de Alta Calidad\!* ✨

📤 Envíame un video y lo optimizaré con *mínima pérdida de calidad* usando `FFmpeg` y el códec *H\.265* \(HEVC\)\.
🔹 *Tamaño máximo:* 50MB
🔹 *Formato recomendado:* MP4, MOV, MKV

🛠️ *Comandos:*
/start \- Muestra este mensaje
/help \- Ayuda y ejemplos
"""

def get_compressing_msg(progress=None, speed=None, remaining=None, cpu=None, mem=None):
    base_msg = """
🔄 *Procesando tu video\.\.\.*  
🔧 *Configuración aplicada:*
▫️ Códec: `libx265` \(HEVC\)
▫️ Calidad: `CRF 20` \(óptima\)
▫️ Preset: `medium`
"""
    
    if progress:
        status_msg = f"""
📊 *Progreso:* `{progress}%`
⚡ *Velocidad:* `{speed or 'calculando...'}`
⏱️ *Tiempo restante:* `{remaining or 'calculando...'}`
💻 *Uso de recursos:* CPU `{cpu or '?'}%` | RAM `{mem or '?'}%`
"""
        return base_msg + status_msg
    
    return base_msg + "\n⏳ _Iniciando compresión..._"

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
▫️ Tiempo de procesamiento excedido\.

💡 *Solución:* Intenta con otro formato \(ej\. MP4\) o video más pequeño\.
"""

async def edit_progress_message(context, chat_id, message_id, progress_data):
    """Edita el mensaje de progreso con la información actualizada"""
    try:
        progress = progress_data.get('progress', 0)
        speed = progress_data.get('speed', 'N/A')
        remaining = progress_data.get('remaining', 'N/A')
        
        # Obtener uso de recursos
        cpu = psutil.cpu_percent()
        mem = psutil.virtual_memory().percent
        
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=get_compressing_msg(
                progress=min(100, progress),
                speed=speed,
                remaining=remaining,
                cpu=round(cpu, 1),
                mem=round(mem, 1)
            ),
            parse_mode=ParseMode.MARKDOWN_V2
        )
    except Exception as e:
        logger.error(f"Error al actualizar progreso: {e}")

def parse_ffmpeg_progress(line):
    """Analiza la salida de FFmpeg para extraer el progreso"""
    time_match = re.search(r'time=(\d{2}:\d{2}:\d{2}\.\d{2})', line)
    speed_match = re.search(r'speed=(\d+\.?\d*)x', line)
    
    if time_match and speed_match:
        time_str = time_match.group(1)
        speed = speed_match.group(1)
        
        # Convertir tiempo a segundos
        h, m, s = map(float, time_str.split(':'))
        total_seconds = h * 3600 + m * 60 + s
        
        return {
            'time_seconds': total_seconds,
            'speed': f"{speed}x"
        }
    return None

async def compress_video(input_path, output_path, context, chat_id, message_id):
    """Ejecuta FFmpeg y monitorea el progreso"""
    cmd = [
        "ffmpeg",
        "-i", input_path,
        "-c:v", "libx265",
        "-crf", "20",
        "-preset", "medium",
        "-movflags", "+faststart",
        "-c:a", "copy",
        "-progress", "pipe:1",  # Enviar progreso a stdout
        "-nostats",  # Evitar información redundante
        "-y",  # Sobrescribir sin preguntar
        output_path
    ]
    
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True
    )
    
    duration = None
    start_time = time.time()
    last_update = 0
    
    # Primero obtenemos la duración del video
    for line in process.stdout:
        if "Duration:" in line:
            duration_match = re.search(r'Duration: (\d{2}:\d{2}:\d{2}\.\d{2})', line)
            if duration_match:
                h, m, s = map(float, duration_match.group(1).split(':'))
                duration = h * 3600 + m * 60 + s
            break
    
    if not duration:
        raise Exception("No se pudo determinar la duración del video")
    
    # Monitorear progreso
    while True:
        line = process.stdout.readline()
        if not line and process.poll() is not None:
            break
            
        progress_data = parse_ffmpeg_progress(line)
        if progress_data:
            current_time = time.time()
            elapsed = current_time - start_time
            
            # Calcular progreso y tiempo restante
            progress = (progress_data['time_seconds'] / duration) * 100
            remaining_seconds = (duration - progress_data['time_seconds']) / float(progress_data['speed'])
            remaining = f"{int(remaining_seconds // 60)}m {int(remaining_seconds % 60)}s"
            
            # Actualizar mensaje si ha pasado el intervalo
            if current_time - last_update >= UPDATE_INTERVAL:
                await edit_progress_message(
                    context,
                    chat_id,
                    message_id,
                    {
                        'progress': round(progress, 1),
                        'speed': progress_data['speed'],
                        'remaining': remaining
                    }
                )
                last_update = current_time
    
    return process.returncode

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja el comando de subida de video"""
    try:
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

        # Mensaje inicial de "procesando"
        processing_msg = await update.message.reply_text(
            get_compressing_msg(),
            parse_mode=ParseMode.MARKDOWN_V2
        )

        # Descargar video
        with NamedTemporaryFile(suffix=".mp4", delete=False) as temp_input:
            await file.download_to_drive(temp_input.name)
            temp_input_path = temp_input.name

        # Comprimir con FFmpeg (H.265)
        output_path = temp_input_path.replace(".mp4", "_compressed.mp4")
        
        return_code = await compress_video(
            temp_input_path,
            output_path,
            context,
            update.message.chat_id,
            processing_msg.message_id
        )

        if return_code == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            # Enviar video comprimido
            await update.message.reply_video(
                video=open(output_path, "rb"),
                caption=SUCCESS_MSG,
                parse_mode=ParseMode.MARKDOWN_V2,
                supports_streaming=True
            )
        else:
            raise Exception(f"FFmpeg falló con código {return_code}")

    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg error: {e}")
        await update.message.reply_text(
            ERROR_MSG,
            parse_mode=ParseMode.MARKDOWN_V2
        )
    except Exception as e:
        logger.error(f"Error general: {e}")
        await update.message.reply_text(
            f"❌ *Error inesperado:* `{str(e)}`\n\n{ERROR_MSG}",
            parse_mode=ParseMode.MARKDOWN_V2
        )
    finally:
        # Limpiar archivos temporales
        for path in [temp_input_path, output_path]:
            try:
                if path and os.path.exists(path):
                    os.unlink(path)
            except Exception as e:
                logger.error(f"Error limpiando {path}: {e}")
        
        # Eliminar mensaje "procesando" si existe
        try:
            await context.bot.delete_message(
                chat_id=update.message.chat_id,
                message_id=processing_msg.message_id
            )
        except Exception as e:
            logger.error(f"Error eliminando mensaje: {e}")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.VIDEO | filters.Document.VIDEO, handle_video))
    app.run_polling()

if __name__ == "__main__":
    main()