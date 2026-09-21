import logging

from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Company, Tender
from database.repositories import Repositories
from ml.embeddings import create_embedding
from ml.ranker import calculate_relevance, generate_missing_report
from services.won_tender_service import get_won_tender_embeddings

logger = logging.getLogger(__name__)


async def analyze_tender(tender: Tender, company: Company, session: AsyncSession):
    logger.info(f"Analyzing tender {tender.tender_number} for company {company.name}")

    repos = Repositories(session)

    skus = await repos.sku.get_by_company(company.id, active_only=True)

    exclusion_words = []
    for sku in skus:
        if sku.exceptions:
            words = [w.strip() for w in sku.exceptions.replace("\n", ",").split(",") if w.strip()]
            exclusion_words.extend(words)

    won_embeddings = await get_won_tender_embeddings(company.id, session)

    result = await calculate_relevance(
        tender=tender, company=company, skus=skus, exclusion_words=exclusion_words, won_tender_embeddings=won_embeddings
    )

    await repos.tender.update_score(
        tender_id=tender.id,
        score=result.score,
        category=result.category,
        risk_flags=result.risk_flags,
        missing_items=result.missing_items,
    )

    logger.info(f"Tender {tender.tender_number} scored {result.score}% " f"(category: {result.category})")

    return result


async def analyze_and_save(tender_data: dict, company_id: int, session: AsyncSession) -> Tender:
    repos = Repositories(session)

    files_text = tender_data.pop("files_text", "")

    existing = await repos.tender.get_by_number(tender_data.get("number", ""), company_id)

    if existing:
        tender = existing
        # Update fields
        tender.title = tender_data.get("title", existing.title)
        tender.customer = tender_data.get("customer", existing.customer)
        tender.price = tender_data.get("price", existing.price)
        tender.deadline = tender_data.get("deadline", existing.deadline)
        tender.description = tender_data.get("description", existing.description)
        tender.requirements = tender_data.get("requirements", existing.requirements)
        tender.url = tender_data.get("url", existing.url)
    else:
        # Create new tender
        tender = await repos.tender.create(
            company_id=company_id,
            tender_number=tender_data.get("number", ""),
            title=tender_data.get("title", ""),
            customer=tender_data.get("customer", ""),
            price=tender_data.get("price", ""),
            deadline=tender_data.get("deadline", ""),
            description=tender_data.get("description", ""),
            requirements=tender_data.get("requirements", ""),
            url=tender_data.get("url", ""),
            status="new",
        )

    # Generate embedding: create if missing, or re-create if files now available
    should_reembed = tender.embedding is None or (files_text and not tender.embedding_has_files)
    if should_reembed:
        text_for_embedding = _prepare_text_for_embedding(tender, files_text)
        try:
            embedding = await create_embedding(text_for_embedding)
            tender.embedding = embedding
            tender.embedding_has_files = bool(files_text)
            await session.flush()
        except Exception as e:
            logger.error(f"Failed to create embedding for tender {tender.tender_number}: {e}")

    # Get company and analyze
    company = await repos.company.get(company_id)
    if company:
        await analyze_tender(tender, company, session)

    await session.commit()
    await session.refresh(tender)

    return tender


async def batch_analyze(tender_ids: list[int], company_id: int, session: AsyncSession):
    repos = Repositories(session)
    results = []
    company = await repos.company.get(company_id)

    if not company:
        logger.error(f"Company {company_id} not found")
        return results

    for tender_id in tender_ids:
        tender = await repos.tender.get(tender_id)
        if tender:
            result = await analyze_tender(tender, company, session)
            results.append(result)

    await session.commit()
    return results


def _prepare_text_for_embedding(tender: Tender, files_text: str = "") -> str:
    parts = [tender.title, tender.description or "", tender.requirements or ""]

    # Если есть позиции товаров (SKU), добавляем их
    # Позиции могут быть в JSON-поле или в requirements
    if hasattr(tender, "positions_json") and tender.positions_json:
        if isinstance(tender.positions_json, list):
            parts.extend(tender.positions_json)
        elif isinstance(tender.positions_json, str):
            parts.append(tender.positions_json)

    # Добавляем текст из прикреплённых файлов
    if files_text:
        parts.append(files_text)

    return " ".join(filter(None, parts))


async def get_analysis_report(tender_id: int, company_id: int, session: AsyncSession) -> str | None:
    from ml.ranker import TenderScoreResult

    repos = Repositories(session)
    tender = await repos.tender.get(tender_id)

    if not tender or tender.company_id != company_id:
        return None

    # Get matched SKUs for report (простой список, без search_by_embedding)
    matched_skus = await repos.sku.get_by_company(company_id, active_only=True)

    result = TenderScoreResult(
        score=tender.relevance_score or 0,
        category=tender.category or "low",
        matched_skus=matched_skus,
        risk_flags=tender.risk_flags or [],
        missing_items=tender.missing_items or [],
        modifiers={},
    )

    return generate_missing_report(result, tender)
