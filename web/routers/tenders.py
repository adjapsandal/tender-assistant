import asyncio
import io
import logging
import math
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import WebUser
from database.repositories import Repositories
from services.parser_service import ParserService
from web.dependencies import get_session
from web.schemas import (
    CategoryInfo,
    TenderBrief,
    TenderDetail,
    TenderFileResponse,
    TenderFilesListResponse,
    TendersListResponse,
)
from web.utils.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()

CATEGORY_MAP = {
    "excluded": {"label": "Не подходит", "color": "#dc3545"},
    "target": {"label": "Целевой", "color": "#28a745"},
    "prospective": {"label": "Перспективный", "color": "#17a2b8"},
    "possible": {"label": "Возможный", "color": "#ffc107"},
    "low": {"label": "Низкий приоритет", "color": "#6c757d"},
}


@router.get("/tenders", response_model=TendersListResponse)
async def list_tenders(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    category: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
    current_user: WebUser = Depends(get_current_user),
):
    """Return all stored tenders with pagination and optional filters."""
    repos = Repositories(session)

    tenders, total = await repos.tender.get_by_company_paginated(
        company_id=current_user.company_id,
        page=page,
        per_page=per_page,
        category=category,
    )

    items = [
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
        for t in tenders
    ]

    return TendersListResponse(
        tenders=items,
        count=len(items),
        page=page,
        per_page=per_page,
        total_pages=math.ceil(total / per_page) if per_page else 1,
    )


@router.get("/tenders/{tender_id}", response_model=TenderDetail)
async def tender_detail(
    tender_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: WebUser = Depends(get_current_user),
):
    repos = Repositories(session)

    tender = await repos.tender.get(tender_id)
    if not tender or tender.company_id != current_user.company_id:
        raise HTTPException(status_code=404, detail="Тендер не найден")

    output_dir = Path("outputs") / (tender.tender_number or "")
    generated_files = []
    if output_dir.exists():
        generated_files = [f.name for f in output_dir.iterdir() if f.is_file()]

    cat_info = None
    if tender.category and tender.category in CATEGORY_MAP:
        info = CATEGORY_MAP[tender.category]
        cat_info = CategoryInfo(label=info["label"], color=info["color"])

    return TenderDetail(
        id=tender.id,
        tender_number=tender.tender_number,
        title=tender.title,
        customer=tender.customer,
        price=tender.price,
        deadline=tender.deadline,
        description=tender.description,
        requirements=tender.requirements,
        url=tender.url,
        relevance_score=tender.relevance_score,
        category=tender.category,
        category_info=cat_info,
        risk_flags=tender.risk_flags or [],
        missing_items=tender.missing_items or [],
        status=tender.status,
        created_at=tender.created_at,
        generated_files=generated_files,
    )


@router.get("/tenders/{tender_id}/files", response_model=TenderFilesListResponse)
async def tender_files(
    tender_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: WebUser = Depends(get_current_user),
):
    repos = Repositories(session)

    tender = await repos.tender.get(tender_id)
    if not tender or tender.company_id != current_user.company_id:
        raise HTTPException(status_code=404, detail="Тендер не найден")

    parser = ParserService.get_parser()
    details = await asyncio.to_thread(parser.get_details, tender.url)

    documents = details.get("documents", [])

    files = [
        TenderFileResponse(
            id=doc.id,
            title=doc.title,
            url=doc.url,
            extension=doc.extension,
        )
        for doc in documents
    ]

    return TenderFilesListResponse(files=files, count=len(files))


@router.get("/tenders/{tender_id}/files/{file_id}/download")
async def download_single_file(
    tender_id: int,
    file_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: WebUser = Depends(get_current_user),
):
    repos = Repositories(session)

    tender = await repos.tender.get(tender_id)
    if not tender or tender.company_id != current_user.company_id:
        raise HTTPException(status_code=404, detail="Тендер не найден")

    parser = ParserService.get_parser()
    details = await asyncio.to_thread(parser.get_details, tender.url)

    target_file = None
    for doc in details.get("documents", []):
        if doc.id == file_id:
            target_file = doc
            break

    if not target_file:
        raise HTTPException(status_code=404, detail="Файл не найден")

    def _download():
        headers = {"Referer": "https://rostender.info"}
        r = parser.session.get(target_file.url, headers=headers, timeout=60)
        r.raise_for_status()
        return r.content, r.headers.get("Content-Type", "application/octet-stream")

    content, content_type = await asyncio.to_thread(_download)

    from urllib.parse import quote

    ext = target_file.extension or ""
    filename = f"{target_file.title}.{ext}" if ext else target_file.title
    encoded = quote(filename)

    return StreamingResponse(
        io.BytesIO(content),
        media_type=content_type,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded}"},
    )


@router.get("/tenders/{tender_id}/download")
async def download_files(
    tender_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: WebUser = Depends(get_current_user),
):
    repos = Repositories(session)

    tender = await repos.tender.get(tender_id)
    if not tender or tender.company_id != current_user.company_id:
        raise HTTPException(status_code=404, detail="Тендер не найден")

    parser = ParserService.get_parser()
    details = await asyncio.to_thread(parser.get_details, tender.url)

    if not details.get("documents"):
        raise HTTPException(status_code=404, detail="К тендеру не прикреплены файлы")

    files_dir = await asyncio.to_thread(parser.download_files, details["documents"], tender.tender_number)

    if not files_dir:
        raise HTTPException(status_code=500, detail="Не удалось скачать файлы")

    zip_buffer = io.BytesIO()
    files_path = Path(files_dir)

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in files_path.iterdir():
            if file_path.is_file():
                zf.write(file_path, file_path.name)

    zip_buffer.seek(0)

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="tender_{tender.tender_number}_files.zip"'},
    )
