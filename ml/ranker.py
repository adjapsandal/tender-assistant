"""
Оценка релевантности тендера (0–100).

1. Базовая оценка: косинусная близость тендера к профилю компании.
2. Стоп-слова: тендер с исключающим словом сразу получает категорию excluded.
3. Бонус за сходство с выигранными тендерами (до +15).
"""

import logging
from dataclasses import dataclass

from database.models import SKU, Company, Tender
from ml.embeddings import cosine_similarity, to_list

logger = logging.getLogger(__name__)


@dataclass
class TenderScoreResult:
    """Result of tender relevance calculation"""

    score: float  # 0-100
    category: str  # target/prospective/possible/low/excluded
    matched_skus: list[tuple[SKU, float]]  # (SKU, similarity)
    risk_flags: list[str]
    missing_items: list[str]
    modifiers: dict[str, float]  # For debugging


async def calculate_relevance(
    tender: Tender,
    company: Company,
    skus: list[SKU],
    exclusion_words: list[str] | None = None,
    won_tender_embeddings: list[list[float]] | None = None,
) -> TenderScoreResult:
    """
    Calculate relevance score for a tender.

    Простая логика: сравниваем embedding тендера с embedding компании.

    Args:
        tender: Tender to evaluate
        company: Company profile
        skus: Company's SKUs (не используется в упрощённой версии)
        exclusion_words: Stop-words that exclude tender
        won_tender_embeddings: Embeddings of previously won tenders

    Returns:
        TenderScoreResult with score and details
    """
    # Check if tender has embedding
    if tender.embedding is None:
        logger.warning(f"Tender {tender.tender_number} has no embedding")
        return TenderScoreResult(
            score=0.0,
            category="low",
            matched_skus=[],
            risk_flags=["No embedding calculated"],
            missing_items=["Unable to analyze"],
            modifiers={},
        )

    # Convert numpy array to list
    tender_emb = to_list(tender.embedding)
    if tender_emb is None or len(tender_emb) == 0:
        logger.warning(f"Tender {tender.tender_number} has empty embedding")
        return TenderScoreResult(
            score=0.0,
            category="low",
            matched_skus=[],
            risk_flags=["Empty embedding"],
            missing_items=["Unable to analyze"],
            modifiers={},
        )

    modifiers = {}
    risk_flags = []
    missing_items = []

    # Step 1: Base score from company similarity
    base_score = 0.0
    company_emb = to_list(company.embedding)
    if company_emb is not None and len(company_emb) > 0:
        base_score = cosine_similarity(tender_emb, company_emb) * 100
        modifiers["company_similarity"] = base_score
    else:
        risk_flags.append("У компании нет embedding")
        return TenderScoreResult(
            score=0.0,
            category="low",
            matched_skus=[],
            risk_flags=risk_flags,
            missing_items=["Создайте профиль компании"],
            modifiers=modifiers,
        )

    # Step 2: Check exclusion words (instant exclusion)
    if exclusion_words:
        tender_text = f"{tender.title} {tender.description} {tender.requirements}".lower()
        for word in exclusion_words:
            if word.lower() in tender_text:
                return TenderScoreResult(
                    score=0.0,
                    category="excluded",
                    matched_skus=[],
                    risk_flags=[f"Содержит исключающее слово: {word}"],
                    missing_items=[],
                    modifiers={"excluded": -999},
                )

    # Calculate final score
    final_score = max(0, min(100, base_score))

    # Historical similarity bonus
    if won_tender_embeddings:
        historical_bonus = check_historical_similarity(tender_emb, won_tender_embeddings)
        if historical_bonus > 0:
            modifiers["historical_bonus"] = historical_bonus
            final_score = min(100, final_score + historical_bonus)

    # Determine category
    category = get_category(final_score)

    return TenderScoreResult(
        score=round(final_score, 1),
        category=category,
        matched_skus=[],  # Не используем SKU в упрощённой версии
        risk_flags=risk_flags,
        missing_items=missing_items,
        modifiers=modifiers,
    )


def check_historical_similarity(tender_embedding: list[float], won_tender_embeddings: list[list[float]]) -> float:
    """
    Check similarity with previously won tenders.

    Returns: Modifier value (0 to +15)
    """
    if not won_tender_embeddings or len(won_tender_embeddings) == 0:
        return 0

    max_similarity = 0
    for won_emb in won_tender_embeddings:
        sim = cosine_similarity(tender_embedding, won_emb)
        max_similarity = max(max_similarity, sim)

    # If very similar to won tender, significant bonus
    if max_similarity > 0.85:
        return 15.0
    elif max_similarity > 0.75:
        return 10.0
    elif max_similarity > 0.65:
        return 5.0

    return 0


def get_category(score: float) -> str:
    """Map score to category"""
    if score >= 90:
        return "target"
    elif score >= 70:
        return "prospective"
    elif score >= 50:
        return "possible"
    else:
        return "low"


def generate_missing_report(result: TenderScoreResult, tender: Tender) -> str:
    """
    Generate human-readable report of what's missing/needed.

    Args:
        result: Score result
        tender: Tender data

    Returns:
        Formatted report string
    """
    lines = [
        f"📊 Тендер №{tender.tender_number} - {result.score:.1f}% соответствия",
        f"Категория: {category_to_emoji(result.category)} {category_to_russian(result.category)}",
        "",
    ]

    if result.risk_flags:
        lines.append("⚠️ Риски:")
        for flag in result.risk_flags:
            lines.append(f"   • {flag}")
        lines.append("")

    if result.missing_items:
        lines.append("❌ Не хватает:")
        for item in result.missing_items:
            lines.append(f"   • {item}")
        lines.append("")

    # Recommendations
    lines.append("💡 Рекомендации:")
    if result.category == "target":
        lines.append("   Идеальное совпадение. Рекомендую участвовать.")
    elif result.category == "prospective":
        lines.append("   Стоит участвовать. Есть минорные риски.")
    elif result.category == "possible":
        lines.append("   Рассмотреть при наличии времени. Требуется доработка.")
    else:
        lines.append("   Низкий приоритет. Лучше пропустить.")

    return "\n".join(lines)


def category_to_emoji(category: str) -> str:
    """Map category to emoji"""
    emoji_map = {"excluded": "🚫", "target": "🎯", "prospective": "📈", "possible": "📊", "low": "📉"}
    return emoji_map.get(category, "❓")


def category_to_russian(category: str) -> str:
    """Map category to Russian name"""
    ru_map = {
        "excluded": "Исключён",
        "target": "Целевой",
        "prospective": "Перспективный",
        "possible": "Возможный",
        "low": "Низкий приоритет",
    }
    return ru_map.get(category, category)
