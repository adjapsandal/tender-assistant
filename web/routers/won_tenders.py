import io
import logging
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import WebUser
from database.repositories import Repositories
from services.won_tender_service import (
    calculate_centroid,
    delete_won_tender,
    import_from_folder,
)
from web.dependencies import get_session
from web.schemas import (
    ImportRequest,
    ImportResponse,
    MessageResponse,
    WonTenderResponse,
    WonTendersListResponse,
)
from web.utils.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()

# Импорт работает только внутри этого каталога: путь из запроса — имя
# подпапки, а не произвольное место на диске.
WON_TENDERS_ROOT = Path("won_tenders")


def _resolve_import_folder(raw_path: str) -> Path:
    """Привести путь из запроса к папке внутри WON_TENDERS_ROOT.

    Раньше путь уходил в файловую систему как есть, поэтому запросом можно
    было прочитать любой каталог на сервере. Теперь принимается только имя
    подпапки, а результат проверяется на выход за пределы корня.
    """
    root = WON_TENDERS_ROOT.resolve()
    candidate = (root / raw_path.strip().lstrip("/\\")).resolve()

    if candidate != root and root not in candidate.parents:
        raise HTTPException(status_code=400, detail="Недопустимый путь")

    if not candidate.is_dir():
        raise HTTPException(status_code=404, detail="Папка не найдена")

    return candidate


@router.get("/won-tenders", response_model=WonTendersListResponse)
async def won_tenders_list(
    session: AsyncSession = Depends(get_session),
    current_user: WebUser = Depends(get_current_user),
):
    repos = Repositories(session)

    won_tenders = await repos.won_tender.get_by_company(current_user.company_id)
    company = await repos.company.get(current_user.company_id)

    has_centroid = company is not None and company.embedding is not None

    items = [
        WonTenderResponse(
            id=wt.id,
            title=wt.title,
            source_folder=wt.source_folder,
            has_embedding=wt.embedding is not None,
            created_at=wt.created_at,
        )
        for wt in won_tenders
    ]

    return WonTendersListResponse(
        won_tenders=items,
        count=len(items),
        has_centroid=has_centroid,
    )


@router.post("/won-tenders/import", response_model=ImportResponse)
async def import_won_tenders(
    data: ImportRequest,
    session: AsyncSession = Depends(get_session),
    current_user: WebUser = Depends(get_current_user),
):
    folder = _resolve_import_folder(data.folder_path)

    imported, skipped, errors = await import_from_folder(str(folder), current_user.company_id, session)

    return ImportResponse(imported=imported, skipped=skipped, errors=errors)


@router.post("/won-tenders/recalculate", response_model=MessageResponse)
async def recalculate_centroid_route(
    session: AsyncSession = Depends(get_session),
    current_user: WebUser = Depends(get_current_user),
):
    centroid = await calculate_centroid(current_user.company_id, session)

    if centroid:
        return MessageResponse(status="success", message="Центроид компании пересчитан")
    else:
        raise HTTPException(status_code=400, detail="Нет эмбеддингов для расчёта центроида")


@router.delete("/won-tenders/{won_tender_id}", response_model=MessageResponse)
async def delete_won_tender_route(
    won_tender_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: WebUser = Depends(get_current_user),
):
    deleted = await delete_won_tender(won_tender_id, current_user.company_id, session)

    if not deleted:
        raise HTTPException(status_code=404, detail="Выигранный тендер не найден")

    return MessageResponse(status="success", message="Выигранный тендер удалён")


@router.get("/won-tenders/{won_tender_id}/download")
async def download_won_tender(
    won_tender_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: WebUser = Depends(get_current_user),
):
    repos = Repositories(session)
    wt = await repos.won_tender.get(won_tender_id)

    if not wt or wt.company_id != current_user.company_id:
        raise HTTPException(status_code=404, detail="Выигранный тендер не найден")

    folder = WON_TENDERS_ROOT / Path(wt.source_folder or "").name
    if not folder.exists() or not folder.is_dir():
        raise HTTPException(status_code=404, detail="Папка с файлами не найдена")

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in folder.iterdir():
            if file_path.is_file():
                zf.write(file_path, file_path.name)

    zip_buffer.seek(0)

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="won_tender_{wt.source_folder}.zip"'},
    )
