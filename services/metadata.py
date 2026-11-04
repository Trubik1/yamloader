import re
import json
import logging
from typing import Optional, Dict, Any, Tuple
import aiohttp

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
}


def is_music_url(text: str) -> bool:
    """Проверяет, содержит ли текст ссылку на Spotify или Яндекс Музыку."""
    return bool(
        re.search(r"https?://(?:open\.)?spotify\.com/", text)
        or re.search(r"https?://music\.yandex\.(?:ru|com|by|kz)/", text)
    )


async def get_spotify_track_info(url: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Извлекает информацию о треке Spotify по ссылке.
    Возвращает (метаданные, ошибка/предупреждение).
    """
    # Проверка на плейлист или альбом
    if re.search(r"spotify\.com/(?:[a-zA-Z-]+/)?(playlist|album)/", url):
        return None, "playlist_not_supported"

    match = re.search(r"spotify\.com/(?:[a-zA-Z-]+/)?track/([a-zA-Z0-9]+)", url)
    if not match:
        return None, "invalid_track_url"

    track_id = match.group(1)
    embed_url = f"https://open.spotify.com/embed/track/{track_id}"

    try:
        async with aiohttp.ClientSession(headers=HEADERS) as session:
            async with session.get(embed_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    logger.warning(f"Spotify embed returned status {resp.status}")
                    return await _get_spotify_oembed_fallback(session, url)

                html = await resp.text()
                match_json = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html)
                if not match_json:
                    return await _get_spotify_oembed_fallback(session, url)

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

                if not title:
                    return await _get_spotify_oembed_fallback(session, url)

                return {
                    "title": title.strip(),
                    "artist": artist.strip(),
                    "source": "Spotify",
                    "cover_url": cover_url,
                    "query": f"{artist} - {title}",
                }, None

    except Exception as e:
        logger.error(f"Error fetching Spotify metadata: {e}")
        return None, "fetch_failed"


async def _get_spotify_oembed_fallback(
    session: aiohttp.ClientSession, url: str
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Резервный метод извлечения через официальный oEmbed API Spotify."""
    try:
        oembed_url = f"https://open.spotify.com/oembed?url={url}"
        async with session.get(oembed_url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
            if resp.status == 200:
                data = await resp.json()
                title = data.get("title", "")
                cover_url = data.get("thumbnail_url")
                # Spotify oEmbed часто возвращает название в формате "Title" или "Title by Artist"
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
    Возвращает (метаданные, ошибка/предупреждение).
    """
    # Проверка на плейлист или альбом без трека
    if "playlists" in url or "/users/" in url:
        return None, "playlist_not_supported"

    # Если ссылка вида /album/12345 без /track/
    if re.search(r"/album/\d+/?$", url):
        return None, "playlist_not_supported"

    match = re.search(r"(?:track/|track=)(\d+)", url)
    if not match:
        return None, "invalid_track_url"

    track_id = match.group(1)
    api_url = f"https://api.music.yandex.net/tracks/{track_id}"

    try:
        async with aiohttp.ClientSession(headers=HEADERS) as session:
            async with session.get(api_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    logger.warning(f"Yandex Music API returned {resp.status}")
                    return None, "fetch_failed"

                data = await resp.json()
                result = data.get("result", [])
                if not result:
                    return None, "track_not_found"

                track = result[0]
                title = track.get("title", "Unknown Title")
                version = track.get("version")
                if version:
                    title = f"{title} ({version})"

                artists_list = [a.get("name") for a in track.get("artists", []) if a.get("name")]
                artist = ", ".join(artists_list) if artists_list else "Unknown Artist"

                # Обложка
                cover_uri = track.get("coverUri")
                if not cover_uri and track.get("albums"):
                    cover_uri = track["albums"][0].get("coverUri")

                cover_url = None
                if cover_uri:
                    cover_url = f"https://{cover_uri.replace('%%', '400x400')}"

                return {
                    "title": title.strip(),
                    "artist": artist.strip(),
                    "source": "Яндекс Музыка",
                    "cover_url": cover_url,
                    "query": f"{artist} - {title}",
                }, None

    except Exception as e:
        logger.error(f"Error fetching Yandex Music metadata: {e}")
        return None, "fetch_failed"


async def parse_music_url(url: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Определяет сервис и извлекает метаданные трека."""
    clean_url = url.strip()
    if "spotify.com" in clean_url:
        return await get_spotify_track_info(clean_url)
    elif any(d in clean_url for d in ["music.yandex.ru", "music.yandex.com", "music.yandex.by", "music.yandex.kz"]):
        return await get_yandex_track_info(clean_url)
    return None, "unsupported_service"
