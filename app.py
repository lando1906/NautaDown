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

from video_utils import sanitize_title, is_valid_video, prepare_download_command, cleanup_files

TOKEN = "7011073342:AAFvvoKngrMkFWGXQLgmtKRTcZrc48suP20"
DOWNLOAD_DIR = "downloads"
PORT = 10000
HOST = "0.0.0.0"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎬 Bot Descargador de Videos\n\n"
        "Envía una URL de YouTube, Vimeo, Twitter, etc. y te mostraré las calidades disponibles."
    )

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()

    if not url.startswith(("http://", "https://")):
        await update.message.reply_text("⚠️ Envía una URL válida.")
        return

    try:
        processing_msg = await update.message.reply_text("🔍 Obteniendo información del video...")

        cmd_info = ["yt-dlp", "--dump-json", "--no-playlist", "--skip-download", url]
        result = subprocess.run(cmd_info, capture_output=True, text=True, timeout=30)

        if result.returncode != 0:
            await processing_msg.edit_text("❌ Error al obtener información del video.")
            return

        video_info = json.loads(result.stdout)
        title = video_info.get("title", "Video sin título")
        duration = video_info.get("duration", 0)

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

        keyboard = [[InlineKeyboardButton(desc, callback_data=f"dl_{fid}")] for fid, desc in formats[:8]]
        keyboard.append([InlineKeyboardButton("❌ Cancelar", callback_data="cancel")])
        reply_markup = InlineKeyboardMarkup(keyboard)

        duration_str = f"{duration//60}:{duration%60:02d}" if duration else "Desconocida"

        await processing_msg.edit_text(
            f"📹 <b>{title}</b>\n⏱ Duración: {duration_str}\n\nSelecciona el formato:",
            reply_markup=reply_markup,
            parse_mode="HTML",
        )

        context.user_data["current_url"] = url
        context.user_data["video_title"] = title

    except Exception as e:
        logger.error(f"Error al procesar la URL: {e}")
        await update.message.reply_text("❌ Ocurrió un error al procesar la URL.")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = process.communicate(timeout=900)

            if process.returncode != 0 or not is_valid_video(file_path):
                error_msg = stderr.decode("utf-8")[:500]
                await downloading_msg.edit_text(
                    f"❌ Error al descargar o validar el video:\n\n<code>{error_msg}</code>",
                    parse_mode="HTML",
                )
                return

            file_size = os.path.getsize(file_path) / (1024 * 1024)

            if file_size > 2000:
                await downloading_msg.edit_text(
                    "⚠️ El video es demasiado grande (límite 2GB).\n\n"
                    f"Tamaño: {file_size:.1f}MB"
                )
            else:
                await context.bot.send_chat_action(chat_id=query.message.chat_id, action="upload_video")
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
            cleanup_files(sanitize_title(title))

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Error en la actualización {update}: {context.error}")
    if update.message:
        await update.message.reply_text("❌ Ocurrió un error inesperado.")

def main():
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_url))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_error_handler(error_handler)

    application.run_webhook(
        listen=HOST,
        port=PORT,
        url_path=TOKEN,
        webhook_url=f"https://videodown-77kj.onrender.com/{TOKEN}",
    )

if __name__ == "__main__":
    main()