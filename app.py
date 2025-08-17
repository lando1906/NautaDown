import os
import subprocess
import json
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler,
    ContextTypes,
)

# Configuración
TOKEN = os.getenv("7011073342:AAFvvoKngrMkFWGXQLgmtKRTcZrc48suP20")  # Usar variable de entorno en Render
DOWNLOAD_DIR = "downloads"
PORT = int(os.getenv("PORT", 10000))  # Para Render
HOST = os.getenv("HOST", "0.0.0.0")  # Para Render

# Configurar logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Crear directorio de descargas si no existe
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja el comando /start"""
    await update.message.reply_text(
        "🎬 Bot Descargador de Videos\n\n"
        "Envía una URL de YouTube, Vimeo, Twitter, etc. y te mostraré las calidades "
        "disponibles para descargar.\n\n"
        "Ejemplo: https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    )

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja cuando el usuario envía una URL"""
    url = update.message.text.strip()
    
    # Verificar si es una URL válida
    if not (url.startswith("http://") or url.startswith("https://")):
        await update.message.reply_text("⚠️ Por favor envía una URL válida (comience con http:// o https://)")
        return
    
    try:
        # Mostrar mensaje de "procesando"
        processing_msg = await update.message.reply_text("🔍 Obteniendo información del video...")
        
        # Obtener información del video con yt-dlp en formato JSON
        cmd_info = [
            "yt-dlp",
            "--dump-json",
            "--no-playlist",
            "--skip-download",
            url,
        ]
        
        result = subprocess.run(cmd_info, capture_output=True, text=True, timeout=30)
        
        if result.returncode != 0:
            await processing_msg.edit_text("❌ Error al obtener información del video. ¿La URL es correcta?")
            return
            
        video_info = json.loads(result.stdout)
        title = video_info.get("title", "Video sin título")
        duration = video_info.get("duration", 0)
        
        # Obtener formatos disponibles con tamaño estimado
        cmd_formats = [
            "yt-dlp",
            "--list-formats",
            "--format-sort", "vcodec:h264,res,br",  # Priorizar h264
            url,
        ]
        
        result = subprocess.run(cmd_formats, capture_output=True, text=True, timeout=30)
        
        if result.returncode != 0:
            await processing_msg.edit_text("❌ Error al obtener los formatos disponibles.")
            return
            
        formats_output = result.stdout
        
        # Procesar formatos disponibles
        formats = []
        lines = formats_output.split("\n")
        for line in lines:
            if "audio only" in line.lower() or "video only" in line.lower() or "mp4" in line.lower():
                parts = [p for p in line.split() if p]
                if len(parts) >= 3:
                    format_id = parts[0]
                    resolution = next((p for p in parts if "x" in p and p[0].isdigit()), None)
                    codec = parts[1]
                    
                    # Extraer tamaño aproximado (si está disponible)
                    size = next((p for p in parts if "MiB" in p or "KiB" in p), "?MB")
                    
                    # Crear descripción amigable
                    desc = ""
                    if resolution:
                        desc += f"{resolution} "
                    if "audio only" in line.lower():
                        desc += "🔉 Audio"
                    else:
                        desc += "🎥 Video"
                    
                    desc += f" | {size}"
                    
                    formats.append((format_id, desc))
        
        if not formats:
            await processing_msg.edit_text("No se encontraron formatos disponibles para descargar.")
            return
        
        # Crear botonera (máximo 8 formatos para no saturar)
        formats = formats[:8]
        keyboard = []
        for i in range(0, len(formats), 2):
            row = []
            if i < len(formats):
                row.append(InlineKeyboardButton(formats[i][1], callback_data=f"dl_{formats[i][0]}"))
            if i + 1 < len(formats):
                row.append(InlineKeyboardButton(formats[i + 1][1], callback_data=f"dl_{formats[i + 1][0]}"))
            keyboard.append(row)
        
        # Añadir botón de cancelar
        keyboard.append([InlineKeyboardButton("❌ Cancelar", callback_data="cancel")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Mensaje con información del video
        duration_str = f"{duration//60}:{duration%60:02d}" if duration else "Desconocida"
        
        await processing_msg.edit_text(
            f"📹 <b>{title}</b>\n"
            f"⏱ Duración: {duration_str}\n\n"
            "Selecciona el formato de descarga:",
            reply_markup=reply_markup,
            parse_mode="HTML",
        )
        
        # Guardar información del video en el contexto
        context.user_data["current_url"] = url
        context.user_data["video_title"] = title
        
    except subprocess.TimeoutExpired:
        await update.message.reply_text("⌛ El servidor tardó demasiado en responder. Intenta nuevamente.")
    except Exception as e:
        logger.error(f"Error al procesar la URL: {e}")
        await update.message.reply_text("❌ Ocurrió un error al procesar la URL.")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja la selección de calidad"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel":
        await query.edit_message_text("✅ Operación cancelada.")
        return
    
    if query.data.startswith("dl_"):
        format_id = query.data.split("_")[1]
        url = context.user_data.get("current_url")
        title = context.user_data.get("video_title", "video")
        
        if not url:
            await query.edit_message_text("❌ Error: URL no encontrada.")
            return
        
        # Mensaje de descarga en progreso
        downloading_msg = await query.edit_message_text(
            f"⏳ Descargando: <b>{title}</b>\n\n"
            "Por favor espera, esto puede tomar varios minutos...",
            parse_mode="HTML",
        )
        
        try:
            # Limpiar el título para usarlo como nombre de archivo
            safe_title = "".join(c for c in title if c.isalnum() or c in (" ", "_")).rstrip()
            output_template = f"{DOWNLOAD_DIR}/{safe_title}.%(ext)s"
            
            # Descargar el video con el formato seleccionado
            cmd = [
                "yt-dlp",
                "-f", f"{format_id}+bestaudio" if "video" in format_id else format_id,
                "--merge-output-format", "mp4",
                "-o", output_template,
                "--no-playlist",
                url,
            ]
            
            # Ejecutar yt-dlp con timeout de 15 minutos
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = process.communicate(timeout=900)
            
            if process.returncode != 0:
                error_msg = stderr.decode("utf-8")[:500]  # Limitar longitud del mensaje de error
                await downloading_msg.edit_text(
                    f"❌ Error al descargar el video:\n\n<code>{error_msg}</code>",
                    parse_mode="HTML",
                )
                return
            
            # Buscar el archivo descargado
            downloaded_files = [f for f in os.listdir(DOWNLOAD_DIR) if f.startswith(safe_title)]
            
            if not downloaded_files:
                await downloading_msg.edit_text("❌ Error: No se encontró el archivo descargado.")
                return
            
            # Enviar el archivo al usuario
            file_path = os.path.join(DOWNLOAD_DIR, downloaded_files[0])
            file_size = os.path.getsize(file_path) / (1024 * 1024)  # Tamaño en MB
            
            if file_size > 50:  # Límite de Telegram: 50MB
                await downloading_msg.edit_text(
                    "⚠️ El archivo es demasiado grande para enviar por Telegram (límite 50MB).\n\n"
                    f"Tamaño: {file_size:.1f}MB"
                )
            else:
                await context.bot.send_chat_action(
                    chat_id=query.message.chat_id, action="upload_document"
                )
                
                await context.bot.send_document(
                    chat_id=query.message.chat_id,
                    document=open(file_path, "rb"),
                    caption=f"✅ <b>{title}</b>\n\n"
                    f"📦 Tamaño: {file_size:.1f}MB",
                    parse_mode="HTML",
                )
                await downloading_msg.delete()
            
        except subprocess.TimeoutExpired:
            await downloading_msg.edit_text("⌛ La descarga tardó demasiado y fue cancelada.")
        except Exception as e:
            logger.error(f"Error al descargar el video: {e}")
            await downloading_msg.edit_text("❌ Ocurrió un error al descargar el video.")
        finally:
            # Limpiar archivos descargados
            for f in downloaded_files:
                try:
                    os.remove(os.path.join(DOWNLOAD_DIR, f))
                except:
                    pass

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja errores"""
    logger.error(f"Error en la actualización {update}: {context.error}")
    if update.message:
        await update.message.reply_text("❌ Ocurrió un error inesperado.")

def main():
    """Inicia el bot"""
    application = Application.builder().token(TOKEN).build()
    
    # Manejadores de comandos
    application.add_handler(CommandHandler("start", start))
    
    # Manejador de URLs
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_url))
    
    # Manejador de botones
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Manejador de errores
    application.add_error_handler(error_handler)
    
    # Configuración para Render
    if os.getenv("RENDER"):
        application.run_webhook(
            listen=HOST,
            port=PORT,
            url_path=TOKEN,
            webhook_url=f"https://{os.getenv('RENDER_SERVICE_NAME')}.onrender.com/{TOKEN}",
        )
    else:
        # Modo local para desarrollo
        application.run_polling()

if __name__ == "__main__":
    main()