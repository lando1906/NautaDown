#!/usr/bin/env python3
"""
🎬 Video Downloader Bot - Versión Universal
Bot de Telegram para descargar videos de cualquier plataforma usando yt-dlp
Con sistema de fallback automático para formatos compatibles
"""

import os
import re
import json
import asyncio
import logging
import subprocess
import shutil
import glob
from typing import Optional, Tuple, List, Dict, Any
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ==================== CONFIGURACIÓN ====================
TOKEN = "8470331129:AAHBJWD_p9m7TMMYPD2iaBZBHLzCLUFpHQw"
DOWNLOAD_DIR = "downloads"
MAX_FILE_SIZE_MB = 2000  # Límite de 2GB (límite práctico de Telegram)
MAX_RETRIES = 3  # Intentos máximos con diferentes formatos

# Estrategias de descarga por orden de prioridad
DOWNLOAD_STRATEGIES = [
    "bestvideo+bestaudio/best",  # Mejor combinación
    "best[height<=1080]",        # Máximo 1080p
    "best[height<=720]",         # Máximo 720p  
    "best[height<=480]",         # Máximo 480p
    "best",                      # El mejor disponible
    "worst",                     # El peor (como último recurso)
]

# ==================== LOGGING CONFIG ====================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bot.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ==================== INICIALIZACIÓN ====================
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
logger.info(f"Directorio de descargas: {os.path.abspath(DOWNLOAD_DIR)}")

# ==================== FUNCIONES UTILITARIAS ====================
def sanitize_title(title: str) -> str:
    """Limpia el título para usarlo como nombre de archivo"""
    title = re.sub(r'[<>:"/\\|?*]', '', title.strip())
    title = re.sub(r'\s+', '_', title)
    return title[:100] or "untitled"

def prepare_download_command(url: str, format_spec: str, safe_title: str, retry_count: int = 0) -> Tuple[List[str], str]:
    """Prepara el comando de yt-dlp con múltiples opciones de robustez"""
    output_path = os.path.join(DOWNLOAD_DIR, f"{safe_title}_{retry_count}.%(ext)s")
    
    cmd = [
        "yt-dlp",
        "-f", format_spec,
        "-o", output_path,
        "--no-playlist",
        "--merge-output-format", "mp4",
        "--retries", "10",
        "--fragment-retries", "10",
        "--socket-timeout", "30",
        "--source-address", "0.0.0.0",
        "--force-ipv4",
        "--throttled-rate", "100K",
        "--console-title",
        "--no-part",
        "--cookies-from-browser", "chrome"  # Intenta usar cookies del navegador
    ]
    
    # Añadir opciones específicas para ciertas plataformas
    if "tiktok" in url.lower():
        cmd.extend(["--referer", "https://www.tiktok.com/"])
    elif "instagram" in url.lower():
        cmd.extend(["--referer", "https://www.instagram.com/"])
    
    cmd.append(url)
    
    return cmd, output_path.replace("%(ext)s", "mp4")

def is_valid_video(file_path: str) -> bool:
    """Verifica si el archivo de video es válido"""
    if not os.path.exists(file_path):
        return False
    
    file_size = os.path.getsize(file_path)
    if file_size < 100 * 1024:  # Menos de 100KB probablemente esté corrupto
        return False
    
    # Verificar integridad básica del archivo
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", file_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10
        )
        return result.returncode == 0
    except:
        return file_path.endswith(('.mp4', '.mkv', '.webm'))

def cleanup_files(basename: str):
    """Limpia todos los archivos temporales relacionados con una descarga"""
    patterns = [".mp4", ".mkv", ".webm", ".part", ".temp", ".ytdl", ".jpg", ".png", ".webp"]
    
    for pattern in patterns:
        for file_path in glob.glob(os.path.join(DOWNLOAD_DIR, f"*{basename}*{pattern}")):
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    logger.info(f"Archivo limpiado: {file_path}")
                except Exception as e:
                    logger.warning(f"Error limpiando {file_path}: {e}")

async def safe_edit_message(message, text: str, **kwargs):
    """Edita un mensaje de forma segura con manejo de errores"""
    try:
        await message.edit_text(text, **kwargs)
    except Exception as e:
        logger.warning(f"No se pudo editar mensaje: {e}")
        # Intentar enviar como nuevo mensaje si falla la edición
        try:
            await message.chat.send_message(text, **kwargs)
        except Exception as e2:
            logger.error(f"También falló enviar nuevo mensaje: {e2}")

