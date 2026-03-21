# backend/core/config.py
import os
import shutil
from pathlib import Path

# Thư mục gốc của project
BASE_DIR = Path(__file__).parent.parent.parent

# Cấu hình Ollama
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma3:12b")

# Cấu hình backend
BACKEND_HOST = os.getenv("BACKEND_HOST", "0.0.0.0")
BACKEND_PORT = int(os.getenv("BACKEND_PORT", "8000"))

# Thư mục temp
TEMP_DIR = BASE_DIR / "temp"
TEMP_DIR.mkdir(exist_ok=True)

# ── FFmpeg path ──
# Ưu tiên: env var → shutil.which → các đường dẫn phổ biến Windows
def _find_ffmpeg() -> str:
    if env := os.getenv("FFMPEG_PATH"):
        return env
    if found := shutil.which("ffmpeg"):
        return found
    # Các vị trí cài đặt phổ biến trên Windows
    for p in [
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
        r"C:\ProgramData\chocolatey\bin\ffmpeg.exe",
        str(Path.home() / "scoop" / "apps" / "ffmpeg" / "current" / "bin" / "ffmpeg.exe"),
    ]:
        if Path(p).exists():
            return p
    return "ffmpeg"  # fallback – sẽ raise FileNotFoundError nếu thực sự không có

FFMPEG_PATH = _find_ffmpeg()