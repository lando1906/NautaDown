import os
import re
import json
import asyncio
import logging
import subprocess
import shutil
from typing import Optional, Tuple, List
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ==================== CONFIGURACIÓN ====================
TOKEN = "8470331129:AAHBJWD_p9m7TMMYPD2iaBZBHLzCLUFpHQw"
DOWNLOAD_DIR = "downloads"
MAX_FILE_SIZE_MB = 2000  # Límite de 2GB (límite práctico de Telegram)
SUPPORTED_PLATFORMS = [
    "youtube.com", "youtu.be", "tiktok.com", "vm.tiktok.com",
    "instagram.com", "twitter.com", "x.com", "reddit.com",
    "facebook.com", "fb.watch", "vimeo.com", "dailymotion.com",
    "twitch.tv", "bilibili.com", "nicovideo.jp", "rumble.com"
]

# ==================== LOGGING CONFIG ====================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bot.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ==================== INICIALIZACIÓN ====================
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
logger.info(f"Directorio de descargas: {os.path.abspath(DOWNLOAD_DIR)}")

# ==================== FUNCIONES UTILITARIAS ====================
def sanitize_title(title: str) -> str:
    """Limpia el título para usarlo como nombre de archivo"""
    title = re.sub(r"[^\w\s-]", "", title.strip())
    title = re.sub(r"\s+", "_", title)
    return title[:100] or "untitled"

def is_supported_url(url: str) -> bool:
    """Verifica si la URL es de una plataforma soportada"""
    return any(platform in url.lower() for platform in SUPPORTED_PLATFORMS)

def prepare_download_command(url: str, format_id: str, safe_title: str) -> Tuple[List[str], str]:
    """Prepara el comando de yt-dlp para descargar el video"""
    output_path = os.path.join(DOWNLOAD_DIR, f"{safe_title}.%(ext)s")
    cmd = [
        "yt-dlp", "-f", format_id, 
        "-o", output_path,
        "--no-playlist",
        "--no-warnings",
        "--quiet",
        "--no-cache-dir",
        "--merge-output-format", "mp4",
        url
    ]
    return cmd, output_path.replace("%(ext)s", "mp4")

def is_valid_video(file_path: str) -> bool:
    """Verifica si el archivo de video es válido"""
    return (os.path.exists(file_path) and 
            os.path.getsize(file_path) > 100 * 1024 and
            file_path.endswith(('.mp4', '.mkv', '.webm')))

def cleanup_files(basename: str):
    """Limpia todos los archivos temporales relacionados con una descarga"""
    patterns = [".mp4", ".mkv", ".webm", ".part", ".temp", ".ytdl", ".jpg", ".png"]
    
    for pattern in patterns:
        file_path = os.path.join(DOWNLOAD_DIR, f"{basename}{pattern}")
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.info(f"Archivo limpiado: {file_path}")
            except Exception as e:
                logger.warning(f"Error limpiando {file_path}: {e}")
    
    # Limpiar directorios de thumbs
    thumb_dir = os.path.join(DOWNLOAD_DIR, f"{basename}thumbs")
    if os.path.isdir(thumb_dir):
        try:
            shutil.rmtree(thumb_dir, ignore_errors=True)
        except Exception as e:
            logger.warning(f"Error limpiando directorio thumbs: {e}")

# ==================== MANEJO DE DESCARGA ====================
progress_pattern = re.compile(
    r"\[download\]\s+(\d+\.\d+)%\s+of\s+~?([\d\.]+\w+)\s+at\s+([\d\.]+\w+/s)\s+ETA\s+([\d:]+)"
)

