from typing import List, Dict, Any
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def get_search_results_keyboard(results: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    """Создает инлайн-клавиатуру с кнопками выбора трека из результатов поиска."""
    buttons_row = []

    for idx, item in enumerate(results, start=1):
        video_id = item.get("id")
        if video_id:
            buttons_row.append(
                InlineKeyboardButton(
                    text=f"▶️ {idx}",
                    callback_data=f"dl:{video_id}",
                )
            )

    keyboard = []
    if buttons_row:
        keyboard.append(buttons_row)

    keyboard.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_search")])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)
