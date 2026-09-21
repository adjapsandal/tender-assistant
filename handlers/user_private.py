import logging
import os
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.filters import CommandStart
from aiogram.filters.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message
from aiogram.utils.text_decorations import html_decoration as hd

from database.repositories import Repositories
from keyboards.inline import (
    get_back_keyboard,
    get_main_menu_keyboard,
    get_tender_actions_keyboard,
    get_tender_view_keyboard,
)
from keyboards.reply import get_preset_keywords_keyboard
from services.document_gen import DocumentGeneratorService
from services.parser_service import ParserService
from services.tender_processor import process_tenders

logger = logging.getLogger(__name__)
router = Router()


class SearchTender(StatesGroup):
    region = State()
    industry = State()
    keyword = State()


parser = None
bot_instance = None


def set_parser(p):
    global parser
    parser = p


def set_bot(bot: Bot):
    global bot_instance
    bot_instance = bot


async def get_company_id(session):
    """Получить ID компании (используем ID 5)."""
    return 5


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "<b>Тендер бот с ML</b> 👋\n\n"
        "Помогу найти тендеры на rostender.info, проанализирую их релевантность "
        "и сгенерирую документы.",
        reply_markup=get_main_menu_keyboard(),
    )


@router.callback_query(F.data == "menu_main")
async def cb_main_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "<b>Тендер бот с ML</b> 👋\n\n"
        "Помогу найти тендеры на rostender.info, проанализирую их релевантность "
        "и сгенерирую документы.",
        reply_markup=get_main_menu_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "menu_search")
