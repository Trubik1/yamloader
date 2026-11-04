import logging
from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, FSInputFile

from services.metadata import is_music_url, parse_music_url, extract_url
from services.downloader import search_top3, download_track, cleanup_files
from keyboards.inline import get_search_results_keyboard

logger = logging.getLogger(__name__)
router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message):
    """Приветственное сообщение."""
    text = (
        "👋 <b>Привет! Я бот для загрузки музыки в высоком качестве.</b>\n\n"
        "🎵 <b>Что я умею:</b>\n"
        "• Принимать ссылки на треки из <b>Яндекс Музыки</b> и <b>Spotify</b>\n"
        "• Искать песни по <b>названию</b> текстом (с выбором из топ-3 версий)\n"
        "• Отдавать чистый <b>MP3 320 kbps</b> с оригинальной обложкой и тегами\n\n"
        "📌 <i>Просто отправь мне ссылку на трек или напиши название песни в чат!</i>"
    )
    await message.answer(text, parse_mode="HTML")


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Справка по использованию."""
    text = (
        "📖 <b>Как пользоваться ботом:</b>\n\n"
        "1️⃣ <b>По ссылке:</b> Скопируй ссылку на песню из приложения Яндекс Музыки "
        "или Spotify и отправь её мне.\n"
        "<i>(Поддерживаются ссылки на отдельные треки)</i>\n\n"
        "2️⃣ <b>По тексту:</b> Напиши в чат название песни или автора (например, "
        "<code>Miyagi Captain</code>). Я покажу топ-3 результата, и ты сможешь выбрать нужный.\n\n"
        "⚡ <i>Все треки конвертируются в максимальный битрейт 320 kbps.</i>"
    )
    await message.answer(text, parse_mode="HTML")


@router.message(F.text)
async def handle_text(message: Message):
    """Обработчик текстовых сообщений: ссылок или поисковых запросов."""
    text = message.text.strip()

    # Проверка: это музыкальная ссылка?
    if is_music_url(text):
        await handle_music_url(message, text)
    else:
        await handle_text_search(message, text)


async def handle_music_url(message: Message, raw_text: str):
    """Обработка ссылки на Яндекс Музыку или Spotify."""
    url = extract_url(raw_text) or raw_text.strip()
    status_msg = await message.answer("🔍 <i>Получаю информацию о треке...</i>", parse_mode="HTML")

    try:
        metadata, err = await parse_music_url(url)

        if err == "playlist_not_supported":
            await status_msg.edit_text(
                "⚠️ <b>Плейлисты и альбомы пока не поддерживаются.</b>\n\n"
                "Чтобы скачивание было моментальным и стабильным, отправь ссылку на "
                "<b>конкретный трек</b>!",
                parse_mode="HTML",
            )
            return

        if err or not metadata:
            await status_msg.edit_text(
                "❌ <b>Не удалось найти информацию по этой ссылке.</b>\n"
                "Убедись, что ссылка ведет на открытый трек в Spotify или Яндекс Музыке.",
                parse_mode="HTML",
            )
            return

        title = metadata["title"]
        artist = metadata["artist"]
        source = metadata["source"]
        cover_url = metadata.get("cover_url")
        query = metadata["query"]

        await status_msg.edit_text(
            f"⏳ <b>Скачиваю трек:</b>\n"
            f"🎵 <i>{artist} — {title}</i>\n\n"
            f"<i>Конвертирую в MP3 320 kbps...</i>",
            parse_mode="HTML",
        )

        res = await download_track(
            search_or_url=query,
            title=title,
            artist=artist,
            cover_url=cover_url,
        )

        if not res or not res.get("file_path"):
            await status_msg.edit_text(
                f"❌ <b>Не удалось загрузить трек:</b> <i>{artist} — {title}</i>\n"
                "Возможно, трек недоступен или защищен от скачивания.",
                parse_mode="HTML",
            )
            return

        # Формируем информативную карточку
        caption = (
            f"🎵 <b>{res['title']}</b>\n"
            f"👤 <b>Исполнитель:</b> {res['artist']}\n"
            f"📻 <b>Источник:</b> {source}\n"
            f"💾 <b>Качество:</b> MP3 320 kbps • {res['duration_str']} • {res['file_size_mb']} МБ"
        )

        audio_file = FSInputFile(str(res["file_path"]))
        thumb_file = FSInputFile(str(res["cover_path"])) if res.get("cover_path") else None

        await message.answer_audio(
            audio=audio_file,
            caption=caption,
            parse_mode="HTML",
            title=res["title"],
            performer=res["artist"],
            duration=res["duration"],
            thumbnail=thumb_file,
        )

        # Удаляем служебное сообщение о статусе
        await status_msg.delete()

        # Очищаем временные файлы
        cleanup_files(res["file_path"], res.get("cover_path"))

    except Exception as e:
        logger.error(f"Error handling music URL: {e}", exc_info=True)
        await status_msg.edit_text("❌ Произошла ошибка при обработке трека. Попробуй еще раз.")


async def handle_text_search(message: Message, query: str):
    """Поиск трека по названию с выдачей топ-3."""
    status_msg = await message.answer(f"🔎 <i>Ищу «{query}»...</i>", parse_mode="HTML")

    try:
        results = await search_top3(query)

        if not results:
            await status_msg.edit_text(
                f"❌ По запросу <b>«{query}»</b> ничего не найдено.\n"
                "Попробуй уточнить имя исполнителя или название песни.",
                parse_mode="HTML",
            )
            return

        lines = [f"🔎 <b>Результаты поиска по запросу:</b> <i>«{query}»</i>\n"]
        for idx, item in enumerate(results, start=1):
            lines.append(f"<b>{idx}.</b> 🎵 <b>{item['title']}</b> ({item['duration']})")

        lines.append("\n<i>Нажми на номер трека ниже, чтобы скачать:</i>")
        text = "\n".join(lines)

        keyboard = get_search_results_keyboard(results)
        await status_msg.edit_text(text, reply_markup=keyboard, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Error searching text '{query}': {e}", exc_info=True)
        await status_msg.edit_text("❌ Ошибка при поиске. Попробуй позже.")


@router.callback_query(F.data == "cancel_search")
async def cb_cancel_search(call: CallbackQuery):
    """Отмена поиска."""
    await call.message.delete()
    await call.answer("Поиск отменен")


@router.callback_query(F.data.startswith("dl:"))
async def cb_download_video(call: CallbackQuery):
    """Скачивание трека по клику на кнопку из поиска."""
    video_id = call.data.split(":", 1)[1]
    video_url = f"https://www.youtube.com/watch?v={video_id}"

    await call.answer("Начинаю загрузку...")
    await call.message.edit_text(
        "⏳ <b>Скачиваю выбранный трек...</b>\n<i>Конвертирую в MP3 320 kbps...</i>",
        parse_mode="HTML",
    )

    try:
        res = await download_track(video_url)

        if not res or not res.get("file_path"):
            await call.message.edit_text("❌ Не удалось скачать выбранный трек. Попробуй другой.")
            return

        caption = (
            f"🎵 <b>{res['title']}</b>\n"
            f"👤 <b>Исполнитель:</b> {res['artist']}\n"
            f"📻 <b>Источник:</b> Поиск\n"
            f"💾 <b>Качество:</b> MP3 320 kbps • {res['duration_str']} • {res['file_size_mb']} МБ"
        )

        audio_file = FSInputFile(str(res["file_path"]))
        thumb_file = FSInputFile(str(res["cover_path"])) if res.get("cover_path") else None

        await call.message.answer_audio(
            audio=audio_file,
            caption=caption,
            parse_mode="HTML",
            title=res["title"],
            performer=res["artist"],
            duration=res["duration"],
            thumbnail=thumb_file,
        )

        await call.message.delete()
        cleanup_files(res["file_path"], res.get("cover_path"))

    except Exception as e:
        logger.error(f"Error downloading from callback: {e}", exc_info=True)
        await call.message.edit_text("❌ Ошибка при загрузке аудио.")
