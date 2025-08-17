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

# 🔥 Configuración Directa (Optimizada para Render)
TOKEN = "8470331129:AAHBJWD_p9m7TMMYPD2iaBZBHLzCLUFpHQw"
DOWNLOAD_DIR = "downloads"
PORT = 10000  # Render usa este puerto por defecto
WEBHOOK_URL = "https://videodown-77kj.onrender.com"  # Reemplaza con tu URL de Render

# ⚡ Configuración Avanzada de yt-dlp
YTDLP_CONFIG = [
    "--external-downloader", "aria2c",
    "--external-downloader-args", "-x16 -s16 -k1M",  # 16 conexiones paralelas
    "--no-warnings",
    "--format", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]",
    "--quiet"
]

# 📝 Configuración de Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# 🛠️ Funciones Esenciales
def sanitize_filename(title: str) -> str:
    """Limpia el título para crear nombres de archivo seguros"""
    return re.sub(r'[^\w\-_\. ]', '', title[:50]).strip().replace(' ', '_')

async def run_ytdlp(command: list) -> tuple:
    """Ejecuta yt-dlp de forma asíncrona"""
    process = await asyncio.create_subprocess_exec(
        "yt-dlp",
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    return await process.communicate()

# 💻 Handlers de Comandos
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja el comando /start"""
    await update.message.reply_text(
        "⚡ **Bot Descargador VIP**\n\n"
        "Envía el enlace de cualquier video y lo descargaré al instante con calidad premium.\n\n"
        "🔹 Soporte: YouTube, Twitter, TikTok, Instagram, etc.\n"
        "🚀 Velocidad: 16 conexiones paralelas (aria2c)",
        parse_mode="Markdown"
    )

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Procesa URLs de video"""
    url = update.message.text.strip()
    
    if not re.match(r'https?://\S+', url):
        return await update.message.reply_text("⚠️ URL inválida. Ejemplo: https://www.youtube.com/watch?v=...")

    msg = await update.message.reply_text("🔍 *Analizando video...*", parse_mode="Markdown")
    
    try:
        # Obtener metadatos del video
        stdout, _ = await run_ytdlp(["--dump-json", url])
        info = json.loads(stdout)
        
        # Crear menú de opciones
        keyboard = [
            [InlineKeyboardButton("🎥 Máxima Calidad", callback_data=f"best_{url}")],
            [InlineKeyboardButton("📱 720p (Optimizado)", callback_data=f"720_{url}")],
            [InlineKeyboardButton("🔊 Solo Audio", callback_data=f"audio_{url}")]
        ]
        
        await msg.edit_text(
            f"📌 **{info.get('title', 'Video')}**\n\n"
            f"⏱ Duración: {info.get('duration', 'N/A')}s\n"
            f"👁 Vistas: {info.get('view_count', 'N/A')}\n\n"
            "Seleccione calidad:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        
    except Exception as e:
        logger.error(f"Error: {e}")
        await msg.edit_text("❌ Error al procesar el video")

async def download_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja las descargas"""
    query = update.callback_query
    await query.answer()
    
    quality, url = query.data.split('_', 1)
    msg = await query.edit_message_text("⚡ *Iniciando descarga VIP...*", parse_mode="Markdown")
    
    try:
        # Configuración según calidad seleccionada
        if quality == "best":
            format_flag = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]"
            file_ext = ".mp4"
        elif quality == "720":
            format_flag = "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]"
            file_ext = "_720p.mp4"
        else:  # audio
            format_flag = "bestaudio[ext=m4a]"
            file_ext = ".m4a"
        
        # Generar nombre de archivo único
        file_name = f"dl_{query.id}{file_ext}"
        file_path = os.path.join(DOWNLOAD_DIR, file_name)
        
        # Comando de descarga
        cmd = [
            *YTDLP_CONFIG,
            "--format", format_flag,
            "--output", file_path,
            url
        ]
        
        # Ejecutar descarga
        await msg.edit_text("🚀 *Descargando con 16 conexiones...*", parse_mode="Markdown")
        await run_ytdlp(cmd)
        
        # Verificar archivo
        if not os.path.exists(file_path) or os.path.getsize(file_path) < 102400:  # 100KB mínimo
            raise ValueError("Archivo descargado inválido")
        
        # Enviar archivo
        await context.bot.send_chat_action(
            chat_id=query.message.chat_id,
            action="upload_video" if quality != "audio" else "upload_audio"
        )
        
        with open(file_path, "rb") as file:
            if quality == "audio":
                await context.bot.send_audio(
                    chat_id=query.message.chat_id,
                    audio=file,
                    caption="🎧 Audio descargado con calidad premium",
                    parse_mode="Markdown"
                )
            else:
                await context.bot.send_video(
                    chat_id=query.message.chat_id,
                    video=file,
                    caption=f"🎬 Video en {quality} | Descarga VIP",
                    supports_streaming=True,
                    parse_mode="Markdown"
                )
        
        await msg.delete()
        
    except Exception as e:
        logger.error(f"Error en descarga: {e}")
        await msg.edit_text("❌ Error VIP: No se completó la descarga")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

# 🚀 Inicialización del Bot
def main():
    # Crear directorio de descargas
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    
    # Configurar aplicación
    app = Application.builder().token(TOKEN).build()
    
    # Registrar handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    app.add_handler(CallbackQueryHandler(download_handler))
    
    # Modo Render (Webhook)
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TOKEN,
        webhook_url=f"{WEBHOOK_URL}/{TOKEN}"
    )

if __name__ == "__main__":
    main()