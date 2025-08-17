import os
import re
import json
import asyncio
import logging
import subprocess
import shutil
from typing import Optional
from telegram import Update, Message, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# Configuración básica
TOKEN = "7011073342:AAFvvoKngrMkFWGXQLgmtKRTcZrc48suP20"
DOWNLOAD_DIR = "downloads"
PORT = 10000
HOST = "0.0.0.0"

# Configuración de logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Asegurar que el directorio de descargas existe
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# --------------------------
# Funciones de video_utils.py
# --------------------------

def sanitize_title(title: str) -> str:
    """Limpia el título para usarlo como nombre de archivo seguro."""
    if not title:
        return "untitled"
    title = title.strip()
    title = re.sub(r"[^\w\s-]", "", title)
    title = re.sub(r"\s+", "_", title)
    return title[:100]  # Limita a 100 caracteres

def prepare_download_command(url: str, format_id: str, safe_title: str) -> tuple[list, str]:
    """Prepara el comando yt-dlp para descargar el video."""
    if not all([url, format_id, safe_title]):
        raise ValueError("Parámetros inválidos (url, format_id o safe_title vacíos)")
    
    output_path = os.path.join(DOWNLOAD_DIR, f"{safe_title}.mp4")
    cmd = [
        "yt-dlp",
        "-f", format_id,
        "-o", output_path,
        "--no-playlist",
        "--no-warnings",
        "--quiet",
        "--no-cache-dir",
        url
    ]
    return cmd, output_path

def is_valid_video(file_path: str) -> bool:
    """Verifica si el archivo existe y tiene tamaño suficiente."""
    if not file_path:
        return False
    return os.path.exists(file_path) and os.path.getsize(file_path) > 1024 * 100  # >100KB

def cleanup_files(base_name: str):
    """Elimina archivos relacionados con el video descargado."""
    if not base_name:
        return
    
    for ext in [".mp4", ".mkv", ".webm", ".part", ".temp"]:
        path = os.path.join(DOWNLOAD_DIR, f"{base_name}{ext}")
        if os.path.exists(path):
            try:
                os.remove(path)
            except:
                pass

    # Elimina carpeta de thumbnails si existe
    thumb_dir = os.path.join(DOWNLOAD_DIR, f"{base_name}_thumbs")
    if os.path.isdir(thumb_dir):
        shutil.rmtree(thumb_dir, ignore_errors=True)

# --------------------------
# Funciones de progress_handler.py
# --------------------------

# Regex para extraer progreso de yt-dlp
progress_pattern = re.compile(
    r"\[download\]\s+(\d+\.\d+)%\s+of\s+~?([\d\.]+\w+)\s+at\s+([\d\.]+\w+\/s)\s+ETA\s+([\d:]+)"
)

async def stream_download_progress(cmd: list, message: Message) -> Optional[str]:
    """Ejecuta yt-dlp y actualiza el progreso en tiempo real."""
    filepath = None
    last_progress = 0
    
    try:
        with subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True
        ) as process:
            
            while process.poll() is None:
                line = process.stdout.readline()
                if not line:
                    await asyncio.sleep(0.1)
                    continue

                # Detectar progreso
                match = progress_pattern.search(line)
                if match:
                    percent, size, speed, eta = match.groups()
                    if float(percent) > last_progress:
                        last_progress = float(percent)
                        text = (
                            f"⏳ <b>Descargando...</b>\n\n"
                            f"📏 Tamaño: {size}\n"
                            f"📊 Progreso: {percent}%\n"
                            f"⚡ Velocidad: {speed}\n"
                            f"⏱ ETA: {eta}"
                        )
                        try:
                            await message.edit_text(text, parse_mode="HTML")
                        except Exception as e:
                            logger.error(f"Error al actualizar mensaje: {e}")

                # Detectar ruta del archivo
                if "[download] Destination:" in line:
                    filepath = line.split("Destination:")[-1].strip()
                elif "has already been downloaded" in line:
                    filepath = line.split("has already been downloaded")[0].strip()

                await asyncio.sleep(1)

            # Verificar si la descarga fue exitosa
            if process.returncode != 0:
                error_msg = "❌ Error en la descarga"
                if filepath and os.path.exists(filepath):
                    os.remove(filepath)
                await message.edit_text(error_msg, parse_mode="HTML")
                return None

    except Exception as e:
        error_msg = f"❌ Error inesperado: {str(e)}"
        await message.edit_text(error_msg, parse_mode="HTML")
        return None

    await message.edit_text("✅ <b>Descarga completada</b>", parse_mode="HTML")
    return filepath

async def simulate_upload_progress(message: Message, filepath: str):
    """Simula el progreso de subida basado en el tamaño real del archivo."""
    try:
        file_size = os.path.getsize(filepath)
        file_size_mb = file_size / (1024 * 1024)
        
        # Progreso más realista
        stages = [5, 15, 30, 50, 70, 85, 95, 100]
        time_per_stage = 10 / len(stages)  # Total 10 segundos
        
        for progress in stages:
            await message.edit_text(
                f"📤 <b>Subiendo video...</b>\n\n"
                f"📦 Tamaño: {file_size_mb:.1f}MB\n"
                f"📊 Progreso: {progress}%",
                parse_mode="HTML"
            )
            await asyncio.sleep(time_per_stage)
            
    except Exception as e:
        logger.error(f"Error en simulación de subida: {e}")
    
    await message.edit_text("✅ <b>Video enviado</b>", parse_mode="HTML")

