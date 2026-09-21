"""
Parser service - wrapper around existing parser.py.

Integrates the existing RostenderParser with the new database architecture.
"""

import logging
import os

from database.models import Tender
from database.repositories import Repositories
from ml.embeddings import create_embedding
from services.parser import RostenderParser
from services.parser import Tender as ParserTender

logger = logging.getLogger(__name__)


class ParserService:
    """
    Service wrapper around RostenderParser.

    Singleton pattern - one parser instance for the entire application.
    """

    _instance = None

    def __init__(self, session=None):
        """
        Initialize parser service.

        Args:
            session: Database session (optional for singleton)
        """
        self.session = session
        if session:
            self.repos = Repositories(session)

    @classmethod
    def get_parser(cls) -> RostenderParser:
        """
        Get single configured parser instance (Singleton).

        Returns:
            RostenderParser instance (created once, reused)
        """
        if cls._instance is None:
            email = os.getenv("ROSTENDER_EMAIL")
            password = os.getenv("ROSTENDER_PASSWORD")

            cls._instance = RostenderParser(email=email, password=password, downloads_dir="downloads")
            logger.info("Парсер инициализирован (Singleton)")

        return cls._instance

    async def search_and_save(
        self,
        region: str,
        industry: str,
        keyword: str = None,
        keywords: str = None,
        exceptions: str = None,
        company_id: int = None,
        limit: int = 40,
    ) -> list[Tender]:
        """
        Search tenders and save to database.

        Args:
            region: Region filter
            industry: Industry filter
            keyword: Simple keyword for search
            keywords: Advanced keywords from preset (*, ~N, "")
            exceptions: Advanced exceptions syntax (*, ~N, "")
            company_id: Company ID for attribution
            limit: Max tenders to fetch

        Returns:
            List of saved Tender objects with embeddings
        """
        logger.info(
            f"Searching tenders: region={region}, industry={industry}, "
            f"keyword={keyword}, keywords={keywords[:50] if keywords else None}..., "
            f"exceptions={exceptions[:50] if exceptions else None}..."
        )

        # Get parser and search
        parser = ParserService.get_parser()
        raw_tenders = parser.search(
            region=region, industry=industry, keyword=keyword, keywords=keywords, exceptions=exceptions, limit=limit
        )

        logger.info(f"Found {len(raw_tenders)} tenders")

        # Convert and save to database
        saved_tenders = []
        for raw in raw_tenders:
            tender = await self._save_raw_tender(raw, company_id)
            if tender:
                saved_tenders.append(tender)

        logger.info(f"Saved {len(saved_tenders)} tenders to database")
        return saved_tenders

    async def _save_raw_tender(self, raw: ParserTender, company_id: int) -> Tender | None:
        """
        Save raw tender from parser to database.

        Args:
            raw: Tender from parser
            company_id: Company ID

        Returns:
            Saved Tender or None if already exists
        """
        # Check if already exists
        existing = await self.repos.tender.get_by_number(raw.number, company_id)
        if existing:
            logger.debug(f"Tender {raw.number} already exists, skipping")
            return None

        # Create new tender
        tender = await self.repos.tender.create(
            company_id=company_id,
            tender_number=raw.number,
            title=raw.title,
            customer=raw.customer,
            price=raw.price,
            deadline=raw.deadline,
            description=raw.description,
            requirements="",  # Will be filled later
            url=raw.url,
            status="new",
        )

        # Generate embedding
        text_for_embedding = f"{raw.title} {raw.description}"
        try:
            embedding = await create_embedding(text_for_embedding)
            tender.embedding = embedding
            await self.session.flush()
            logger.debug(f"Created embedding for tender {raw.number}")
        except Exception as e:
            logger.error(f"Failed to create embedding: {e}")

        return tender

    async def fetch_details_and_update(self, tender_id: int, company_id: int) -> Tender | None:
        """
        Fetch full tender details from rostender and update.

        Args:
            tender_id: Tender ID in database
            company_id: Company ID

        Returns:
            Updated Tender or None
        """
        tender = await self.repos.tender.get(tender_id)
        if not tender or tender.company_id != company_id:
            return None

        # Get parser and fetch details
        parser = ParserService.get_parser()
        details = parser.get_details(tender.url)

        # Update tender
        if details.get("description"):
            tender.description = details["description"][:5000]
        if details.get("requirements"):
            tender.requirements = details["requirements"][:5000]

        # Update embedding with new data
        text_for_embedding = f"{tender.title} {tender.description} {tender.requirements}"
        try:
            embedding = await create_embedding(text_for_embedding)
            tender.embedding = embedding
        except Exception as e:
            logger.error(f"Failed to update embedding: {e}")

        await self.session.flush()
        await self.session.refresh(tender)

        logger.info(f"Updated details for tender {tender.tender_number}")
        return tender

    async def download_tender_files(self, tender_id: int, company_id: int) -> str | None:
        """
        Download tender files using existing parser.

        Args:
            tender_id: Tender ID in database
            company_id: Company ID

        Returns:
            Path to downloaded files or None
        """
        tender = await self.repos.tender.get(tender_id)
        if not tender or tender.company_id != company_id:
            return None

        # Get details with files
        parser = ParserService.get_parser()
        details = parser.get_details(tender.url)

        if not details.get("documents"):
            logger.info(f"No documents found for tender {tender.tender_number}")
            return None

        # Download files
        files_dir = parser.download_files(details["documents"], tender.tender_number)

        logger.info(f"Downloaded files to: {files_dir}")
        return files_dir
