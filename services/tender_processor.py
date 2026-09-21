import asyncio
import logging
import os
import shutil
import tempfile

from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Tender
from database.repositories import Repositories
from services.document_reader import read_file
from services.parser_service import ParserService
from services.tender_analyzer import analyze_and_save

logger = logging.getLogger(__name__)

MAX_FILE_TEXT_LEN = 5000
MAX_FILES_PER_TENDER = 10


async def _fetch_one(raw, parser, sem: asyncio.Semaphore) -> dict:
    """Fetch details + download/read files for a single tender. Runs under semaphore."""
    async with sem:
        try:
            details = await asyncio.to_thread(parser.get_details, raw.url)
        except Exception as e:
            logger.error(f"get_details failed for {raw.number}: {e}")
            return {"raw": raw, "details": {}, "files_text": ""}

        positions = details.get("positions", [])
        documents = details.get("documents", [])

        files_text = ""
        if documents:
            temp_dir = tempfile.mkdtemp(prefix=f"tender_{raw.number}_")
            try:
                downloaded_path = await asyncio.to_thread(
                    parser.download_files, documents[:MAX_FILES_PER_TENDER], temp_dir
                )

                if downloaded_path:
                    files_content = []
                    for file in documents[:MAX_FILES_PER_TENDER]:
                        if file.local_path and os.path.exists(file.local_path):
                            content = await asyncio.to_thread(read_file, file.local_path)

                            if len(content) > MAX_FILE_TEXT_LEN:
                                content = content[:MAX_FILE_TEXT_LEN] + "\n[...]"

                            if content and not content.startswith("[Unsupported") and not content.startswith("[Error]"):
                                files_content.append(f"=== {file.title} ===\n{content}")

                    if files_content:
                        files_text = "\n\n".join(files_content)
                        logger.info(f"Tender {raw.number}: extracted {len(files_text)} chars from files")
            except Exception as e:
                logger.error(f"File download/read error for {raw.number}: {e}")
            finally:
                shutil.rmtree(temp_dir, ignore_errors=True)

        requirements = details.get("requirements", "")
        if positions:
            positions_text = "Позиции: " + ", ".join(positions[:5])
            requirements = f"{requirements}\n{positions_text}" if requirements else positions_text

        return {
            "raw": raw,
            "details": details,
            "files_text": files_text,
            "requirements": requirements,
        }


async def process_tenders(
    raw_tenders: list,
    company_id: int,
    session: AsyncSession,
    max_concurrent: int = 5,
) -> list[Tender]:
    """
    Process tenders with parallel file downloads and embedding cache.

    1. Check DB cache — skip file downloads for tenders with embedding_has_files=True
    2. Parallel fetch details + files for non-cached tenders
    3. Sequential analyze_and_save for all tenders

    Args:
        raw_tenders: List of raw tender objects from parser.search()
        company_id: Company ID for analysis
        session: Database session
        max_concurrent: Max parallel fetches (default 5)

    Returns:
        List of Tender objects sorted by relevance_score DESC
    """
    if not raw_tenders:
        return []

    parser = ParserService.get_parser()
    repos = Repositories(session)
    sem = asyncio.Semaphore(max_concurrent)

    # Phase 1: Check cache
    cached = {}
    to_fetch = []
    for raw in raw_tenders:
        existing = await repos.tender.get_by_number(raw.number, company_id)
        if existing and existing.embedding_has_files:
            cached[raw.number] = {
                "raw": raw,
                "tender": existing,
            }
        else:
            to_fetch.append(raw)

    logger.info(f"Tenders: {len(cached)} cached, {len(to_fetch)} to fetch")

    # Phase 2: Parallel fetch for non-cached
    fetch_results = []
    if to_fetch:
        tasks = [_fetch_one(raw, parser, sem) for raw in to_fetch]
        fetch_results = await asyncio.gather(*tasks, return_exceptions=True)

    # Phase 3: Sequential DB writes
    results = []

    # Process cached tenders (re-score with existing embedding)
    for info in cached.values():
        raw = info["raw"]
        try:
            tender_data = {
                "number": raw.number,
                "title": raw.title,
                "customer": raw.customer,
                "price": raw.price,
                "deadline": raw.deadline,
                "description": raw.description,
                "requirements": "",
                "url": raw.url,
                "files_text": "",
            }
            tender = await analyze_and_save(tender_data, company_id, session)
            results.append(tender)
        except Exception as e:
            logger.error(f"Error re-scoring cached tender {raw.number}: {e}")

    # Process fetched tenders
    for result in fetch_results:
        if isinstance(result, Exception):
            logger.error(f"Fetch task failed: {result}")
            continue

        raw = result["raw"]
        try:
            tender_data = {
                "number": raw.number,
                "title": raw.title,
                "customer": raw.customer,
                "price": raw.price,
                "deadline": raw.deadline,
                "description": result["details"].get("description", raw.description),
                "requirements": result.get("requirements", ""),
                "url": raw.url,
                "files_text": result["files_text"],
            }
            tender = await analyze_and_save(tender_data, company_id, session)
            results.append(tender)
        except Exception as e:
            logger.error(f"Error analyzing tender {raw.number}: {e}")

    await session.commit()

    results.sort(key=lambda t: t.relevance_score or 0, reverse=True)
    return results
