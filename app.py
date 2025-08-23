import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
import yt_dlp
import os

BOT_TOKEN = "8470331129:AAHBJWD_p9m7TMMYPD2iaBZBHLzCLUFpHQw"
WEBHOOK_URL = "https://videodown-77kj.onrender.com/"  # Reemplaza con tu URL real

logging.basicConfig(level=logging.INFO)

async def download_video(url: str) -> str:
    os.makedirs("downloads", exist_ok=True)
    ydl_opts = {
        'outtmpl': 'downloads/%(title)s.%(ext)s',
        'format': 'bestvideo+bestaudio/best',
        'quiet': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return ydl.prepare_filename(info)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎬 Envíame un enlace de video para descargarlo.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    await update.message.reply_text("⏳ Descargando...")
    try:
        filepath = await download_video(url)
        await update.message.reply_document(document=open(filepath, 'rb'))
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error: {e}")

async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Configura webhook
    await app.bot.set_webhook(url=f"{WEBHOOK_URL}/webhook")
    await app.start()
    await app.updater.start_webhook(
        listen="0.0.0.0",
        port=int(os.environ.get("PORT", 10000)),
        webhook_url=f"{WEBHOOK_URL}/webhook"
    )
    await app.updater.idle()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())