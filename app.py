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

TOKEN = "8470331129:AAHBJWD_p9m7TMMYPD2iaBZBHLzCLUFpHQw"
DOWNLOAD_DIR = "downloads"
PORT = 10000
WEBHOOK_URL = "https://videodown-77kj.onrender.com"

# ⚡ Configuración Avanzada de yt-dlp
YTDLP_CONFIG = {
    "outtmpl": os.path.join(DOWNLOAD_DIR, "%(id)s.%(ext)s"),
    "quiet": True,
    "no_warnings": True,
    "external_downloader": "aria2c",
    "external_downloader_args": ["-x16", "-s16", "-k1M"],
    "progress_hooks": [lambda d: None],  # Placeholder, será configurado dinámicamente
}

# 📝 Configuración de Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG
)
logger = logging.getLogger(__name__)

# 🛠️ Funciones Esenciales
def sanitize_filename(title: str) -> str:
    return re.sub(r'[^\w\-_\. ]', '', title[:50]).strip().replace(' ', '_')

async def get_video_info(url: str) -> dict:
    """Obtiene metadatos del video con yt-dlp."""
    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
            return ydl.sanitize_info(info)
        except Exception as e:
            logger.error(f"Error al obtener info: {str(e)}")
            raise

async def get_format_size(format_entry: dict) -> float:
    """Obtiene el tamaño estimado de un formato en MB."""
    filesize = format_entry.get('filesize') or format_entry.get('filesize_approx')
    return filesize / (1024 * 1024) if filesize else 0.0

# 💻 Handlers de Comandos
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
        logger.info(f"Video analizado: {info.get('title')} (Duración: {info.get('duration')}s)")
        
        # Obtener formatos disponibles
        formats = info.get('formats', [])
        keyboard = []
        
        # Filtrar formatos relevantes (MP4 para video, M4A para audio)
        for fmt in formats:
            if fmt.get('ext') in ['mp4', 'm4a'] and fmt.get('format_id'):
                # Determinar tipo y etiqueta
                if fmt.get('vcodec') != 'none' and fmt.get('ext') == 'mp4':
                    height = fmt.get('height')
                    label = f"🎥 {height}p" if height else "🎥 Video"
                elif fmt.get('acodec') != 'none' and fmt.get('vcodec') == 'none' and fmt.get('ext') == 'm4a':
                    label = "🔊 Audio"
                else:
                    continue
                
                size_mb = await get_format_size(fmt)
                size_text = f" ({size_mb:.2f} MB)" if size_mb > 0 else ""
                keyboard.append([InlineKeyboardButton(
                    f"{label}{size_text}",
                    callback_data=f"{fmt['format_id']}_{url}"
                )])
        
        if not keyboard:
            raise ValueError("No hay formatos disponibles para descargar")
        
        await msg.edit_text(
            f"📌 **{info.get('title', 'Video')}**\n\n"
            f"🕒 {info.get('duration', 'N/A')}s | 👁 {info.get('view_count', 'N/A')} vistas\n"
            "Selecciona formato:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        
    except Exception as e:
        logger.error(f"Error en handle_url: {str(e)}", exc_info=True)
        await msg.edit_text(f"❌ Error: {str(e)}")

async def update_progress_message(msg, status: dict):
    """Actualiza el mensaje con el progreso de la descarga."""
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
    
    format_id, url = query.data.split('_', 1)
    logger.info(f"Iniciando descarga: Formato={format_id}, URL={url}")
    
    msg = await query.edit_message_text("⚡ *Preparando descarga...*", parse_mode="Markdown")
    file_path = ""
    
    try:
        # Configurar el progress hook
        progress_data = {"last_update": 0, "msg": msg}
        async def progress_hook(d):
            nonlocal progress_data
            current_time = asyncio.get_event_loop().time()
            if current_time - progress_data["last_update"] >= 0.80:
                progress_data["last_update"] = current_time
                await update_progress_message(progress_data["msg"], d)
        
        ydl_opts = {**YTDLP_CONFIG, "format": format_id, "progress_hooks": [progress_hook]}
        file_ext = ".m4a" if format_id.startswith("bestaudio") else ".mp4"
        file_name = f"dl_{query.id}{file_ext}"
        file_path = os.path.join(DOWNLOAD_DIR, file_name)
        ydl_opts["outtmpl"] = file_path
        
        # Descargar
        await context.bot.send_chat_action(
            chat_id=query.message.chat_id,
            action="upload_video" if not format_id.startswith("bestaudio") else "upload_audio"
        )
        
        loop = asyncio.get_event_loop()
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = await loop.run_in_executor(None, lambda: ydl.download([url]))
        
        # Validar archivo
        if not os.path.exists(file_path):
            raise ValueError("El archivo no se creó")
        
        file_size = os.path.getsize(file_path) / (1024 * 1024)  # MB
        logger.info(f"Archivo descargado: {file_path} ({file_size:.2f} MB)")
        
        if file_size < 0.1:
            raise ValueError("Archivo demasiado pequeño (posible error)")
        
        # Enviar archivo
        with open(file_path, "rb") as file:
            if format_id.startswith("bestaudio"):
                await context.bot.send_audio(
                    chat_id=query.message.chat_id,
                    audio=file,
                    caption="🎧 Audio descargado"
                )
            else:
                await context.bot.send_video(
                    chat_id=query.message.chat_id,
                    video=file,
                    caption=f"🎬 Video en formato {format_id}",
                    supports_streaming=True
                )
        
        await msg.delete()
        
    except Exception as e:
        logger.error(f"Error en descarga: {str(e)}", exc_info=True)
        await msg.edit_text(f"❌ Error al descargar: {str(e)}")
    finally:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
            logger.debug(f"Archivo temporal eliminado: {file_path}")

# 🚀 Inicialización
def main():
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    
    logger.info("Verificando dependencias...")
    if not os.path.exists("/usr/local/bin/yt-dlp"):
        logger.warning("yt-dlp no encontrado. Instalando...")
        os.system("pip install yt-dlp && yt-dlp -U")
    
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
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