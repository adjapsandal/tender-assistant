"""
Tender ranking functions using embeddings and rule-based modifiers.

Calculates relevance score (0-100%) for tenders based on:
1. Semantic similarity (cosine similarity)
2. Exclusion filters (stop-words)
3. SKU matches
4. Certificate requirements
5. Price range
6. Historical performance
"""

import logging
from dataclasses import dataclass

from database.models import SKU, Company, Tender
from ml.embeddings import cosine_similarity, to_list

logger = logging.getLogger(__name__)


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class TenderScoreResult:
    """Result of tender relevance calculation"""

    score: float  # 0-100
    category: str  # target/prospective/possible/low/excluded
    matched_skus: list[tuple[SKU, float]]  # (SKU, similarity)
    risk_flags: list[str]
    missing_items: list[str]
    modifiers: dict[str, float]  # For debugging


# =============================================================================
# Main Ranking Function
# =============================================================================


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
        won_tender_embeddings: Embeddings of previously won tenders (не используется)

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


# =============================================================================
# Helper Functions
# =============================================================================


def find_matching_skus(
    tender_embedding: list[float], skus: list[SKU], threshold: float = 0.6
) -> list[tuple[SKU, float]]:
    """
    Find SKUs that match tender by semantic similarity.

    Args:
        tender_embedding: Tender embedding vector
        skus: List of SKUs to check
        threshold: Minimum similarity threshold

    Returns:
        List of (SKU, similarity) tuples sorted by similarity descending
    """
    matches = []

    for sku in skus:
        # Convert numpy array to list
        sku_emb = to_list(sku.embedding)
        if sku_emb is None or len(sku_emb) == 0 or not sku.is_active:
            continue

        similarity = cosine_similarity(tender_embedding, sku_emb)

        if similarity >= threshold:
            matches.append((sku, similarity))

    # Sort by similarity descending
    matches.sort(key=lambda x: x[1], reverse=True)
    return matches


def check_certificates(tender: Tender, matched_skus: list[tuple[SKU, float]]) -> tuple[float, list[str], list[str]]:
    """
    Check certificate requirements.

    Returns: (modifier, risk_flags, missing_items)
    """
    tender_text = f"{tender.title} {tender.description} {tender.requirements}".lower()

    has_ru_req = "регистрац" in tender_text or "ру " in tender_text or " руп" in tender_text
    has_ss_req = "сертификат соответств" in tender_text or "сс " in tender_text
    has_gisp_req = "гисп" in tender_text or "гост" in tender_text

    modifier = 0
    risk_flags = []
    missing_items = []

    # Check matched SKUs for certificates
    if matched_skus:
        for sku, _ in matched_skus:
            if has_ru_req and not sku.has_ru:
                missing_items.append(f"РУ сертификат для {sku.name}")
                modifier -= 5
            elif has_ru_req and sku.has_ru:
                modifier += 2.5

            if has_ss_req and not sku.has_ss:
                missing_items.append(f"СС сертификат для {sku.name}")
                modifier -= 5
            elif has_ss_req and sku.has_ss:
                modifier += 2.5

            if has_gisp_req and not sku.has_gisp:
                missing_items.append(f"ГИСП для {sku.name}")
                modifier -= 5
            elif has_gisp_req and sku.has_gisp:
                modifier += 2.5

    # If certificates required but no SKUs matched
    if (has_ru_req or has_ss_req or has_gisp_req) and not matched_skus:
        if has_ru_req:
            missing_items.append("РУ сертификат")
        if has_ss_req:
            missing_items.append("СС сертификат")
        if has_gisp_req:
            missing_items.append("ГИСП")
        modifier -= 15

    # Bonus for having all certificates
    if modifier > 0 and not missing_items:
        risk_flags.append("Все требуемые сертификаты имеются")
        modifier = min(modifier, 10)

    return modifier, risk_flags, missing_items


def check_shelf_life(tender: Tender, matched_skus: list[tuple[SKU, float]]) -> tuple[float, list[str], list[str]]:
    """
    Check shelf life requirements.

    Returns: (modifier, risk_flags, missing_items)
    """
    tender_text = f"{tender.title} {tender.description} {tender.requirements}".lower()

    # Extract shelf life requirement (e.g., "срок годности 18 месяцев")
    import re

    shelf_match = re.search(r"срок.*годност[ии].*?(\d+)\s*месяц", tender_text)
    if not shelf_match:
        shelf_match = re.search(r"(\d+)\s*месяц.*годност", tender_text)

    if not shelf_match:
        return 0, [], []

    required_months = int(shelf_match.group(1))

    modifier = 0
    risk_flags = []
    missing_items = []

    if matched_skus:
        for sku, _ in matched_skus:
            if sku.shelf_life_months and sku.shelf_life_months < required_months:
                risk_flags.append(f"Срок годности {sku.name}: {sku.shelf_life_months}м < требуемых {required_months}м")
                modifier -= 10
            elif sku.shelf_life_months and sku.shelf_life_months >= required_months:
                modifier += 5

    return max(modifier, -20), risk_flags, missing_items


def check_price_range(tender: Tender, matched_skus: list[tuple[SKU, float]]) -> float:
    """
    Check if tender price is in acceptable range.

    Returns: Modifier value (0 to +5)
    """
    # Extract price from tender string (e.g., "2 500 000 ₽")
    import re

    price_match = re.search(r"([\d\s]+)", str(tender.price))
    if not price_match:
        return 0

    try:
        tender_price = float(price_match.group(1).replace(" ", ""))

        # Check if any SKU can cover this price range
        if matched_skus:
            for sku, _ in matched_skus:
                if sku.price_min and sku.price_max:
                    if sku.price_min <= tender_price <= sku.price_max:
                        return 5.0
    except (ValueError, AttributeError):
        pass

    return 0


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


# =============================================================================
# Report Generation
# =============================================================================


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
