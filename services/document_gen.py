"""
Document generator service - refactored document.py.

Integrates document generation with database templates and company profiles.
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from database.models import SKU, Company, DocumentTemplate, Tender
from database.repositories import Repositories
from services.document import DocumentGenerator as BaseDocumentGenerator

logger = logging.getLogger(__name__)


class DocumentGeneratorService(BaseDocumentGenerator):
    """
    Extended document generator that loads templates from database.

    Inherits from existing DocumentGenerator and adds database integration.
    """

    def __init__(self, session: AsyncSession, api_key: str | None = None):
        """
        Initialize document generator with database support.

        Args:
            session: Database session
            api_key: OpenAI API key (optional, from config if None)
        """
        super().__init__(api_key=api_key)
        self.session = session
        self.repos = Repositories(session)

    async def generate_proposal_for_tender(
        self,
        tender: Tender,
        company: Company,
        files_dir: str = "",
        template_id: int | None = None,
    ) -> str:
        """Generate commercial proposal for a specific tender."""
        template = await self._get_template("proposal", company.id, template_id)
        skus = await self._get_matched_skus(tender, company)
        company_dict = self._company_to_dict(company)

        data = {
            "number": tender.tender_number,
            "title": tender.title,
            "customer": tender.customer,
            "price": tender.price,
            "description": tender.description or "",
            "requirements": tender.requirements or "",
            "deadline": tender.deadline,
            "company": company_dict,
            "skus": [self._sku_to_dict(sku) for sku, _ in skus],
        }

        if template and template.content:
            return await self._generate_from_template(template, data, company_dict)
        else:
            return self.generate_proposal(data, files_dir, company_profile=company_dict)

    async def generate_letter_for_tender(
        self,
        tender: Tender,
        company: Company,
        files_dir: str = "",
        template_id: int | None = None,
    ) -> str:
        """Generate cover letter for a tender."""
        template = await self._get_template("letter", company.id, template_id)
        company_dict = self._company_to_dict(company)

        data = {
            "number": tender.tender_number,
            "title": tender.title,
            "customer": tender.customer,
            "price": tender.price,
            "description": tender.description or "",
            "company": company_dict,
        }

        if template and template.content:
            return await self._generate_from_template(template, data, company_dict)
        else:
            return self.generate_letter(data, files_dir, company_profile=company_dict)

    async def generate_requirements_for_tender(
        self,
        tender: Tender,
        company: Company,
        files_dir: str = "",
        template_id: int | None = None,
    ) -> str:
        """Generate requirements response for a tender."""
        template = await self._get_template("requirements", company.id, template_id)
        skus = await self._get_matched_skus(tender, company)
        company_dict = self._company_to_dict(company)

        data = {
            "number": tender.tender_number,
            "title": tender.title,
            "customer": tender.customer,
            "price": tender.price,
            "description": tender.description or "",
            "requirements": tender.requirements or "",
            "company": company_dict,
            "skus": [self._sku_to_dict(sku) for sku, _ in skus],
        }

        if template and template.content:
            return await self._generate_from_template(template, data, company_dict)
        else:
            return self.generate_requirements(data, files_dir, company_profile=company_dict)

    async def _get_template(
        self, template_type: str, company_id: int, template_id: int | None = None
    ) -> DocumentTemplate | None:
        """Get template from database"""
        if template_id:
            return await self.repos.document_template.get(template_id)

        return await self.repos.document_template.get_default(company_id, template_type)

    async def _generate_from_template(
        self, template: DocumentTemplate, data: dict, company_profile: dict = None
    ) -> str:
        """Generate document from database template using AI"""
        prompt = self._build_prompt_from_template(template, data)
        return self._call_ai(prompt, company_profile=company_profile)

    def _build_prompt_from_template(self, template: DocumentTemplate, data: dict) -> str:
        """Build AI prompt from template and data"""
        return f"""Используй следующий шаблон документа:

{template.content}

Данные для подстановки:
{self._format_data(data)}

Заполни шаблон, используя предоставленные данные. Сохраняй структуру и форматирование шаблона, но подставь реальные значения."""

    def _format_data(self, data: dict) -> str:
        """Format data for prompt"""
        lines = []
        for key, value in data.items():
            if isinstance(value, dict):
                lines.append(f"{key}:")
                for k, v in value.items():
                    lines.append(f"  {k}: {v}")
            elif isinstance(value, list):
                lines.append(f"{key}: {len(value)} элементов")
            else:
                lines.append(f"{key}: {value}")
        return "\n".join(lines)

    async def _get_matched_skus(self, tender: Tender, company: Company) -> list[tuple[SKU, float]]:
        """Get active SKUs for the company to provide context in document generation."""
        skus = await self.repos.sku.get_by_company(company.id, active_only=True)
        return [(sku, 1.0) for sku in skus]

    def _company_to_dict(self, company: Company) -> dict:
        """Convert company model to dict for templates"""
        return {
            "name": company.name,
            "full_name": company.full_name or company.name,
            "inn": company.inn or "",
            "kpp": company.kpp or "",
            "ogrn": company.ogrn or "",
            "address": company.address or "",
            "phone": company.phone or "",
            "director": company.director or "",
            "experience": company.experience or "",
            "stack": company.stack or "",
        }

    def _sku_to_dict(self, sku: SKU) -> dict:
        """Convert SKU model to dict for templates"""
        return {
            "name": sku.name,
            "description": sku.description or "",
            "keywords": sku.keywords or "",
        }