# ==================== MANEJO DE DESCARGA ====================
async def download_with_retry(url: str, message, title: str, max_retries: int = MAX_RETRIES) -> Optional[str]:
    """
    Intenta descargar el video con múltiples estrategias hasta que una funcione
    """
    safe_title = sanitize_title(title)
    
    for retry in range(max_retries):
        strategy = DOWNLOAD_STRATEGIES[retry % len(DOWNLOAD_STRATEGIES)]
        
        await safe_edit_message(
            message,
            f"🔄 **Intentando descarga ({retry + 1}/{max_retries})**\n"
            f"🎥 **Título:** {title[:50]}{'...' if len(title) > 50 else ''}\n"
            f"⚙️ **Estrategia:** {strategy}",
            parse_mode="Markdown"
        )
        
        try:
            cmd, expected_path = prepare_download_command(url, strategy, safe_title, retry)
            downloaded_path = await stream_download_progress(cmd, message, url, title)
            
            if downloaded_path and is_valid_video(downloaded_path):
                return downloaded_path
                
            # Si el path esperado es diferente al retornado
            if is_valid_video(expected_path):
                return expected_path
                
        except Exception as e:
            logger.warning(f"Intento {retry + 1} falló: {e}")
            await asyncio.sleep(2)  # Pequeña pausa entre intentos
    
    return None

async def stream_download_progress(cmd: List[str], message, url: str, title: str) -> Optional[str]:
    """
    Ejecuta la descarga mostrando progreso en tiempo real
    """
    filepath = None
    
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT
        )
        
        logger.info(f"Iniciando descarga: {' '.join(cmd)}")
        
        # Leer salida en tiempo real
        async for line_bytes in process.stdout:
            line = line_bytes.decode('utf-8', errors='ignore').strip()
            
            # Detectar progreso
            if '[download]' in line and '%' in line:
                try:
                    parts = line.split()
                    percent = parts[1] if len(parts) > 1 else '0%'
                    size = parts[3] if len(parts) > 3 else 'N/A'
                    speed = parts[5] if len(parts) > 5 else 'N/A'
                    eta = parts[7] if len(parts) > 7 else 'N/A'
                    
                    await safe_edit_message(
                        message,
                        f"⏳ **Descargando...**\n"
                        f"📏 **Tamaño:** {size}\n"
                        f"📊 **Progreso:** {percent}\n"
                        f"⚡ **Velocidad:** {speed}\n"
                        f"⏱ **ETA:** {eta}",
                        parse_mode="Markdown"
                    )
                except:
                    pass
            
            # Detectar ruta del archivo
            if 'Destination:' in line:
                filepath = line.split('Destination:')[-1].strip()
            elif 'has already been downloaded' in line:
                filepath = line.split('has already been downloaded')[0].strip()
        
        # Esperar que el proceso termine
        await process.wait()
        
        if process.returncode == 0:
            return filepath
        else:
            logger.error(f"Error en descarga (código: {process.returncode})")
            return None
            
    except Exception as e:
        logger.error(f"Error inesperado en descarga: {e}")
        return None

