import os
from pathlib import Path
from dotenv import load_dotenv

# Загружаем переменные из .env, если есть
load_dotenv()

# Токен бота (из переменных окружения или дефолтный)
BOT_TOKEN = os.getenv("BOT_TOKEN", "9241982445:AAGav98u9oKFMshRXf7KwEqxRUvl1FuoSoE")

# Директория для временных файлов
BASE_DIR = Path(__file__).parent
DOWNLOAD_DIR = BASE_DIR / "downloads"
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Порт для веб-сервера проверки работоспособности (Hugging Face Spaces / Render)
PORT = int(os.getenv("PORT", 7860))
