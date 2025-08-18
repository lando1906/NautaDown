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

TOKEN = "8470331129:AAHBJWD_p9m7TMMYPD2iaBZBHLzCLUFpHQw"
DOWNLOAD_DIR = "downloads"
PORT = 10000
WEBHOOK_URL = "https://videodown-77kj.onrender.com"

# Configuración de yt-dlp
YTDLP_CONFIG = {
    "outtmpl": os.path.join(DOWNLOAD_DIR, "%(id)s.%(ext)s"),
    "quiet": True,
    "no_warnings": True,
    "external_downloader": "aria2c",
    "external_downloader_args": ["-x16", "-s16", "-k1M"],
    "progress_hooks": [lambda d: None],
}

# Configuración de Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Almacenamiento temporal para paginación
temp_data = {}

def sanitize_filename(title: str) -> str:
    return re.sub(r'[^\w\-_\. ]', '', title[:50]).strip().replace(' ', '_')

async def get_video_info(url: str) -> dict:
    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
            return ydl.sanitize_info(info)
        except Exception as e:
            logger.error(f"Error al obtener info: {str(e)}")
            raise

async def get_format_size(format_entry: dict) -> float:
    filesize = format_entry.get('filesize') or format_entry.get('filesize_approx')
    return filesize / (1024 * 1024) if filesize else 0.0

def create_button_label(format_info: dict) -> str:
    """Crea una etiqueta legible para el botón"""
    height = format_info.get('height', '')
    ext = format_info.get('ext', '')
    size_mb = format_info.get('size_mb', 0)
    
    parts = []
    if height:
        parts.append(f"{height}p")
    if size_mb > 0:
        parts.append(f"{size_mb:.2f}MB")
    if ext:
        parts.append(ext.upper())
    
    return '•'.join(parts) if parts else "Descargar"

async def organize_formats(formats: list) -> dict:
    """Organiza los formatos por tipo y calidad"""
    organized = defaultdict(list)
    
    for fmt in formats:
        if not fmt.get('format_id'):
            continue
            
        size_mb = await get_format_size(fmt)
        format_info = {
            'format_id': fmt['format_id'],
            'height': fmt.get('height'),
            'ext': fmt.get('ext'),
            'vcodec': fmt.get('vcodec'),
            'acodec': fmt.get('acodec'),
            'size_mb': size_mb
        }
        
        # Clasificar el formato
        if fmt.get('vcodec') != 'none' and fmt.get('acodec') != 'none':
            key = f"video_{fmt.get('height', 0)}"
        elif fmt.get('vcodec') != 'none':
            key = f"video_{fmt.get('height', 0)}"
        elif fmt.get('acodec') != 'none':
            key = "audio"
        else:
            continue
            
        organized[key].append(format_info)
    
    return organized

async def create_keyboard(organized_formats: dict, url: str, page: int = 0, per_page: int = 8) -> InlineKeyboardMarkup:
    """Crea un teclado inline paginado"""
    keyboard = []
    all_formats = []
    
    # Agregar formatos de video ordenados por calidad
    video_keys = [k for k in organized_formats if k.startswith('video')]
    for key in sorted(video_keys, key=lambda x: int(x.split('_')[1]), reverse=True):
        all_formats.extend(organized_formats[key])
    
    # Agregar formatos de audio
    if 'audio' in organized_formats:
        all_formats.extend(organized_formats['audio'])
    
    # Paginación
    total_pages = (len(all_formats) + per_page - 1) // per_page
    start_idx = page * per_page
    end_idx = start_idx + per_page
    
    for fmt in all_formats[start_idx:end_idx]:
        label = create_button_label(fmt)
        callback_data = json.dumps({
            'f': fmt['format_id'],
            'u': url,
            't': 'video' if fmt.get('vcodec') != 'none' else 'audio'
        }).encode('utf-8')[:64].decode('utf-8', 'ignore')
        
        keyboard.append([InlineKeyboardButton(label, callback_data=callback_data)])
    
    # Botones de navegación si hay múltiples páginas
    if total_pages > 1:
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("⬅️ Anterior", callback_data=f"page_{page-1}_{url}"))
        if page < total_pages - 1:
            nav_buttons.append(InlineKeyboardButton("Siguiente ➡️", callback_data=f"page_{page+1}_{url}"))
        keyboard.append(nav_buttons)
    
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚡ **Bot Descargador VIP**\n\nEnvía un enlace de video para descargar.",
        parse_mode="Markdown"
    )

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    logger.info(f"URL recibida: {url}")

    if not re.match(r'https?://\S+', url):
        logger.warning(f"URL inválida: {url}")
        return await update.message.reply_text("⚠️ URL inválida. Ejemplo: https://www.youtube.com/watch?v=...")

    msg = await update.message.reply_text("🔍 *Analizando video...*", parse_mode="Markdown")

    try:
        info = await get_video_info(url)
        logger.info(f"Video analizado: {info.get('title')}")

        formats = info.get('formats', [])
        organized = await organize_formats(formats)
        
        if not organized:
            raise ValueError("No hay formatos disponibles para descargar")
        
        keyboard = await create_keyboard(organized, url)
        
        await msg.edit_text(
            f"📌 **{info.get('title', 'Video')}**\n\n"
            f"🕒 {info.get('duration', 'N/A')}s | 👁 {info.get('view_count', 'N/A')} vistas\n"
            "Selecciona formato:",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )

    except Exception as e:
        logger.error(f"Error en handle_url: {str(e)}", exc_info=True)
        await msg.edit_text(f"❌ Error: {str(e)}")

