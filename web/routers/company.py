import logging
import tempfile

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import WebUser
from database.repositories import Repositories
from services.document import DocumentGenerator
from web.dependencies import get_session
from web.schemas import (
    CompanyDocumentResponse,
    CompanyDocumentsListResponse,
    CompanyResponse,
    CompanyUpdateRequest,
)
from web.utils.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/company", response_model=CompanyResponse)
async def get_company(
    current_user: WebUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    repos = Repositories(session)
    company = await repos.company.get(current_user.company_id)
    if not company:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return company


@router.post("/company", response_model=CompanyResponse)
async def update_company(
    data: CompanyUpdateRequest,
    current_user: WebUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    repos = Repositories(session)

    update_fields = data.model_dump(exclude_unset=True)
    if not update_fields:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update")

    company = await repos.company.update(current_user.company_id, **update_fields)
    if not company:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")

    await session.commit()
    return company


@router.get("/company/documents", response_model=CompanyDocumentsListResponse)
async def get_company_documents(
    current_user: WebUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    repos = Repositories(session)
    templates = await repos.document_template.get_by_company(current_user.company_id)

    documents = [
        CompanyDocumentResponse(
            id=t.id,
            name=t.name,
            type=t.type,
            is_default=t.is_default,
            created_at=t.created_at,
        )
        for t in templates
    ]

    return CompanyDocumentsListResponse(documents=documents, count=len(documents))


@router.get("/company/documents/{document_id}/download")
async def download_company_document(
    document_id: int,
    current_user: WebUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    repos = Repositories(session)
    template = await repos.document_template.get(document_id)

    if not template or template.company_id != current_user.company_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Документ не найден")

    gen = DocumentGenerator()
    tmp_dir = tempfile.mkdtemp()
    path = gen.save_docx(template.content, template.name, folder=tmp_dir)

    return FileResponse(
        path=path,
        filename=f"{template.name}.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
