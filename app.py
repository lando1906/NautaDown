import os
import secrets
from flask import Flask, request, jsonify
from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, MessageHandler, filters, CallbackContext, Dispatcher
import threading
import logging

# Configuración
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'storage'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

TOKEN = "7011073342:AAFvvoKngrMkFWGXQLgmtKRTcZrc48suP20"
bot = Bot(token=TOKEN)

# Base de datos simple (para producción usa SQLite/PostgreSQL)
file_db = {}

# Generar ID de 24 caracteres
def generate_id():
    return secrets.token_urlsafe(18)[:24]  # Ej: 'aBcD1234eFgH5678iJkL9012'

# Handlers de Telegram
def start(update: Update, context: CallbackContext):
    welcome_msg = """
    🚀 *Bienvenido a MiCloud Bot* 🚀

    Envíame cualquier archivo y te daré un enlace de descarga directa con formato:
    `https://micloud.com/<ID-24-caracteres>`

    📌 *Características*:
    - Soporta archivos hasta 100MB
    - Enlaces permanentes
    - Descarga ultrarrápida
    """
    keyboard = [
        [InlineKeyboardButton("🌐 Sitio Web", url="https://micloud.onrender.com")],
        [InlineKeyboardButton("📌 Ejemplo", callback_data='example')]
    ]
    update.message.reply_text(
        welcome_msg,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard))
    
def example(update: Update, context: CallbackContext):
    update.callback_query.answer()
    update.callback_query.message.reply_text(
        "Ejemplo de enlace: https://micloud.com/aBcD1234eFgH5678iJkL9012")

def handle_file(update: Update, context: CallbackContext):
    file = update.message.effective_attachment
    file_id = generate_id()
    
    # Descargar archivo
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.file_name)
    new_file = bot.get_file(file.file_id)
    new_file.download(file_path)
    
    # Registrar en DB
    file_db[file_id] = file.file_name
    
    # Responder con enlace
    update.message.reply_text(
        f"✅ *Archivo subido correctamente!*\n\n"
        f"🔗 Enlace de descarga:\n"
        f"`https://micloud.com/{file_id}`\n\n"
        f"📁 Nombre: `{file.file_name}`",
        parse_mode='Markdown')

# Configurar webhook para Telegram
@app.route('/webhook', methods=['POST'])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    dp.process_update(update)
    return 'OK'

# Servidor de archivos
@app.route('/<file_id>')
def download_file(file_id):
    if file_id in file_db:
        return send_from_directory(
            app.config['UPLOAD_FOLDER'],
            file_db[file_id],
            as_attachment=True)
    return jsonify({"error": "File not found"}), 404

# Iniciar bot
dp = Dispatcher(bot, None)
dp.add_handler(CommandHandler('start', start))
dp.add_handler(MessageHandler(Filters.document, handle_file))
dp.add_handler(CallbackQueryHandler(example, pattern='example'))

if __name__ == '__main__':
    # Configurar webhook en producción
    if os.getenv('RENDER'):
        bot.set_webhook(url=f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}/webhook")
    app.run(host='0.0.0.0', port=10000)