from flask import Flask, send_file, render_template
from deltabot import Bot
import os

# Inicializa el bot con la base de datos
bot = Bot("db_account")

# Define la función que responde a todos los mensajes
@bot.message()
def responder(ctx):
    ctx.reply("En desarrollo 🛠️")

# Inicia el bot
bot.start()

# Crea la app Flask
app = Flask(__name__)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/qr")
def qr():
    return send_file("static/qr.png", mimetype="image/png")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)