async def simulate_upload_progress(message, filepath: str, title: str):
    """Simula el progreso de subida a Telegram"""
    try:
        file_size = os.path.getsize(filepath)
        size_mb = file_size / (1024 * 1024)
        
        if size_mb > MAX_FILE_SIZE_MB:
            await safe_edit_message(
                message, 
                f"❌ **Video demasiado grande**\n"
                f"📦 **Tamaño:** {size_mb:.1f}MB\n"
                f"📏 **Límite:** {MAX_FILE_SIZE_MB}MB\n"
                f"⚠️ Reduce la calidad o elige otro formato",
                parse_mode="Markdown"
            )
            return False
        
        progress_steps = [10, 25, 45, 65, 80, 90, 95, 100]
        
        for progress in progress_steps:
            try:
                await message.edit_text(
                    f"📤 **Subiendo video...**\n"
                    f"🎥 **Título:** {title[:50]}{'...' if len(title) > 50 else ''}\n"
                    f"📦 **Tamaño:** {size_mb:.1f}MB\n"
                    f"📊 **Progreso:** {progress}%",
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.warning(f"No se pudo actualizar progreso de subida: {e}")
            
            await asyncio.sleep(1.5)
        
        return True
        
    except Exception as e:
        logger.error(f"Error en simulación de subida: {e}")
        return False

async def process_successful_download(context, msg, downloaded_path: str, title: str):
    """Procesa un archivo descargado exitosamente"""
    safe_title = sanitize_title(title)
    
    try:
        # Verificar tamaño del archivo
        file_size = os.path.getsize(downloaded_path)
        size_mb = file_size / (1024 * 1024)
        
        if size_mb > MAX_FILE_SIZE_MB:
            await safe_edit_message(
                msg, 
                f"❌ **Video demasiado grande**\n📦 **Tamaño:** {size_mb:.1f}MB",
                parse_mode="Markdown"
            )
            cleanup_files(safe_title)
            return
        
        # Simular subida
        upload_success = await simulate_upload_progress(msg, downloaded_path, title)
        
        if upload_success:
            await context.bot.send_chat_action(msg.chat.id, "upload_video")
            
            with open(downloaded_path, 'rb') as video_file:
                await context.bot.send_video(
                    chat_id=msg.chat.id,
                    video=video_file,
                    caption=f"🎥 **{title}**\n✅ Via @{context.bot.username}",
                    parse_mode="Markdown",
                    supports_streaming=True,
                    read_timeout=60,
                    write_timeout=60,
                    connect_timeout=60
                )
            
            await safe_edit_message(msg, "✅ **Video enviado correctamente**", parse_mode="Markdown")
        
        cleanup_files(safe_title)
        
    except Exception as e:
        logger.error(f"Error enviando video: {e}")
        await safe_edit_message(msg, "❌ **Error al enviar el video**", parse_mode="Markdown")
        cleanup_files(safe_title)

# ==================== HANDLERS DE TELEGRAM ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mensaje de bienvenida"""
    welcome_text = """
    🎬 *Video Downloader*
    
    *Soporte ampliado:* Casi cualquier plataforma de video
    
    *Cómo usar:*
    1. Envíame el enlace de un video
    2. El bot intentará automáticamente descargarlo
    3. Espera a que se descargue y envíe
    
    *Límites:*
    • Máximo {}MB por video
    • Videos públicos sin restricciones
    
    ⚠️ *Solo para uso personal y educativo*
    """.format(MAX_FILE_SIZE_MB)
    
    await update.message.reply_text(welcome_text, parse_mode="Markdown")

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Procesa URLs de video de cualquier plataforma"""
    url = update.message.text.strip()
    
    if not url.startswith(("http://", "https://")):
        await update.message.reply_text("❌ **URL inválida**\nDebe comenzar con http:// o https://", parse_mode="Markdown")
        return
    
    msg = await update.message.reply_text("🔍 **Analizando video...**", parse_mode="Markdown")
    
    try:
        # Obtener información del video con timeout
        info_process = await asyncio.wait_for(
            asyncio.create_subprocess_exec(
                "yt-dlp", "--dump-json", "--no-playlist", "--skip-download", url,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            ),
            timeout=45
        )
        
        stdout, stderr = await info_process.communicate()
        
        if info_process.returncode != 0:
            error_msg = stderr.decode() if stderr else "Error desconocido"
            logger.error(f"Error yt-dlp info: {error_msg}")
            
            # Intentar con método alternativo incluso sin información
            await safe_edit_message(msg, "🔄 **Intentando descarga directa...**", parse_mode="Markdown")
            downloaded_path = await download_with_retry(url, msg, "video_descargado")
            
            if downloaded_path:
                await process_successful_download(context, msg, downloaded_path, "Video Descargado")
            else:
                await safe_edit_message(msg, "❌ **No se pudo descargar el video**", parse_mode="Markdown")
            return
        
        video_info = json.loads(stdout.decode())
        title = video_info.get("title", "Video sin título")
        duration = video_info.get("duration", 0)
        duration_str = f"{duration//60}:{duration%60:02d}" if duration else "Desconocida"
        
        # Guardar contexto
        context.user_data["url"] = url
        context.user_data["title"] = title
        
        # Ofrecer opciones de formato o descarga directa
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎥 Mejor Calidad", callback_data="dl_best")],
            [InlineKeyboardButton("📱 720p", callback_data="dl_720")],
            [InlineKeyboardButton("📼 480p", callback_data="dl_480")],
            [InlineKeyboardButton("🚀 Descarga Automática", callback_data="dl_auto")],
            [InlineKeyboardButton("❌ Cancelar", callback_data="cancel")]
        ])
        
        await safe_edit_message(
            msg,
            f"📹 **{title}**\n"
            f"⏱ **Duración:** {duration_str}\n"
            f"🔗 **URL:** {url[:30]}...\n\n"
            f"**Selecciona la calidad o usa automático:**",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        
    except asyncio.TimeoutError:
        await safe_edit_message(msg, "⏰ **Timeout al analizar el video**\nIntentando descarga automática...", parse_mode="Markdown")
        # Intentar descarga automática incluso con timeout
        downloaded_path = await download_with_retry(url, msg, "video_descargado")
        if downloaded_path:
            await process_successful_download(context, msg, downloaded_path, "Video Descargado")
        else:
            await safe_edit_message(msg, "❌ **No se pudo descargar el video**", parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error procesando URL: {e}")
        await safe_edit_message(msg, "❌ **Error al procesar el video**\nIntentando descarga automática...", parse_mode="Markdown")
        # Intentar descarga automática incluso con error
        downloaded_path = await download_with_retry(url, msg, "video_descargado")
        if downloaded_path:
            await process_successful_download(context, msg, downloaded_path, "Video Descargado")
        else:
            await safe_edit_message(msg, "❌ **No se pudo descargar con ningún método**", parse_mode="Markdown")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja las acciones de los botones inline con múltiples estrategias"""
    query = update.callback_query
    await query.answer()
    
    user_data = context.user_data
    url = user_data.get("url")
    title = user_data.get("title", "video")
    
    if not url:
        await query.edit_message_text("❌ **URL no encontrada**\nEnvía el enlace nuevamente.", parse_mode="Markdown")
        return
    
    if query.data == "cancel":
        await query.edit_message_text("✅ **Operación cancelada**", parse_mode="Markdown")
        return
    
    # Mapear selección a estrategia
    format_map = {
        "dl_best": "bestvideo+bestaudio/best",
        "dl_720": "best[height<=720]",
        "dl_480": "best[height<=480]",
        "dl_auto": "best"  # Estrategia automática
    }
    
    format_spec = format_map.get(query.data, "bestvideo+bestaudio/best")
    
    msg = await query.edit_message_text(
        f"⏳ **Iniciando descarga...**\n"
        f"🎥 **Título:** {title[:50]}{'...' if len(title) > 50 else ''}\n"
        f"⚙️ **Calidad:** {format_spec}",
        parse_mode="Markdown"
    )
    
    try:
        # Intentar descarga con la estrategia seleccionada
        if query.data == "dl_auto":
            # Para modo automático, probar todas las estrategias
            downloaded_path = await download_with_retry(url, msg, title)
        else:
            # Para modo específico, usar solo la estrategia seleccionada
            safe_title = sanitize_title(title)
            cmd, expected_path = prepare_download_command(url, format_spec, safe_title)
            downloaded_path = await stream_download_progress(cmd, msg, url, title)
            
            if not downloaded_path and is_valid_video(expected_path):
                downloaded_path = expected_path
        
        if downloaded_path:
            await process_successful_download(context, msg, downloaded_path, title)
        else:
            await safe_edit_message(msg, "❌ **No se pudo descargar**\nIntentando método alternativo...", parse_mode="Markdown")
            # Fallback a método automático
            downloaded_path = await download_with_retry(url, msg, title)
            if downloaded_path:
                await process_successful_download(context, msg, downloaded_path, title)
            else:
                await safe_edit_message(msg, "❌ **No se pudo descargar con ningún método**", parse_mode="Markdown")
                cleanup_files(sanitize_title(title))
            
    except Exception as e:
        logger.error(f"Error en callback: {e}")
        await safe_edit_message(msg, "❌ **Error crítico al procesar el video**", parse_mode="Markdown")
        cleanup_files(sanitize_title(title))

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancela cualquier operación en curso"""
    await update.message.reply_text("✅ **Operaciones canceladas**", parse_mode="Markdown")
    # Limpiar user_data
    context.user_data.clear()

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja errores no capturados"""
    logger.error(f"Error no capturado: {context.error}", exc_info=context.error)
    
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "❌ **Error interno del bot**\nPor favor, intenta nuevamente.",
                parse_mode="Markdown"
            )
        except:
            pass

# ==================== FUNCIÓN PRINCIPAL ====================
def main():
    """Función principal que inicia el bot"""
    try:
        # Crear aplicación
        application = Application.builder().token(TOKEN).build()
        
        # Añadir handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("cancel", cancel))
        application.add_handler(CommandHandler("help", start))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
        application.add_handler(CallbackQueryHandler(button_callback))
        
        # Manejo de errores
        application.add_error_handler(error_handler)
        
        # Información de inicio
        logger.info("=" * 50)
        logger.info("🎬 Video Downloader Bot Universal - INICIANDO")
        logger.info(f"📁 Descargas en: {os.path.abspath(DOWNLOAD_DIR)}")
        logger.info(f"📏 Límite de tamaño: {MAX_FILE_SIZE_MB}MB")
        logger.info("=" * 50)
        
        # Iniciar polling
        print("\n🤖 Bot iniciado correctamente!")
        print("📍 Presiona Ctrl+C para detener\n")
        
        application.run_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES
        )
        
    except Exception as e:
        logger.critical(f"Error fatal al iniciar el bot: {e}")
        raise

if __name__ == "__main__":
    main()