async def handle_page_change(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    _, page, url = query.data.split('_', 2)
    page = int(page)
    
    msg = query.message
    await msg.edit_text("🔍 Reorganizando formatos...")
    
    try:
        info = await get_video_info(url)
        formats = info.get('formats', [])
        organized = await organize_formats(formats)
        
        keyboard = await create_keyboard(organized, url, page)
        
        await msg.edit_text(
            f"📌 **{info.get('title', 'Video')}**\n\n"
            f"🕒 {info.get('duration', 'N/A')}s | 👁 {info.get('view_count', 'N/A')} vistas\n"
            "Selecciona formato:",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error al cambiar página: {str(e)}")
        await msg.edit_text("❌ Error al cargar formatos")

async def update_progress_message(msg, status: dict):
    if status.get('status') == 'downloading':
        downloaded = status.get('downloaded_bytes', 0) / (1024 * 1024)
        total = status.get('total_bytes', status.get('total_bytes_estimate', 0)) / (1024 * 1024)
        percentage = (downloaded / total * 100) if total > 0 else 0
        speed = status.get('speed', 0) / (1024 * 1024) if status.get('speed') else 0
        eta = status.get('eta', 'N/A')
        text = (
            f"🚀 *Descargando...*\n"
            f"📊 Progreso: {percentage:.1f}%\n"
            f"💾 Descargado: {downloaded:.2f} MB / {total:.2f} MB\n"
            f"⚡ Velocidad: {speed:.2f} MB/s\n"
            f"⏰ ETA: {eta}s"
        )
    elif status.get('status') == 'finished':
        text = "✅ *Descarga completada, enviando archivo...*"
    else:
        text = "⚡ *Preparando descarga...*"
    try:
        await msg.edit_text(text, parse_mode="Markdown")
    except Exception as e:
        logger.debug(f"No se pudo actualizar mensaje: {e}")

async def download_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    try:
        data = json.loads(query.data)
        format_id = data['f']
        url = data['u']
        file_type = data.get('t', 'video')
    except:
        await query.edit_message_text("❌ Datos inválidos. Intenta de nuevo.")
        return

    logger.info(f"Iniciando descarga: Formato={format_id}, URL={url}")
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

        ydl_opts = {**YTDLP_CONFIG, "format": format_id, "progress_hooks": [progress_hook]}
        file_ext = ".m4a" if file_type == 'audio' else ".mp4"
        file_name = f"dl_{query.id}{file_ext}"
        file_path = os.path.join(DOWNLOAD_DIR, file_name)
        ydl_opts["outtmpl"] = file_path

        await context.bot.send_chat_action(
            chat_id=query.message.chat_id,
            action="upload_video" if file_type == 'video' else "upload_audio"
        )

        loop = asyncio.get_event_loop()
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = await loop.run_in_executor(None, lambda: ydl.download([url]))

        if not os.path.exists(file_path):
            raise ValueError("El archivo no se creó")

        file_size = os.path.getsize(file_path) / (1024 * 1024)
        logger.info(f"Archivo descargado: {file_path} ({file_size:.2f} MB)")

        if file_size < 0.1:
            raise ValueError("Archivo demasiado pequeño (posible error)")

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
        await msg.edit_text(f"❌ Error al descargar: {str(e)}")
    finally:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)

def main():
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    logger.info("Verificando dependencias...")
    if not os.path.exists("/usr/local/bin/yt-dlp"):
        logger.warning("yt-dlp no encontrado. Instalando...")
        os.system("pip install yt-dlp && yt-dlp -U")

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    app.add_handler(CallbackQueryHandler(handle_page_change, pattern=r'^page_\d+_'))
    app.add_handler(CallbackQueryHandler(download_handler))

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