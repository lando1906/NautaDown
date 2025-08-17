# progress_handler.py
import re
import asyncio
import subprocess
import os
from telegram import Message

# Regex para extraer progreso de yt-dlp
progress_pattern = re.compile(
    r"\[download\]\s+(\d+\.\d+)%\s+of\s+[\d\.]+\w+\s+at\s+([\d\.]+\w+/s)\s+ETA\s+([\d:]+)"
)

async def stream_download_progress(cmd: list, message: Message) -> str:
    """
    Ejecuta yt-dlp y actualiza el mensaje con el progreso en tiempo real.
    Retorna la ruta del archivo descargado.
    """
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    filepath = None

    while True:
        line = process.stdout.readline()
        if not line:
            break

        match = progress_pattern.search(line)
        if match:
            percent, speed, eta = match.groups()
            text = (
                f"⏳ <b>Descargando...</b>\n\n"
                f"📊 Progreso: {percent}%\n"
                f"⚡ Velocidad: {speed}\n"
                f"⏱ ETA: {eta}"
            )
            try:
                await message.edit_text(text, parse_mode="HTML")
            except:
                pass

        if "[download] Destination:" in line:
            filepath = line.strip().split("Destination:")[1].strip()

        await asyncio.sleep(1)

    await message.edit_text("✅ <b>Descarga completada</b>", parse_mode="HTML")
    return filepath

async def simulate_upload_progress(message: Message, file_size_mb: float):
    """
    Simula el progreso de subida en Telegram.
    """
    for i in range(0, 101, 10):
        await message.edit_text(
            f"📤 <b>Subiendo video...</b>\n\n"
            f"📦 Tamaño: {file_size_mb:.1f}MB\n"
            f"📊 Progreso: {i}%",
            parse_mode="HTML"
        )
        await asyncio.sleep(1)

    await message.edit_text("✅ <b>Video enviado</b>", parse_mode="HTML")