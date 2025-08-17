import os
import re
import shutil

DOWNLOAD_DIR = "downloads"

def sanitize_title(title: str) -> str:
    """
    Limpia el título para usarlo como nombre de archivo seguro.
    """
    title = title.strip()
    title = re.sub(r"[^\w\s-]", "", title)
    title = re.sub(r"\s+", "_", title)
    return title[:100]  # Limita a 100 caracteres

def prepare_download_command(url: str, format_id: str, safe_title: str):
    """
    Prepara el comando yt-dlp para descargar el video en el formato seleccionado.
    """
    output_path = os.path.join(DOWNLOAD_DIR, f"{safe_title}.mp4")
    cmd = [
        "yt-dlp",
        "-f", format_id,
        "-o", output_path,
        "--no-playlist",
        "--no-warnings",
        "--quiet",
        "--no-cache-dir",
        url
    ]
    return cmd, output_path

def is_valid_video(file_path: str) -> bool:
    """
    Verifica si el archivo existe y tiene tamaño suficiente para considerarse válido.
    """
    return os.path.exists(file_path) and os.path.getsize(file_path) > 1024 * 100  # >100KB

def cleanup_files(base_name: str):
    """
    Elimina archivos relacionados con el video descargado.
    """
    for ext in [".mp4", ".mkv", ".webm", ".part", ".temp"]:
        path = os.path.join(DOWNLOAD_DIR, f"{base_name}{ext}")
        if os.path.exists(path):
            try:
                os.remove(path)
            except:
                pass

    # Elimina carpeta de thumbnails o metadata si existe
    thumb_dir = os.path.join(DOWNLOAD_DIR, f"{base_name}_thumbs")
    if os.path.isdir(thumb_dir):
        shutil.rmtree(thumb_dir, ignore_errors=True)