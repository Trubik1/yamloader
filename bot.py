import asyncio
import logging
import sys
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from config import BOT_TOKEN, PORT
from handlers.music import router as music_router

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


async def handle_health_check(request):
    """Эндпоинт для проверки активности сервиса."""
    return web.json_response(
        {
            "status": "ok",
            "service": "Yamloader Telegram Bot",
            "version": "v1.2",
            "message": "Bot is running 24/7",
        }
    )


async def handle_diagnostic(request):
    """Диагностика парсинга трека прямо из контейнера Render с детальными ошибками."""
    import traceback
    import aiohttp
    from services.metadata import CRAWLER_HEADERS, BROWSER_HEADERS

    url = request.query.get("url", "https://music.yandex.ru/album/43869814/track/155560266")
    results = {}

    # Тест 1: Запрос веб-страницы
    try:
        async with aiohttp.ClientSession(headers=CRAWLER_HEADERS) as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                text = await resp.text()
                results["web_page"] = {
                    "status": resp.status,
                    "url": str(resp.url),
                    "len": len(text),
                    "snippet": text[:300],
                }
    except Exception as e:
        results["web_page_error"] = str(e)

    # Тест 2: Запрос к api.music.yandex.net
    try:
        api_url = "https://api.music.yandex.net/tracks/155560266"
        async with aiohttp.ClientSession(headers=BROWSER_HEADERS) as session:
            async with session.get(api_url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                text = await resp.text()
                results["api"] = {
                    "status": resp.status,
                    "len": len(text),
                    "snippet": text[:300],
                }
    except Exception as e:
        results["api_error"] = str(e)

    return web.json_response({"version": "v1.3", "results": results})


async def start_web_server():
    """Запуск фонового веб-сервера для healthcheck."""
    app = web.Application()
    app.router.add_get("/", handle_health_check)
    app.router.add_get("/health", handle_health_check)
    app.router.add_get("/version", handle_health_check)
    app.router.add_get("/test", handle_diagnostic)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=PORT)
    await site.start()
    logger.info(f"Health-check web server started on port {PORT}")
    return runner


async def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN is not set! Please provide it in .env or config.")
        return

    # Запускаем фоновый веб-сервер (нужен для Hugging Face / Render)
    runner = await start_web_server()

    # Инициализируем бота и диспетчер
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    # Регистрируем роутеры
    dp.include_router(music_router)

    try:
        logger.info("Bot is starting polling...")
        # Удаляем вебхуки, если они были установлены ранее, чтобы polling работал сразу
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        await runner.cleanup()
        logger.info("Bot stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot shut down gracefully.")
