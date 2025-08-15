from flask import Flask, render_template
from deltachat_bot import handle_events, generate_qr

app = Flask(__name__)

@app.route("/")
def index():
    handle_events()
    return "✅ Bot activo y escuchando mensajes."

@app.route("/qr")
def qr():
    generate_qr()
    return render_template("qr.html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)