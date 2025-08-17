import os
import subprocess
import logging

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

logger = logging.getLogger(__name__)

def sanitize_title(title: str) -> str:
    """Limpia el título para usarlo como nombre de archivo"""
    return "".join(c for c in title if c.isalnum() or c in (" ", "_")).rstrip()

def is_valid_video(file_path: str) -> bool:
    """Verifica si el archivo existe y tiene tamaño mínimo"""
    try:
        return os.path.exists(file_path) and os.path.getsize(file_path) > 1024 * 100
    except:
        return False

def prepare_download_command(url: str, format_id: str, safe_title: str) -> tuple:
    """Genera el comando yt-dlp para descargar y remuxear el video"""
    output_path = os.path.join(DOWNLOAD_DIR, f"{safe_title}.mp4")

    cmd = [
        "yt-dlp",
        "-f", f"{format_id}+bestaudio" if "video" in format_id else format_id,
        "--remux-video", "mp4",
        "--embed-metadata",
        "--embed-thumbnail",
        "--add-metadata",
        "--output", output_path,
        "--no-playlist",
        "--force-keyframes-at-cuts",
        url,
    ]
    return cmd, output_path

def cleanup_files(prefix: str):
    """Elimina archivos descargados que comiencen con el prefijo"""
    for f in os.listdir(DOWNLOAD_DIR):
        if f.startswith(prefix):
            try:
                os.remove(os.path.join(DOWNLOAD_DIR, f))
            except Exception as e:
                logger.warning(f"No se pudo eliminar {f}: {e}")