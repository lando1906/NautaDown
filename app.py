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

# Configuración directa
TOKEN = "7011073342:AAFvvoKngrMkFWGXQLgmtKRTcZrc48suP20"
DOWNLOAD_DIR = "downloads"
PORT = 10000
HOST = "0.0.0.0"

# Configurar logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
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
    
    if not (url.startswith("http://") or url.startswith("https://")):
        await update.message.reply_text("⚠️ Por favor envía una URL válida (comience con http:// o https://)")
        return
    
    try:
        processing_msg = await update.message.reply_text("🔍 Obteniendo información del video...")
        
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
        
        cmd_formats = [
            "yt-dlp",
            "--list-formats",
            "--format-sort", "vcodec:h264,res,br",
            url,
        ]
        
        result = subprocess.run(cmd_formats, capture_output=True, text=True, timeout=30)
        
        if result.returncode != 0:
            await processing_msg.edit_text("❌ Error al obtener los formatos disponibles.")
            return
            
        formats_output = result.stdout
        
        formats = []
        lines = formats_output.split("\n")
        for line in lines:
            if "audio only" in line.lower() or "video only" in line.lower() or "mp4" in line.lower():
                parts = [p for p in line.split() if p]
                if len(parts) >= 3:
                    format_id = parts[0]
                    resolution = next((p for p in parts if "x" in p and p[0].isdigit()), None)
                    codec = parts[1]
                    size = next((p for p in parts if "MiB" in p or "KiB" in p), "?MB")
                    
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
        
        formats = formats[:8]
        keyboard = []
        for i in range(0, len(formats), 2):
            row = []
            if i < len(formats):
                row.append(InlineKeyboardButton(formats[i][1], callback_data=f"dl_{formats[i][0]}"))
            if i + 1 < len(formats):
                row.append(InlineKeyboardButton(formats[i + 1][1], callback_data=f"dl_{formats[i + 1][0]}"))
            keyboard.append(row)
        
        keyboard.append([InlineKeyboardButton("❌ Cancelar", callback_data="cancel")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        duration_str = f"{duration//60}:{duration%60:02d}" if duration else "Desconocida"
        
        await processing_msg.edit_text(
            f"📹 <b>{title}</b>\n"
            f"⏱ Duración: {duration_str}\n\n"
            "Selecciona el formato de descarga:",
            reply_markup=reply_markup,
            parse_mode="HTML",
        )
        
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
        
        downloading_msg = await query.edit_message_text(
            f"⏳ Descargando: <b>{title}</b>\n\n"
            "Por favor espera, esto puede tomar varios minutos...",
            parse_mode="HTML",
        )
        
        try:
            safe_title = "".join(c for c in title if c.isalnum() or c in (" ", "_")).rstrip()
            output_template = f"{DOWNLOAD_DIR}/{safe_title}.%(ext)s"
            
            cmd = [
                "yt-dlp",
                "-f", f"{format_id}+bestaudio" if "video" in format_id else format_id,
                "--merge-output-format", "mp4",
                "-o", output_template,
                "--no-playlist",
                url,
            ]
            
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = process.communicate(timeout=900)
            
            if process.returncode != 0:
                error_msg = stderr.decode("utf-8")[:500]
                await downloading_msg.edit_text(
                    f"❌ Error al descargar el video:\n\n<code>{error_msg}</code>",
                    parse_mode="HTML",
                )
                return
            
            downloaded_files = [f for f in os.listdir(DOWNLOAD_DIR) if f.startswith(safe_title)]
            
            if not downloaded_files:
                await downloading_msg.edit_text("❌ Error: No se encontró el archivo descargado.")
                return
            
            file_path = os.path.join(DOWNLOAD_DIR, downloaded_files[0])
            file_size = os.path.getsize(file_path) / (1024 * 1024)
            
            if file_size > 50:
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
    
    # Manejadores
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_url))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_error_handler(error_handler)
    
    # Configuración para Render
    application.run_webhook(
        listen=HOST,
        port=PORT,
        url_path=TOKEN,
        webhook_url=f"https://videodown-77kj.onrender.com/{TOKEN}",
    )

if __name__ == "__main__":
    main()