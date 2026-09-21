import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from database.connection import Database
from database.models import Company
from database.repositories import Repositories
from services.parser import RostenderParser
from services.parser_service import ParserService
from services.tender_analyzer import analyze_and_save


async def select_or_create_company(repos: Repositories) -> Company:
    """Выбрать существующую компанию или создать новую."""
    print("\n=== ВЫБОР КОМПАНИИ ===")

    # Проверка существования компаний
    companies = await repos.company.get_all()

    if companies:
        print(f"\nНайдено компаний: {len(companies)}")
        for i, c in enumerate(companies, 1):
            print(f"  [{i}] {c.name} (ИНН: {c.inn})")

        print("\n[А] Создать новую компанию")

        while True:
            choice = input("\nВыберите компанию (номер или А для новой): ").strip().upper()

            if choice == "A" or choice == "А":
                return await create_company_interactive(repos)

            if choice.isdigit() and 1 <= int(choice) <= len(companies):
                company = companies[int(choice) - 1]
                print(f"\n[OK] Выбрана: {company.name}")
                return company

            print("Неверный выбор. Попробуйте снова.")
    else:
        print("\nКомпании не найдены. Создание новой...")
        return await create_company_interactive(repos)


async def create_company_interactive(repos: Repositories) -> Company:
    """Создание компании в интерактивном режиме."""
    print("\n=== СОЗДАНИЕ НОВОЙ КОМПАНИИ ===")

    name = input("Название компании: ").strip()
    if not name:
        print("[ОШИБКА] Название обязательно")
        return await select_or_create_company(repos)

    full_name = input("Полное название (опционально): ").strip() or name
    inn = input("ИНН (опционально): ").strip()
    director = input("Директор (опционально): ").strip()
    experience = input("Опыт (опционально): ").strip()
    stack = input("Продукты/Услуги (через запятую): ").strip()

    # Создание компании
    company = await repos.company.create(
        name=name, full_name=full_name, inn=inn, director=director, experience=experience, stack=stack
    )

    # Создание embedding
    from ml.embeddings import create_embedding

    description = f"{name} {experience} {stack}"
    print("\n[*] Создание embedding для компании...")
    embedding = await create_embedding(description)
    company.embedding = embedding
    await repos.session.commit()

    print(f"[OK] Компания создана: {company.name} (ID: {company.id})")
    return company


async def search_tenders_console(repos: Repositories, parser: RostenderParser, company: Company):
    """Поиск тендеров на rostender.info."""
    print("\n=== ПОИСК ТЕНДЕРОВ ===")

    print("\nОставьте пустым для пропуска:")
    region = input("Регион (например, Татарстан): ").strip() or ""
    industry = input("Отрасль (например, Медицина): ").strip() or ""
    keyword = input("Ключевое слово (обязательно): ").strip()

    if not keyword:
        print("[ОШИБКА] Ключевое слово обязательно")
        return []

    # Получаем exclusion filters из БД
    exclusion_filters = await repos.exclusion_filter.get_by_company(company.id)
    exclusion_words = [f.word for f in exclusion_filters]

    print("\n[*] Поиск тендеров...")
    print(f"    Регион: {region or 'Все'}")
    print(f"    Отрасль: {industry or 'Все'}")
    print(f"    Ключевое слово: {keyword}")
    if exclusion_words:
        print(f"    Исключающих слов: {len(exclusion_words)}")

    raw_tenders = parser.search(region, industry, keyword, exceptions=exclusion_words, limit=40)

    if not raw_tenders:
        print("\n[ИНФО] Тендеры не найдены")
        return []

    print(f"\n[OK] Найдено тендеров: {len(raw_tenders)}")

    return raw_tenders


