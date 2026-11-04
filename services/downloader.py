import asyncio
import logging
import os
import urllib.request
import uuid
from pathlib import Path
from typing import Optional, Dict, Any, List

import yt_dlp
from mutagen.id3 import ID3, APIC, TIT2, TPE1, ID3NoHeaderError
from mutagen.mp3 import MP3

from config import DOWNLOAD_DIR

logger = logging.getLogger(__name__)


def format_duration(seconds: Optional[int]) -> str:
    """Форматирует длительность в секундах в формат ММ:СС."""
    if not seconds:
        return "00:00"
    mins = seconds // 60
    secs = seconds % 60
    return f"{mins:02d}:{secs:02d}"


def _get_ydl_base_opts() -> dict:
    """Базовые настройки yt-dlp с защитой от блокировок дата-центров."""
    return {
        "format": "bestaudio/best",
        "quiet": True,
        "no_warnings": True,
        "nocheckcertificate": True,
        "ignoreerrors": False,
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "web"],
                "player_skip": ["webpage", "configs"],
            }
        },
        "default_search": "ytsearch",
        "socket_timeout": 20,
    }


def _search_top3_sync(query: str) -> List[Dict[str, Any]]:
    """Синхронный поиск топ-3 результатов на YouTube."""
    ydl_opts = _get_ydl_base_opts()
    ydl_opts["extract_flat"] = True

    search_query = f"ytsearch3:{query}"
    results = []

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(search_query, download=False)
            if not info or "entries" not in info:
                return []

            for entry in info["entries"]:
                if not entry:
                    continue
                results.append(
                    {
                        "id": entry.get("id"),
                        "title": entry.get("title", "Без названия"),
                        "duration": format_duration(entry.get("duration")),
                        "duration_sec": entry.get("duration", 0),
                        "uploader": entry.get("uploader", "Неизвестен"),
                        "url": f"https://www.youtube.com/watch?v={entry.get('id')}",
                    }
                )
    except Exception as e:
        logger.error(f"Search top 3 error for query '{query}': {e}")

    return results


async def search_top3(query: str) -> List[Dict[str, Any]]:
    """Асинхронная обертка для поиска топ-3 треков."""
    return await asyncio.to_thread(_search_top3_sync, query)


def _embed_tags_and_cover(
    mp3_path: Path,
    title: str,
    artist: str,
    cover_url: Optional[str] = None,
) -> Optional[Path]:
    """Вшивает теги ID3 (название, артист) и обложку в MP3 файл."""
    cover_file_path = None
    cover_bytes = None

    if cover_url:
        try:
            req = urllib.request.Request(
                cover_url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                cover_bytes = resp.read()

            # Сохраняем обложку временно для Telegram thumb
            cover_file_path = mp3_path.with_suffix(".jpg")
            with open(cover_file_path, "wb") as f:
                f.write(cover_bytes)
        except Exception as e:
            logger.warning(f"Failed to fetch cover art from {cover_url}: {e}")

    try:
        try:
            tags = ID3(mp3_path)
        except ID3NoHeaderError:
            tags = ID3()

        tags.add(TIT2(encoding=3, text=title))
        tags.add(TPE1(encoding=3, text=artist))

        if cover_bytes:
            tags.add(
                APIC(
                    encoding=3,
                    mime="image/jpeg",
                    type=3,  # Album front cover
                    desc="Cover",
                    data=cover_bytes,
                )
            )

        tags.save(mp3_path)
    except Exception as e:
        logger.error(f"Failed to write ID3 tags to {mp3_path}: {e}")

    return cover_file_path


def _download_track_sync(
    search_or_url: str,
    title: Optional[str] = None,
    artist: Optional[str] = None,
    cover_url: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Синхронная функция скачивания аудио через yt-dlp и конвертации в MP3 320 kbps.
    """
    unique_id = uuid.uuid4().hex[:8]
    output_template = str(DOWNLOAD_DIR / f"{unique_id}_%(title).50s.%(ext)s")

    ydl_opts = _get_ydl_base_opts()
    ydl_opts.update(
        {
            "outtmpl": output_template,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "320",
                }
            ],
        }
    )

    # Если передан не прямой URL на youtube, формируем поисковый запрос
    query = search_or_url
    if not (search_or_url.startswith("http://") or search_or_url.startswith("https://")):
        query = f"ytsearch1:{search_or_url} audio"

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(query, download=True)
            if not info:
                return None

            # Если это был поиск, берем первую запись
            if "entries" in info and info["entries"]:
                video_info = info["entries"][0]
            else:
                video_info = info

            if not video_info:
                return None

            # Находим получившийся mp3 файл
            # yt-dlp заменяет расширение на .mp3
            extracted_title = video_info.get("title", "Unknown Track")
            extracted_uploader = video_info.get("uploader", "Unknown Artist")
            duration = video_info.get("duration", 0)

            # Ищем созданный файл по префиксу
            mp3_files = list(DOWNLOAD_DIR.glob(f"{unique_id}_*.mp3"))
            if not mp3_files:
                logger.error(f"No mp3 file generated for {unique_id}")
                return None

            mp3_path = mp3_files[0]

            final_title = title or extracted_title
            final_artist = artist or extracted_uploader

            # Если обложка не была передана (например, при текстовом поиске),
            # пробуем взять thumbnail с YouTube
            if not cover_url:
                cover_url = video_info.get("thumbnail")

            # Вшиваем теги и получаем файл обложки для Telegram
            cover_file_path = _embed_tags_and_cover(
                mp3_path, final_title, final_artist, cover_url
            )

            # Получаем длительность из MP3 или info
            try:
                audio = MP3(mp3_path)
                final_duration = int(audio.info.length)
            except Exception:
                final_duration = int(duration) if duration else 0

            file_size_mb = os.path.getsize(mp3_path) / (1024 * 1024)

            return {
                "file_path": mp3_path,
                "cover_path": cover_file_path,
                "title": final_title,
                "artist": final_artist,
                "duration": final_duration,
                "duration_str": format_duration(final_duration),
                "file_size_mb": round(file_size_mb, 2),
            }

    except Exception as e:
        logger.error(f"Download failed for query '{query}': {e}")
        return None


async def download_track(
    search_or_url: str,
    title: Optional[str] = None,
    artist: Optional[str] = None,
    cover_url: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Асинхронная обертка для скачивания и подготовки трека."""
    return await asyncio.to_thread(
        _download_track_sync, search_or_url, title, artist, cover_url
    )


def cleanup_files(*paths: Optional[Path]):
    """Удаляет временные файлы с диска."""
    for p in paths:
        if p and isinstance(p, Path) and p.exists():
            try:
                p.unlink()
            except Exception as e:
                logger.warning(f"Failed to delete temporary file {p}: {e}")
