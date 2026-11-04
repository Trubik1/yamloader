FROM python:3.12-slim

# Системные зависимости: ffmpeg для конвертации аудио
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Создаем пользователя user (UID 1000 — стандарт Hugging Face Spaces)
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1

WORKDIR $HOME/app

# Установка зависимостей Python
COPY --chown=user:user requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Копирование проекта
COPY --chown=user:user . .

# Создаем директорию для временных загрузок
RUN mkdir -p downloads

# Порт для Hugging Face Spaces (или Render через переменную $PORT)
EXPOSE 7860

CMD ["python", "bot.py"]
