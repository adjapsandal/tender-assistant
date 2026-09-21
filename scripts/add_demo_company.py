"""Завести демонстрационную компанию с эмбеддингом профиля.

Эмбеддинг профиля — опорный вектор для оценки релевантности тендеров:
найденные закупки сравниваются с ним косинусной мерой. Без компании
в базе поиск не с чем сопоставлять, поэтому этот скрипт нужен при
первом развёртывании.

Запуск: python -m scripts.add_demo_company
"""

import asyncio

from sqlalchemy import select

from database.connection import db
from database.repositories import Repositories
from ml.embeddings import create_embedding

COMPANY_NAME = "ООО «Пример»"

COMPANY_PROFILE = """ООО «Пример» — производитель и поставщик расходных материалов
и оборудования для лечебно-профилактических учреждений.

Работаем с государственными и частными медицинскими учреждениями по всем регионам РФ.
Поставляем расходные материалы и оборудование по долгосрочным контрактам.

Основные направления:
- Расходные материалы для сбора медицинских отходов
- Оборудование для утилизации медицинских отходов
- Контейнеры для медицинских отходов
- Пробирки, баночки, пакеты для лабораторных анализов
- Медицинские изделия расходного характера"""


async def add_demo_company():
    await db.connect()
    async with db.session_factory() as session:
        repos = Repositories(session)

        existing = await session.execute(select(repos.company.model).where(repos.company.model.name == COMPANY_NAME))
        if existing.scalar_one_or_none():
            print("Компания уже существует")
            return

        print("Создание embedding для компании...")
        embedding = await create_embedding(COMPANY_PROFILE)

        company = await repos.company.create(
            name=COMPANY_NAME,
            full_name="Общество с ограниченной ответственностью «Пример»",
            inn="0000000000",
            kpp="000000000",
            ogrn="0000000000000",
            address="г. Казань, ул. Примерная, д. 1",
            phone="+7 (000) 000-00-00",
            director="Иванов Иван Иванович",
            experience=COMPANY_PROFILE,
            stack="Медицинские расходные материалы, оборудование для утилизации отходов, контейнеры, пробирки",
            embedding=embedding,
        )

        await session.commit()
        await session.refresh(company)

        print("[OK] Компания добавлена:")
        print(f"   ID: {company.id}")
        print(f"   Название: {company.name}")
        print(f"   Embedding: {len(embedding)} dims")

    await db.disconnect()


if __name__ == "__main__":
    asyncio.run(add_demo_company())