async def analyze_and_display_tenders(
    repos: Repositories, raw_tenders: list, company: Company, parser: RostenderParser
):
    """Анализ тендеров и отображение ранжированных результатов."""
    import os

    from services.document_reader import read_file

    print("\n=== АНАЛИЗ ТЕНДЕРОВ ===")

    results = []
    for i, raw in enumerate(raw_tenders, 1):
        print(f"\n[{i}/{len(raw_tenders)}] Анализ: {raw.title[:50]}...")

        # Получаем детали тендера с позициями товаров и документами
        details = parser.get_details(raw.url)
        positions = details.get("positions", [])
        documents = details.get("documents", [])

        if positions:
            print(f"    Позиций: {len(positions)}")
            for pos in positions[:3]:
                print(f"      - {pos}")
            if len(positions) > 3:
                print(f"      ... и ещё {len(positions) - 3}")

        # Скачиваем и читаем файлы для анализа
        files_text = ""
        if documents:
            print(f"    Файлов: {len(documents)}")

            # Создаём папку для скачивания
            import tempfile

            temp_dir = tempfile.mkdtemp(prefix=f"tender_{raw.number}_")

            try:
                # Скачиваем файлы
                downloaded_path = parser.download_files(documents, temp_dir)

                if downloaded_path:
                    # Читаем содержимое файлов
                    files_content = []

                    for file in documents:
                        if file.local_path and os.path.exists(file.local_path):
                            print(f"      Чтение: {file.title[:30]}...")
                            content = read_file(file.local_path)

                            # Ограничиваем размер текста
                            if len(content) > 5000:
                                content = content[:5000] + "\n[...]"

                            if content and not content.startswith("[Unsupported") and not content.startswith("[Error]"):
                                files_content.append(f"=== {file.title} ===\n{content}")

                    if files_content:
                        files_text = "\n\n".join(files_content)
                        print(f"      Извлечено текста: {len(files_text)} символов")
            except Exception as e:
                print(f"      [ОШИБКА] Чтение файлов: {e}")
            finally:
                # Очищаем временные файлы
                import shutil

                # ignore_errors=True уже гасит ошибки удаления
                shutil.rmtree(temp_dir, ignore_errors=True)

        # Добавляем позиции в requirements для лучшего анализа
        requirements = details.get("requirements", "")
        if positions:
            positions_text = "Позиции товаров: " + ", ".join(positions)
            requirements = f"{requirements}\n{positions_text}" if requirements else positions_text

        tender_data = {
            "number": raw.number,
            "title": raw.title,
            "customer": raw.customer,
            "price": raw.price,
            "deadline": raw.deadline,
            "description": details.get("description", raw.description),
            "requirements": requirements,
            "url": raw.url,
            "files_text": files_text,  # Добавляем текст файлов
        }

        try:
            tender = await analyze_and_save(tender_data, company.id, repos.session)
            results.append(tender)
            print(f"    Оценка: {tender.relevance_score or 0:.1f}% | Категория: {tender.category or 'неизвестно'}")
        except Exception as e:
            print(f"    [ОШИБКА] {e}")

    await repos.session.commit()

    # Показ отсортированных результатов
    print("\n=== РЕЗУЛЬТАТЫ РАНЖИРОВАНИЯ ===")

    # Сортировка по релевантности
    results.sort(key=lambda t: t.relevance_score or 0, reverse=True)

    categories_order = ["target", "prospective", "possible", "low"]
    category_names = {"target": "ЦЕЛЕВЫЕ", "prospective": "ПЕРСПЕКТИВНЫЕ", "possible": "ВОЗМОЖНЫЕ", "low": "НИЗКИЙ"}

    for category in categories_order:
        category_tenders = [t for t in results if (t.category or "low") == category]
        if not category_tenders:
            continue

        print(f"\n--- {category_names.get(category, category.upper())} ({len(category_tenders)}) ---")

        for tender in category_tenders[:5]:  # Топ 5 в каждой категории
            print(f"\n[{tender.tender_number}] {tender.title}")
            print(f"    Оценка: {tender.relevance_score or 0:.1f}%")
            print(f"    Заказчик: {tender.customer}")
            print(f"    Цена: {tender.price}")
            print(f"    Срок: {tender.deadline}")

            if tender.risk_flags:
                print(f"    Риски: {', '.join(tender.risk_flags)}")

            if tender.missing_items:
                print(f"    Отсутствует: {', '.join(tender.missing_items)}")


async def show_company_details(repos: Repositories, company: Company):
    """Показать детали и статистику компании."""
    print("\n=== ДЕТАЛИ КОМПАНИИ ===")
    print(f"Название: {company.name}")
    print(f"Полное название: {company.full_name}")
    print(f"ИНН: {company.inn}")
    print(f"Директор: {company.director}")
    print(f"Опыт: {company.experience}")
    print(f"Продукты: {company.stack}")

    # Получение SKU
    skus = await repos.sku.get_by_company(company.id, active_only=True)
    print(f"\nПродукты ({len(skus)}):")
    for sku in skus[:10]:
        certs = []
        if sku.has_ru:
            certs.append("РУ")
        if sku.has_ss:
            certs.append("СС")
        if sku.has_gisp:
            certs.append("ГИСП")
        cert_str = f" ({', '.join(certs)})" if certs else ""

        print(f"  - {sku.name}{cert_str}")

    if len(skus) > 10:
        print(f"  ... и ещё {len(skus) - 10}")

    # Получение фильтров исключения
    filters = await repos.exclusion_filter.get_by_company(company.id)
    if filters:
        print(f"\nСлова исключения ({len(filters)}):")
        for f in filters:
            print(f"  - {f.word}")


async def main():
    """Главная консольная программа."""
    print("=" * 70)
    print(" Tender Assistant - Консольный интерфейс")
    print("=" * 70)

    # Подключение к базе данных
    print("\n[*] Подключение к базе данных...")
    db = Database()
    await db.connect()

    print("[OK] Подключение установлено")

    async for session in db.get_session():
        repos = Repositories(session)

        try:
            # Шаг 1: Выбор или создание компании
            company = await select_or_create_company(repos)

            # Шаг 2: Показ деталей компании
            await show_company_details(repos, company)

            # Шаг 3: Поиск тендеров
            parser_service = ParserService(session)
            parser = parser_service.get_parser()

            raw_tenders = await search_tenders_console(repos, parser, company)

            if not raw_tenders:
                print("\n[ИНФО] Выход...")
                return

            # Шаг 4: Анализ и ранжирование
            await analyze_and_display_tenders(repos, raw_tenders, company, parser)

            print("\n" + "=" * 70)
            print("[OK] ГОТОВО!")
            print("=" * 70)

        except Exception as e:
            print(f"\n[ОШИБКА] {e}")
            import traceback

            traceback.print_exc()

    await db.disconnect()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n[ИНФО] Прервано пользователем")
        sys.exit(0)
