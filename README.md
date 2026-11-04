# 🎵 Yamloader — Музыкальный Telegram-бот

Telegram-бот для мгновенного скачивания музыки из **Яндекс Музыки** и **Spotify**, а также поиска песен по названию с конвертацией в **MP3 320 kbps**, оригинальной обложкой и тегами.

---

## ✨ Возможности
* 🎧 **Поддержка Spotify:** извлечение названия, артиста и обложки напрямую по ссылке на трек.
* 🟡 **Поддержка Яндекс Музыки:** мгновенное извлечение метаданных по открытому API Яндекс Музыки.
* 🔎 **Инлайн-поиск:** если отправить название песни текстом — бот выдаст топ-3 версии с кнопками выбора.
* 🎚️ **Высокое качество:** конвертация аудиопотока через `FFmpeg` в постоянный битрейт `320 kbps`.
* 🖼️ **Красивые карточки и обложки:** вшивание ID3-тегов и отправка информативной карточки под треком.
* 🐳 **100% готов к бесплатному деплою 24/7:** Dockerfile оптимизирован под **Hugging Face Spaces** и **Render.com** (не требует банковских карт).

---

## 🚀 Бесплатный деплой на Hugging Face Spaces (2 минуты)

1. Зарегистрируйтесь или войдите на [Hugging Face](https://huggingface.co/).
2. Перейдите в раздел **Spaces** и нажмите **Create new Space** (или откройте [huggingface.co/new-space](https://huggingface.co/new-space)).
3. Заполните поля:
   * **Space name:** `yamloader` (или любое другое)
   * **License:** `mit`
   * **Select the Space SDK:** выберите **Docker** -> **Blank**
   * **Space hardware:** оставьте бесплатный **CPU basic (2 vCPU · 16 GB RAM)**
   * Нажмите кнопку **Create Space**.
4. В созданном Space перейдите во вкладку **Settings** -> блок **Variables and secrets**:
   * Нажмите **New secret**
   * Name: `BOT_TOKEN`
   * Value: `9241982445:AAGav98u9oKFMshRXf7KwEqxRUvl1FuoSoE`
5. Перейдите во вкладку **Files** -> нажмите **Add file** -> **Upload files**:
   * Перетащите все файлы из этой папки (`Dockerfile`, `bot.py`, `config.py`, `requirements.txt`, папки `services`, `handlers`, `keyboards`).
   * Нажмите **Commit changes to main**.
6. Hugging Face автоматически соберет Docker-контейнер и запустит бота круглосуточно! Статус станет зеленым: **Running**.

---

## 💻 Локальный запуск на ПК

Если вы хотите запустить бота прямо на своем компьютере:

```bash
# 1. Установите зависимости
pip install -r requirements.txt

# 2. Убедитесь, что FFmpeg установлен в системе

# 3. Запустите бота
python bot.py
```

---

## 📁 Структура проекта

```text
├── bot.py                  # Точка входа (aiogram 3 + aiohttp healthcheck)
├── config.py               # Конфигурация и переменные окружения
├── Dockerfile              # Сборка контейнера для Hugging Face / Render
├── requirements.txt        # Python зависимости
├── services/
│   ├── metadata.py         # Парсер Spotify и Яндекс Музыки
│   └── downloader.py       # Поиск, скачивание через yt-dlp, FFmpeg и теги
├── handlers/
│   └── music.py            # Обработчики команд, ссылок и поиска
└── keyboards/
    └── inline.py           # Кнопки выбора из топ-3 результатов
```
