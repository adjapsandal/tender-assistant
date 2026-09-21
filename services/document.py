import logging
import os
import platform
import re
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt
from openai import OpenAI

logger = logging.getLogger("document")
if os.getenv("DEBUG", "false").lower() == "true":
    logging.basicConfig(level=logging.DEBUG)
    logger.setLevel(logging.DEBUG)
else:
    logger.addHandler(logging.NullHandler())

# Import functions from document_reader (refactored from class)
try:
    from services.document_reader import read_directory as read_files_from_directory

    READER_AVAILABLE = True
except ImportError:
    READER_AVAILABLE = False

try:
    from reportlab.lib.colors import HexColor
    from reportlab.lib.enums import TA_JUSTIFY
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

# Запасной профиль на случай, когда компания не передана явно. Боевые
# реквизиты берутся из базы (таблица companies) и подставляются
# параметром company_profile.
COMPANY_PROFILE = {
    "name": "ООО «Пример»",
    "full_name": "Общество с ограниченной ответственностью «Пример»",
    "details": "ИНН 0000000000, КПП 000000000, ОГРН 0000000000000",
    "address": "422700, Республика Татарстан, г. Казань, ул. Примерная, д. 1",
    "phone": "Тел: +7 (000) 000-00-00, Email: info@example.com",
    "director": "Иванов И.И.",
    "experience": "Производитель и поставщик расходных материалов и оборудования для сбора, хранения и утилизации медицинских отходов. Работаем с государственными и частными медицинскими учреждениями по всем регионам РФ.",
    "stack": "Расходные материалы для сбора медицинских отходов (контейнеры, пробирки, баночки, пакеты), оборудование для утилизации медицинских отходов, лабораторная посуда, медицинские изделия расходного характера.",
    "advantages": "Собственные производственные мощности и контроль качества на всех этапах. Сертифицированная продукция. Работа по всем регионам РФ. Оперативная логистика и своевременные поставки.",
}


# =============================================================================
# Module-level font registration (called once at import)
# =============================================================================


def _register_font() -> str:
    """Register and return font name for PDF generation."""
    if not PDF_AVAILABLE:
        return None

    system = platform.system()
    paths = []

    if system == "Windows":
        paths = ["C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/tahoma.ttf", "C:/Windows/Fonts/calibri.ttf"]
    elif system == "Darwin":
        paths = ["/Library/Fonts/Arial.ttf"]
    else:
        paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/TTF/Arial.ttf",
            "/usr/share/fonts/liberation/LiberationSans-Regular.ttf",
        ]

    for path in paths:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont("CustomFont", path))
                return "CustomFont"
            except Exception:
                continue
    return "Helvetica"


