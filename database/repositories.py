from typing import Any

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import SKU, Company, DocumentTemplate, Tender, User, WebUser, WonTender


class BaseRepository:
    def __init__(self, session: AsyncSession, model):
        self.session = session
        self.model = model

    async def get(self, id: int) -> Any | None:
        """Get entity by ID"""
        result = await self.session.execute(select(self.model).where(self.model.id == id))
        return result.scalar_one_or_none()

    async def get_all(self, limit: int = 100, offset: int = 0) -> list[Any]:
        """Get all entities with pagination"""
        result = await self.session.execute(select(self.model).offset(offset).limit(limit))
        return list(result.scalars().all())

    async def create(self, **kwargs) -> Any:
        """Create new entity"""
        entity = self.model(**kwargs)
        self.session.add(entity)
        await self.session.flush()
        await self.session.refresh(entity)
        return entity

    async def update(self, id: int, **kwargs) -> Any | None:
        """Update entity by ID"""
        entity = await self.get(id)
        if entity is None:
            return None

        for key, value in kwargs.items():
            if hasattr(entity, key):
                setattr(entity, key, value)

        await self.session.flush()
        await self.session.refresh(entity)
        return entity

    async def delete(self, id: int) -> bool:
        """Delete entity by ID"""
        entity = await self.get(id)
        if entity is None:
            return False

        await self.session.delete(entity)
        return True


class CompanyRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, Company)

    async def get_by_telegram_id(self, telegram_id: int) -> Company | None:
        result = await self.session.execute(select(Company).join(User).where(User.telegram_id == telegram_id))
        return result.scalar_one_or_none()

    async def get_with_relations(self, company_id: int) -> Company | None:
        result = await self.session.execute(select(Company).where(Company.id == company_id))
        return result.scalar_one_or_none()


class SKURepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, SKU)

    async def get_by_company(self, company_id: int, active_only: bool = True) -> list[SKU]:
        """Get all SKUs for a company"""
        query = select(SKU).where(SKU.company_id == company_id)
        if active_only:
            query = query.where(SKU.is_active == True)

        result = await self.session.execute(query.order_by(SKU.name))
        return list(result.scalars().all())


class TenderRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, Tender)

    async def get_by_company(self, company_id: int, status: str | None = None, limit: int = 100) -> list[Tender]:
        query = select(Tender).where(Tender.company_id == company_id)

        if status:
            query = query.where(Tender.status == status)

        result = await self.session.execute(query.order_by(Tender.relevance_score.desc()).limit(limit))
        return list(result.scalars().all())

    async def get_by_company_paginated(
        self,
        company_id: int,
        page: int = 1,
        per_page: int = 20,
        category: str | None = None,
    ) -> tuple[list[Tender], int]:
        """Get tenders for a company with pagination and optional filters."""
        query = select(Tender).where(Tender.company_id == company_id)

        if category:
            query = query.where(Tender.category == category)

        # Total count
        count_result = await self.session.execute(select(func.count()).select_from(query.subquery()))
        total = count_result.scalar() or 0

        # Paginated results
        offset = (page - 1) * per_page
        result = await self.session.execute(query.order_by(Tender.created_at.desc()).offset(offset).limit(per_page))
        tenders = list(result.scalars().all())

        return tenders, total

    async def get_by_number(self, tender_number: str, company_id: int) -> Tender | None:
        result = await self.session.execute(
            select(Tender).where(and_(Tender.tender_number == tender_number, Tender.company_id == company_id))
        )
        return result.scalar_one_or_none()

    async def get_by_category(self, company_id: int, category: str) -> list[Tender]:
        result = await self.session.execute(
            select(Tender)
            .where(and_(Tender.company_id == company_id, Tender.category == category))
            .order_by(Tender.relevance_score.desc())
        )
        return list(result.scalars().all())

    async def search_by_embedding(self, embedding: list[float], company_id: int, limit: int = 10) -> list[Tender]:
        result = await self.session.execute(
            select(Tender)
            .where(and_(Tender.company_id == company_id, Tender.embedding.isnot(None)))
            .order_by(Tender.embedding.cosine_distance(embedding))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def update_score(
        self, tender_id: int, score: float, category: str, risk_flags: list[str], missing_items: list[str]
    ) -> None:
        await self.session.execute(
            update(Tender)
            .where(Tender.id == tender_id)
            .values(relevance_score=score, category=category, risk_flags=risk_flags, missing_items=missing_items)
        )

    async def update_status(self, tender_id: int, status: str) -> None:
        await self.session.execute(update(Tender).where(Tender.id == tender_id).values(status=status))


class DocumentTemplateRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, DocumentTemplate)

    async def get_by_company(self, company_id: int) -> list[DocumentTemplate]:
        result = await self.session.execute(
            select(DocumentTemplate)
            .where(DocumentTemplate.company_id == company_id)
            .order_by(DocumentTemplate.type, DocumentTemplate.name)
        )
        return list(result.scalars().all())

    async def get_by_type(self, company_id: int, template_type: str) -> list[DocumentTemplate]:
        result = await self.session.execute(
            select(DocumentTemplate)
            .where(and_(DocumentTemplate.company_id == company_id, DocumentTemplate.type == template_type))
            .order_by(DocumentTemplate.is_default.desc(), DocumentTemplate.name)
        )
        return list(result.scalars().all())

    async def get_default(self, company_id: int, template_type: str) -> DocumentTemplate | None:
        result = await self.session.execute(
            select(DocumentTemplate).where(
                and_(
                    DocumentTemplate.company_id == company_id,
                    DocumentTemplate.type == template_type,
                    DocumentTemplate.is_default == True,
                )
            )
        )
        return result.scalar_one_or_none()


class WonTenderRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, WonTender)

    async def get_by_company(self, company_id: int) -> list[WonTender]:
        result = await self.session.execute(
            select(WonTender).where(WonTender.company_id == company_id).order_by(WonTender.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_folder(self, company_id: int, folder_name: str) -> WonTender | None:
        result = await self.session.execute(
            select(WonTender).where(and_(WonTender.company_id == company_id, WonTender.source_folder == folder_name))
        )
        return result.scalar_one_or_none()

    async def get_embeddings(self, company_id: int) -> list[list[float]]:
        result = await self.session.execute(
            select(WonTender.embedding).where(and_(WonTender.company_id == company_id, WonTender.embedding.isnot(None)))
        )
        return [row[0] for row in result.all()]


class WebUserRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, WebUser)

    async def get_by_email(self, email: str) -> WebUser | None:
        result = await self.session.execute(select(WebUser).where(WebUser.email == email))
        return result.scalar_one_or_none()

    async def create_user(self, email: str, hashed_password: str, company_id: int) -> WebUser:
        user = WebUser(
            email=email,
            hashed_password=hashed_password,
            company_id=company_id,
        )
        self.session.add(user)
        await self.session.flush()
        await self.session.refresh(user)
        return user


class Repositories:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.company = CompanyRepository(session)
        self.sku = SKURepository(session)
        self.tender = TenderRepository(session)
        self.document_template = DocumentTemplateRepository(session)
        self.won_tender = WonTenderRepository(session)
        self.web_user = WebUserRepository(session)
