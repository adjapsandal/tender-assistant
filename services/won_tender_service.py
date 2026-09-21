import logging
from pathlib import Path

import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession

from database.repositories import Repositories
from ml.embeddings import create_embedding, to_list
from services.document_reader import read_directory, read_file

logger = logging.getLogger(__name__)


async def import_from_folder(folder_path: str, company_id: int, session: AsyncSession) -> tuple[int, int, list[str]]:
    repos = Repositories(session)
    root = Path(folder_path)

    if not root.exists() or not root.is_dir():
        return 0, 0, [f"Directory not found: {folder_path}"]

    imported = 0
    skipped = 0
    errors = []

    subfolders = sorted([d for d in root.iterdir() if d.is_dir()])

    if not subfolders:
        return 0, 0, ["No subfolders found in directory"]

    for subfolder in subfolders:
        folder_name = subfolder.name

        existing = await repos.won_tender.get_by_folder(company_id, folder_name)
        if existing:
            skipped += 1
            continue

        title = folder_name
        info_path = subfolder / "info.txt"
        if info_path.exists():
            try:
                content = read_file(str(info_path))
                first_line = content.strip().split("\n")[0].strip()
                if first_line:
                    title = first_line
            except Exception:
                pass

        text_content = read_directory(str(subfolder))

        if not text_content or len(text_content.strip()) < 50:
            errors.append(f"{folder_name}: insufficient text content")
            continue

        try:
            embedding = await create_embedding(text_content)
        except Exception as e:
            errors.append(f"{folder_name}: embedding failed - {e}")
            continue

        await repos.won_tender.create(
            company_id=company_id,
            title=title,
            source_folder=folder_name,
            text_content=text_content[:50000],
            embedding=embedding,
        )

        imported += 1
        logger.info(f"Imported won tender: {title} (from {folder_name})")

    await session.commit()
    return imported, skipped, errors


async def calculate_centroid(company_id: int, session: AsyncSession) -> list[float] | None:
    repos = Repositories(session)

    raw_embeddings = await repos.won_tender.get_embeddings(company_id)

    if not raw_embeddings:
        logger.warning(f"No won tender embeddings for company {company_id}")
        return None

    embeddings = [to_list(e) for e in raw_embeddings if to_list(e)]

    if not embeddings:
        return None

    matrix = np.array(embeddings)
    centroid = np.mean(matrix, axis=0)

    norm = np.linalg.norm(centroid)
    if norm > 0:
        centroid = centroid / norm

    centroid_list = centroid.tolist()

    company = await repos.company.get(company_id)
    if company:
        company.embedding = centroid_list
        await session.flush()
        await session.commit()
        logger.info(f"Updated company {company_id} embedding with centroid " f"from {len(embeddings)} won tenders")

    return centroid_list


async def delete_won_tender(won_tender_id: int, company_id: int, session: AsyncSession) -> bool:
    repos = Repositories(session)
    won_tender = await repos.won_tender.get(won_tender_id)

    if not won_tender or won_tender.company_id != company_id:
        return False

    await repos.won_tender.delete(won_tender_id)
    await session.commit()
    return True


async def get_won_tender_embeddings(company_id: int, session: AsyncSession) -> list[list[float]]:
    repos = Repositories(session)
    raw_embeddings = await repos.won_tender.get_embeddings(company_id)
    return [to_list(e) for e in raw_embeddings if to_list(e)]
