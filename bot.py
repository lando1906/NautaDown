from flask import Flask
from deltachat2 import MsgData, events
from deltabot_cli import BotCli

# 🔐 Credenciales embebidas
EMAIL = "tubot@ejemplo.com"
PASSWORD = "tu_contraseña_segura"

# 🤖 Inicializar CLI del bot
cli = BotCli("echobot", addr=EMAIL, pass_=PASSWORD)

@cli.on(events.NewMessage)
def echo(bot, accid, event):
    msg = event.msg
    print(f"📨 Recibido: {msg.text}")
    bot.rpc.send_msg(accid, msg.chat_id, MsgData(text=f"Eco: {msg.text}"))

# 🌐 Servidor web mínimo para Render
app = Flask(__name__)

@app.route("/")
def index():
    return "🤖 DeltaBot con deltabot-cli está corriendo en Render."

if __name__ == "__main__":
    import threading
    threading.Thread(target=cli.start).start()
    app.run(host="0.0.0.0", port=10000)