# --------------------------
# Handlers de Telegram
# --------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja el comando /start."""
    await update.message.reply_text(
        "🎬 Bot Descargador de Videos\n\n"
        "Envía una URL de YouTube, Vimeo, Twitter, etc. y te mostraré las calidades disponibles."
    )

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Procesa la URL recibida y muestra los formatos disponibles."""
    url = update.message.text.strip()

    if not url.startswith(("http://", "https://")):
        await update.message.reply_text("⚠️ Envía una URL válida.")
        return

    try:
        processing_msg = await update.message.reply_text("🔍 Obteniendo información del video...")

        # Obtener información básica del video
        cmd_info = ["yt-dlp", "--dump-json", "--no-playlist", "--skip-download", url]
        result = subprocess.run(cmd_info, capture_output=True, text=True, timeout=30)

        if result.returncode != 0:
            await processing_msg.edit_text("❌ Error al obtener información del video.")
            return

        video_info = json.loads(result.stdout)
        title = video_info.get("title", "Video sin título")
        duration = video_info.get("duration", 0)

        # Obtener formatos disponibles
        cmd_formats = ["yt-dlp", "--list-formats", "--format-sort", "vcodec:h264,res,br", url]
        result = subprocess.run(cmd_formats, capture_output=True, text=True, timeout=30)

        if result.returncode != 0:
            await processing_msg.edit_text("❌ Error al obtener los formatos disponibles.")
            return

        formats = []
        for line in result.stdout.split("\n"):
            if "audio only" in line.lower() or "video only" in line.lower() or "mp4" in line.lower():
                parts = [p for p in line.split() if p]
                if len(parts) >= 3:
                    format_id = parts[0]
                    resolution = next((p for p in parts if "x" in p and p[0].isdigit()), None)
                    size = next((p for p in parts if "MiB" in p or "KiB" in p), "?MB")
                    desc = f"{resolution or ''} {'🔉 Audio' if 'audio only' in line.lower() else '🎥 Video'} | {size}"
                    formats.append((format_id, desc))

        if not formats:
            await processing_msg.edit_text("No se encontraron formatos disponibles.")
            return

        # Crear teclado con opciones
        keyboard = [[InlineKeyboardButton(desc, callback_data=f"dl_{fid}")] for fid, desc in formats[:8]]
        keyboard.append([InlineKeyboardButton("❌ Cancelar", callback_data="cancel")])
        reply_markup = InlineKeyboardMarkup(keyboard)

        duration_str = f"{duration//60}:{duration%60:02d}" if duration else "Desconocida"

        await processing_msg.edit_text(
            f"📹 <b>{title}</b>\n⏱ Duración: {duration_str}\n\nSelecciona el formato:",
            reply_markup=reply_markup,
            parse_mode="HTML",
        )

        # Guardar datos en contexto
        context.user_data["current_url"] = url
        context.user_data["video_title"] = title

    except Exception as e:
        logger.error(f"Error al procesar la URL: {e}")
        await update.message.reply_text("❌ Ocurrió un error al procesar la URL.")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja las acciones de los botones inline."""
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
            f"⏳ Descargando: <b>{title}</b>\n\nPor favor espera...",
            parse_mode="HTML",
        )

        try:
            safe_title = sanitize_title(title)
            cmd, file_path = prepare_download_command(url, format_id, safe_title)

            # Descargar con progreso
            file_path = await stream_download_progress(cmd, downloading_msg)

            # Validar el archivo descargado
            if not is_valid_video(file_path):
                await downloading_msg.edit_text("❌ El archivo descargado no es válido.")
                return

            file_size = os.path.getsize(file_path) / (1024 * 1024)

            if file_size > 2000:
                await downloading_msg.edit_text(
                    "⚠️ El video es demasiado grande (límite 2GB).\n\n"
                    f"Tamaño: {file_size:.1f}MB"
                )
            else:
                # Simular subida
                await simulate_upload_progress(downloading_msg, file_path)

                # Enviar video
                await context.bot.send_chat_action(
                    chat_id=query.message.chat_id, 
                    action="upload_video"
                )
                await context.bot.send_video(
                    chat_id=query.message.chat_id,
                    video=open(file_path, "rb"),
                    caption=f"✅ <b>{title}</b>\n\n📦 Tamaño: {file_size:.1f}MB",
                    supports_streaming=True,
                    parse_mode="HTML",
                    read_timeout=60,
                    write_timeout=60,
                    connect_timeout=60,
                )
                await downloading_msg.delete()

        except Exception as e:
            logger.error(f"Error al descargar el video: {e}")
            await downloading_msg.edit_text("❌ Ocurrió un error al descargar el video.")
        finally:
            cleanup_files(safe_title)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja errores no capturados."""
    logger.error(f"Error en la actualización {update}: {context.error}")
    if update.message:
        await update.message.reply_text("❌ Ocurrió un error inesperado.")

# --------------------------
# Inicialización
# --------------------------

def main():
    """Configura y ejecuta el bot."""
    application = Application.builder().token(TOKEN).build()
    
    # Registro de handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_url))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_error_handler(error_handler)

    # Configuración de webhook (para Render)
    application.run_webhook(
        listen=HOST,
        port=PORT,
        url_path=TOKEN,
        webhook_url=f"https://videodown-77kj.onrender.com/{TOKEN}",
    )

if __name__ == "__main__":
    main()