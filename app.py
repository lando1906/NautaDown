import os
import secrets
from flask import Flask, request, jsonify, send_from_directory
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler
)
import logging

# Configuración Flask
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'storage'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

TOKEN = "7011073342:AAFvvoKngrMkFWGXQLgmtKRTcZrc48suP20"

# Base de datos simple
file_db = {}

def generate_id():
    return secrets.token_urlsafe(18)[:24]

# Handlers de Telegram (async ahora)
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_msg = """
    🚀 *Bienvenido a MiCloud Bot* 🚀

    Envíame cualquier archivo y te daré un enlace de descarga directa:
    `https://micloud.com/<ID-24-caracteres>`
    """
    keyboard = [
        [InlineKeyboardButton("🌐 Sitio Web", url="https://micloud.onrender.com")],
        [InlineKeyboardButton("📌 Ejemplo", callback_data='example')]
    ]
    await update.message.reply_text(
        welcome_msg,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard))

async def example(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.reply_text(
        "Ejemplo de enlace: https://micloud.com/aBcD1234eFgH5678iJkL9012")

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document = update.message.document
    file_id = generate_id()
    file_name = document.file_name
    
    # Descargar archivo
    file = await context.bot.get_file(document.file_id)
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], file_name)
    await file.download_to_drive(file_path)
    
    # Registrar en DB
    file_db[file_id] = file_name
    
    # Responder con enlace
    await update.message.reply_text(
        f"✅ *Archivo subido!*\n\n🔗 Enlace:\n`https://micloud.com/{file_id}`\n\n"
        f"📁 Nombre: `{file_name}`",
        parse_mode='Markdown')

# Configuración del Bot
application = Application.builder().token(TOKEN).build()

# Registro de handlers
application.add_handler(CommandHandler('start', start))
application.add_handler(MessageHandler(filters.Document.ALL, handle_file))
application.add_handler(CallbackQueryHandler(example, pattern='example'))

# Webhook para Flask
@app.route('/webhook', methods=['POST'])
async def telegram_webhook():
    json_data = await request.get_json()
    update = Update.de_json(json_data, application.bot)
    await application.process_update(update)
    return jsonify({"status": "ok"})

# Servidor de archivos
@app.route('/<file_id>')
def download_file(file_id):
    if file_id in file_db:
        return send_from_directory(
            app.config['UPLOAD_FOLDER'],
            file_db[file_id],
            as_attachment=True)
    return jsonify({"error": "File not found"}), 404

if __name__ == '__main__':
    if os.getenv('RENDER'):
        # Configuración para Render
        application.run_webhook(
            listen='0.0.0.0',
            port=int(os.getenv('PORT', 10000)),
            webhook_url=f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}/webhook"
        )
    else:
        # Modo desarrollo con polling
        application.run_polling()