async def cb_search(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.answer("Введите регион:")
    await state.set_state(SearchTender.region)
    await callback.answer()


@router.callback_query(F.data == "back_to_region")
async def cb_back_to_region(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите регион:")
    await state.set_state(SearchTender.region)
    await callback.answer()


@router.callback_query(F.data == "back_to_industry")
async def cb_back_to_industry(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите отрасль:", reply_markup=get_back_keyboard("to_region"))
    await state.set_state(SearchTender.industry)
    await callback.answer()


@router.message(SearchTender.region)
async def process_region(message: Message, state: FSMContext):
    region = message.text.strip()
    if not region:
        await message.answer("Регион не может быть пустым. Попробуйте еще раз:")
        return

    await state.update_data(region=region)
    await message.answer("Введите отрасль:", reply_markup=get_back_keyboard("to_region"))
    await state.set_state(SearchTender.industry)


@router.message(SearchTender.industry)
async def process_industry(message: Message, state: FSMContext, session):
    industry = message.text.strip()
    if not industry:
        await message.answer("Отрасль не может быть пустой. Попробуйте еще раз:")
        return

    await state.update_data(industry=industry)

    # Получаем SKU из БД для показа reply keyboard
    repos = Repositories(session)
    company_id = await get_company_id(session)
    if company_id:
        skus = await repos.sku.get_by_company(company_id)
        sku_names = [s.name for s in skus]
    else:
        sku_names = []

    if sku_names:
        # Показываем reply keyboard с SKU
        await message.answer(
            "Выберите товар или введите свое ключевое слово:", reply_markup=get_preset_keywords_keyboard(sku_names)
        )
    else:
        await message.answer("Введите ключевое слово:")

    await state.set_state(SearchTender.keyword)


@router.message(SearchTender.keyword)
async def process_keyword(message: Message, state: FSMContext, session):
    user_input = message.text.strip()
    if not user_input:
        await message.answer("Ключевое слово не может быть пустым. Попробуйте еще раз:")
        return

    data = await state.get_data()
    region = data.get("region", "")
    industry = data.get("industry", "")

    processing_msg = await message.answer("⏳ Обработка данных...")

    try:
        # Получаем ID компании
        company_id = await get_company_id(session)
        if not company_id:
            await processing_msg.edit_text(
                "❌ Компания не найдена. Сначала создайте компанию через test_db.py",
                reply_markup=get_main_menu_keyboard(),
            )
            await state.clear()
            return

        repos = Repositories(session)

        # Проверяем, выбрал ли пользователь SKU или "Свой запрос"
        skus = await repos.sku.get_by_company(company_id)
        sku_names = [s.name for s in skus]
        selected_sku = None

        if user_input in sku_names:
            # Пользователь выбрал SKU
            selected_sku = next((s for s in skus if s.name == user_input), None)
        elif user_input == "🔍 Свой запрос":
            # Пользователь хочет ввести свой запрос - спрашиваем keyword
            await processing_msg.delete()
            await message.answer("Введите ключевое слово для поиска:")
            # Сохраняем флаг что нужно будет использовать простой keyword
            await state.update_data(waiting_for_custom_keyword=True)
            return

        # Ищем тендеры
        p = ParserService.get_parser()

        if selected_sku:
            # Используем keywords/exceptions из SKU
            raw_tenders = p.search(
                region=region,
                industry=industry,
                keywords=selected_sku.keywords,
                exceptions=selected_sku.exceptions,
                limit=40,
            )
            search_info = f"SKU: {hd.quote(selected_sku.name)}"
        else:
            # Используем простой keyword
            raw_tenders = p.search(region=region, industry=industry, keyword=user_input, limit=40)
            search_info = f"Слово: {hd.quote(user_input)}"

        if not raw_tenders:
            await processing_msg.edit_text(
                "<b>Тендеры не найдены</b>\n\n" "Попробуйте изменить параметры поиска.",
                reply_markup=get_main_menu_keyboard(),
            )
            await state.clear()
            return

        # Показываем параметры
        rid = p._resolve_entity(region, "regions")
        bid = p._resolve_entity(industry, "branches", user_input)

        r_name = region
        b_name = industry

        if rid:
            r_name = next((k.title() for k, v in p.regions_map.items() if v == rid), region)
        if bid:
            b_name = next((k.title() for k, v in p.branches_map.items() if v == bid), industry)

        await processing_msg.edit_text(
            f"<b>Параметры поиска:</b>\n"
            f"Регион: {hd.quote(r_name)}\n"
            f"Отрасль: {hd.quote(b_name)}\n"
            f"{search_info}"
        )

        search_msg = await message.answer("🔍 Поиск и анализ тендеров (с файлами)...")

        results = await process_tenders(raw_tenders, company_id, repos.session)

        await state.update_data(tenders=results, current_page=0)
        await state.set_state(None)

        await show_tender_page(search_msg, results, 0)

    except Exception as e:
        logger.error(f"Search error: {e}")
        await processing_msg.edit_text(f"Произошла ошибка при поиске: {hd.quote(str(e))}")
        await state.clear()


def category_to_russian(category: str) -> str:
    """Перевод категории на русский с бизнес-логикой."""
    ru_map = {
        "excluded": "❌ Не подходит",
        "target": "🎯 Идеально",
        "prospective": "📈 Перспективно",
        "possible": "📊 Требуется анализ",
        "low": "📉 Низкий приоритет",
    }
    return ru_map.get(category, "❓ Неизвестно")


async def show_tender_page(message, tenders, page_index):
    if page_index < 0 or page_index >= len(tenders):
        logger.error(f"Invalid page index: {page_index}, total: {len(tenders)}")
        return

    tender = tenders[page_index]
    desc_short = tender.description[:300] + "..." if len(tender.description) > 300 else tender.description

    # Форматируем дату - добавляем пробелы
    deadline = tender.deadline
    if deadline:
        # "Окончание (МСК)18.12.202508:00" -> "Окончание (МСК) 18.12.2025 08:00"
        deadline = deadline.replace("(МСК)", "(МСК) ").replace("2025", "2025 ").replace("2026", "2026 ")
        # Убираем двойные пробелы
        deadline = deadline.replace("  ", " ")

    category_ru = category_to_russian(tender.category) if tender.category else "❓ Неизвестно"

    text = (
        f"<b>📋 Тендер {page_index + 1} из {len(tenders)}</b>\n\n"
        f"<b>{tender.title}</b>\n\n"
        f"<b>№:</b> {tender.tender_number}\n"
        f"<b>Заказчик:</b> {tender.customer}\n"
        f"<b>Цена:</b> {tender.price}\n"
        f"<b>До:</b> {deadline}\n\n"
        f"<b>Релевантность:</b> {tender.relevance_score or 0:.1f}%\n"
        f"<b>Статус:</b> {category_ru}\n\n"
        f"<b>Описание:</b>\n{desc_short}"
    )

    await message.edit_text(text, reply_markup=get_tender_view_keyboard(page_index, len(tenders)))


@router.callback_query(F.data.startswith("page_"))
async def cb_page_navigation(callback: CallbackQuery, state: FSMContext):
    try:
        parts = callback.data.split("_")
        if len(parts) != 3:
            await callback.answer("Неверный формат данных", show_alert=True)
            return

        action = parts[1]
        page = int(parts[2])

        data = await state.get_data()
        tenders = data.get("tenders", [])

        if not tenders:
            await callback.answer("Список тендеров пуст. Начните поиск заново.", show_alert=True)
            return

        current_page = data.get("current_page", 0)

        if action == "prev":
            new_page = max(0, current_page - 1)
        elif action == "next":
            new_page = min(len(tenders) - 1, current_page + 1)
        elif action == "show":
            new_page = page
        else:
            await callback.answer("Неизвестное действие", show_alert=True)
            return

        await state.update_data(current_page=new_page)
        await show_tender_page(callback.message, tenders, new_page)
        await callback.answer()

    except (ValueError, IndexError) as e:
        logger.error(f"Navigation error: {e} - callback_data: {callback.data}")
        await callback.answer("Ошибка навигации", show_alert=True)


@router.callback_query(F.data.startswith("select_"))
async def cb_select_tender(callback: CallbackQuery, state: FSMContext, session):
    try:
        _, page_str = callback.data.split("_")
        page = int(page_str)

        data = await state.get_data()
        tenders = data.get("tenders", [])

        if not tenders or page < 0 or page >= len(tenders):
            await callback.answer("Тендер не найден", show_alert=True)
            return

        tender = tenders[page]
        await state.update_data(selected_tender=tender, selected_index=page)

        # Получаем детали
        p = ParserService.get_parser()
        details = p.get_details(tender.url)

        # Форматируем дату
        deadline = tender.deadline
        if deadline:
            deadline = deadline.replace("(МСК)", "(МСК) ").replace("2025", "2025 ").replace("2026", "2026 ")
            deadline = deadline.replace("  ", " ")

        category_ru = category_to_russian(tender.category) if tender.category else "❓ Неизвестно"

        text = (
            f"<b>📋 {tender.title}</b>\n\n"
            f"<b>№:</b> {tender.tender_number}\n"
            f"<b>Заказчик:</b> {tender.customer}\n"
            f"<b>Цена:</b> {tender.price}\n"
            f"<b>До:</b> {deadline}\n\n"
            f"<b>Релевантность:</b> {tender.relevance_score or 0:.1f}%\n"
            f"<b>Статус:</b> {category_ru}\n\n"
        )

        if tender.risk_flags:
            text += "<b>⚠️ Риски:</b>\n"
            for flag in tender.risk_flags[:3]:
                text += f"  • {flag}\n"

        if tender.missing_items:
            text += "\n<b>❌ Отсутствует:</b>\n"
            for item in tender.missing_items[:3]:
                text += f"  • {item}\n"

        text += f"\n<b>Описание:</b>\n{(details['description'] or tender.description)[:500]}"

        await callback.message.edit_text(text, reply_markup=get_tender_actions_keyboard(page))
        await callback.answer()

    except (ValueError, IndexError) as e:
        logger.error(f"Tender selection error: {e}")
        await callback.answer("Ошибка выбора тендера", show_alert=True)


@router.callback_query(F.data == "back_to_results")
async def cb_back_to_results(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    tenders = data.get("tenders", [])
    page = data.get("current_page", 0)

    if not tenders:
        await callback.answer("Список тендеров пуст", show_alert=True)
        return

    await show_tender_page(callback.message, tenders, page)
    await callback.answer()


@router.callback_query(F.data.startswith("download_"))
async def cb_download_files(callback: CallbackQuery, state: FSMContext):
    """Скачать файлы тендера."""
    try:
        data = await state.get_data()
        tender = data.get("selected_tender")

        if not tender:
            await callback.answer("Тендер не выбран", show_alert=True)
            return

        await callback.answer("⏳ Получение списка файлов...")

        # Получаем детали тендера
        p = ParserService.get_parser()
        details = p.get_details(tender.url)

        if not details.get("documents"):
            await callback.message.answer(f"❌ К тендеру **{tender.tender_number}** не прикреплены файлы.")
            return

        # Отправляем статус отдельным сообщением
        status_msg = await callback.message.answer(
            f"📥 Найдено файлов: <b>{len(details['documents'])}</b>\n" f"Скачивание..."
        )

        # Скачиваем файлы
        files_dir = p.download_files(details["documents"], tender.tender_number)

        if not files_dir:
            await status_msg.edit_text("❌ Не удалось скачать файлы")
            return

        # Отправляем файлы пользователю
        files_path = Path(files_dir)

        sent_count = 0
        for file_path in files_path.iterdir():
            if file_path.is_file():
                try:
                    file = FSInputFile(file_path)
                    await bot_instance.send_document(callback.message.chat.id, file)
                    sent_count += 1
                except Exception as e:
                    logger.error(f"Failed to send file {file_path.name}: {e}")

        # Обновляем статусное сообщение (не трогаем описание тендера!)
        await status_msg.edit_text(f"✅ Отправлено файлов: <b>{sent_count}</b>\n\n" f"Тендер: {tender.title[:50]}...")

    except Exception as e:
        logger.error(f"Download error: {e}")
        await callback.answer(f"Ошибка: {str(e)}", show_alert=True)


@router.callback_query(F.data.startswith("generate_"))
async def cb_generate_docs(callback: CallbackQuery, state: FSMContext, session):
    try:
        data = await state.get_data()
        tender = data.get("selected_tender")

        if not tender:
            await callback.answer("Тендер не выбран", show_alert=True)
            return

        await callback.answer("⏳ Генерация документов...")

        # Отправляем статус отдельным сообщением (не трогаем описание тендера!)
        status_msg = await callback.message.answer("📄 Получение деталей тендера...")

        p = ParserService.get_parser()
        details = p.get_details(tender.url)

        doc_data = {
            "number": tender.tender_number,
            "title": tender.title,
            "customer": tender.customer,
            "price": tender.price,
            "description": details["description"] or tender.description,
            "requirements": details["requirements"],
        }

        files_dir = ""
        if details["documents"]:
            await status_msg.edit_text(f"📥 Найдено файлов: {len(details['documents'])}\n" f"Скачивание для анализа...")
            files_dir = p.download_files(details["documents"], tender.tender_number)

        await status_msg.edit_text("📝 Генерация документов...")

        gen = DocumentGeneratorService(session)
        output_folder = os.path.join("outputs", tender.tender_number)
        os.makedirs(output_folder, exist_ok=True)

        tasks = [
            ("Коммерческое предложение", gen.generate_proposal, "commercial_proposal"),
            ("Сопроводительное письмо", gen.generate_letter, "cover_letter"),
            ("Ответы на требования", gen.generate_requirements, "requirements_response"),
        ]

        generated_files = []
        for i, (name, func, file_suffix) in enumerate(tasks, 1):
            await status_msg.edit_text(f"📝 [{i}/{len(tasks)}] {name}...")
            content = func(doc_data, files_dir)

            docx_path = gen.save_docx(content, f"{tender.tender_number}_{file_suffix}", folder=output_folder)
            generated_files.append(("DOCX", docx_path, name))

            pdf_path = gen.save_pdf(content, f"{tender.tender_number}_{file_suffix}", folder=output_folder)
            if pdf_path:
                generated_files.append(("PDF", pdf_path, name))

        await status_msg.edit_text(f"📤 Отправка {len(generated_files)} файлов...")

        for _doc_type, path, _name in generated_files:
            if os.path.exists(path):
                file = FSInputFile(path)
                await bot_instance.send_document(callback.message.chat.id, file)

        # Обновляем только статусное сообщение
        await status_msg.edit_text(
            f"✅ Все документы сгенерированы и отправлены!\n\n"
            f"Тендер: {tender.title[:50]}...\n"
            f"Документов: {len(generated_files)}"
        )

    except Exception as e:
        logger.error(f"Generation error: {e}")
        await callback.answer(f"Ошибка: {str(e)}", show_alert=True)
