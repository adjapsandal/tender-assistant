import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import WebUser
from database.repositories import Repositories
from services.parser_service import ParserService
from services.tender_processor import process_tenders
from web.dependencies import get_session
from web.schemas import SearchRequest, SearchResponse, SKUCreateRequest, SKUResponse, SKUUpdateRequest, TenderBrief
from web.utils.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/skus", response_model=list[SKUResponse])
async def get_skus(
    session: AsyncSession = Depends(get_session),
    current_user: WebUser = Depends(get_current_user),
):
    repos = Repositories(session)
    skus = await repos.sku.get_by_company(current_user.company_id, active_only=True)
    return skus


@router.post("/skus", response_model=SKUResponse, status_code=201)
async def create_sku(
    data: SKUCreateRequest,
    session: AsyncSession = Depends(get_session),
    current_user: WebUser = Depends(get_current_user),
):
    repos = Repositories(session)
    sku = await repos.sku.create(
        company_id=current_user.company_id,
        name=data.name,
        keywords=data.keywords,
        description=data.description,
        exceptions=data.exceptions,
    )
    await session.commit()
    return sku


@router.put("/skus/{sku_id}", response_model=SKUResponse)
async def update_sku(
    sku_id: int,
    data: SKUUpdateRequest,
    session: AsyncSession = Depends(get_session),
    current_user: WebUser = Depends(get_current_user),
):
    repos = Repositories(session)
    sku = await repos.sku.get(sku_id)
    if not sku or sku.company_id != current_user.company_id:
        raise HTTPException(status_code=404, detail="Набор фильтров не найден")

    update_data = data.model_dump(exclude_unset=True)
    if update_data:
        for key, value in update_data.items():
            setattr(sku, key, value)
        await session.commit()
        await session.refresh(sku)

    return sku


@router.delete("/skus/{sku_id}", status_code=204)
async def delete_sku(
    sku_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: WebUser = Depends(get_current_user),
):
    repos = Repositories(session)
    sku = await repos.sku.get(sku_id)
    if not sku or sku.company_id != current_user.company_id:
        raise HTTPException(status_code=404, detail="Набор фильтров не найден")

    await repos.sku.delete(sku_id)
    await session.commit()


@router.post("/search", response_model=SearchResponse)
async def search(
    data: SearchRequest,
    session: AsyncSession = Depends(get_session),
    current_user: WebUser = Depends(get_current_user),
):
    if not data.region.strip() and not data.industry.strip() and not data.keyword.strip() and data.sku_id == 0:
        raise HTTPException(status_code=400, detail="Заполните хотя бы одно поле")

    repos = Repositories(session)
    search_keywords = None
    search_exceptions = None
    search_keyword = data.keyword.strip() or None

    if data.sku_id:
        selected_sku = await repos.sku.get(data.sku_id)
        if selected_sku and selected_sku.company_id == current_user.company_id:
            search_keywords = selected_sku.keywords
            search_exceptions = selected_sku.exceptions
            search_keyword = None

    parser = ParserService.get_parser()
    raw_tenders = await asyncio.to_thread(
        parser.search,
        region=data.region.strip(),
        industry=data.industry.strip(),
        keyword=search_keyword,
        keywords=search_keywords,
        exceptions=search_exceptions,
        limit=50,
    )

    if not raw_tenders:
        return SearchResponse(tenders=[], count=0)

    results = await process_tenders(raw_tenders, current_user.company_id, session)

    tenders = [
        TenderBrief(
            id=t.id,
            tender_number=t.tender_number,
            title=t.title,
            customer=t.customer,
            price=t.price,
            deadline=t.deadline,
            url=t.url,
            relevance_score=t.relevance_score,
            category=t.category,
        )
        for t in results
    ]

    return SearchResponse(tenders=tenders, count=len(tenders))
