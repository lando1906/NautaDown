import os
import requests
from telegram import Update, InputFile
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

# 🔐 Token desde variable de entorno
TOKEN = os.getenv("BOT_TOKEN")

# 📤 Subir archivo a Uguu
def upload_to_uguu(file_path):
    with open(file_path, 'rb') as f:
        response = requests.post("https://uguu.se/api.php?d=upload-tool", files={"file": f})
    return response.text if response.status_code == 200 else None

# 📥 Descargar archivo desde link directo
def download_file(url, filename="descarga.tmp"):
    response = requests.get(url, stream=True)
    if response.status_code == 200:
        with open(filename, 'wb') as f:
            for chunk in response.iter_content(1024):
                f.write(chunk)
        return filename
    return None

# 🤖 Manejar mensajes
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message

    # Si hay documento adjunto
    if message.document:
        file = await message.document.get_file()
        file_path = f"temp_{message.document.file_name}"
        await file.download_to_drive(file_path)

        link = upload_to_uguu(file_path)
        os.remove(file_path)

        if link:
            await message.reply_text(f"✅ Archivo subido a Uguu:\n{link}")
        else:
            await message.reply_text("❌ Error al subir el archivo.")

    # Si el mensaje es un link directo
    elif message.text and message.text.startswith("http"):
        filename = download_file(message.text)
        if filename:
            await message.reply_document(InputFile(filename))
            os.remove(filename)
        else:
            await message.reply_text("❌ No se pudo descargar el archivo.")

# 🚀 Inicializar bot
def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.ALL, handle_message))
    print("🤖 Bot activo en Render...")
    app.run_polling()

if __name__ == "__main__":
    main()