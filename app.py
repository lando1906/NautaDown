import os
import re
import json
import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
import yt_dlp
from collections import defaultdict
import time

TOKEN = "8470331129:AAHBJWD_p9m7TMMYPD2iaBZBHLzCLUFpHQw"
DOWNLOAD_DIR = "downloads"
PORT = 10000
WEBHOOK_URL = "https://videodown-77kj.onrender.com"

# Configuración mejorada de yt-dlp
YTDLP_CONFIG = {
    "outtmpl": os.path.join(DOWNLOAD_DIR, "%(id)s.%(ext)s"),
    "quiet": True,
    "no_warnings": True,
    "extractor_args": {
        "facebook": {
            "skip": ["auth", "webpage"]
        }
    },
    "external_downloader": "aria2c",
    "external_downloader_args": ["-x16", "-s16", "-k1M"],
    "progress_hooks": [lambda d: None],
}

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

download_data = {}
MAX_RETRIES = 3

def safe_compare(a, b):
    """Comparación segura que maneja valores None"""
    if a is None and b is None:
        return 0
    if a is None:
        return -1
    if b is None:
        return 1
    return (a > b) - (a < b)

def sanitize_filename(title: str) -> str:
    return re.sub(r'[^\w\-_\. ]', '', title[:50]).strip().replace(' ', '_')

async def get_video_info(url: str, retry_count: int = 0) -> dict:
    """Obtiene metadatos del video con manejo de errores mejorado"""
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extractor_args": {
            "facebook": {
                "skip": ["auth", "webpage"]
            }
        }
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return ydl.sanitize_info(info)
            
    except yt_dlp.utils.DownloadError as e:
        if retry_count < MAX_RETRIES:
            logger.warning(f"Reintentando ({retry_count + 1}/{MAX_RETRIES})...")
            await asyncio.sleep(2)
            return await get_video_info(url, retry_count + 1)
            
        logger.error(f"Error al obtener info: {str(e)}")
        raise Exception(f"No se pudo obtener información del video. Error: {str(e)}")
        
    except Exception as e:
        logger.error(f"Error inesperado al obtener info: {str(e)}")
        raise Exception(f"Error al procesar el enlace: {str(e)}")

async def get_format_size(format_entry: dict) -> float:
    filesize = format_entry.get('filesize') or format_entry.get('filesize_approx')
    return filesize / (1024 * 1024) if filesize else 0.0

def create_button_label(format_info: dict) -> str:
    """Crea una etiqueta descriptiva para el botón"""
    label_parts = []
    
    # Tipo de contenido
    if format_info['vcodec'] != 'none' and format_info['acodec'] != 'none':
        content_type = "🎥 Video+Audio"
    elif format_info['vcodec'] != 'none':
        content_type = "🎥 Video"
    else:
        content_type = "🔊 Audio"
    
    label_parts.append(content_type)
    
    # Resolución (si es video)
    if format_info.get('height'):
        label_parts.append(f"{format_info['height']}p")
    
    # Tamaño del archivo
    if format_info.get('size_mb', 0) > 0:
        label_parts.append(f"{format_info['size_mb']:.2f}MB")
    
    # Extensión del archivo
    if format_info.get('ext'):
        label_parts.append(format_info['ext'].upper())
    
    return ' • '.join(label_parts)

async def get_all_formats(info: dict) -> list:
    """Obtiene todos los formatos disponibles con manejo de errores"""
    formats = []
    
    # Asegurarse de que hay formatos disponibles
    if not info.get('formats'):
        if info.get('url'):  # Si hay una URL directa
            format_info = {
                'format_id': 'direct',
                'url': info['url'],
                'ext': info.get('ext', 'mp4'),
                'vcodec': info.get('vcodec', 'none'),
                'acodec': info.get('acodec', 'none'),
                'size_mb': await get_format_size(info),
                'protocol': info.get('protocol', 'direct'),
                'height': info.get('height'),
                'fps': info.get('fps'),
                'tbr': info.get('tbr')
            }
            formats.append(format_info)
        return formats
    
    for fmt in info.get('formats', []):
        try:
            if not fmt.get('format_id'):
                continue
                
            size_mb = await get_format_size(fmt)
            format_info = {
                'format_id': fmt['format_id'],
                'url': fmt['url'] if 'url' in fmt else info['original_url'],
                'height': fmt.get('height'),
                'ext': fmt.get('ext'),
                'vcodec': fmt.get('vcodec', 'none'),
                'acodec': fmt.get('acodec', 'none'),
                'size_mb': size_mb,
                'protocol': fmt.get('protocol'),
                'fps': fmt.get('fps'),
                'tbr': fmt.get('tbr')
            }
            formats.append(format_info)
        except Exception as e:
            logger.warning(f"Error al procesar formato {fmt.get('format_id')}: {str(e)}")
            continue
    
    return formats

