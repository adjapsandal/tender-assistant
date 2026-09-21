from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import ReplyKeyboardBuilder


def get_preset_keywords_keyboard(preset_names: list[str]) -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()

    # Добавляем кнопки для каждого пресета
    for name in preset_names:
        builder.row(KeyboardButton(text=name))

    # one_time_keyboard=True - клавиатура скроется после выбора
    # resize_keyboard=True - клавиатура будет компактной
    return builder.as_markup(resize_keyboard=True, one_time_keyboard=True)


def get_skip_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура с кнопкой пропуска."""
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="⏭ Пропустить"))
    return builder.as_markup(resize_keyboard=True, one_time_keyboard=True)
