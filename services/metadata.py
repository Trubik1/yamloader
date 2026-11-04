import re
import json
import logging
import html
from typing import Optional, Dict, Any, Tuple
import aiohttp

logger = logging.getLogger(__name__)

CRAWLER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; TelegramBot/1.0; +https://core.telegram.org/bots/webpages)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
}

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8",
}


def extract_url(text: str) -> Optional[str]:
    """Извлекает чистый URL из сообщения."""
    match = re.search(r"(https?://[^\s]+)", text.strip())
    return match.group(1) if match else None


def is_music_url(text: str) -> bool:
    """Проверяет, содержит ли текст ссылку на Spotify или Яндекс Музыку."""
    return bool(
        re.search(r"https?://(?:open\.)?spotify\.com/", text, re.IGNORECASE)
        or re.search(r"https?://music\.yandex\.(?:ru|com|by|kz)/", text, re.IGNORECASE)
    )


async def get_spotify_track_info(url: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Извлекает информацию о треке Spotify по ссылке.
    Возвращает (метаданные, ошибка/предупреждение).
    """
    clean_url = url.split("?")[0]

    # Проверка на плейлист или альбом
    if re.search(r"spotify\.com/(?:[a-zA-Z-]+/)?(playlist|album)/", clean_url):
        return None, "playlist_not_supported"

    match = re.search(r"spotify\.com/(?:[a-zA-Z-]+/)?track/([a-zA-Z0-9]+)", clean_url)
    if not match:
        return None, "invalid_track_url"

    track_id = match.group(1)
    embed_url = f"https://open.spotify.com/embed/track/{track_id}"

    # 1. Пробуем через Embed JSON-LD
    try:
        async with aiohttp.ClientSession(headers=CRAWLER_HEADERS) as session:
            async with session.get(embed_url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status == 200:
                    html_text = await resp.text()
                    match_json = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html_text)
                    if match_json:
                        data = json.loads(match_json.group(1))
                        entity = (
                            data.get("props", {})
                            .get("pageProps", {})
                            .get("state", {})
                            .get("data", {})
                            .get("entity", {})
                        )
                        title = entity.get("title") or entity.get("name")
                        artists_list = [a.get("name") for a in entity.get("artists", []) if a.get("name")]
                        artist = ", ".join(artists_list) if artists_list else "Unknown Artist"
                        images = entity.get("visualIdentity", {}).get("image", [])
                        cover_url = images[0].get("url") if images else None

                        if title:
                            return {
                                "title": title.strip(),
                                "artist": artist.strip(),
                                "source": "Spotify",
                                "cover_url": cover_url,
                                "query": f"{artist} - {title}",
                            }, None
    except Exception as e:
        logger.warning(f"Spotify embed fetch error: {e}")

    # 2. Резервный метод: через oEmbed API Spotify
    try:
        oembed_url = f"https://open.spotify.com/oembed?url=https://open.spotify.com/track/{track_id}"
        async with aiohttp.ClientSession(headers=BROWSER_HEADERS) as session:
            async with session.get(oembed_url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    title = data.get("title", "")
                    cover_url = data.get("thumbnail_url")
                    if " by " in title:
                        parts = title.split(" by ")
                        track_title = parts[0].strip()
                        artist = parts[1].strip()
                    else:
                        track_title = title.strip()
                        artist = "Spotify Artist"

                    return {
                        "title": track_title,
                        "artist": artist,
                        "source": "Spotify",
                        "cover_url": cover_url,
                        "query": f"{artist} - {track_title}" if artist != "Spotify Artist" else track_title,
                    }, None
    except Exception as e:
        logger.error(f"Spotify oEmbed fallback failed: {e}")

    return None, "fetch_failed"


async def get_yandex_track_info(url: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Извлекает информацию о треке Яндекс Музыки по ссылке.
    Использует многоуровневый парсинг:
    1. Открытые OpenGraph мета-теги веб-страницы (работает из любых дата-центров без блокировок).
    2. Внутренний API Яндекс Музыки (резервный).
    """
    clean_url = url.strip()

    # Проверка на плейлист или альбом без трека
    if "playlists" in clean_url or "/users/" in clean_url:
        return None, "playlist_not_supported"

    # Если ссылка вида /album/12345 без /track/
    clean_without_query = clean_url.split("?")[0]
    if re.search(r"/album/\d+/?$", clean_without_query):
        return None, "playlist_not_supported"

    match = re.search(r"(?:track/|track=)(\d+)", clean_url)
    if not match:
        return None, "invalid_track_url"

    track_id = match.group(1)

    # 1. Основной способ: парсинг OpenGraph тегов со страницы трека
    try:
        page_url = clean_url
        async with aiohttp.ClientSession(headers=CRAWLER_HEADERS) as session:
            async with session.get(page_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    raw_html = await resp.text()

                    m_title = re.search(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']', raw_html)
                    if not m_title:
                        m_title = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:title["\']', raw_html)

                    m_desc = re.search(r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']', raw_html)
                    if not m_desc:
                        m_desc = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:description["\']', raw_html)

                    m_img = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', raw_html)
                    if not m_img:
                        m_img = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']', raw_html)

                    if m_title:
                        title = html.unescape(m_title.group(1)).strip()
                        desc = html.unescape(m_desc.group(1)).strip() if m_desc else ""
                        cover_url = html.unescape(m_img.group(1)).strip() if m_img else None

                        # Выделяем артиста из описания (например, "vuksai, k0vertessence • Трек • 2026")
                        artist = desc
                        for sep in ["•", "·", " - ", "|"]:
                            if sep in artist:
                                artist = artist.split(sep)[0].strip()

                        if not artist or artist.lower() == "яндекс музыка":
                            artist = "Неизвестный исполнитель"

                        logger.info(f"Yandex Music parsed via OpenGraph: '{artist} - {title}'")
                        return {
                            "title": title,
                            "artist": artist,
                            "source": "Яндекс Музыка",
                            "cover_url": cover_url,
                            "query": f"{artist} - {title}",
                        }, None
    except Exception as e:
        logger.warning(f"Yandex Music OpenGraph parse failed: {e}")

    # 2. Резервный способ: через открытый API Яндекс Музыки
    try:
        api_url = f"https://api.music.yandex.net/tracks/{track_id}"
        async with aiohttp.ClientSession(headers=BROWSER_HEADERS) as session:
            async with session.get(api_url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    result = data.get("result", [])
                    if result:
                        track = result[0]
                        title = track.get("title", "Unknown Title")
                        version = track.get("version")
                        if version:
                            title = f"{title} ({version})"

                        artists_list = [a.get("name") for a in track.get("artists", []) if a.get("name")]
                        artist = ", ".join(artists_list) if artists_list else "Unknown Artist"

                        cover_uri = track.get("coverUri")
                        if not cover_uri and track.get("albums"):
                            cover_uri = track["albums"][0].get("coverUri")

                        cover_url = f"https://{cover_uri.replace('%%', '400x400')}" if cover_uri else None

                        logger.info(f"Yandex Music parsed via API: '{artist} - {title}'")
                        return {
                            "title": title.strip(),
                            "artist": artist.strip(),
                            "source": "Яндекс Музыка",
                            "cover_url": cover_url,
                            "query": f"{artist} - {title}",
                        }, None
    except Exception as e:
        logger.error(f"Yandex Music API fallback failed: {e}")

    return None, "fetch_failed"


async def parse_music_url(url: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Определяет сервис и извлекает метаданные трека."""
    clean_url = url.strip()
    if "spotify.com" in clean_url:
        return await get_spotify_track_info(clean_url)
    elif any(d in clean_url for d in ["music.yandex.ru", "music.yandex.com", "music.yandex.by", "music.yandex.kz"]):
        return await get_yandex_track_info(clean_url)
    return None, "unsupported_service"
