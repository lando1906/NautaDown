from flask import Flask, render_template
import qrcode
import os
from deltabot import Bot

app = Flask(__name__)

# Inicializa el bot usando deltabot-cli
bot = Bot("db_account")  # Asegúrate de que esta carpeta exista y tenga la cuenta configurada

def generar_qr():
    accid = bot.get_default_account_id()
    uri = bot.rpc.get_qr(accid)  # URI de verificación del cifrado
    img = qrcode.make(uri)
    img.save("static/qr.png")
    return uri

@app.route("/")
def index():
    uri = generar_qr()
    return render_template("index.html", uri=uri)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))