async def create_keyboard(formats: list, page: int = 0, per_page: int = 8) -> InlineKeyboardMarkup:
    """Crea un teclado inline paginado con todos los formatos"""
    keyboard = []
    
    # Ordenar formatos de manera segura
    def sort_key(f):
        video_score = 0 if f['vcodec'] != 'none' else 1
        audio_score = 0 if f['acodec'] != 'none' else 1
        height = f.get('height', 0) or 0
        size_mb = f.get('size_mb', 0) or 0
        tbr = f.get('tbr', 0) or 0
        
        return (
            video_score,
            audio_score,
            height,
            size_mb,
            tbr
        )
    
    formats.sort(key=sort_key, reverse=True)
    
    # Paginación
    total_pages = (len(formats) + per_page - 1) // per_page
    start_idx = page * per_page
    end_idx = start_idx + per_page
    
    # ID único para esta solicitud
    request_id = str(int(time.time()))
    
    # Almacenar datos
    download_data[request_id] = {
        'formats': formats,
        'page': page,
        'total_pages': total_pages,
        'expiry': time.time() + 3600  # Expira en 1 hora
    }
    
    # Crear botones
    for fmt in formats[start_idx:end_idx]:
        label = create_button_label(fmt)
        callback_data = f"dl_{request_id}_{fmt['format_id']}"
        keyboard.append([InlineKeyboardButton(label, callback_data=callback_data)])
    
    # Botones de navegación
    if total_pages > 1:
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("⬅️ Anterior", callback_data=f"pg_{request_id}_{page-1}"))
        if page < total_pages - 1:
            nav_buttons.append(InlineKeyboardButton("Siguiente ➡️", callback_data=f"pg_{request_id}_{page+1}"))
        keyboard.append(nav_buttons)
    
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚡ **Bot Descargador VIP**\n\nEnvía un enlace de video para descargar.\n\nSoportado: YouTube, Facebook, Instagram, TikTok y más.",
        parse_mode="Markdown"
    )

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    logger.info(f"URL recibida: {url}")

    # Validación básica de URL
    if not re.match(r'https?://\S+', url):
        return await update.message.reply_text("⚠️ URL inválida. Ejemplo: https://www.youtube.com/watch?v=...")

    msg = await update.message.reply_text("🔍 *Analizando video...*", parse_mode="Markdown")

    try:
        info = await get_video_info(url)
        info['original_url'] = url
        
        if not info:
            raise ValueError("No se pudo obtener información del video")
            
        formats = await get_all_formats(info)
        
        if not formats:
            raise ValueError("No se encontraron formatos descargables")
        
        keyboard = await create_keyboard(formats)
        
        await msg.edit_text(
            f"📌 **{info.get('title', 'Video')[:100]}**\n\n"
            f"🕒 Duración: {info.get('duration', 'N/A')}s\n"
            "Selecciona formato:",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )

    except Exception as e:
        logger.error(f"Error en handle_url: {str(e)}", exc_info=True)
        
        error_msg = "❌ Error: "
        if "Unsupported URL" in str(e):
            error_msg += "Este tipo de enlace no es soportado. Prueba con YouTube, Facebook, Instagram o TikTok."
        elif "private" in str(e).lower():
            error_msg += "El video parece ser privado o no está disponible."
        else:
            error_msg += f"Ocurrió un error al procesar el enlace. Detalles: {str(e)}"
            
        await msg.edit_text(error_msg)

