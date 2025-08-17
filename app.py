import os
import re
import json
import asyncio
import logging
import time
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

# Configuración
TOKEN = "8470331129:AAHBJWD_p9m7TMMYPD2iaBZBHLzCLUFpHQw"
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Regex para progreso de descarga
progress_pattern = re.compile(
    r"\[download\]\s+(\d+\.\d+)%\s+of\s+~?([\d\.]+\w+)\s+at\s+([\d\.]+\w+\/s)\s+ETA\s+([\d:]+)"
)

# --------------------------
# Funciones Clave
# --------------------------

def sanitize_title(title: str) -> str:
    """Limpia el título para usarlo como nombre de archivo."""
    return re.sub(r"[^\w\s-]", "", title)[:100].replace(" ", "_")

async def run_command(cmd: list) -> tuple[str, str]:
    """Ejecuta un comando y retorna (stdout, stderr)."""
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await process.communicate()
    return stdout.decode(), stderr.decode()

async def stream_download_progress(cmd: list, message: Message) -> Optional[str]:
    """Muestra el progreso de descarga en tiempo real."""
    filepath = None
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT
    )

    last_update = 0
    while True:
        line = (await process.stdout.readline()).decode().strip()
        if not line:
            if process.returncode is not None:
                break
            await asyncio.sleep(0.1)
            continue

        # Actualizar progreso cada 1 segundo
        if time.time() - last_update >= 1:
            if match := progress_pattern.search(line):
                percent, size, speed, eta = match.groups()
                text = (
                    f"⏳ **Descargando...**\n\n"
                    f"📏 **Tamaño:** `{size}`\n"
                    f"📊 **Progreso:** `{percent}%`\n"
                    f"⚡ **Velocidad:** `{speed}`\n"
                    f"⏱ **ETA:** `{eta}`"
                )
                try:
                    await message.edit_text(text, parse_mode="Markdown")
                    last_update = time.time()
                except Exception as e:
                    logger.error(f"Error editando mensaje: {e}")

        # Detectar ruta del archivo
        if "[download] Destination:" in line:
            filepath = line.split("Destination:")[-1].strip()

    if process.returncode != 0:
        if filepath and os.path.exists(filepath):
            os.remove(filepath)
        await message.edit_text("❌ **Error en la descarga**", parse_mode="Markdown")
        return None

    await message.edit_text("✅ **Descarga completada**\n📤 **Enviando video...**", parse_mode="Markdown")
    return filepath

# --------------------------
# Handlers de Telegram
# --------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja el comando /start."""
    await update.message.reply_text(
        "🎬 **Bot Descargador de Videos**\n\n"
        "Envía un enlace de YouTube, Twitter, TikTok, etc. y te lo descargaré al instante.\n\n"
        "⚡ **Velocidad máxima garantizada**"
    )

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Procesa la URL y muestra formatos disponibles."""
    url = update.message.text.strip()
    if not url.startswith(("http://", "https://")):
        await update.message.reply_text("⚠️ **Envía una URL válida.**")
        return

    msg = await update.message.reply_text("🔍 **Analizando video...**")

    try:
        # Obtener metadatos
        stdout, _ = await run_command([
            "yt-dlp", "--dump-json", "--no-playlist", url
        ])
        video_info = json.loads(stdout)
        title = video_info.get("title", "video")

        # Obtener formatos
        stdout, _ = await run_command([
            "yt-dlp", "--list-formats", "--format-sort", "vcodec:h264,res,br", url
        ])

        # Parsear formatos
        formats = []
        for line in stdout.split("\n"):
            if "audio only" in line.lower() or "video only" in line.lower():
                parts = [p for p in line.split() if p]
                if len(parts) >= 3:
                    format_id = parts[0]
                    resolution = next((p for p in parts if "x" in p), "?")
                    size = next((p for p in parts if "MiB" in p or "KiB" in p), "?MB")
                    desc = f"{resolution} | {size}"
                    formats.append((format_id, desc))

        if not formats:
            await msg.edit_text("❌ **No se encontraron formatos disponibles.**")
            return

        # Crear teclado
        keyboard = [
            [InlineKeyboardButton(desc, callback_data=f"dl_{fid}")]
            for fid, desc in formats[:8]
        ]
        keyboard.append([InlineKeyboardButton("❌ Cancelar", callback_data="cancel")])

        await msg.edit_text(
            f"🎥 **{title}**\n\nSelecciona un formato:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        context.user_data["url"] = url
        context.user_data["title"] = title

    except Exception as e:
        logger.error(f"Error: {e}")
        await msg.edit_text("❌ **Error al procesar el video.**")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja la selección de formato."""
    query = update.callback_query
    await query.answer()

    if query.data == "cancel":
        await query.edit_message_text("✅ **Operación cancelada.**")
        return

    if query.data.startswith("dl_"):
        format_id = query.data.split("_")[1]
        url = context.user_data.get("url")
        title = context.user_data.get("title", "video")

        if not url:
            await query.edit_message_text("❌ **URL no encontrada.**")
            return

        msg = await query.edit_message_text("⚡ **Preparando descarga...**")

        try:
            safe_title = sanitize_title(title)
            output = os.path.join(DOWNLOAD_DIR, f"{safe_title}.mp4")
            cmd = [
                "yt-dlp",
                "-f", format_id,
                "-o", output,
                "--no-playlist",
                "--external-downloader", "aria2c",  # ¡Más velocidad!
                "--external-downloader-args", "-x16 -s16 -k1M",
                url
            ]

            # Descargar con progreso
            filepath = await stream_download_progress(cmd, msg)

            if not filepath or not os.path.exists(filepath):
                return

            # Enviar video
            await context.bot.send_chat_action(
                chat_id=query.message.chat_id,
                action="upload_video"
            )
            with open(filepath, "rb") as video:
                await context.bot.send_video(
                    chat_id=query.message.chat_id,
                    video=video,
                    caption=f"🎥 **{title}**",
                    supports_streaming=True,
                    parse_mode="Markdown"
                )
            await msg.delete()

        except Exception as e:
            logger.error(f"Error: {e}")
            await msg.edit_text("❌ **Error al enviar el video.**")
        finally:
            if filepath and os.path.exists(filepath):
                os.remove(filepath)

# --------------------------
# Inicialización
# --------------------------

def main():
    app = Application.builder().token(TOKEN).build()

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    app.add_handler(CallbackQueryHandler(button_callback))

    # Iniciar bot
    app.run_polling()

if __name__ == "__main__":
    main()