async def stream_download_progress(cmd: List[str], message, url: str, title: str) -> Optional[str]:
    """
    Ejecuta la descarga mostrando progreso en tiempo real
    Retorna la ruta del archivo descargado o None en caso de error
    """
    filepath = None
    last_progress = 0
    safe_title = sanitize_title(title)
    
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT
        )
        
        logger.info(f"Iniciando descarga: {url}")
        
        while True:
            line_bytes = await process.stdout.readline()
            if not line_bytes:
                break
                
            line = line_bytes.decode('utf-8', errors='ignore').strip()
            
            # Log detallado para depuración
            if any(x in line for x in ['[download]', 'ETA', 'Destination']):
                logger.debug(f"yt-dlp: {line}")
            
            # Extraer progreso
            match = progress_pattern.search(line)
            if match:
                percent, size, speed, eta = match.groups()
                current_progress = float(percent)
                
                if current_progress > last_progress + 2:  # Actualizar cada 2% para no spamear
                    last_progress = current_progress
                    try:
                        await message.edit_text(
                            f"⏳ **Descargando...**\n"
                            f"📏 **Tamaño:** {size}\n"
                            f"📊 **Progreso:** {percent}%\n"
                            f"⚡ **Velocidad:** {speed}\n"
                            f"⏱ **ETA:** {eta}",
                            parse_mode="Markdown"
                        )
                    except Exception as e:
                        logger.warning(f"No se pudo actualizar progreso: {e}")
            
            # Detectar ruta del archivo
            if "Destination:" in line:
                filepath = line.split("Destination:")[-1].strip()
            elif "has already been downloaded" in line:
                filepath = line.split("has already been downloaded")[0].strip()
            
            await asyncio.sleep(0.1)
        
        # Esperar que el proceso termine
        await process.wait()
        
        if process.returncode != 0:
            error_msg = f"Error en descarga (código: {process.returncode})"
            logger.error(error_msg)
            await safe_edit_message(message, "❌ **Error en la descarga**\nEl video podría estar restringido o ser muy largo.", parse_mode="Markdown")
            return None
            
    except asyncio.TimeoutError:
        logger.error("Timeout en la descarga")
        await safe_edit_message(message, "⏰ **Timeout excedido**\nEl video es demasiado largo o la conexión es lenta.", parse_mode="Markdown")
        return None
    except Exception as e:
        logger.error(f"Error inesperado en descarga: {e}")
        await safe_edit_message(message, "❌ **Error inesperado en la descarga**", parse_mode="Markdown")
        return None
    
    await safe_edit_message(message, "✅ **Descarga completada**", parse_mode="Markdown")
    return filepath