async def handle_page_change(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    try:
        _, request_id, page = query.data.split('_')
        page = int(page)
        
        if request_id not in download_data or time.time() > download_data[request_id]['expiry']:
            await query.edit_message_text("❌ Los datos han expirado. Envía el enlace nuevamente.")
            return
            
        formats = download_data[request_id]['formats']
        keyboard = await create_keyboard(formats, page)
        
        await query.edit_message_reply_markup(reply_markup=keyboard)
    except Exception as e:
        logger.error(f"Error al cambiar página: {str(e)}")
        await query.edit_message_text("❌ Error al cargar formatos")

async def download_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    try:
        _, request_id, format_id = query.data.split('_')
        
        if request_id not in download_data or time.time() > download_data[request_id]['expiry']:
            await query.edit_message_text("❌ Los datos han expirado. Envía el enlace nuevamente.")
            return
            
        selected_format = next(
            (fmt for fmt in download_data[request_id]['formats'] if fmt['format_id'] == format_id), 
            None
        )
        
        if not selected_format:
            await query.edit_message_text("❌ Formato no disponible. Elige otro.")
            return
            
        url = selected_format['url']
        file_type = 'video' if selected_format['vcodec'] != 'none' else 'audio'
        
    except Exception as e:
        logger.error(f"Error en download_handler: {str(e)}")
        await query.edit_message_text("❌ Error al procesar la solicitud.")
        return

    msg = await query.edit_message_text("⚡ *Preparando descarga...*", parse_mode="Markdown")
    file_path = ""

    try:
        progress_data = {"last_update": 0, "msg": msg}
        async def progress_hook(d):
            nonlocal progress_data
            current_time = asyncio.get_event_loop().time()
            if current_time - progress_data["last_update"] >= 0.80:
                progress_data["last_update"] = current_time
                await update_progress_message(progress_data["msg"], d)

        ydl_opts = {
            **YTDLP_CONFIG,
            "format": format_id,
            "progress_hooks": [progress_hook],
            "extractor_args": {
                "facebook": {
                    "skip": ["auth", "webpage"]
                }
            }
        }
        
        file_ext = selected_format.get('ext', 'mp4' if file_type == 'video' else 'm4a')
        file_name = f"dl_{query.id}.{file_ext}"
        file_path = os.path.join(DOWNLOAD_DIR, file_name)
        ydl_opts["outtmpl"] = file_path

        await context.bot.send_chat_action(
            chat_id=query.message.chat_id,
            action="upload_video" if file_type == 'video' else "upload_audio"
        )

        loop = asyncio.get_event_loop()
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            await loop.run_in_executor(None, lambda: ydl.download([url]))

        if not os.path.exists(file_path):
            raise ValueError("El archivo no se descargó correctamente")

        file_size = os.path.getsize(file_path) / (1024 * 1024)
        if file_size < 0.1:
            raise ValueError("Archivo demasiado pequeño, posible error")

        with open(file_path, "rb") as file:
            if file_type == 'audio':
                await context.bot.send_audio(
                    chat_id=query.message.chat_id,
                    audio=file,
                    caption="🎧 Audio descargado"
                )
            else:
                await context.bot.send_video(
                    chat_id=query.message.chat_id,
                    video=file,
                    caption="🎬 Video descargado",
                    supports_streaming=True
                )

        await msg.delete()

    except Exception as e:
        logger.error(f"Error en descarga: {str(e)}", exc_info=True)
        error_msg = "❌ Error al descargar: "
        if "private" in str(e).lower():
            error_msg += "El video parece ser privado o no está disponible."
        elif "unavailable" in str(e).lower():
            error_msg += "El video no está disponible."
        else:
            error_msg += str(e)
        await msg.edit_text(error_msg)
    finally:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
        # Limpiar datos antiguos
        for req_id in list(download_data.keys()):
            if time.time() > download_data[req_id]['expiry']:
                del download_data[req_id]

async def update_progress_message(msg, status: dict):
    try:
        if status.get('status') == 'downloading':
            downloaded = status.get('downloaded_bytes', 0) / (1024 * 1024)
            total = status.get('total_bytes', status.get('total_bytes_estimate', 0)) / (1024 * 1024)
            percentage = (downloaded / total * 100) if total > 0 else 0
            speed = status.get('speed', 0) / (1024 * 1024) if status.get('speed') else 0
            eta = status.get('eta', 'N/A')
            text = (
                f"🚀 *Descargando...*\n"
                f"📊 Progreso: {percentage:.1f}%\n"
                f"💾 Descargado: {downloaded:.2f}MB / {total:.2f}MB\n"
                f"⚡ Velocidad: {speed:.2f}MB/s\n"
                f"⏰ ETA: {eta}s"
            )
        elif status.get('status') == 'finished':
            text = "✅ *Descarga completada, enviando archivo...*"
        else:
            text = "⚡ *Preparando descarga...*"
        
        await msg.edit_text(text, parse_mode="Markdown")
    except Exception as e:
        logger.debug(f"No se pudo actualizar mensaje: {e}")

def cleanup_old_data():
    """Limpia datos expirados"""
    current_time = time.time()
    for req_id in list(download_data.keys()):
        if current_time > download_data[req_id]['expiry']:
            del download_data[req_id]

def main():
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    # Verificar y actualizar yt-dlp
    logger.info("Verificando yt-dlp...")
    try:
        yt_dlp.YoutubeDL().update()
    except Exception as e:
        logger.warning(f"No se pudo actualizar yt-dlp: {str(e)}")

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    app.add_handler(CallbackQueryHandler(handle_page_change, pattern=r'^pg_'))
    app.add_handler(CallbackQueryHandler(download_handler, pattern=r'^dl_'))

    # Limpieza periódica
    app.job_queue.run_repeating(
        lambda _: cleanup_old_data(),
        interval=3600,
        first=10
    )

    logger.info("Iniciando bot en modo webhook...")
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TOKEN,
        webhook_url=f"{WEBHOOK_URL}/{TOKEN}",
        secret_token="WEBHOOK_SECRET"
    )

if __name__ == "__main__":
    logger.info("=== Iniciando Bot ===")
    main()