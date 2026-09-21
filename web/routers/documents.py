import asyncio
import logging
import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import WebUser
from database.repositories import Repositories
from services.document_gen import DocumentGeneratorService
from services.parser_service import ParserService
from web.dependencies import get_session
from web.schemas import GenerateResponse
from web.utils.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/tenders/{tender_id}/generate", response_model=GenerateResponse)
async def generate_documents(
    tender_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: WebUser = Depends(get_current_user),
):
    repos = Repositories(session)

    tender = await repos.tender.get(tender_id)
    if not tender or tender.company_id != current_user.company_id:
        raise HTTPException(status_code=404, detail="Тендер не найден")

    company = await repos.company.get(current_user.company_id)
    if not company:
        raise HTTPException(status_code=500, detail="Компания не найдена")

    parser = ParserService.get_parser()
    details = await asyncio.to_thread(parser.get_details, tender.url)

    # Update tender with fresh details if available
    if details.get("description") and not tender.description:
        tender.description = details["description"]
    if details.get("requirements") and not tender.requirements:
        tender.requirements = details["requirements"]

    files_dir = ""
    if details.get("documents"):
        files_dir = await asyncio.to_thread(parser.download_files, details["documents"], tender.tender_number)
        files_dir = files_dir or ""

    output_folder = os.path.join("outputs", tender.tender_number)
    os.makedirs(output_folder, exist_ok=True)

    gen = DocumentGeneratorService(session)

    tasks = [
        ("Коммерческое предложение", gen.generate_proposal_for_tender),
        ("Сопроводительное письмо", gen.generate_letter_for_tender),
        ("Ответ на требования", gen.generate_requirements_for_tender),
    ]

    generated_files = []
    for filename, func in tasks:
        content = await func(tender, company, files_dir=files_dir)

        await asyncio.to_thread(gen.save_docx, content, filename, output_folder)
        # await asyncio.to_thread(gen.save_pdf, content, filename, output_folder)

        generated_files.append(f"{filename}.docx")
        # generated_files.append(f"{filename}.pdf")

    return GenerateResponse(status="success", files=generated_files)


@router.get("/outputs/{tender_number}/{filename}")
async def download_output(
    tender_number: str,
    filename: str,
    session: AsyncSession = Depends(get_session),
    current_user: WebUser = Depends(get_current_user),
):
    safe_number = Path(tender_number).name
    safe_filename = Path(filename).name

    # Документы сгенерированы по тендеру — отдаём их только компании,
    # которой этот тендер принадлежит.
    repos = Repositories(session)
    tender = await repos.tender.get_by_number(safe_number, current_user.company_id)
    if not tender:
        raise HTTPException(status_code=404, detail="Файл не найден")

    file_path = Path("outputs") / safe_number / safe_filename

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Файл не найден")

    return FileResponse(path=str(file_path), filename=safe_filename, media_type="application/octet-stream")