async def simulate_upload_progress(message, filepath: str, title: str):
    """Simula el progreso de subida a Telegram"""
    try:
        file_size = os.path.getsize(filepath)
        size_mb = file_size / (1024 * 1024)
        
        if size_mb > MAX_FILE_SIZE_MB:
            await safe_edit_message(
                message, 
                f"❌ **Video demasiado grande**\n"
                f"📦 **Tamaño:** {size_mb:.1f}MB\n"
                f"📏 **Límite:** {MAX_FILE_SIZE_MB}MB\n"
                f"⚠️ Reduce la calidad o elige otro formato",
                parse_mode="Markdown"
            )
            return False
        
        progress_steps = [10, 25, 45, 65, 80, 90, 95, 100]
        
        for progress in progress_steps:
            try:
                await message.edit_text(
                    f"📤 **Subiendo video...**\n"
                    f"🎥 **Título:** {title[:50]}{'...' if len(title) > 50 else ''}\n"
                    f"📦 **Tamaño:** {size_mb:.1f}MB\n"
                    f"📊 **Progreso:** {progress}%",
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.warning(f"No se pudo actualizar progreso de subida: {e}")
            
            await asyncio.sleep(1.5)
        
        return True
        
    except Exception as e:
        logger.error(f"Error en simulación de subida: {e}")
        return False

async def safe_edit_message(message, text: str, **kwargs):
    """Edita un mensaje de forma segura con manejo de errores"""
    try:
        await message.edit_text(text, **kwargs)
    except Exception as e:
        logger.warning(f"No se pudo editar mensaje: {e}")
        # Intentar enviar como nuevo mensaje si falla la edición
        try:
            await message.chat.send_message(text, **kwargs)
        except Exception as e2:
            logger.error(f"También falló enviar nuevo mensaje: {e2}")

# ==================== HANDLERS DE TELEGRAM ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mensaje de bienvenida"""
    welcome_text = """
    🎬 **Video Downloader Bot**
    
    **Soportado:** YouTube, TikTok, Instagram, Twitter/X, Reddit, Facebook, Vimeo, Twitch y más!
    
    **Cómo usar:**
    1. Envíame el enlace de un video
    2. Elige el formato deseado
    3. Espera a que se descargue y envíe
    
    **Límites:**
    • Máximo {}MB por video
    • Videos públicos sin restricciones
    
    ⚠️ **Solo para uso personal y educativo**
    """.format(MAX_FILE_SIZE_MB)
    
    await update.message.reply_text(welcome_text, parse_mode="Markdown")

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Procesa URLs de video"""
    url = update.message.text.strip()
    
    if not url.startswith(("http://", "https://")):
        await update.message.reply_text("❌ **URL inválida**\nDebe comenzar con http:// o https://", parse_mode="Markdown")
        return
    
    if not is_supported_url(url):
        platforms = ", ".join(sorted(set([p.split('.')[0] for p in SUPPORTED_PLATFORMS])))
        await update.message.reply_text(
            f"❌ **Plataforma no soportada**\n\n"
            f"**Soportadas:** {platforms}\n"
            f"**URL recibida:** {url[:50]}...",
            parse_mode="Markdown"
        )
        return
    
    msg = await update.message.reply_text("🔍 **Analizando video...**", parse_mode="Markdown")
    
    try:
        # Obtener información del video
        info_process = await asyncio.create_subprocess_exec(
            "yt-dlp", "--dump-json", "--no-playlist", "--skip-download", url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            timeout=30
        )
        
        stdout, stderr = await info_process.communicate()
        
        if info_process.returncode != 0:
            error_msg = stderr.decode() if stderr else "Error desconocido"
            logger.error(f"Error yt-dlp info: {error_msg}")
            await safe_edit_message(msg, "❌ **No se pudo obtener información**\nEl video podría ser privado o estar eliminado.", parse_mode="Markdown")
            return
        
        video_info = json.loads(stdout.decode())
        title = video_info.get("title", "Video sin título")
        duration = video_info.get("duration", 0)
        duration_str = f"{duration//60}:{duration%60:02d}" if duration else "Desconocida"
        
        # Obtener formatos disponibles
        formats_process = await asyncio.create_subprocess_exec(
            "yt-dlp", "--list-formats", url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            timeout=30
        )
        
        stdout, stderr = await formats_process.communicate()
        
        if formats_process.returncode != 0:
            await safe_edit_message(msg, "❌ **Error al obtener formatos disponibles**", parse_mode="Markdown")
            return
        
        formats_output = stdout.decode()
        buttons = []
        
        # Parsear formatos
        for line in formats_output.split('\n'):
            if ('video only' not in line.lower() and 
                ('mp4' in line.lower() or 'webm' in line.lower() or 'mkv' in line.lower())):
                parts = line.split()
                if len(parts) >= 2:
                    format_id = parts[0]
                    description = " ".join(parts[1:])
                    
                    if len(description) > 50:
                        description = description[:47] + "..."
                    
                    buttons.append([InlineKeyboardButton(
                        f"🎥 {description}", 
                        callback_data=f"dl_{format_id}"
                    )])
        
        if not buttons:
            await safe_edit_message(msg, "❌ **No hay formatos de video disponibles**", parse_mode="Markdown")
            return
        
        # Limitar a 6 opciones y añadir cancelar
        buttons = buttons[:6]
        buttons.append([InlineKeyboardButton("❌ Cancelar", callback_data="cancel")])
        
        keyboard = InlineKeyboardMarkup(buttons)
        
        await safe_edit_message(
            msg,
            f"📹 **{title}**\n"
            f"⏱ **Duración:** {duration_str}\n"
            f"🔗 **URL:** {url[:30]}...\n\n"
            f"**Selecciona el formato:**",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        
        # Guardar contexto
        context.user_data["url"] = url
        context.user_data["title"] = title
        context.user_data["message_id"] = msg.message_id
        
    except asyncio.TimeoutError:
        await safe_edit_message(msg, "⏰ **Timeout al analizar el video**\nIntenta nuevamente.", parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error procesando URL: {e}")
        await safe_edit_message(msg, "❌ **Error al procesar el video**", parse_mode="Markdown")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja las acciones de los botones inline"""
    query = update.callback_query
    await query.answer()
    
    user_data = context.user_data
    url = user_data.get("url")
    title = user_data.get("title", "video")
    
    if not url:
        await query.edit_message_text("❌ **URL no encontrada**\nEnvía el enlace nuevamente.", parse_mode="Markdown")
        return
    
    if query.data == "cancel":
        await query.edit_message_text("✅ **Operación cancelada**", parse_mode="Markdown")
        return
    
    if query.data.startswith("dl_"):
        format_id = query.data[3:]
        safe_title = sanitize_title(title)
        
        msg = await query.edit_message_text(
            f"⏳ **Iniciando descarga...**\n"
            f"🎥 **Título:** {title[:50]}{'...' if len(title) > 50 else ''}\n"
            f"📊 **Formato:** {format_id}",
            parse_mode="Markdown"
        )
        
        try:
            # Preparar y ejecutar descarga
            cmd, expected_path = prepare_download_command(url, format_id, safe_title)
            downloaded_path = await stream_download_progress(cmd, msg, url, title)
            
            if not downloaded_path or not is_valid_video(downloaded_path):
                if is_valid_video(expected_path):
                    downloaded_path = expected_path
                else:
                    await safe_edit_message(msg, "❌ **Error: Archivo inválido**", parse_mode="Markdown")
                    cleanup_files(safe_title)
                    return
            
            # Simular y realizar subida
            upload_success = await simulate_upload_progress(msg, downloaded_path, title)
            
            if upload_success:
                await context.bot.send_chat_action(query.message.chat.id, "upload_video")
                
                with open(downloaded_path, 'rb') as video_file:
                    await context.bot.send_video(
                        chat_id=query.message.chat.id,
                        video=video_file,
                        caption=f"🎥 **{title}**\n✅ Descargado via @{context.bot.username}",
                        parse_mode="Markdown",
                        supports_streaming=True
                    )
                
                await safe_edit_message(msg, "✅ **Video enviado correctamente**", parse_mode="Markdown")
            
            # Limpieza final
            cleanup_files(safe_title)
            
        except Exception as e:
            logger.error(f"Error en callback: {e}")
            await safe_edit_message(msg, "❌ **Error crítico al procesar el video**", parse_mode="Markdown")
            cleanup_files(safe_title)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancela cualquier operación en curso"""
    await update.message.reply_text("✅ **Operaciones canceladas**", parse_mode="Markdown")
    # Limpiar user_data
    context.user_data.clear()

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja errores no capturados"""
    logger.error(f"Error no capturado: {context.error}", exc_info=context.error)
    
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "❌ **Error interno del bot**\nPor favor, intenta nuevamente.",
                parse_mode="Markdown"
            )
        except:
            pass

# ==================== FUNCIÓN PRINCIPAL ====================
def main():
    """Función principal que inicia el bot"""
    try:
        # Crear aplicación
        application = Application.builder().token(TOKEN).build()
        
        # Añadir handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("cancel", cancel))
        application.add_handler(CommandHandler("help", start))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
        application.add_handler(CallbackQueryHandler(button_callback))
        
        # Manejo de errores
        application.add_error_handler(error_handler)
        
        # Información de inicio
        logger.info("=" * 50)
        logger.info("🎬 Video Downloader Bot - INICIANDO")
        logger.info(f"📁 Descargas en: {os.path.abspath(DOWNLOAD_DIR)}")
        logger.info(f"📏 Límite de tamaño: {MAX_FILE_SIZE_MB}MB")
        logger.info("=" * 50)
        
        # Iniciar polling
        print("\n🤖 Bot iniciado correctamente!")
        print("📍 Presiona Ctrl+C para detener\n")
        
        application.run_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES
        )
        
    except Exception as e:
        logger.critical(f"Error fatal al iniciar el bot: {e}")
        raise

if __name__ == "__main__":
    main()