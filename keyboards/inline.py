"""
Inline клавиатуры для бота.

Стиль как в старом боте - минималистично, функционально.
"""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Главная клавиатура меню."""
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(text="🔎 Поиск тендеров", callback_data="menu_search"),
    )

    return builder.as_markup()


def get_back_keyboard(back_to: str = "menu_main") -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой назад."""
    builder = InlineKeyboardBuilder()

    callbacks = {
        "to_region": "back_to_region",
        "to_industry": "back_to_industry",
        "to_keyword": "back_to_industry",
    }

    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data=callbacks.get(back_to, "menu_main")))

    return builder.as_markup()


def get_tender_view_keyboard(page: int, total: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    # Навигация: стрелки с кнопкой "Открыть" посередине
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="◀️", callback_data=f"page_prev_{page}"))

    nav_row.append(InlineKeyboardButton(text="Открыть", callback_data=f"select_{page}"))

    if page < total - 1:
        nav_row.append(InlineKeyboardButton(text="▶️", callback_data=f"page_next_{page}"))

    builder.row(*nav_row)

    # Кнопка меню
    builder.row(InlineKeyboardButton(text="🏠 Меню", callback_data="menu_main"))

    return builder.as_markup()


def get_tender_actions_keyboard(page: int) -> InlineKeyboardMarkup:
    """Клавиатура действий с выбранным тендером."""
    builder = InlineKeyboardBuilder()

    # Кнопка скачивания файлов
    builder.row(InlineKeyboardButton(text="📥 Скачать файлы", callback_data=f"download_{page}"))

    # Кнопка генерации
    builder.row(InlineKeyboardButton(text="📄 Сгенерировать документы", callback_data=f"generate_{page}"))

    # Кнопка назад
    builder.row(InlineKeyboardButton(text="◀️ Назад к списку", callback_data="back_to_results"))

    # Кнопка меню
    builder.row(InlineKeyboardButton(text="🏠 Меню", callback_data="menu_main"))

    return builder.as_markup()