class DocumentGenerator:
    def __init__(self, api_key: str = None, base_url: str = "https://api.proxyapi.ru/openai/v1"):
        self.client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"), base_url=base_url)
        self.model = "gpt-4o-mini"
        self.font_name = _register_font()

    def _read_files(self, directory: str) -> str:
        """Read files from directory using document_reader functions."""
        if not READER_AVAILABLE or not directory or not os.path.exists(directory):
            return ""
        try:
            print(f"   (Анализ файлов из папки {os.path.basename(directory)}...)")
            return read_files_from_directory(directory)
        except Exception as e:
            logger.debug(f"File read error: {e}")
            return ""

    def _call_ai(self, prompt: str, max_tokens: int = 4000, company_profile: dict = None) -> str:
        profile = company_profile or COMPANY_PROFILE
        system_msg = (
            f"Ты — опытный тендерный специалист компании {profile.get('name', '')}. "
            f"Твоя задача — готовить профессиональную документацию для участия в закупках. "
            f"Используй официально-деловой стиль. "
            f"Информация о компании: {profile.get('experience', '')} {profile.get('stack', '')}. "
            f"Подписант: Генеральный директор {profile.get('director', '')}."
        )
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": system_msg}, {"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=0.4,
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.debug(f"AI Error: {e}")
            return "Ошибка генерации текста. Проверьте баланс API или настройки."

    def generate_proposal(self, data: dict, files_dir: str = "", company_profile: dict = None) -> str:
        profile = company_profile or COMPANY_PROFILE
        files_content = self._read_files(files_dir)
        details = f"{profile.get('inn', '')}"
        if profile.get("kpp"):
            details = f"ИНН {details}, КПП {profile['kpp']}"
        if profile.get("ogrn"):
            details += f", ОГРН {profile['ogrn']}"
        prompt = (
            f"Подготовь КОММЕРЧЕСКОЕ ПРЕДЛОЖЕНИЕ (КП) для тендера.\n\n"
            f"ЗАКАЗЧИК: {data['customer']}\n"
            f"ТЕНДЕР: {data['title']} (№ {data['number']})\n"
            f"БЮДЖЕТ: {data['price']}\n"
            f"КРАТКОЕ ОПИСАНИЕ: {data['description'][:1500]}\n"
            f"КОНТЕКСТ ИЗ ФАЙЛОВ (ТЗ): {files_content[:10000]}\n\n"
            f"Требования к документу:\n"
            f"1. Структура:\n"
            f"   - Шапка (от кого: {profile.get('full_name', profile.get('name', ''))}, {details}).\n"
            f"   - Заголовок (Коммерческое предложение на ...).\n"
            f"   - Уважаемые коллеги (обращение к заказчику).\n"
            f"   - Понимание задачи (кратко опиши, что нужно сделать, исходя из ТЗ).\n"
            f"   - Наше решение (предложи техническое решение на стеке {profile.get('stack', '')}, этапы работ).\n"
            f"   - Стоимость и сроки (если точных нет, напиши 'Согласно ТЗ' или предложи расчет).\n"
            f"   - Почему мы (опиши преимущества компании).\n"
            f"   - Заключение и подпись.\n"
            f"2. Стиль: Строгий, убедительный, без воды.\n"
            f"3. Форматирование: Используй Markdown (заголовки #, жирный шрифт **)."
        )
        return self._call_ai(prompt, 4000, company_profile=company_profile)

    def generate_letter(self, data: dict, files_dir: str = "", company_profile: dict = None) -> str:
        profile = company_profile or COMPANY_PROFILE
        prompt = (
            f"Подготовь СОПРОВОДИТЕЛЬНОЕ ПИСЬМО к заявке на участие в тендере.\n"
            f"Тендер: {data['title']} (№ {data['number']})\n"
            f"Заказчик: {data['customer']}\n\n"
            f"Структура:\n"
            f"1. Шапка (на бланке организации).\n"
            f"2. Исх. номер и дата (текущая).\n"
            f"3. Текст: Мы, {profile.get('full_name', profile.get('name', ''))}, изучили документацию, согласны со всеми условиями и предлагаем свои услуги.\n"
            f"4. Гарантируем качество и соблюдение сроков.\n"
            f"5. Приложения (перечислить: Коммерческое предложение, Опись документов и др.).\n"
            f"6. Подпись ({profile.get('director', '')})."
        )
        return self._call_ai(prompt, 1500, company_profile=company_profile)

    def generate_requirements(self, data: dict, files_dir: str = "", company_profile: dict = None) -> str:
        profile = company_profile or COMPANY_PROFILE
        files_content = self._read_files(files_dir)
        reqs = data.get("requirements") or data.get("description", "")
        prompt = (
            f"Составь ТАБЛИЦУ СООТВЕТСТВИЯ ТРЕБОВАНИЯМ (Форма 2 / Техническое предложение).\n"
            f"Тендер: {data['title']}\n"
            f"Выдержка из требований заказчика: {reqs[:3000]}\n"
            f"Контекст из файлов документации: {files_content[:10000]}\n\n"
            f"Задача:\n"
            f"1. Проанализируй требования и напиши ответ на каждый пункт.\n"
            f"2. Формат: Таблица (или список), где есть 'Требование заказчика' и 'Предложение участника ({profile.get('name', '')})'.\n"
            f"3. В графе 'Предложение' пиши конкретные характеристики, подтверждающие соответствие (слово 'Соответствует' используй, но добавляй детали).\n"
            f"4. Если в требованиях указаны ГОСТы или конкретные параметры, подтверждай их."
        )
        return self._call_ai(prompt, 4000, company_profile=company_profile)

    def save_docx(self, content: str, filename: str, folder: str = "outputs") -> str:
        Path(folder).mkdir(exist_ok=True)
        path = os.path.join(folder, f"{filename}.docx")

        doc = Document()
        style = doc.styles["Normal"]
        style.font.name = "Arial"
        style.font.size = Pt(11)

        for line in content.split("\n"):
            line = line.strip()
            if not line:
                continue

            if line.startswith("# "):
                doc.add_heading(line.lstrip("# ").strip(), level=1)
            elif line.startswith("## "):
                doc.add_heading(line.lstrip("# ").strip(), level=2)
            elif line.startswith("### "):
                doc.add_heading(line.lstrip("# ").strip(), level=3)
            elif line.startswith(("-", "*", "•")):
                p = doc.add_paragraph(style="List Bullet")
                self._format_text(p, line.lstrip("-*• "))
            else:
                p = doc.add_paragraph()
                p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                self._format_text(p, line)

        doc.save(path)
        return path

    def _format_text(self, paragraph, text):
        parts = re.split(r"(\*\*.*\*\*)", text)
        for part in parts:
            if part.startswith("**") and part.endswith("**"):
                run = paragraph.add_run(part[2:-2])
                run.font.bold = True
            else:
                paragraph.add_run(part)

    def save_pdf(self, content: str, filename: str, folder: str = "outputs") -> str | None:
        if not PDF_AVAILABLE:
            return None
        Path(folder).mkdir(exist_ok=True)
        path = os.path.join(folder, f"{filename}.pdf")

        doc = SimpleDocTemplate(
            path, pagesize=A4, rightMargin=20 * mm, leftMargin=20 * mm, topMargin=20 * mm, bottomMargin=20 * mm
        )

        styles = getSampleStyleSheet()
        base_style = ParagraphStyle(
            "Base",
            parent=styles["Normal"],
            fontName=self.font_name,
            fontSize=10,
            leading=14,
            alignment=TA_JUSTIFY,
            spaceAfter=6,
        )

        h1_style = ParagraphStyle(
            "H1",
            parent=base_style,
            fontSize=14,
            leading=18,
            spaceBefore=12,
            spaceAfter=6,
            textColor=HexColor("#003366"),
            fontName=self.font_name,
        )
        h2_style = ParagraphStyle(
            "H2",
            parent=base_style,
            fontSize=12,
            leading=16,
            spaceBefore=10,
            spaceAfter=6,
            fontName=self.font_name,
            textColor=HexColor("#003366"),
        )

        story = []

        for line in content.split("\n"):
            line = line.strip()
            if not line:
                story.append(Spacer(1, 4))
                continue

            clean_line = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            fmt_line = re.sub(r"(\*\*.*?\*\*)", r"<b>\1</b>", clean_line)

            if line.startswith("# "):
                story.append(Paragraph(fmt_line.lstrip("# "), h1_style))
            elif line.startswith("## "):
                story.append(Paragraph(fmt_line.lstrip("# "), h2_style))
            elif line.startswith("### "):
                story.append(Paragraph(fmt_line.lstrip("# "), h2_style))
            elif line.startswith(("-", "*", "•")):
                story.append(Paragraph(f"• {fmt_line.lstrip('-*• ')}", base_style))
            else:
                story.append(Paragraph(fmt_line, base_style))

        try:
            doc.build(story)
            return path
        except Exception as e:
            logger.debug(f"PDF Save error: {e}")
            return None
